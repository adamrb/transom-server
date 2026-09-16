"""Shared helpers for the agent-runner actions that hand work to Paseo.

Paseo (systemd user unit `paseo.service`, port 6767) runs the user's Claude Code
agents and is the app he watches them in. Every Claude task the Plaud pipeline
kicks off goes through it, so each run shows up in the Paseo app with its full
transcript instead of in a log file. Two actions use this module:

  start-paseo-session.py  "Ask Claude": detached interactive session (runner
                          completion = "child", the session reports back itself)
  paseo-agent.py          filing recipes (Vault notes, Work meetings, default):
                          run to completion, print the agent's last line so the
                          runner can show it as the outcome

Both read their input on stdin as a small header block followed by a blank line
and the body (the transcript or the rendered prompt):

    TITLE: <AI title of the recording>
    RECORDING: <recording id>

    <body>

Header parsing is lenient: without a leading `KEY: value` line the whole stdin
is the body. Payload text never becomes an argv element or a shell string.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

HOME = Path.home()
NODE_BIN = HOME / ".nvm/versions/node/v24.14.1/bin"
SECRETS_FILE = HOME / ".config/secrets/paseo.env"
SPILL_DIR = HOME / ".cache/plaud-agent-runner/prompts"
SPILL_RETENTION_S = 7 * 24 * 3600

PROVIDER = os.environ.get("PASEO_PROVIDER", "claude/claude-fable-5-1")
MODEL_LABEL = os.environ.get("PASEO_MODEL_LABEL", "Fable 5.1")  # the model label goes in every session title
MODE = os.environ.get("PASEO_MODE", "bypassPermissions")  # unattended: never stall on a prompt
# Prompts longer than this are written to a file the agent reads first; a single
# argv element is capped by the kernel (128 KiB) and long meetings get close.
INLINE_PROMPT_MAX = int(os.environ.get("PASEO_INLINE_PROMPT_MAX", "60000"))
# Budget for `paseo run` (workspace + agent creation). The runner's
# timeout_seconds for a launcher action must exceed this with headroom, or the
# runner kills the launcher while a daemon-owned agent may already exist.
CREATE_TIMEOUT_S = 90
_HEADER_RE = re.compile(r"^([A-Z][A-Z_]*):(?: (.*))?$")
# What a finished filing agent's last line must look like (our prompts demand
# it). Anything else means the turn was interrupted or ended early, and the
# delivery must stay retryable rather than be shown as done.
OUTCOME_LINE_RE = re.compile(r"^(Filed|Created|Saved|Skipped|Done):", re.IGNORECASE)
_LABEL_VALUE_RE = re.compile(r"[^A-Za-z0-9._-]+")


class PaseoError(RuntimeError):
    pass


# --- environment ---------------------------------------------------------------

def paseo_env() -> dict[str, str]:
    """Environment for `paseo` CLI calls: node + CLI on PATH, the daemon
    password (the daemon listens on 0.0.0.0 behind a password) loaded from the
    secrets file, and the agent-scope variables dropped. When this code runs
    inside a Paseo agent those variables make `paseo run` ignore --cwd and nest
    the new agent under the caller; we always want a top-level agent."""
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join([str(HOME / ".local/bin"), str(NODE_BIN), env.get("PATH", "")])
    for key in ("PASEO_AGENT_ID", "PASEO_AGENT_CWD", "PASEO_WORKSPACE_ID"):
        env.pop(key, None)
    if not env.get("PASEO_PASSWORD") and SECRETS_FILE.is_file():
        for line in SECRETS_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key.startswith("export "):
                key = key[len("export "):].strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            env.setdefault(key, value)
    return env


# --- stdin message ---------------------------------------------------------------

def read_message(stream=None) -> tuple[dict[str, str], str]:
    """(headers, body) from the runner's stdin_template. Headers are the
    leading `KEY: value` lines up to the first blank line."""
    raw = (stream or sys.stdin).read()
    lines = raw.split("\n")
    if not lines or not _HEADER_RE.match(lines[0]):
        return {}, raw
    headers: dict[str, str] = {}
    idx = 0
    while idx < len(lines) and lines[idx].strip():
        m = _HEADER_RE.match(lines[idx])
        if not m:
            break
        headers[m.group(1)] = (m.group(2) or "").strip()
        idx += 1
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    return headers, "\n".join(lines[idx:])


def label_value(value: str, limit: int = 60) -> str:
    cleaned = _LABEL_VALUE_RE.sub("-", value or "").strip("-")
    return (cleaned or "none")[:limit]


def agent_title(prefix: str, title: str, fallback: str = "voice memo", limit: int = 90) -> str:
    subject = " ".join((title or "").split()) or fallback
    head = f"{prefix}: {subject}"
    if len(head) > limit:
        head = head[: limit - 1].rstrip() + "…"
    return f"{head} · {MODEL_LABEL}"


# --- prompt handling ---------------------------------------------------------------

def prompt_argument(prompt: str, name_hint: str) -> tuple[str, Path | None]:
    """The prompt to hand `paseo run`. Long prompts are spilled to a 0600 file
    and replaced by a short pointer the agent follows; returns the spill path so
    the caller can delete it once the agent is done."""
    if len(prompt.encode("utf-8")) <= INLINE_PROMPT_MAX:
        return prompt, None
    SPILL_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(SPILL_DIR, 0o700)
    _sweep_spill_dir()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = SPILL_DIR / f"{stamp}-{label_value(name_hint, 40)}-{os.getpid()}.md"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(prompt)
    pointer = (
        "Your full instructions, including a long transcript, did not fit in this message. "
        f"Read them first with the Read tool from {path} and then carry them out exactly as written there."
    )
    return pointer, path


def _sweep_spill_dir() -> None:
    cutoff = time.time() - SPILL_RETENTION_S
    try:
        for p in SPILL_DIR.iterdir():
            try:
                if p.is_file() and p.stat().st_mtime < cutoff:
                    p.unlink()
            except OSError:
                pass
    except OSError:
        pass


# --- working directory choice ----------------------------------------------------

def match_workdir(transcript: str) -> Path:
    """If the transcript names an existing repo under ~/git or ~/tools, open
    the session there; otherwise $HOME. A repo matches only when every token
    of its name (split on - and _) appears as a separate word, and at least two
    tokens matched or one is distinctive (6+ chars), so a lone common word
    ("park", "sync") cannot grab a session. Longest name wins."""
    words = set(re.sub(r"[^a-z0-9]+", " ", transcript.lower()).split())
    best, best_len = HOME, 0
    for parent in (HOME / "git", HOME / "tools"):
        if not parent.is_dir():
            continue
        for d in parent.iterdir():
            if not d.is_dir():
                continue
            tokens = [t for t in re.split(r"[-_]", d.name.lower()) if t]
            if not tokens or not all(t in words for t in tokens):
                continue
            if len(tokens) >= 2 or any(len(t) >= 6 for t in tokens):
                if len(d.name) > best_len:
                    best, best_len = d, len(d.name)
    return best


# --- paseo CLI ----------------------------------------------------------------------

def _run(args: list[str], env: dict[str, str], timeout: float) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["paseo", *args], env=env, capture_output=True, text=True,
                              timeout=timeout, check=False, stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        raise PaseoError("paseo CLI not found on PATH")
    except subprocess.TimeoutExpired:
        raise PaseoError(f"paseo {args[0]} did not answer within {int(timeout)}s")


def _json_tail(text: str):
    """`paseo --json` sometimes prints a human line first ("Created workspace
    ..."); the JSON document starts at the first line beginning with { or [."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.lstrip().startswith(("{", "[")):
            return json.loads("\n".join(lines[i:]))
    raise ValueError("no JSON in paseo output")


def create_agent(*, title: str, cwd: Path, prompt: str, labels: dict[str, str],
                 agent_env: dict[str, str] | None = None, env: dict[str, str],
                 provider: str | None = None, mode: str | None = None,
                 timeout: float = CREATE_TIMEOUT_S) -> str:
    """Start a background agent and return its id. Bounded by `timeout`; the
    runner's timeout_seconds for the action must leave headroom above it.

    Every launch carries a unique `launch=<id>` label. If the CLI call fails
    or times out AFTER the daemon accepted the request, the agent exists and is
    working; rather than report a failure that would make the delivery
    retryable (a second agent doing the same filing), look it up by that label
    and carry on with it. Only a launch that cannot be found is a failure."""
    launch_id = uuid.uuid4().hex[:16]
    args = ["run", "--background", "--json", "--title", title, "--provider", provider or PROVIDER,
            "--mode", mode or MODE, "--cwd", str(cwd), "--label", f"launch={launch_id}"]
    for k, v in labels.items():
        args += ["--label", f"{label_value(k, 30)}={label_value(v)}"]
    for k, v in (agent_env or {}).items():
        args += ["--env", f"{k}={v}"]
    args += ["--", prompt]  # end of options: a prompt starting with '-' is still positional
    # One creation deadline covers the launch AND the recovery lookup.
    deadline = time.monotonic() + timeout
    lookup_reserve = min(20.0, timeout / 4)
    proc = None
    try:
        proc = _run(args, env, timeout=max(5.0, timeout - lookup_reserve))
        data = _json_tail(proc.stdout)
    except (PaseoError, ValueError) as e:
        found = find_agent_by_label("launch", launch_id, env, timeout=max(5.0, deadline - time.monotonic()))
        if found:
            return found
        raise PaseoError(f"paseo run failed: {_cli_failure_detail(proc, e)}")
    if isinstance(data, dict) and data.get("error"):
        raise PaseoError(f"paseo run failed: {data['error'].get('message', 'unknown error')}")
    agent_id = data.get("agentId") if isinstance(data, dict) else None
    if not agent_id:
        found = find_agent_by_label("launch", launch_id, env, timeout=max(5.0, deadline - time.monotonic()))
        if found:
            return found
        raise PaseoError("paseo run returned no agentId")
    return agent_id


def _cli_failure_detail(proc: subprocess.CompletedProcess | None, exc: Exception) -> str:
    """Why a CLI call failed, for the runner log and the app: the CLI writes
    its JSON error to stderr (stdout stays empty), so read that first."""
    if proc is None:
        return str(exc)
    for stream in (proc.stderr, proc.stdout):
        try:
            data = _json_tail(stream or "")
            if isinstance(data, dict) and data.get("error"):
                return str(data["error"].get("message") or data["error"])[:300]
        except ValueError:
            pass
    tail = [ln for ln in (proc.stderr or "").strip().splitlines() if ln.strip()]
    if tail:
        return tail[-1][:300]
    return f"exit {proc.returncode}, no JSON reply"


def find_agent_by_label(key: str, value: str, env: dict[str, str], timeout: float = 30.0) -> str | None:
    """Id of the (single) agent carrying label key=value, or None."""
    try:
        proc = _run(["ls", "--global", "--label", f"{key}={value}", "--json"], env, timeout=timeout)
        data = _json_tail(proc.stdout)
    except (PaseoError, ValueError):
        return None
    if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict) and data[0].get("id"):
        return str(data[0]["id"])
    return None


def wait_agent(agent_id: str, timeout_s: int, env: dict[str, str]) -> str:
    """Block until the agent is idle; returns the reported status
    ('idle' on success, anything else on timeout/error). Takes at most
    timeout_s + 15 seconds so callers can budget against a deadline."""
    proc = _run(["agent", "wait", agent_id, "--timeout", str(int(timeout_s)), "--json"],
                env, timeout=timeout_s + 15)
    try:
        data = _json_tail(proc.stdout)
    except ValueError:
        return "unknown"
    if isinstance(data, dict) and data.get("error"):
        return f"error: {data['error'].get('message', '')}"[:200]
    return str(data.get("status", "unknown")) if isinstance(data, dict) else "unknown"


def last_text_line(agent_id: str, env: dict[str, str]) -> str:
    """Last line of the agent's final reply (our prompts end with
    `Filed:/Created:/Skipped:`); empty when the agent never replied."""
    # Only real assistant replies count: `--filter text` would also return the
    # user prompt and reasoning, whose text can contain a proposed outcome line
    # that was never actually delivered. Unknown filter values match the
    # timeline item type verbatim.
    proc = _run(["agent", "logs", agent_id, "--tail", "1", "--filter", "assistant_message"], env, timeout=30)
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    # The CLI prints a sentinel instead of nothing when the history is empty.
    if not lines or lines[0].startswith("[User]") or lines == ["No activity to display."]:
        return ""
    return lines[-1]


def stop_agent(agent_id: str, env: dict[str, str]) -> bool:
    """Interrupt the agent. True only when the daemon confirmed it stopped
    THIS agent; a False return means it may still be working and the caller
    must say so. The CLI exits 0 even when it stopped nothing (it prints
    {"stoppedCount":0,"agentIds":[]}), so the payload is what counts."""
    try:
        proc = _run(["agent", "stop", agent_id, "--json"], env, timeout=30)
        data = _json_tail(proc.stdout)
    except (PaseoError, ValueError):
        return False
    if proc.returncode != 0 or not isinstance(data, dict) or data.get("error"):
        return False
    ids = data.get("agentIds")
    if isinstance(ids, list):
        return any(isinstance(i, str) and (i == agent_id or agent_id.startswith(i) or i.startswith(agent_id)) for i in ids)
    count = data.get("stoppedCount")
    return isinstance(count, int) and count >= 1

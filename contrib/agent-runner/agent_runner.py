#!/usr/bin/env python3
"""agent-runner: webhook-to-agent bridge for plaud-bridge routes, over ACP.

Receives `route.matched` webhook payloads from plaud-bridge and dispatches
them to a coding agent via ACP (Agent Client Protocol,
https://agentclientprotocol.com — JSON-RPC 2.0, newline-delimited JSON over
the agent child process's stdio). Works with `claude-code-acp`, `codex acp`,
or any other ACP agent, running on your local subscription auth — no LLM API
keys. Plain argv `command` actions are also supported for non-agent work
(append-to-file scripts etc.).

Also exposes a minimal OpenAI-compatible `POST /v1/chat/completions` shim so
plaud-bridge's AI router/summarizer can point at this runner instead of a
hosted API.

Python 3.11+ standard library only. See README.md and config.example.toml.
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import queue
import re
import signal
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
import time
import tomllib
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_LISTEN = "127.0.0.1:8091"
DEFAULT_QUEUE_SIZE = 16
DEFAULT_TIMEOUT_S = 600
MAX_BODY_BYTES = 10 * 1024 * 1024
MAX_ACP_LINE_BYTES = 1024 * 1024          # per JSON-RPC frame from the agent
MAX_RESPONSE_CHARS = 2 * 1024 * 1024      # accumulated agent response text
MAX_STDERR_CHARS = 256 * 1024             # captured child stderr tail
MAX_STDOUT_CHARS = 256 * 1024             # captured plain-command stdout tail
MAX_LOG_FIELD_CHARS = 4096                # any single logged string field
MAX_CHAT_CONCURRENCY = 2
MAX_REQUEST_THREADS = 32
SOCKET_TIMEOUT_S = 30
ACP_PROTOCOL_VERSION = 1
DEFAULT_CHAT_TEMPLATE = (
    "Answer directly. Do not use tools or modify files.\n\n{prompt}"
)

# The only tokens ever substituted. Anything else inside braces -- including
# brace sequences that arrive inside the transcript text -- is left verbatim.
TEMPLATE_VARS = (
    "text",
    "summary",
    "title",
    "route_name",
    "route_description",
    "recording_id",
    "filename",
    "started_at",
    "prompt",
    "file",
    # What the user typed when re-running automations by hand (server >= 2026-09-08).
    "instructions",
    # Ready-made paragraph introducing {instructions}, empty when there are none,
    # so templates can include it unconditionally.
    "instructions_block",
)
_TOKEN_RE = re.compile(r"\{(" + "|".join(TEMPLATE_VARS) + r")\}")

# Payload-controlled free-text variables. Substituting these into a plain
# `command` argv is unsafe by default: shell=False keeps argument boundaries,
# but the executed program still interprets its arguments (sh -c executes
# them; most tools parse leading-dash values as options). Use stdin_template
# instead, or opt in explicitly with allow_unsafe_interpolation = true.
FORBIDDEN_COMMAND_VARS = ("text", "summary", "prompt", "route_description", "instructions", "instructions_block")
_FORBIDDEN_ARG_RE = re.compile(r"\{(?:" + "|".join(FORBIDDEN_COMMAND_VARS) + r")\}")


def render(template: str, variables: dict[str, str]) -> str:
    """Single-pass substitution of known {tokens} only.

    Deliberately NOT str.format(): values (e.g. transcript text) are inserted
    in one pass and never re-scanned, so a transcript containing "{token}",
    "{text}" or shell syntax stays inert data. Unknown {things} are preserved
    verbatim.
    """
    return _TOKEN_RE.sub(lambda m: variables.get(m.group(1), ""), template)


class ConfigError(Exception):
    pass


def _validate_argv(section: str, key: str, value) -> None:
    if not isinstance(value, list) or not value or not all(isinstance(a, str) for a in value):
        raise ConfigError(
            f"[{section}] {key} must be a non-empty LIST of strings (argv). "
            "A shell string is rejected by design."
        )


def _validate_executor(section: str, table: dict) -> None:
    agent, command = table.get("agent"), table.get("command")
    if (agent is None) == (command is None):
        raise ConfigError(
            f"[{section}] must define exactly one of `agent` (ACP agent argv) "
            "or `command` (plain argv)"
        )
    if agent is not None:
        _validate_argv(section, "agent", agent)
    else:
        _validate_argv(section, "command", command)
        if not table.get("allow_unsafe_interpolation", False):
            for arg in command:
                if _FORBIDDEN_ARG_RE.search(arg):
                    raise ConfigError(
                        f"[{section}] command argv contains a payload-controlled "
                        f"variable ({_FORBIDDEN_ARG_RE.search(arg).group(0)}). The "
                        "executed program interprets its arguments (interpreters "
                        "execute them, tools parse leading '-' as options), so this "
                        "is injectable. Pass content via stdin_template instead, or "
                        "set allow_unsafe_interpolation = true if you accept the risk."
                    )
    if not isinstance(table.get("allow_unsafe_interpolation", False), bool):
        raise ConfigError(f"[{section}] allow_unsafe_interpolation must be a boolean")
    if not isinstance(table.get("stdin_template", ""), str):
        raise ConfigError(f"[{section}] stdin_template must be a string")
    if not isinstance(table.get("timeout_seconds", DEFAULT_TIMEOUT_S), (int, float)):
        raise ConfigError(f"[{section}] timeout_seconds must be a number")
    if not isinstance(table.get("auto_approve", False), bool):
        raise ConfigError(f"[{section}] auto_approve must be a boolean")
    env = table.get("env", {})
    if not isinstance(env, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
        raise ConfigError(f"[{section}] env must be a table of string -> string")
    if not isinstance(table.get("model", ""), str):
        raise ConfigError(f"[{section}] model must be a string (ACP modelId)")


_RESULT_URL_RE = re.compile(r"/api/v1/deliveries/[A-Za-z0-9_-]{8,64}/result")
# Re-report 'queued' this often for accepted-but-unfinished jobs; the bridge
# declares a delivery abandoned after hours of silence, so 10 minutes leaves
# plenty of margin without chatter.
DEFAULT_HEARTBEAT_S = 600.0
# Final outcomes waiting for an unreachable bridge: bounded in count and age.
MAX_PENDING_TERMINAL = 200
PENDING_TERMINAL_TTL_S = 6 * 3600
MAX_REPORT_QUEUE = 500


_OUTCOME_LINE_RE = re.compile(r"^(Filed|Created|Saved|Skipped|Done|Started)\b.*", re.IGNORECASE)


def _summary_from_reply(text: str) -> str:
    """The outcome shown in the app: an agent's final 'Filed: Life/...' style
    line when it ends with one (our prompts ask for it), else the whole reply
    trimmed to the summary limit."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if lines and _OUTCOME_LINE_RE.match(lines[-1]):
        return lines[-1][:2000]
    return (" ".join(lines) if lines else "Agent finished with no reply")[:2000]


_ACP_SUCCESS_STOP_REASONS = {"end_turn", "stop", "completed", "end"}


def _acp_outcome(result: dict) -> tuple[str, str]:
    """(status, summary) for the bridge from an ACP run. Only a normal end of
    turn is 'done'; a timeout, a token or turn cap, a refusal, a cancellation
    or an unknown stop reason means the job did not finish and must stay
    retryable."""
    if result.get("timeout"):
        return "failed", "Agent timed out"
    reason = str(result.get("stop_reason") or "").lower()
    if reason and reason not in _ACP_SUCCESS_STOP_REASONS:
        tail = _summary_from_reply(result.get("text") or "")
        return "failed", f"Agent stopped early ({reason}): {tail}"[:2000]
    if result.get("truncated"):
        return "failed", "Agent output was truncated before it finished"
    return "done", _summary_from_reply(result.get("text") or "")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None  # turn any 3xx into an HTTPError instead of following it


_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirect)


def _read_token_file(path: str) -> str | None:
    """A bare token, or an env-style file holding PB_AUTH_TOKENS=a,b (first token wins)."""
    try:
        with open(path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, val = line.partition("=")
                    if key.strip() == "PB_AUTH_TOKENS":
                        return val.strip().strip('"').split(",")[0].strip() or None
                    continue
                return line
    except OSError:
        return None
    return None


def load_config(path: str) -> dict:
    with open(path, "rb") as f:
        cfg = tomllib.load(f)

    server = cfg.get("server", {})
    if not isinstance(server.get("token"), str) or not server["token"]:
        raise ConfigError("[server] token must be a non-empty string")
    listen = server.get("listen", DEFAULT_LISTEN)
    if ":" not in listen:
        raise ConfigError(f"[server] listen must be host:port, got {listen!r}")
    host, _, port_s = listen.rpartition(":")
    try:
        server["_host"], server["_port"] = host, int(port_s)
    except ValueError:
        raise ConfigError(f"[server] listen has invalid port: {listen!r}") from None
    queue_size = server.get("queue_size", DEFAULT_QUEUE_SIZE)
    if not isinstance(queue_size, int) or isinstance(queue_size, bool) \
            or not 1 <= queue_size <= 1024:
        raise ConfigError("[server] queue_size must be an integer in 1..1024")
    server["queue_size"] = queue_size
    if not isinstance(server.get("log_responses", False), bool):
        raise ConfigError("[server] log_responses must be a boolean")
    cfg["server"] = server

    actions = cfg.get("actions", {})
    if not actions:
        raise ConfigError("config defines no [actions.*]")
    for name, action in actions.items():
        if not isinstance(action, dict):
            raise ConfigError(f"[actions.{name}] must be a table")
        _validate_executor(f"actions.{name}", action)
    cfg["actions"] = actions

    callback = cfg.get("callback")
    if callback is not None:
        if not isinstance(callback, dict) or not isinstance(callback.get("base_url"), str) or not callback["base_url"]:
            raise ConfigError("[callback] must define base_url (the plaud-bridge server, e.g. http://127.0.0.1:8090)")
        # No bridge credential here on purpose: each payload carries a one-shot
        # result token that is only good for its own delivery's result URL.
        hb = callback.get("heartbeat_seconds", DEFAULT_HEARTBEAT_S)
        if isinstance(hb, bool) or not isinstance(hb, (int, float)) or not 1 <= hb <= 3600:
            raise ConfigError("[callback] heartbeat_seconds must be a number of seconds in 1..3600")
        cfg["callback"] = callback

    chat = cfg.get("chat")
    if chat is not None:
        if not isinstance(chat, dict) or chat.get("agent") is None:
            raise ConfigError("[chat] must define `agent` (ACP agent argv)")
        _validate_executor("chat", chat)
    return cfg


def payload_vars(payload: dict) -> dict[str, str]:
    route = payload.get("route") or {}
    recording = payload.get("recording") or {}
    transcript = payload.get("transcript") or {}

    def s(v) -> str:
        return "" if v is None else str(v)

    instructions = s(payload.get("instructions")).strip()
    instructions_block = (
        "The recorder's owner typed these instructions for this run in the app. They "
        "come from the owner, not from the memo, so follow them (they take precedence "
        f"over the default handling):\n<instructions>\n{instructions}\n</instructions>\n\n"
        if instructions else ""
    )
    return {
        "instructions": instructions,
        "instructions_block": instructions_block,
        "text": s(transcript.get("text")),
        "summary": s(transcript.get("summary")),
        # AI-generated title (server >= 2026-09-07); empty for older payloads.
        "title": s(transcript.get("title")).replace("\n", " ").strip(),
        "route_name": s(route.get("name")),
        "route_description": s(route.get("description")),
        "recording_id": s(recording.get("id")),
        "filename": s(recording.get("filename")),
        "started_at": s(recording.get("started_at")),
    }


class JobLogger:
    def __init__(self, log_path: str, secret: str | None = None):
        self.log_path = log_path
        self.secret = secret or None
        self._lock = threading.Lock()

    def _clean(self, value):
        if isinstance(value, str):
            if self.secret:
                value = value.replace(self.secret, "[REDACTED]")
            if len(value) > MAX_LOG_FIELD_CHARS:
                value = value[:MAX_LOG_FIELD_CHARS] + "...[truncated]"
            return value
        if isinstance(value, dict):
            return {k: self._clean(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._clean(v) for v in value]
        return value

    def log(self, **fields) -> None:
        fields = {k: self._clean(v) for k, v in fields.items()}
        fields["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        line = json.dumps(fields, ensure_ascii=False)
        if self.secret:  # belt and braces: never let the token hit disk/journal
            line = line.replace(self.secret, "[REDACTED]")
        with self._lock:
            print(line, flush=True)
            try:
                fd = os.open(self.log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                with os.fdopen(fd, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError as e:
                print(f'{{"event":"log_write_error","error":"{e}"}}', file=sys.stderr, flush=True)


# --------------------------------------------------------------------------
# In-flight child tracking, so SIGTERM shutdown can kill active jobs.
# NOTE (containment limits): killing the process group reaps normal children,
# but a tool that forks and setsid()s escapes the group and survives both
# timeout and shutdown. Full containment requires running the runner in its
# container variant (see Dockerfile) or an OS sandbox; we deliberately do not
# manage cgroups here.
# --------------------------------------------------------------------------

_ACTIVE_PIDS: set[int] = set()
_ACTIVE_PIDS_LOCK = threading.Lock()


def _track_pid(pid: int) -> None:
    with _ACTIVE_PIDS_LOCK:
        _ACTIVE_PIDS.add(pid)


def _untrack_pid(pid: int) -> None:
    with _ACTIVE_PIDS_LOCK:
        _ACTIVE_PIDS.discard(pid)


def _kill_pgid(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _kill_all_active() -> None:
    with _ACTIVE_PIDS_LOCK:
        pids = list(_ACTIVE_PIDS)
    for pid in pids:
        _kill_pgid(pid)


def _reap(proc: subprocess.Popen, logger, label: str) -> None:
    """Post-kill cleanup that can never block the worker: close pipes and
    wait a bounded time; log if descendants may have leaked."""
    for stream in (proc.stdin, proc.stdout, proc.stderr):
        try:
            if stream:
                stream.close()
        except (OSError, ValueError):
            pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        logger.log(event="job.leak_warning", label=label, pid=proc.pid,
                   detail="child did not exit 5s after SIGKILL; detached "
                          "descendants may have escaped the process group")


# --------------------------------------------------------------------------
# ACP client
# --------------------------------------------------------------------------

class ACPError(Exception):
    pass


class ACPTimeout(ACPError):
    pass


class NDJSONStdio:
    """Framing layer: JSON-RPC 2.0 as newline-delimited JSON over a child
    process's stdin/stdout. One JSON object per line, UTF-8. Malformed lines
    are skipped (reported via on_garbage). Isolated here so it can be swapped
    if an agent turns out to use different framing."""

    def __init__(self, proc: subprocess.Popen, on_garbage=None):
        self.proc = proc
        self.on_garbage = on_garbage

    def send(self, message: dict) -> None:
        line = json.dumps(message, ensure_ascii=False)
        try:
            self.proc.stdin.write(line + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, ValueError, OSError) as e:
            raise ACPError(f"agent stdin closed: {e}") from e

    def recv(self) -> dict | None:
        """Next parsed message, or None on EOF. Raises on an oversized frame
        (memory-exhaustion guard); the caller kills the job."""
        while True:
            line = self.proc.stdout.readline(MAX_ACP_LINE_BYTES + 1)
            if line == "":
                return None
            if len(line) > MAX_ACP_LINE_BYTES:
                raise ACPError(
                    f"agent sent an oversized frame (> {MAX_ACP_LINE_BYTES} bytes)")
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                if self.on_garbage:
                    self.on_garbage(line[:500])
                continue
            if isinstance(msg, dict):
                return msg
            if self.on_garbage:
                self.on_garbage(line[:500])


class ACPSession:
    """One-shot ACP client: spawn agent, initialize, session/new,
    session/prompt, collect agent_message_chunk text, return on stopReason.

    Verified against @zed-industries/claude-code-acp: newline-delimited
    JSON-RPC 2.0 on stdio; `initialize` -> `session/new` (cwd + mcpServers)
    -> `session/prompt` (content blocks); agent streams `session/update`
    notifications and may call `session/request_permission`.
    """

    def __init__(self, argv, cwd, auto_approve, logger, label="acp", extra_env=None,
                 model=None, log_content=False):
        self.argv = list(argv)
        self.cwd = cwd or os.getcwd()
        self.auto_approve = bool(auto_approve)
        self.logger = logger
        self.label = label
        self.extra_env = dict(extra_env or {})
        self.model = model or None
        self.truncated = False
        self._text_chars = 0
        self.log_content = bool(log_content)
        self.text_parts: list[str] = []
        self._next_id = 0
        self._stderr_tail = ""

    def _drain_stderr(self, proc):
        def run():
            tail = ""
            try:
                while True:
                    chunk = proc.stderr.read(65536)
                    if not chunk:
                        break
                    tail = (tail + chunk)[-MAX_STDERR_CHARS:]
            except (ValueError, OSError):
                pass
            self._stderr_tail = tail
        t = threading.Thread(target=run, daemon=True)
        t.start()

    def run_prompt(self, prompt: str, timeout: float) -> dict:
        """Returns {"stop_reason", "text", "timeout", "stderr_tail"}."""
        deadline = time.monotonic() + timeout
        timed_out = threading.Event()
        # claude-code-acp (via the Claude Code SDK) refuses to start when it
        # thinks it is nested inside another Claude Code session; make sure a
        # stray CLAUDECODE marker never leaks into the agent.
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        env.update(self.extra_env)
        proc = subprocess.Popen(
            self.argv, cwd=self.cwd, shell=False, start_new_session=True, env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
        )

        _track_pid(proc.pid)

        def kill():
            timed_out.set()
            _kill_pgid(proc.pid)
            proc.kill()

        watchdog = threading.Timer(timeout, kill)
        watchdog.daemon = True
        watchdog.start()
        self._drain_stderr(proc)
        io = NDJSONStdio(proc, on_garbage=lambda s: self.logger.log(
            event="acp.garbage_line", label=self.label,
            line=s if self.log_content else f"<{len(s)} chars suppressed>"))
        try:
            self._call(io, "initialize", {
                "protocolVersion": ACP_PROTOCOL_VERSION,
                "clientCapabilities": {
                    "fs": {"readTextFile": False, "writeTextFile": False},
                    "terminal": False,
                },
            })
            new = self._call(io, "session/new", {"cwd": self.cwd, "mcpServers": []})
            session_id = new.get("sessionId")
            if not session_id:
                raise ACPError(f"session/new returned no sessionId: {new}")
            if self.model:
                # session/new advertises availableModels; an explicitly
                # configured model must be honored, so a failure here is fatal.
                self._call(io, "session/set_model",
                           {"sessionId": session_id, "modelId": self.model})
            result = self._call(io, "session/prompt", {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": prompt}],
            })
            return {
                "stop_reason": result.get("stopReason", "unknown"),
                "text": "".join(self.text_parts),
                "timeout": False,
                "truncated": self.truncated,
                "stderr_tail": self._stderr_tail,
            }
        except ACPError as e:
            if timed_out.is_set() or time.monotonic() >= deadline:
                return {"stop_reason": "timeout", "text": "".join(self.text_parts),
                        "timeout": True, "truncated": self.truncated,
                        "stderr_tail": self._stderr_tail}
            raise ACPError(f"{e} (stderr: {self._stderr_tail[-500:]})") from e
        finally:
            watchdog.cancel()
            _kill_pgid(proc.pid)
            _reap(proc, self.logger, self.label)
            _untrack_pid(proc.pid)

    # -- JSON-RPC plumbing ---------------------------------------------------

    def _call(self, io: NDJSONStdio, method: str, params: dict) -> dict:
        self._next_id += 1
        req_id = self._next_id
        io.send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        while True:
            msg = io.recv()
            if msg is None:
                raise ACPError(f"agent exited before responding to {method}")
            if "method" in msg:
                if "id" in msg:
                    self._handle_agent_request(io, msg)
                else:
                    self._handle_notification(msg)
                continue
            if msg.get("id") == req_id:
                if "error" in msg:
                    raise ACPError(f"{method} error: {json.dumps(msg['error'])[:500]}")
                result = msg.get("result")
                return result if isinstance(result, dict) else {}
            # response to something we didn't ask for; ignore

    def _handle_notification(self, msg: dict) -> None:
        if msg.get("method") != "session/update":
            return
        update = (msg.get("params") or {}).get("update") or {}
        if update.get("sessionUpdate") == "agent_message_chunk":
            content = update.get("content") or {}
            if content.get("type") == "text":
                if self.truncated:
                    return
                text = content.get("text", "")
                remaining = MAX_RESPONSE_CHARS - self._text_chars
                if len(text) > remaining:
                    self.text_parts.append(text[:remaining])
                    self.text_parts.append("...[response truncated]")
                    self.truncated = True
                    self._text_chars = MAX_RESPONSE_CHARS
                else:
                    self.text_parts.append(text)
                    self._text_chars += len(text)

    def _handle_agent_request(self, io: NDJSONStdio, msg: dict) -> None:
        method, req_id = msg.get("method"), msg.get("id")
        if method == "session/request_permission":
            options = (msg.get("params") or {}).get("options") or []
            outcome = self._pick_permission(options)
            self.logger.log(event="acp.permission", label=self.label,
                            auto_approve=self.auto_approve,
                            tool=((msg.get("params") or {}).get("toolCall") or {}).get("title"),
                            outcome=outcome)
            io.send({"jsonrpc": "2.0", "id": req_id, "result": {"outcome": outcome}})
        else:
            # We declared no fs/terminal capabilities; refuse anything else.
            io.send({"jsonrpc": "2.0", "id": req_id,
                     "error": {"code": -32601, "message": f"method not supported: {method}"}})

    def _pick_permission(self, options: list) -> dict:
        def find(*kinds):
            # strict kind priority: earlier kinds win regardless of the order
            # the agent lists its options in
            for kind in kinds:
                for opt in options:
                    if isinstance(opt, dict) and opt.get("kind") == kind:
                        return opt.get("optionId")
            return None

        if self.auto_approve:
            # NEVER allow_always: a persistent approval outlives this job's
            # audit trail (and may outlive the session in some agents).
            option_id = find("allow_once")
        else:
            option_id = find("reject_once", "reject_always")
        if option_id is None:
            return {"outcome": "cancelled"}
        return {"outcome": "selected", "optionId": option_id}


# --------------------------------------------------------------------------
# Job runner (webhook actions)
# --------------------------------------------------------------------------

class Runner:
    """Single worker thread consuming a bounded job queue."""

    def __init__(self, config: dict, logger: JobLogger):
        self.config = config
        self.logger = logger
        self.jobs: queue.Queue = queue.Queue(maxsize=config["server"]["queue_size"])
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._seq = 0
        self._seq_lock = threading.Lock()
        # Jobs accepted but not finished (queued or running), for the heartbeat.
        self._inflight: dict[int, dict] = {}
        # Final outcomes the bridge has not acknowledged yet (job_id -> (payload, status, summary, since)).
        self._pending_terminal: dict[int, tuple] = {}
        self._inflight_lock = threading.Lock()
        # Reports travel to the bridge on their own thread (see _enqueue_report);
        # bounded so a blackholed bridge cannot grow memory without limit.
        self._reports: queue.Queue = queue.Queue(maxsize=MAX_REPORT_QUEUE)
        self.heartbeat_s = float((config.get("callback") or {}).get("heartbeat_seconds", DEFAULT_HEARTBEAT_S))
        # non-blocking gate: at most N concurrent chat sessions, 503 beyond
        self.chat_slots = threading.BoundedSemaphore(MAX_CHAT_CONCURRENCY)

    @property
    def log_responses(self) -> bool:
        return bool(self.config["server"].get("log_responses", False))

    def start(self) -> None:
        self._thread.start()
        if self.config.get("callback"):
            self._start_reporting()

    def _start_reporting(self) -> None:
        """Reporter + heartbeat threads (idempotent). Split from start() so a
        callback configured after construction can still be served."""
        if getattr(self, "_reporting_started", False):
            return
        self._reporting_started = True
        threading.Thread(target=self._reporter_loop, daemon=True, name="result-reporter").start()
        threading.Thread(target=self._heartbeat_loop, daemon=True, name="result-heartbeat").start()

    def report_result(self, payload: dict, status: str, summary: str) -> None:
        """Tell plaud-bridge what this job did (POST delivery.result_url) so the
        app and dashboard can show the outcome instead of 'handed off'. Best
        effort: a failed report is logged, never raised; nothing is sent when
        the payload has no delivery block or no [callback] is configured."""
        cb = self.config.get("callback")
        delivery = (payload or {}).get("delivery") or {}
        url_path, token = delivery.get("result_url"), delivery.get("result_token")
        # Strict shape and a per-delivery token: the runner never holds a bridge
        # credential, and a path smuggled in with '..' is refused outright.
        if not cb or not isinstance(url_path, str) or not _RESULT_URL_RE.fullmatch(url_path) \
                or not isinstance(token, str) or not token:
            if cb and url_path:
                self.logger.log(event="result.skipped", reason="invalid result_url or missing result_token")
            return True  # nothing to deliver, nothing to retry
        body = json.dumps({"status": status, "summary": (summary or "")[:2000]}).encode()
        try:
            req = urllib.request.Request(
                cb["base_url"].rstrip("/") + url_path, data=body, method="POST",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
            # No redirects: urllib would follow a 3xx to another host and carry the
            # Authorization header along with it.
            with _NO_REDIRECT_OPENER.open(req, timeout=10) as resp:
                self.logger.log(event="result.reported", status=status, http=resp.status, path=url_path)
            return True
        except urllib.error.HTTPError as e:
            # Permanent 4xx (rotated token, terminal already recorded, bad request)
            # means the bridge will never accept this report: retrying is
            # pointless. Redirects (refused above), 408/429 and 5xx may recover.
            self.logger.log(event="result.report_failed", status=status, path=url_path, error=f"HTTP {e.code}")
            return 400 <= e.code < 500 and e.code not in (408, 429)
        except Exception as e:  # noqa: BLE001 - reporting must never take the job down
            self.logger.log(event="result.report_failed", status=status, path=url_path, error=str(e)[:300])
            return False

    def _enqueue_report(self, job_id: int, payload: dict, status: str, summary: str, terminal: bool) -> None:
        """Hand a report to the reporter thread. The worker never waits on the
        bridge: a slow or blackholed callback endpoint must not stall actions or
        back up the job queue. Terminal reports are bookkept by the reporter."""
        if not self.config.get("callback") or not ((payload or {}).get("delivery") or {}).get("result_url"):
            if terminal:
                with self._inflight_lock:
                    self._inflight.pop(job_id, None)
            return
        # Only the delivery block travels: the reporter never needs the transcript.
        slim = {"delivery": (payload or {}).get("delivery")}
        try:
            self._reports.put_nowait((job_id, slim, status, summary, terminal))
        except queue.Full:
            # A blackholed bridge backs the reporter up. Heartbeats are
            # disposable; a final outcome goes straight to the bounded retry
            # backlog so it is not lost.
            if terminal:
                with self._inflight_lock:
                    self._inflight.pop(job_id, None)
                    self._pending_terminal[job_id] = (slim, status, summary, time.monotonic())
                    while len(self._pending_terminal) > MAX_PENDING_TERMINAL:
                        oldest = min(self._pending_terminal, key=lambda j: self._pending_terminal[j][3])
                        self._pending_terminal.pop(oldest, None)
                        self.logger.log(event="result.dropped", job=oldest, reason="pending backlog full")
            else:
                self.logger.log(event="result.dropped", job=job_id, reason="report queue full")

    def _terminal(self, job_id: int, payload: dict, status: str, summary: str) -> None:
        """Deliver a job's final outcome (asynchronously; see _enqueue_report)."""
        self._enqueue_report(job_id, payload, status, summary, terminal=True)

    def _reporter_loop(self) -> None:
        while True:
            job_id, payload, status, summary, terminal = self._reports.get()
            try:
                delivered = self.report_result(payload, status, summary)
            except Exception:  # noqa: BLE001 - the reporter must outlive any single report
                delivered = False
            if not terminal:
                continue
            with self._inflight_lock:
                self._inflight.pop(job_id, None)
                if delivered:
                    self._pending_terminal.pop(job_id, None)
                    continue
                # Keep the outcome for the heartbeat loop to retry, bounded in
                # count: an unreachable bridge must not grow memory without limit.
                self._pending_terminal[job_id] = (payload, status, summary, time.monotonic())
                while len(self._pending_terminal) > MAX_PENDING_TERMINAL:
                    oldest = min(self._pending_terminal, key=lambda j: self._pending_terminal[j][3])
                    self._pending_terminal.pop(oldest, None)
                    self.logger.log(event="result.dropped", job=oldest, reason="pending backlog full")

    def resolve_action(self, route_name: str) -> tuple[str, dict] | None:
        actions = self.config["actions"]
        if route_name in actions:
            return route_name, actions[route_name]
        if "default" in actions:
            return "default", actions["default"]
        return None

    def enqueue(self, action_name: str, action: dict, payload: dict) -> int | None:
        """Returns a job id, or None if the queue is full."""
        with self._seq_lock:
            self._seq += 1
            job_id = self._seq
        # Registration and publication under one lock: the worker's pop and the
        # heartbeat's snapshot both take this lock, so neither can see a job
        # that was rejected by a full queue, and a fast job cannot finish before
        # its registration exists.
        with self._inflight_lock:
            try:
                self.jobs.put_nowait((job_id, action_name, action, payload))
            except queue.Full:
                return None
            self._inflight[job_id] = payload
        return job_id

    def _heartbeat_loop(self) -> None:
        """Every HEARTBEAT_S, re-report 'queued' for every job still waiting or
        running. The bridge treats a long silence as 'the consumer is gone'
        and lets the user retry; the heartbeat is what keeps a legitimately
        slow or deeply queued job from being mistaken for a dead one."""
        while True:
            time.sleep(self.heartbeat_s)
            # First: final outcomes the bridge did not acknowledge (it was down or
            # slow). Delivering them wins over any heartbeat.
            with self._inflight_lock:
                pending = list(self._pending_terminal.items())
            now = time.monotonic()
            for job_id, (payload, status, summary, since) in pending:
                if now - since > PENDING_TERMINAL_TTL_S:
                    with self._inflight_lock:
                        self._pending_terminal.pop(job_id, None)
                        self._inflight.pop(job_id, None)
                    self.logger.log(event="result.dropped", job=job_id, reason="bridge unreachable past TTL")
                    continue
                try:
                    delivered = self.report_result(payload, status, summary)
                except Exception:  # noqa: BLE001
                    delivered = False
                if delivered:
                    with self._inflight_lock:
                        self._pending_terminal.pop(job_id, None)
                        self._inflight.pop(job_id, None)
            with self._inflight_lock:
                snapshot = [(j, p) for j, p in self._inflight.items() if j not in self._pending_terminal]
            for job_id, payload in snapshot:
                # Re-check right before sending: a job that finished (and reported
                # its terminal outcome) since the snapshot must not get a stale
                # 'queued'. The bridge also refuses to reopen a terminal result.
                with self._inflight_lock:
                    still = job_id in self._inflight and job_id not in self._pending_terminal
                if not still:
                    continue
                try:
                    self.report_result(payload, "queued", "Still working")
                except Exception:  # noqa: BLE001 - never let the heartbeat die
                    pass

    def _worker(self) -> None:
        while True:
            job_id, action_name, action, payload = self.jobs.get()
            try:
                self._run_job(job_id, action_name, action, payload)
            except Exception as e:  # never kill the worker
                self.logger.log(event="job.error", job=job_id, action=action_name,
                                error=f"{type(e).__name__}: {e}")
            finally:
                with self._inflight_lock:
                    # A job whose final outcome the bridge has not taken yet stays
                    # registered; the heartbeat loop retries that report.
                    if job_id not in self._pending_terminal:
                        self._inflight.pop(job_id, None)
                self.jobs.task_done()

    def _run_job(self, job_id: int, action_name: str, action: dict, payload: dict) -> None:
        try:
            self._run_job_inner(job_id, action_name, action, payload)
        except Exception as e:  # noqa: BLE001 - setup failures (temp dir, template) must reach the bridge too
            self.logger.log(event="job.end", job=job_id, action=action_name, error=str(e)[:2000])
            self._terminal(job_id, payload, "failed", f"Runner error: {str(e)[:400]}")
            raise

    def _run_job_inner(self, job_id: int, action_name: str, action: dict, payload: dict) -> None:
        variables = payload_vars(payload)
        variables["_payload"] = payload  # not a template token (see TEMPLATE_VARS); used for result reporting
        temp_path = None
        try:
            if action.get("write_transcript_to_file"):
                fd, temp_path = tempfile.mkstemp(prefix="plaud-transcript-", suffix=".txt")
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(variables["text"])
                variables["file"] = temp_path

            prompt_template = action.get("prompt_template", "")
            variables["prompt"] = render(prompt_template, variables) if prompt_template else variables["text"]
            timeout = float(action.get("timeout_seconds", DEFAULT_TIMEOUT_S))
            cwd = action.get("cwd") or None

            if action.get("agent"):
                self._run_acp_job(job_id, action_name, action, variables, timeout, cwd)
            else:
                self._run_command_job(job_id, action_name, action, variables, timeout, cwd)
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    def _run_acp_job(self, job_id, action_name, action, variables, timeout, cwd) -> None:
        self.logger.log(event="job.start", job=job_id, action=action_name, mode="acp",
                        route=variables["route_name"], recording=variables["recording_id"],
                        agent=action["agent"][0], timeout_s=timeout)
        started = time.monotonic()
        self._enqueue_report(job_id, variables.get("_payload") or {}, "queued", "Agent started working", terminal=False)
        session = ACPSession(action["agent"], cwd, action.get("auto_approve", False),
                             self.logger, label=f"job-{job_id}",
                             extra_env=action.get("env"), model=action.get("model"),
                             log_content=self.log_responses)
        try:
            result = session.run_prompt(variables["prompt"], timeout)
        except (OSError, ValueError) as e:  # executable/cwd missing, bad argv: never reached ACPError
            self.logger.log(event="job.end", job=job_id, action=action_name, mode="acp",
                            route=variables["route_name"], stop_reason="error", timeout=False,
                            duration_s=round(time.monotonic() - started, 3), error=str(e)[:2000])
            self._terminal(job_id, variables.get("_payload") or {}, "failed", f"Could not start the agent: {str(e)[:400]}")
            return
        except ACPError as e:
            self.logger.log(event="job.end", job=job_id, action=action_name, mode="acp",
                            route=variables["route_name"], stop_reason="error",
                            timeout=False, duration_s=round(time.monotonic() - started, 3),
                            error=str(e)[:2000])
            self._terminal(job_id, variables.get("_payload") or {}, "failed", f"Agent error: {str(e)[:500]}")
            return
        status, summary = _acp_outcome(result)
        self._terminal(job_id, variables.get("_payload") or {}, status, summary)
        extra = {}
        if self.log_responses:
            extra = {"response": result["text"][:4000],
                     "stderr_tail": result["stderr_tail"][-500:]}
        self.logger.log(event="job.end", job=job_id, action=action_name, mode="acp",
                        route=variables["route_name"], stop_reason=result["stop_reason"],
                        timeout=result["timeout"], truncated=result["truncated"],
                        duration_s=round(time.monotonic() - started, 3),
                        response_chars=len(result["text"]), **extra)

    @staticmethod
    def _capped_tail(stream, cap: int):
        """Drain a binary stream on a thread, keeping only the tail."""
        state = {"tail": b"", "bytes": 0}

        def run():
            try:
                while True:
                    chunk = stream.read(65536)
                    if not chunk:
                        break
                    state["bytes"] += len(chunk)
                    state["tail"] = (state["tail"] + chunk)[-cap:]
            except (ValueError, OSError):
                pass
        t = threading.Thread(target=run, daemon=True)
        t.start()
        return state, t

    def _run_command_job(self, job_id, action_name, action, variables, timeout, cwd) -> None:
        argv = [render(arg, variables) for arg in action["command"]]
        stdin_template = action.get("stdin_template", "")
        stdin_data = render(stdin_template, variables).encode() if stdin_template else None
        self.logger.log(event="job.start", job=job_id, action=action_name, mode="command",
                        route=variables["route_name"], recording=variables["recording_id"],
                        command=argv[0], stdin_bytes=len(stdin_data or b""),
                        timeout_s=timeout)
        started = time.monotonic()
        self._enqueue_report(job_id, variables.get("_payload") or {}, "queued", "Started", terminal=False)
        timed_out = False
        try:
            proc = subprocess.Popen(
                argv, cwd=cwd, shell=False, start_new_session=True,
                stdin=subprocess.PIPE if stdin_data is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
        except FileNotFoundError as e:
            self.logger.log(event="job.end", job=job_id, action=action_name, mode="command",
                            exit_code=None, error=f"command not found: {e.filename}")
            self._terminal(job_id, variables.get("_payload") or {}, "failed", f"command not found: {e.filename}")
            return
        _track_pid(proc.pid)
        try:
            if stdin_data is not None:
                def feed():  # on a thread so a non-reading child can't block us
                    try:
                        proc.stdin.write(stdin_data)
                        proc.stdin.close()
                    except (BrokenPipeError, OSError, ValueError):
                        pass
                threading.Thread(target=feed, daemon=True).start()
            out_state, out_t = self._capped_tail(proc.stdout, MAX_STDOUT_CHARS)
            err_state, err_t = self._capped_tail(proc.stderr, MAX_STDERR_CHARS)
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill_pgid(proc.pid)
                proc.kill()
            out_t.join(timeout=5)
            err_t.join(timeout=5)
        finally:
            _kill_pgid(proc.pid)
            _reap(proc, self.logger, f"job-{job_id}")
            _untrack_pid(proc.pid)
        extra = {}
        if self.log_responses:
            extra = {"stderr_tail": err_state["tail"].decode("utf-8", "replace")[-2000:]}
        self.logger.log(event="job.end", job=job_id, action=action_name, mode="command",
                        route=variables["route_name"], exit_code=proc.returncode,
                        timeout=timed_out, duration_s=round(time.monotonic() - started, 3),
                        stdout_bytes=out_state["bytes"], stderr_bytes=err_state["bytes"],
                        **extra)
        # Outcome for the bridge: a script's last stdout line is its own summary
        # ("Saved note 0_Quick Add/....md"); failures carry the exit code and stderr tail.
        payload = variables.get("_payload") or {}
        if timed_out:
            self._terminal(job_id, payload, "failed", f"Timed out after {int(timeout)}s")
        elif proc.returncode == 0:
            lines = [ln.strip() for ln in out_state["tail"].decode("utf-8", "replace").splitlines() if ln.strip()]
            self._terminal(job_id, payload, "done", (lines[-1] if lines else "Done")[:2000])
        else:
            err = err_state["tail"].decode("utf-8", "replace").strip().splitlines()
            self._terminal(job_id, payload, "failed",
                           f"Exit code {proc.returncode}" + (f": {err[-1][:300]}" if err else ""))


# --------------------------------------------------------------------------
# HTTP server
# --------------------------------------------------------------------------

def flatten_chat_messages(messages: list) -> str:
    """system content first, then the remaining messages' content in order."""
    def text_of(content) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):  # OpenAI content-part arrays
            return "\n".join(p.get("text", "") for p in content
                             if isinstance(p, dict) and p.get("type") == "text")
        return ""

    system = [text_of(m.get("content")) for m in messages if m.get("role") == "system"]
    rest = [text_of(m.get("content")) for m in messages if m.get("role") != "system"]
    return "\n\n".join(p for p in system + rest if p)


def make_handler(runner: Runner):
    token = runner.config["server"]["token"]
    # cap concurrent in-flight request bodies (ThreadingHTTPServer still
    # spawns a thread per connection, but each is bounded by the socket
    # timeout, and only this many get to do real work at once)
    request_gate = threading.BoundedSemaphore(MAX_REQUEST_THREADS)

    class Handler(BaseHTTPRequestHandler):
        server_version = "plaud-agent-runner/2.0"
        protocol_version = "HTTP/1.1"
        timeout = SOCKET_TIMEOUT_S  # slowloris guard: socket deadline

        def _send(self, code: int, body: dict, close: bool = False) -> None:
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            if close:
                # the request body was not (fully) consumed; keeping the
                # connection alive would desynchronize HTTP framing
                self.send_header("Connection", "close")
                self.close_connection = True
            self.end_headers()
            self.wfile.write(data)

        def _authorized(self) -> bool:
            supplied = self.headers.get("X-Runner-Token", "")
            if not supplied:
                auth = self.headers.get("Authorization", "")
                if auth.startswith("Bearer "):
                    supplied = auth[len("Bearer "):]
            return hmac.compare_digest(supplied.encode(), token.encode())

        def _read_json(self) -> dict | None:
            # HTTP request-smuggling hardening: no Transfer-Encoding, exactly
            # one Content-Length. Reject with Connection: close (body unread).
            if self.headers.get("Transfer-Encoding") is not None:
                self._send(400, {"error": "Transfer-Encoding not supported"}, close=True)
                return None
            lengths = self.headers.get_all("Content-Length") or []
            if len(lengths) != 1:
                self._send(400, {"error": "exactly one Content-Length required"}, close=True)
                return None
            try:
                length = int(lengths[0])
            except ValueError:
                length = -1
            if length <= 0 or length > MAX_BODY_BYTES:
                self._send(400, {"error": "bad content length"}, close=True)
                return None
            body = self.rfile.read(length)
            if len(body) < length:  # short read; connection is broken anyway
                self.close_connection = True
                return None
            try:
                payload = json.loads(body)
                if not isinstance(payload, dict):
                    raise ValueError("payload must be a JSON object")
                return payload
            except (ValueError, UnicodeDecodeError) as e:
                self._send(400, {"error": f"invalid JSON: {e}"})
                return None

        def _gated(self, fn) -> None:
            if not request_gate.acquire(blocking=False):
                self._send(503, {"error": "too many requests"}, close=True)
                return
            try:
                fn()
            finally:
                request_gate.release()

        def do_GET(self) -> None:
            self._gated(self._get)

        def do_POST(self) -> None:
            self._gated(self._post)

        def _get(self) -> None:
            if self.path == "/healthz":
                self._send(200, {"status": "ok", "queued": runner.jobs.qsize()})
            else:
                self._send(404, {"error": "not found"})

        def _post(self) -> None:
            if not self._authorized():
                # body not consumed -> close
                self._send(401, {"error": "unauthorized"}, close=True)
                return
            if self.path == "/":
                self._post_webhook()
            elif self.path == "/v1/chat/completions":
                self._post_chat()
            else:
                self._send(404, {"error": "not found"}, close=True)

        def _post_webhook(self) -> None:
            payload = self._read_json()
            if payload is None:
                return
            route_name = str((payload.get("route") or {}).get("name") or "")
            resolved = runner.resolve_action(route_name)
            if resolved is None:
                self._send(404, {"error": f"no action for route {route_name!r} and no default"})
                return
            action_name, action = resolved
            job_id = runner.enqueue(action_name, action, payload)
            if job_id is None:
                self._send(503, {"error": "queue full"})
                return
            runner.logger.log(event="job.queued", job=job_id, action=action_name,
                              route=route_name, queued=runner.jobs.qsize())
            self._send(202, {"status": "queued", "job": job_id, "action": action_name})

        def _post_chat(self) -> None:
            chat_cfg = runner.config.get("chat")
            if not chat_cfg:
                self._send(404, {"error": "no [chat] section configured"})
                return
            payload = self._read_json()
            if payload is None:
                return
            messages = payload.get("messages")
            if not isinstance(messages, list) or not messages:
                self._send(400, {"error": "messages must be a non-empty list"})
                return
            model = str(payload.get("model", ""))
            flattened = flatten_chat_messages(messages)
            template = chat_cfg.get("prompt_template", DEFAULT_CHAT_TEMPLATE)
            prompt = render(template, {"prompt": flattened})
            timeout = float(chat_cfg.get("timeout_seconds", DEFAULT_TIMEOUT_S))
            started = time.monotonic()
            if not runner.chat_slots.acquire(blocking=False):
                self._send(503, {"error": "chat capacity exhausted"})
                return
            runner.logger.log(event="chat.start", model=model, prompt_chars=len(prompt))
            try:
                session = ACPSession(chat_cfg["agent"], chat_cfg.get("cwd"),
                                     chat_cfg.get("auto_approve", False),
                                     runner.logger, label="chat",
                                     extra_env=chat_cfg.get("env"),
                                     model=chat_cfg.get("model"),
                                     log_content=runner.log_responses)
                try:
                    result = session.run_prompt(prompt, timeout)
                except ACPError as e:
                    runner.logger.log(event="chat.end", error=str(e)[:2000],
                                      duration_s=round(time.monotonic() - started, 3))
                    self._send(502, {"error": f"agent failed: {e}"})
                    return
            finally:
                runner.chat_slots.release()
            duration = round(time.monotonic() - started, 3)
            runner.logger.log(event="chat.end", model=model,
                              stop_reason=result["stop_reason"], timeout=result["timeout"],
                              duration_s=duration, response_chars=len(result["text"]))
            if result["timeout"]:
                self._send(504, {"error": "agent timed out"})
                return
            self._send(200, {
                "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model or "agent-runner",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": result["text"]},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            })

        def log_message(self, fmt, *args):  # quiet the default access log
            pass

    return Handler


def serve(config_path: str) -> None:
    config = load_config(config_path)
    log_path = config["server"].get(
        "log_file",
        os.path.join(os.path.dirname(os.path.abspath(config_path)), "agent-runner.jobs.jsonl"),
    )
    logger = JobLogger(log_path, secret=config["server"]["token"])
    runner = Runner(config, logger)
    runner.start()
    host, port = config["server"]["_host"], config["server"]["_port"]
    httpd = ThreadingHTTPServer((host, port), make_handler(runner))

    def on_sigterm(signum, frame):
        logger.log(event="server.shutdown", signal=signum,
                   active_children=len(_ACTIVE_PIDS))
        _kill_all_active()
        # detached (setsid) descendants can still escape; see README
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, on_sigterm)
    logger.log(event="server.start", listen=f"{host}:{port}",
               actions=sorted(config["actions"]), chat="chat" in config,
               log_file=log_path)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        _kill_all_active()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", required=True, help="path to TOML config")
    args = parser.parse_args()
    try:
        serve(args.config)
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()

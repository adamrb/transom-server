#!/usr/bin/env python3
"""agent-runner action for the "Ask Claude" route.

Reads a Plaud voice-memo transcript on stdin (TITLE/RECORDING header block,
blank line, transcript) and starts a NEW Claude Code session in Paseo seeded
with it, hands-free (bypassPermissions), visible in the user's Paseo app to watch
and steer. The agent lives in the Paseo daemon, so it outlives this webhook
call; we return as soon as it exists.

Working directory: if the transcript names an existing repo under ~/git or
~/tools ("start a session in plaud-bridge-server ..."), the session opens
there; otherwise $HOME. The user can always redirect it from the app.

Result callback: the runner (completion = "child") hands us PB_RESULT_URL and
PB_RESULT_TOKEN. They go into a 0600 file and only that file's path travels to
the agent (PB_RESULT_FILE), so the token never sits in a process environment
listing; the session runs report-result.sh when the task is done.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paseo_common as pc  # noqa: E402

HERE = Path(__file__).resolve().parent
RESULT_DIR = Path(os.environ.get("XDG_RUNTIME_DIR") or (Path.home() / ".cache")) / "plaud-agent-runner/results"


def write_result_file(session: str) -> Path | None:
    url, token = os.environ.pop("PB_RESULT_URL", ""), os.environ.pop("PB_RESULT_TOKEN", "")
    if not url or not token:
        return None
    try:
        RESULT_DIR.mkdir(parents=True, exist_ok=True)
        os.chmod(RESULT_DIR, 0o700)
        path = RESULT_DIR / f"{session}.json"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump({"url": url, "token": token}, f)
        return path
    except OSError as e:
        print(f"start-paseo-session: could not write result file ({e}); the session will not report back", file=sys.stderr)
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default=None, help=f"Paseo provider/model (default {pc.PROVIDER})")
    ap.add_argument("--mode", default=None, help=f"Paseo permission mode (default {pc.MODE})")
    ns = ap.parse_args()
    headers, transcript = pc.read_message()
    if not transcript.strip():
        print("start-paseo-session: empty transcript on stdin", file=sys.stderr)
        return 1
    title = headers.get("TITLE", "")
    recording_id = headers.get("RECORDING", "")
    workdir = pc.match_workdir(transcript)  # matched on the raw transcript only, never the preamble
    session = f"plaud-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
    result_file = write_result_file(session)

    parts = [
        "You're being started from a voice memo the user dictated on their Plaud recorder. Treat the "
        "following as his instruction and get to work. If it names a project you're likely already "
        "in that repo; otherwise ask or work from the current directory. The user reads this session "
        "in the Paseo app on his phone, so keep replies short and finish with a clear summary.",
    ]
    if result_file is not None:
        parts.append(
            "When the task is finished, or if it turns out you cannot do it, report back to the user's "
            "recordings app exactly once, before your final reply, by running: "
            f"{HERE}/report-result.sh done \"<two or three plain sentences: what you did and where the "
            f"result is>\" (or: {HERE}/report-result.sh failed \"<why>\"). This is what the user sees next "
            "to the recording, so write it for him, not for a log."
        )
    parts.append(transcript.rstrip())
    prompt, _spill = pc.prompt_argument("\n\n".join(parts), title or "ask-claude")

    env = pc.paseo_env()
    agent_env = {"PB_RESULT_FILE": str(result_file)} if result_file is not None else {}
    labels = {"source": "plaud", "route": "ask-claude"}
    if recording_id:
        labels["recording"] = recording_id
    try:
        agent_id = pc.create_agent(title=pc.agent_title("Plaud", title), cwd=workdir, prompt=prompt,
                                   labels=labels, agent_env=agent_env, env=env,
                                   provider=ns.provider, mode=ns.mode)
    except pc.PaseoError as e:
        if result_file is not None:
            try:
                result_file.unlink()
            except OSError:
                pass
        print(f"start-paseo-session: {e}", file=sys.stderr)
        return 1
    where = "your home folder" if workdir == Path.home() else workdir.name
    # Last stdout line = what the app shows while the session works.
    print(f"Started a Claude session in Paseo ({where}, agent {agent_id[:8]}); it reports back here when the task is done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

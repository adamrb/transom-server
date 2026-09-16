#!/usr/bin/env python3
"""agent-runner action that runs a filing recipe as a Paseo agent and waits.

Replaces the headless `claude-code-acp` executor for the "Vault notes", "Work
meetings" and default routes: the rendered prompt arrives on stdin (TITLE and
RECORDING header block, blank line, prompt), a Claude Code agent runs it in
Paseo (visible in the user's Paseo app with the full transcript), and this script prints
the agent's final line, which the runner shows as the delivery outcome
(`Filed: ...` / `Created: ...` / `Skipped: ...`).

    paseo-agent.py --route "Vault notes" --cwd /path/to/vault --timeout 870

--timeout is the total budget in seconds (creation, wait, cleanup); keep it a
little under the runner's timeout_seconds so a stuck agent is stopped and
reported instead of the runner killing this launcher blind. --provider and
--mode override the defaults in paseo_common.py per action (the runner passes
an action's `env` only to completion = "child" commands, so flags are the way
to configure a filing action). A timed-out or errored agent exits non-zero, so
the delivery stays retryable.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paseo_common as pc  # noqa: E402

# Seconds of --timeout held back for stopping a stuck agent and reading its reply.
CLEANUP_RESERVE_S = 60


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--route", required=True, help="route name, used for the agent title and label")
    ap.add_argument("--cwd", required=True, help="working directory for the agent")
    ap.add_argument("--timeout", type=int, default=870, help="seconds to wait for the agent")
    ap.add_argument("--provider", default=None, help=f"Paseo provider/model (default {pc.PROVIDER})")
    ap.add_argument("--mode", default=None, help=f"Paseo permission mode (default {pc.MODE})")
    ns = ap.parse_args()

    headers, body = pc.read_message()
    if not body.strip():
        print("paseo-agent: empty prompt on stdin", file=sys.stderr)
        return 1
    title = headers.get("TITLE", "")
    recording_id = headers.get("RECORDING", "")
    cwd = Path(ns.cwd)
    if not cwd.is_dir():
        print(f"paseo-agent: cwd does not exist: {cwd}", file=sys.stderr)
        return 1

    prompt, spill = pc.prompt_argument(body, f"{ns.route}-{title}")
    env = pc.paseo_env()
    labels = {"source": "plaud", "route": ns.route}
    if recording_id:
        labels["recording"] = recording_id
    # Every phase is bounded by one deadline (--timeout from start): creation,
    # the wait, and a reserve for stopping the agent and reading its reply, so
    # the runner's own watchdog (timeout_seconds, a little above --timeout)
    # never has to kill us mid-cleanup with a daemon-owned agent still running.
    started = time.monotonic()
    deadline = started + ns.timeout
    create_budget = min(pc.CREATE_TIMEOUT_S, max(10, ns.timeout - CLEANUP_RESERVE_S))
    try:
        agent_id = pc.create_agent(title=pc.agent_title(f"Plaud {ns.route}", title), cwd=cwd,
                                   prompt=prompt, labels=labels, env=env,
                                   provider=ns.provider, mode=ns.mode, timeout=create_budget)
    except pc.PaseoError as e:
        _cleanup(spill)
        print(f"paseo-agent: {e}", file=sys.stderr)
        return 1

    try:
        wait_budget = int(deadline - time.monotonic()) - CLEANUP_RESERVE_S
        if wait_budget < 10:
            status = "no time left to wait"
        else:
            try:
                status = pc.wait_agent(agent_id, wait_budget, env)
            except pc.PaseoError as e:
                status = f"wait failed: {e}"
        if status != "idle":
            # Whatever went wrong, do not leave a daemon-owned agent working on a
            # delivery the runner is about to report as failed (a retry would
            # start a second one).
            stopped = pc.stop_agent(agent_id, env)
            minutes = max(1, round((time.monotonic() - started) / 60))
            outcome = "stopped it" if stopped else "could NOT confirm it stopped, check it in Paseo before retrying"
            print(f"Agent {agent_id[:8]} did not finish ({status}) after {minutes} min; {outcome}", file=sys.stderr)
            return 2
        # A very fast idle report can race the first reply; give the transcript a
        # moment, but never past the deadline.
        last = ""
        while True:
            try:
                last = pc.last_text_line(agent_id, env)
            except pc.PaseoError:
                last = ""
            if last or time.monotonic() > deadline - 10:
                break
            time.sleep(5)
        if not last:
            print(f"Agent {agent_id[:8]} finished without a reply; see Paseo", file=sys.stderr)
            return 3
        if not pc.OUTCOME_LINE_RE.match(last):
            # Idle without an outcome line = the turn was interrupted (from the
            # app) or ended early; the same case the ACP path treats as failed.
            print(f"Agent {agent_id[:8]} stopped before reporting an outcome (last line: {last[:160]}); see Paseo",
                  file=sys.stderr)
            return 4
        print(last)
        return 0
    finally:
        _cleanup(spill)


def _cleanup(spill: Path | None) -> None:
    if spill is not None:
        try:
            spill.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())

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
import time
import tomllib
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_LISTEN = "127.0.0.1:8091"
DEFAULT_QUEUE_SIZE = 16
DEFAULT_TIMEOUT_S = 600
MAX_BODY_BYTES = 10 * 1024 * 1024
ACP_PROTOCOL_VERSION = 1
DEFAULT_CHAT_TEMPLATE = (
    "Answer directly. Do not use tools or modify files.\n\n{prompt}"
)

# The only tokens ever substituted. Anything else inside braces -- including
# brace sequences that arrive inside the transcript text -- is left verbatim.
TEMPLATE_VARS = (
    "text",
    "summary",
    "route_name",
    "route_description",
    "recording_id",
    "filename",
    "started_at",
    "prompt",
    "file",
)
_TOKEN_RE = re.compile(r"\{(" + "|".join(TEMPLATE_VARS) + r")\}")


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
    server.setdefault("queue_size", DEFAULT_QUEUE_SIZE)
    cfg["server"] = server

    actions = cfg.get("actions", {})
    if not actions:
        raise ConfigError("config defines no [actions.*]")
    for name, action in actions.items():
        if not isinstance(action, dict):
            raise ConfigError(f"[actions.{name}] must be a table")
        _validate_executor(f"actions.{name}", action)
    cfg["actions"] = actions

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

    return {
        "text": s(transcript.get("text")),
        "summary": s(transcript.get("summary")),
        "route_name": s(route.get("name")),
        "route_description": s(route.get("description")),
        "recording_id": s(recording.get("id")),
        "filename": s(recording.get("filename")),
        "started_at": s(recording.get("started_at")),
    }


class JobLogger:
    def __init__(self, log_path: str):
        self.log_path = log_path
        self._lock = threading.Lock()

    def log(self, **fields) -> None:
        fields["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        line = json.dumps(fields, ensure_ascii=False)
        with self._lock:
            print(line, flush=True)
            try:
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError as e:
                print(f'{{"event":"log_write_error","error":"{e}"}}', file=sys.stderr, flush=True)


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
        """Next parsed message, or None on EOF."""
        while True:
            line = self.proc.stdout.readline()
            if line == "":
                return None
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
                 model=None):
        self.argv = list(argv)
        self.cwd = cwd or os.getcwd()
        self.auto_approve = bool(auto_approve)
        self.logger = logger
        self.label = label
        self.extra_env = dict(extra_env or {})
        self.model = model or None
        self.text_parts: list[str] = []
        self._next_id = 0
        self._stderr_tail = ""

    def _drain_stderr(self, proc):
        def run():
            try:
                data = proc.stderr.read()
                if data:
                    self._stderr_tail = data[-2000:]
            except (ValueError, OSError):
                pass
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

        def kill():
            timed_out.set()
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                proc.kill()

        watchdog = threading.Timer(timeout, kill)
        watchdog.daemon = True
        watchdog.start()
        self._drain_stderr(proc)
        io = NDJSONStdio(proc, on_garbage=lambda s: self.logger.log(
            event="acp.garbage_line", label=self.label, line=s))
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
                "stderr_tail": self._stderr_tail,
            }
        except ACPError as e:
            if timed_out.is_set() or time.monotonic() >= deadline:
                return {"stop_reason": "timeout", "text": "".join(self.text_parts),
                        "timeout": True, "stderr_tail": self._stderr_tail}
            raise ACPError(f"{e} (stderr: {self._stderr_tail[-500:]})") from e
        finally:
            watchdog.cancel()
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass
            try:
                proc.stdin.close()
            except OSError:
                pass
            proc.wait(timeout=5)

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
                self.text_parts.append(content.get("text", ""))

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
            for opt in options:
                if isinstance(opt, dict) and opt.get("kind") in kinds:
                    return opt.get("optionId")
            return None

        if self.auto_approve:
            option_id = find("allow_once", "allow_always")
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
        self.chat_lock = threading.Lock()

    def start(self) -> None:
        self._thread.start()

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
        try:
            self.jobs.put_nowait((job_id, action_name, action, payload))
        except queue.Full:
            return None
        return job_id

    def _worker(self) -> None:
        while True:
            job_id, action_name, action, payload = self.jobs.get()
            try:
                self._run_job(job_id, action_name, action, payload)
            except Exception as e:  # never kill the worker
                self.logger.log(event="job.error", job=job_id, action=action_name,
                                error=f"{type(e).__name__}: {e}")
            finally:
                self.jobs.task_done()

    def _run_job(self, job_id: int, action_name: str, action: dict, payload: dict) -> None:
        variables = payload_vars(payload)
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
        session = ACPSession(action["agent"], cwd, action.get("auto_approve", False),
                             self.logger, label=f"job-{job_id}",
                             extra_env=action.get("env"), model=action.get("model"))
        try:
            result = session.run_prompt(variables["prompt"], timeout)
        except ACPError as e:
            self.logger.log(event="job.end", job=job_id, action=action_name, mode="acp",
                            route=variables["route_name"], stop_reason="error",
                            timeout=False, duration_s=round(time.monotonic() - started, 3),
                            error=str(e)[:2000])
            return
        self.logger.log(event="job.end", job=job_id, action=action_name, mode="acp",
                        route=variables["route_name"], stop_reason=result["stop_reason"],
                        timeout=result["timeout"],
                        duration_s=round(time.monotonic() - started, 3),
                        response_chars=len(result["text"]),
                        response=result["text"][:4000],
                        stderr_tail=result["stderr_tail"][-500:])

    def _run_command_job(self, job_id, action_name, action, variables, timeout, cwd) -> None:
        argv = [render(arg, variables) for arg in action["command"]]
        self.logger.log(event="job.start", job=job_id, action=action_name, mode="command",
                        route=variables["route_name"], recording=variables["recording_id"],
                        command=argv[0], timeout_s=timeout)
        started = time.monotonic()
        timed_out = False
        try:
            proc = subprocess.Popen(
                argv, cwd=cwd, shell=False, start_new_session=True,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
        except FileNotFoundError as e:
            self.logger.log(event="job.end", job=job_id, action=action_name, mode="command",
                            exit_code=None, error=f"command not found: {e.filename}")
            return
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            out, err = proc.communicate()
        self.logger.log(event="job.end", job=job_id, action=action_name, mode="command",
                        route=variables["route_name"], exit_code=proc.returncode,
                        timeout=timed_out, duration_s=round(time.monotonic() - started, 3),
                        stdout_bytes=len(out),
                        stderr_tail=err.decode("utf-8", "replace")[-2000:])


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

    class Handler(BaseHTTPRequestHandler):
        server_version = "plaud-agent-runner/2.0"
        protocol_version = "HTTP/1.1"

        def _send(self, code: int, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
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
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length <= 0 or length > MAX_BODY_BYTES:
                self._send(400, {"error": "bad content length"})
                return None
            try:
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("payload must be a JSON object")
                return payload
            except (ValueError, UnicodeDecodeError) as e:
                self._send(400, {"error": f"invalid JSON: {e}"})
                return None

        def do_GET(self) -> None:
            if self.path == "/healthz":
                self._send(200, {"status": "ok", "queued": runner.jobs.qsize()})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self) -> None:
            if not self._authorized():
                self._send(401, {"error": "unauthorized"})
                return
            if self.path == "/":
                self._post_webhook()
            elif self.path == "/v1/chat/completions":
                self._post_chat()
            else:
                self._send(404, {"error": "not found"})

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
            runner.logger.log(event="chat.start", model=model, prompt_chars=len(prompt))
            with runner.chat_lock:  # one agent session at a time
                session = ACPSession(chat_cfg["agent"], chat_cfg.get("cwd"),
                                     chat_cfg.get("auto_approve", False),
                                     runner.logger, label="chat",
                                     extra_env=chat_cfg.get("env"),
                                     model=chat_cfg.get("model"))
                try:
                    result = session.run_prompt(prompt, timeout)
                except ACPError as e:
                    runner.logger.log(event="chat.end", error=str(e)[:2000],
                                      duration_s=round(time.monotonic() - started, 3))
                    self._send(502, {"error": f"agent failed: {e}"})
                    return
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
    logger = JobLogger(log_path)
    runner = Runner(config, logger)
    runner.start()
    host, port = config["server"]["_host"], config["server"]["_port"]
    httpd = ThreadingHTTPServer((host, port), make_handler(runner))
    logger.log(event="server.start", listen=f"{host}:{port}",
               actions=sorted(config["actions"]), chat="chat" in config,
               log_file=log_path)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


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

#!/usr/bin/env python3
"""A minimal fake ACP agent for tests: speaks newline-delimited JSON-RPC 2.0
on stdio like claude-code-acp. Behavior selected by argv[1] (or FAKE_ACP_MODE):

  echo        chunk back the received prompt text, stopReason end_turn
  model       chunk back "model=<modelId>" set via session/set_model
  happy       two chunks "Hello " + "world", stopReason end_turn
  permission  asks session/request_permission; chunk APPROVED/REJECTED
              depending on the client's answer
  hang        accepts session/prompt then never replies
  garbage     emits a malformed line, then behaves like happy
  slow        sleeps 1.5s, then echoes (for concurrency-limit tests)
  bigline     emits a >1 MiB single frame (oversized-frame kill test)
  bigresponse emits ~3 MiB of chunks (response-truncation test)
"""

import json
import os
import sys


def send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def notify(method, params):
    send({"jsonrpc": "2.0", "method": method, "params": params})


def chunk(session_id, text):
    notify("session/update", {
        "sessionId": session_id,
        "update": {"sessionUpdate": "agent_message_chunk",
                   "content": {"type": "text", "text": text}},
    })


def read_msg():
    line = sys.stdin.readline()
    if line == "":
        sys.exit(0)
    return json.loads(line)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("FAKE_ACP_MODE", "echo")
    next_agent_id = 1000
    selected_model = ""
    while True:
        msg = read_msg()
        method, msg_id, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
        if method == "initialize":
            send({"jsonrpc": "2.0", "id": msg_id,
                  "result": {"protocolVersion": 1, "agentCapabilities": {}, "authMethods": []}})
        elif method == "session/new":
            send({"jsonrpc": "2.0", "id": msg_id, "result": {"sessionId": "sess-fake-1"}})
        elif method == "session/set_model":
            selected_model = params.get("modelId", "")
            send({"jsonrpc": "2.0", "id": msg_id, "result": {}})
        elif method == "session/prompt":
            sid = params["sessionId"]
            prompt_text = "".join(b.get("text", "") for b in params.get("prompt", [])
                                  if b.get("type") == "text")
            if mode == "hang":
                while True:
                    read_msg()
            if mode == "garbage":
                sys.stdout.write("this is {not json%%%\n")
                sys.stdout.flush()
                mode = "happy"
            if mode == "happy":
                chunk(sid, "Hello ")
                chunk(sid, "world")
            elif mode == "echo":
                chunk(sid, prompt_text)
            elif mode == "model":
                chunk(sid, "model=" + selected_model)
            elif mode == "permission":
                req_id = next_agent_id
                next_agent_id += 1
                # allow_always deliberately listed FIRST, like claude-code-acp
                # 0.16.x does: the client must still pick allow_once.
                send({"jsonrpc": "2.0", "id": req_id, "method": "session/request_permission",
                      "params": {"sessionId": sid,
                                 "toolCall": {"toolCallId": "t1", "title": "Write file"},
                                 "options": [
                                     {"optionId": "allow-always", "name": "Always", "kind": "allow_always"},
                                     {"optionId": "allow-once", "name": "Allow", "kind": "allow_once"},
                                     {"optionId": "reject-once", "name": "Reject", "kind": "reject_once"},
                                 ]}})
                reply = read_msg()
                outcome = (reply.get("result") or {}).get("outcome") or {}
                if outcome.get("outcome") == "selected" and outcome.get("optionId", "").startswith("allow"):
                    chunk(sid, "APPROVED:" + outcome.get("optionId", ""))
                else:
                    chunk(sid, "REJECTED:" + outcome.get("optionId", ""))
            elif mode == "slow":
                import time as _time
                _time.sleep(1.5)
                chunk(sid, prompt_text)
            elif mode == "bigline":
                # oversized single frame (>1 MiB) -- client must kill the job
                sys.stdout.write("x" * (2 * 1024 * 1024) + "\n")
                sys.stdout.flush()
                chunk(sid, "should never be seen")
            elif mode == "bigresponse":
                # ~3 MiB of chunks -- client must truncate at its cap
                for _ in range(48):
                    chunk(sid, "y" * 65536)
            send({"jsonrpc": "2.0", "id": msg_id, "result": {"stopReason": "end_turn"}})
        elif msg_id is not None and method is not None:
            send({"jsonrpc": "2.0", "id": msg_id,
                  "error": {"code": -32601, "message": f"unknown method {method}"}})


if __name__ == "__main__":
    try:
        main()
    except (BrokenPipeError, KeyboardInterrupt):
        pass

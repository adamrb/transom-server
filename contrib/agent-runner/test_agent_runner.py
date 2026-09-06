#!/usr/bin/env python3
"""Tests for agent_runner.py. Run: python3 test_agent_runner.py

ACP protocol tests use fake_acp_agent.py, a canned newline-delimited JSON-RPC
agent, so no real agent or network is needed.
"""

import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent_runner  # noqa: E402

TOKEN = "test-token-123"


def payload(route_name="default", text="hello world", description="do the thing"):
    return {
        "event": "route.matched",
        "route": {"name": route_name, "description": description},
        "recording": {"id": "rec-1", "device_sn": "SN1", "session_id": 1,
                      "filename": "a.mp3", "started_at": "2026-01-01T00:00:00Z",
                      "duration_s": 1.0, "url": "/api/v1/recordings/rec-1"},
        "transcript": {"text": text, "summary": "a summary", "language": "en"},
    }


class RunnerTestBase(unittest.TestCase):
    """Spins up a real server on an ephemeral port with a given actions dict."""

    actions: dict = {}
    queue_size = 16

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.log_file = os.path.join(cls.tmpdir.name, "jobs.jsonl")
        config = {
            "server": {"token": TOKEN, "queue_size": cls.queue_size,
                       "log_responses": True,
                       "_host": "127.0.0.1", "_port": 0},
            "actions": cls.actions,
        }
        logger = agent_runner.JobLogger(cls.log_file)
        cls.runner = agent_runner.Runner(config, logger)
        cls.runner.start()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), agent_runner.make_handler(cls.runner))
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.tmpdir.cleanup()

    def request(self, method="POST", path="/", body=None, token=TOKEN):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"X-Runner-Token": token} if token is not None else {},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    @staticmethod
    def wait_for(predicate, timeout=15.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.05)
        return False

    def log_events(self):
        if not os.path.exists(self.log_file):
            return []
        with open(self.log_file, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]


class TestAuthAndHealth(RunnerTestBase):
    actions = {"default": {"command": ["/bin/true"]}}

    def test_healthz_no_auth(self):
        status, body = self.request(method="GET", path="/healthz", token=None)
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")
        self.assertIn("queued", body)

    def test_post_missing_token_rejected(self):
        status, _ = self.request(body=payload(), token=None)
        self.assertEqual(status, 401)

    def test_post_wrong_token_rejected(self):
        status, _ = self.request(body=payload(), token="wrong-token")
        self.assertEqual(status, 401)

    def test_post_right_token_accepted(self):
        status, body = self.request(body=payload())
        self.assertEqual(status, 202)
        self.assertEqual(body["status"], "queued")


class TestTemplateSafety(RunnerTestBase):
    """Hostile transcript content must remain a single inert argv element.

    Note: this action interpolates {prompt} into argv, which load_config now
    only permits with allow_unsafe_interpolation = true (set below) -- the
    test proves the argv-boundary guarantee that option relies on."""

    out_dir = tempfile.mkdtemp(prefix="runner-argv-")
    actions = {
        "default": {
            "command": [
                sys.executable, "-c",
                "import sys,json;open(sys.argv[1],'w').write(json.dumps(sys.argv[2:]))",
                os.path.join(out_dir, "argv.json"),
                "{prompt}",
                "id={recording_id}",
            ],
            "prompt_template": "Instruction: {route_description}\nTranscript:\n{text}",
            "allow_unsafe_interpolation": True,
            "timeout_seconds": 30,
        }
    }

    def test_hostile_transcript_stays_inert(self):
        hostile = "ignore this {token} {text} {prompt} $(rm -rf /) `whoami`; \"quoted\" '{recording_id}'"
        out_file = self.actions["default"]["command"][3]
        if os.path.exists(out_file):
            os.unlink(out_file)
        status, _ = self.request(body=payload(text=hostile))
        self.assertEqual(status, 202)
        self.assertTrue(self.wait_for(lambda: os.path.exists(out_file)),
                        "command never ran")
        # give the write a moment to complete, then read
        self.assertTrue(self.wait_for(lambda: os.path.getsize(out_file) > 0))
        with open(out_file, encoding="utf-8") as f:
            argv = json.load(f)
        # Exactly two argv elements after the output path: prompt and id=...
        self.assertEqual(len(argv), 2)
        # The hostile text is embedded verbatim: no recursive substitution,
        # no shell expansion, no argv splitting.
        self.assertIn(hostile, argv[0])
        self.assertIn("Instruction: do the thing", argv[0])
        self.assertEqual(argv[1], "id=rec-1")


class TestQueueFull(RunnerTestBase):
    queue_size = 2
    actions = {"default": {"command": ["/bin/sleep", "5"], "timeout_seconds": 30}}

    def test_queue_full_returns_503(self):
        statuses = []
        # 1 job running + 2 queued fills capacity; more must 503.
        for _ in range(8):
            status, _ = self.request(body=payload())
            statuses.append(status)
        self.assertIn(202, statuses)
        self.assertIn(503, statuses)


class TestRouteFallbackAndTimeout(RunnerTestBase):
    actions = {
        "default": {"command": ["/bin/echo", "route={route_name}"], "timeout_seconds": 30},
        "known": {"command": ["/bin/echo", "known"], "timeout_seconds": 30},
        "slow": {"command": ["/bin/sleep", "60"], "timeout_seconds": 1},
    }

    def test_unknown_route_falls_back_to_default(self):
        status, body = self.request(body=payload(route_name="no-such-route"))
        self.assertEqual(status, 202)
        self.assertEqual(body["action"], "default")

    def test_known_route_uses_its_action(self):
        status, body = self.request(body=payload(route_name="known"))
        self.assertEqual(status, 202)
        self.assertEqual(body["action"], "known")

    def test_no_default_returns_404(self):
        original = self.runner.config["actions"]
        self.runner.config["actions"] = {"known": original["known"]}
        try:
            status, _ = self.request(body=payload(route_name="no-such-route"))
            self.assertEqual(status, 404)
        finally:
            self.runner.config["actions"] = original

    def test_timeout_kills_job(self):
        start = time.monotonic()
        status, body = self.request(body=payload(route_name="slow"))
        self.assertEqual(status, 202)
        job_id = body["job"]

        def job_ended():
            return any(e.get("event") == "job.end" and e.get("job") == job_id
                       for e in self.log_events())

        self.assertTrue(self.wait_for(job_ended, timeout=20),
                        "timed-out job never logged job.end")
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 20, "job was not killed at timeout")
        end = next(e for e in self.log_events()
                   if e.get("event") == "job.end" and e.get("job") == job_id)
        self.assertTrue(end["timeout"])
        self.assertNotEqual(end["exit_code"], 0)


FAKE_AGENT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_acp_agent.py")


class TestACP(RunnerTestBase):
    actions = {
        "default": {
            "agent": [sys.executable, FAKE_AGENT, "happy"],
            "prompt_template": "Instruction: {route_description}\n\n{text}",
            "timeout_seconds": 30,
        },
        "approve": {
            "agent": [sys.executable, FAKE_AGENT, "permission"],
            "auto_approve": True,
            "timeout_seconds": 30,
        },
        "reject": {
            "agent": [sys.executable, FAKE_AGENT, "permission"],
            "auto_approve": False,
            "timeout_seconds": 30,
        },
        "hang": {
            "agent": [sys.executable, FAKE_AGENT, "hang"],
            "timeout_seconds": 2,
        },
        "garbage": {
            "agent": [sys.executable, FAKE_AGENT, "garbage"],
            "timeout_seconds": 30,
        },
        "pick-model": {
            "agent": [sys.executable, FAKE_AGENT, "model"],
            "model": "haiku",
            "timeout_seconds": 30,
        },
        "bigline": {
            "agent": [sys.executable, FAKE_AGENT, "bigline"],
            "timeout_seconds": 30,
        },
        "bigresponse": {
            "agent": [sys.executable, FAKE_AGENT, "bigresponse"],
            "timeout_seconds": 60,
        },
    }

    def _end_event(self, job_id, timeout=20):
        def done():
            return any(e.get("event") == "job.end" and e.get("job") == job_id
                       for e in self.log_events())
        self.assertTrue(self.wait_for(done, timeout=timeout),
                        f"job {job_id} never logged job.end")
        return next(e for e in self.log_events()
                    if e.get("event") == "job.end" and e.get("job") == job_id)

    def test_happy_path_collects_response(self):
        status, body = self.request(body=payload())
        self.assertEqual(status, 202)
        end = self._end_event(body["job"])
        self.assertEqual(end["mode"], "acp")
        self.assertEqual(end["stop_reason"], "end_turn")
        self.assertFalse(end["timeout"])
        self.assertEqual(end["response"], "Hello world")

    def test_permission_auto_approve_picks_allow_once_only(self):
        status, body = self.request(body=payload(route_name="approve"))
        self.assertEqual(status, 202)
        end = self._end_event(body["job"])
        # the fake agent lists allow_always FIRST; the runner must still
        # select the one-shot approval, never the persistent one
        self.assertEqual(end["response"], "APPROVED:allow-once")
        perm = [e for e in self.log_events() if e.get("event") == "acp.permission"
                and e.get("label") == f"job-{body['job']}"]
        self.assertTrue(perm and perm[0]["outcome"]["outcome"] == "selected")
        self.assertEqual(perm[0]["outcome"]["optionId"], "allow-once")

    def test_permission_reject(self):
        status, body = self.request(body=payload(route_name="reject"))
        self.assertEqual(status, 202)
        end = self._end_event(body["job"])
        self.assertEqual(end["response"], "REJECTED:reject-once")

    def test_timeout_kills_agent(self):
        start = time.monotonic()
        status, body = self.request(body=payload(route_name="hang"))
        self.assertEqual(status, 202)
        end = self._end_event(body["job"])
        self.assertTrue(end["timeout"])
        self.assertEqual(end["stop_reason"], "timeout")
        self.assertLess(time.monotonic() - start, 15)

    def test_model_selection_via_set_model(self):
        status, body = self.request(body=payload(route_name="pick-model"))
        self.assertEqual(status, 202)
        end = self._end_event(body["job"])
        self.assertEqual(end["response"], "model=haiku")

    def test_malformed_json_line_tolerated(self):
        status, body = self.request(body=payload(route_name="garbage"))
        self.assertEqual(status, 202)
        end = self._end_event(body["job"])
        self.assertEqual(end["response"], "Hello world")
        self.assertTrue(any(e.get("event") == "acp.garbage_line"
                            for e in self.log_events()))

    def test_oversized_frame_kills_job(self):
        status, body = self.request(body=payload(route_name="bigline"))
        self.assertEqual(status, 202)
        end = self._end_event(body["job"])
        self.assertEqual(end["stop_reason"], "error")
        self.assertIn("oversized frame", end["error"])

    def test_oversized_response_truncated(self):
        status, body = self.request(body=payload(route_name="bigresponse"))
        self.assertEqual(status, 202)
        end = self._end_event(body["job"], timeout=40)
        self.assertTrue(end["truncated"])
        self.assertLessEqual(end["response_chars"],
                             agent_runner.MAX_RESPONSE_CHARS + 100)

    def test_response_not_logged_when_disabled(self):
        self.runner.config["server"]["log_responses"] = False
        try:
            status, body = self.request(body=payload())
            self.assertEqual(status, 202)
            end = self._end_event(body["job"])
            self.assertNotIn("response", end)
            self.assertNotIn("stderr_tail", end)
            self.assertEqual(end["response_chars"], len("Hello world"))
        finally:
            self.runner.config["server"]["log_responses"] = True


class TestChatShim(RunnerTestBase):
    actions = {"default": {"command": ["/bin/true"]}}
    chat = {
        "agent": [sys.executable, FAKE_AGENT, "echo"],
        "auto_approve": False,
        "timeout_seconds": 30,
    }

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.runner.config["chat"] = cls.chat

    def _chat(self, body, auth_header):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/v1/chat/completions",
            method="POST", data=json.dumps(body).encode(), headers=auth_header)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_chat_completion_end_to_end(self):
        status, body = self._chat(
            {"model": "gpt-test", "messages": [
                {"role": "system", "content": "You are a router."},
                {"role": "user", "content": "Say PONG"},
            ]},
            {"Authorization": "Bearer " + TOKEN},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["object"], "chat.completion")
        content = body["choices"][0]["message"]["content"]
        # echo agent returns the full rendered prompt: template wrap + flattened
        self.assertIn("Do not use tools", content)
        self.assertIn("You are a router.", content)
        self.assertIn("Say PONG", content)
        self.assertEqual(body["choices"][0]["finish_reason"], "stop")

    def test_chat_accepts_x_runner_token(self):
        status, _ = self._chat({"messages": [{"role": "user", "content": "hi"}]},
                               {"X-Runner-Token": TOKEN})
        self.assertEqual(status, 200)

    def test_chat_auth_rejected(self):
        status, _ = self._chat({"messages": [{"role": "user", "content": "hi"}]},
                               {"Authorization": "Bearer wrong"})
        self.assertEqual(status, 401)


class TestStdinMode(RunnerTestBase):
    """stdin_template is the safe path for payload text into plain commands."""

    out_dir = tempfile.mkdtemp(prefix="runner-stdin-")
    actions = {
        "default": {
            "command": [
                sys.executable, "-c",
                "import sys,json;open(sys.argv[1],'w').write("
                "json.dumps({'argv':sys.argv[2:],'stdin':sys.stdin.read()}))",
                os.path.join(out_dir, "stdin.json"),
                "id={recording_id}",
            ],
            "stdin_template": "Instruction: {route_description}\n{text}",
            "timeout_seconds": 30,
        }
    }

    def test_hostile_text_arrives_via_stdin_not_argv(self):
        hostile = "--delete-everything $(rm -rf /) {token} {text} -o /etc/passwd"
        out_file = self.actions["default"]["command"][3]
        if os.path.exists(out_file):
            os.unlink(out_file)
        status, _ = self.request(body=payload(text=hostile))
        self.assertEqual(status, 202)
        self.assertTrue(self.wait_for(
            lambda: os.path.exists(out_file) and os.path.getsize(out_file) > 0))
        with open(out_file, encoding="utf-8") as f:
            result = json.load(f)
        # argv is exactly the static config: no transcript-derived elements,
        # so a leading "--" can never become an option
        self.assertEqual(result["argv"], ["id=rec-1"])
        self.assertIn(hostile, result["stdin"])
        self.assertIn("Instruction: do the thing", result["stdin"])


class TestChatSaturation(RunnerTestBase):
    actions = {"default": {"command": ["/bin/true"]}}
    chat = {
        "agent": [sys.executable, FAKE_AGENT, "slow"],
        "timeout_seconds": 30,
    }

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.runner.config["chat"] = cls.chat

    def test_third_concurrent_chat_gets_503(self):
        results = []
        def one():
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/v1/chat/completions",
                method="POST",
                data=json.dumps({"messages": [{"role": "user", "content": "hi"}]}).encode(),
                headers={"X-Runner-Token": TOKEN})
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    results.append(resp.status)
            except urllib.error.HTTPError as e:
                e.read()
                results.append(e.code)
        threads = [threading.Thread(target=one) for _ in range(4)]
        for t in threads:
            t.start()
            time.sleep(0.1)  # ensure the first two occupy the slots
        for t in threads:
            t.join(timeout=40)
        self.assertIn(503, results)
        self.assertIn(200, results)
        self.assertEqual(len(results), 4)


class TestHTTPFraming(RunnerTestBase):
    """Raw-socket tests for request-smuggling hardening."""

    actions = {"default": {"command": ["/bin/true"]}}

    def _raw(self, request_bytes):
        import socket
        with socket.create_connection(("127.0.0.1", self.port), timeout=10) as s:
            s.sendall(request_bytes)
            s.shutdown(socket.SHUT_WR)
            data = b""
            while True:
                chunk = s.recv(65536)
                if not chunk:
                    break
                data += chunk
            return data

    def test_duplicate_content_length_rejected_and_closed(self):
        body = b'{"a":1}'
        req = (b"POST / HTTP/1.1\r\nHost: x\r\n"
               b"X-Runner-Token: " + TOKEN.encode() + b"\r\n"
               b"Content-Length: 7\r\nContent-Length: 7\r\n\r\n" + body)
        resp = self._raw(req)
        self.assertIn(b" 400 ", resp.split(b"\r\n", 1)[0])
        self.assertIn(b"exactly one content-length", resp.lower())
        self.assertIn(b"connection: close", resp.lower())

    def test_transfer_encoding_rejected(self):
        req = (b"POST / HTTP/1.1\r\nHost: x\r\n"
               b"X-Runner-Token: " + TOKEN.encode() + b"\r\n"
               b"Transfer-Encoding: chunked\r\nContent-Length: 7\r\n\r\n"
               b'{"a":1}')
        resp = self._raw(req)
        self.assertIn(b" 400 ", resp.split(b"\r\n", 1)[0])
        self.assertIn(b"transfer-encoding", resp.lower())
        self.assertIn(b"connection: close", resp.lower())

    def test_auth_reject_closes_connection(self):
        req = (b"POST / HTTP/1.1\r\nHost: x\r\n"
               b"X-Runner-Token: wrong\r\nContent-Length: 7\r\n\r\n" + b'{"a":1}')
        resp = self._raw(req)
        self.assertIn(b" 401 ", resp.split(b"\r\n", 1)[0])
        self.assertIn(b"connection: close", resp.lower())


class TestLogger(unittest.TestCase):
    def test_log_file_mode_0600_and_token_redacted(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "jobs.jsonl")
            old_umask = os.umask(0o000)  # permissive umask must not matter
            try:
                logger = agent_runner.JobLogger(path, secret="sekrit-token-42")
                logger.log(event="test", detail="agent printed sekrit-token-42 here")
            finally:
                os.umask(old_umask)
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            with open(path, encoding="utf-8") as f:
                content = f.read()
            self.assertNotIn("sekrit-token-42", content)
            self.assertIn("[REDACTED]", content)

    def test_log_fields_capped(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "jobs.jsonl")
            logger = agent_runner.JobLogger(path)
            logger.log(event="test", blob="z" * 100000)
            with open(path, encoding="utf-8") as f:
                entry = json.loads(f.read())
            self.assertLess(len(entry["blob"]),
                            agent_runner.MAX_LOG_FIELD_CHARS + 50)
            self.assertTrue(entry["blob"].endswith("...[truncated]"))


class TestConfigValidation(unittest.TestCase):
    def _load(self, toml_text):
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
            f.write(toml_text)
            path = f.name
        try:
            return agent_runner.load_config(path)
        finally:
            os.unlink(path)

    def test_string_command_rejected(self):
        with self.assertRaises(agent_runner.ConfigError):
            self._load('[server]\ntoken="t"\n[actions.default]\ncommand="echo hi"\n')

    def test_missing_token_rejected(self):
        with self.assertRaises(agent_runner.ConfigError):
            self._load('[server]\nlisten="127.0.0.1:1"\n[actions.default]\ncommand=["/bin/true"]\n')

    def test_valid_config_loads(self):
        cfg = self._load('[server]\ntoken="t"\n[actions.default]\ncommand=["/bin/true"]\n')
        self.assertEqual(cfg["server"]["_port"], 8091)

    def test_agent_string_rejected(self):
        with self.assertRaises(agent_runner.ConfigError):
            self._load('[server]\ntoken="t"\n[actions.default]\nagent="claude-code-acp"\n')

    def test_agent_and_command_both_rejected(self):
        with self.assertRaises(agent_runner.ConfigError):
            self._load('[server]\ntoken="t"\n[actions.default]\n'
                       'agent=["a"]\ncommand=["b"]\n')

    def test_chat_requires_agent(self):
        with self.assertRaises(agent_runner.ConfigError):
            self._load('[server]\ntoken="t"\n[actions.default]\ncommand=["/bin/true"]\n'
                       '[chat]\ncommand=["/bin/true"]\n')

    def test_payload_var_in_command_argv_rejected(self):
        with self.assertRaises(agent_runner.ConfigError):
            self._load('[server]\ntoken="t"\n[actions.default]\n'
                       'command=["/usr/bin/tool", "{text}"]\n')

    def test_shell_wrapper_with_text_rejected(self):
        with self.assertRaises(agent_runner.ConfigError):
            self._load('[server]\ntoken="t"\n[actions.default]\n'
                       'command=["/bin/sh", "-c", "echo {text}"]\n')

    def test_unsafe_interpolation_optin_allowed(self):
        cfg = self._load('[server]\ntoken="t"\n[actions.default]\n'
                         'command=["/usr/bin/tool", "{text}"]\n'
                         'allow_unsafe_interpolation=true\n')
        self.assertTrue(cfg["actions"]["default"]["allow_unsafe_interpolation"])

    def test_safe_vars_in_command_argv_allowed(self):
        cfg = self._load('[server]\ntoken="t"\n[actions.default]\n'
                         'command=["/usr/bin/tool", "{file}", "id={recording_id}"]\n'
                         'stdin_template="{text}"\n')
        self.assertEqual(cfg["actions"]["default"]["stdin_template"], "{text}")

    def test_queue_size_zero_or_negative_rejected(self):
        for bad in ("0", "-4", '"16"'):
            with self.assertRaises(agent_runner.ConfigError, msg=bad):
                self._load(f'[server]\ntoken="t"\nqueue_size={bad}\n'
                           '[actions.default]\ncommand=["/bin/true"]\n')

    def test_render_single_pass(self):
        out = agent_runner.render("{text}|{prompt}", {"text": "{prompt}{text}", "prompt": "P"})
        self.assertEqual(out, "{prompt}{text}|P")


if __name__ == "__main__":
    unittest.main(verbosity=2)

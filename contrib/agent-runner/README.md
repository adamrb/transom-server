# agent-runner

A single-file, stdlib-only HTTP service that turns plaud-bridge
`route.matched` webhooks into agent runs: pipe a voice memo transcript into
Claude Code or Codex via **ACP** ([Agent Client
Protocol](https://agentclientprotocol.com)), or into any plain command. The
agents run on your local Claude Code / Codex subscription auth — no LLM API
keys anywhere. It also exposes a minimal OpenAI-compatible chat endpoint so
plaud-bridge's AI router and summarizer can use the same subscription.

Requires Python 3.11+ (uses `tomllib`) for the service. ACP agents are
separate installs (Node for `claude-code-acp`).

## How it works

plaud-bridge POSTs a route webhook payload:

```json
{
  "event": "route.matched",
  "route": {"name": "obsidian-note", "description": "Append to my notes"},
  "recording": {"id": "...", "device_sn": "...", "session_id": 1,
                "filename": "...", "started_at": "...", "duration_s": 1.0,
                "url": "/api/v1/recordings/<id>"},
  "transcript": {"text": "...", "summary": "...", "language": "en"}
}
```

The runner looks up `[actions."<route name>"]` in its config (falling back to
`[actions.default]`), renders the prompt template, and enqueues the job on a
bounded queue (default 16; `503` when full) served by a single worker thread,
so jobs run one at a time with a per-action timeout (process group killed on
expiry). The webhook gets `202` immediately. Every job — including the
agent's final response text — is logged as JSON to stdout and to
`agent-runner.jobs.jsonl` next to the config.

`GET /healthz` returns `200 {"status":"ok","queued":n}` (no auth). Everything
else requires the `X-Runner-Token` header (constant-time compare); the chat
endpoint also accepts `Authorization: Bearer <token>`.

### ACP execution

For an action with `agent = ["claude-code-acp"]` (or `["codex", "acp"]`), the
runner spawns the agent process and speaks JSON-RPC 2.0 over its stdio.
Framing is **newline-delimited JSON** — one message per line — verified
against `@zed-industries/claude-code-acp` 0.16.x. The exchange:

1. `initialize` — protocolVersion 1, declaring no fs/terminal client
   capabilities (the agent uses its own tools, not ours).
2. `session/new` — with the action's `cwd` and `mcpServers: []`. The reply
   advertises `models.availableModels`; if the action sets `model`, the
   runner sends `session/set_model` with that modelId.
3. `session/prompt` — the rendered prompt as a single text content block.
   `session/update` notifications stream in; `agent_message_chunk` text is
   collected as the response. Incoming `session/request_permission` requests
   are answered from config: `auto_approve = true` picks an allow option,
   `false` picks a reject option (or cancels). Other agent→client requests
   (fs, terminal) are refused with JSON-RPC `-32601`.
4. The `session/prompt` response's `stopReason` ends the job; the process is
   then killed. On timeout the whole process group is SIGKILLed.

Actions with `command = [...]` instead run a plain argv (no agent, no shell)
— useful for append-to-file scripts, and as a fallback executor
(`command = ["claude", "-p", "{prompt}"]` also works if ACP ever misbehaves).

### OpenAI-compat chat shim

`POST /v1/chat/completions` (non-streaming) flattens `messages` into one
prompt (system content first), wraps it in the `[chat]` section's
`prompt_template` (default: "Answer directly. Do not use tools or modify
files.\n\n{prompt}"), runs a one-shot ACP session, and returns a standard
`chat.completion` object. The `model` field is logged and otherwise ignored —
pick the agent-side model with `[chat] model` instead. Point plaud-bridge at
it:

```
PB_ROUTER_BASE_URL=http://<runner>:8091/v1     # AI routing on your subscription
PB_ROUTER_API_KEY=<runner token>
PB_SUMMARY_BASE_URL=http://<runner>:8091/v1    # summaries too, if you like
PB_SUMMARY_API_KEY=<runner token>
```

Chat calls are serialized (one agent session at a time) and answered
synchronously; size `timeout_seconds` accordingly (a routing call with
claude-code-acp takes roughly 5–15 s).

## Security notes

- `agent`/`command` must be argv **lists**; string commands are rejected and
  no shell is ever invoked.
- Template tokens (`{text}`, `{summary}`, `{route_name}`,
  `{route_description}`, `{recording_id}`, `{filename}`, `{started_at}`,
  `{prompt}`, `{file}`) are substituted in a **single pass**, so transcript
  content containing `{token}`, `$(...)`, quotes, etc. stays inert data and
  can never become extra argv elements, shell syntax, or JSON-RPC structure
  (prompts travel as JSON string values).
- Still: the whole point is driving an agent from spoken words. With
  `auto_approve = true` anyone who can record on your Plaud device can make
  the agent edit files in its cwd. Scope actions, cwd, and approval
  accordingly, and keep the listener off untrusted networks (bind narrowly;
  the token is a second layer, not the only one).

## Setup (host, systemd) — simplest auth

1. Install an ACP agent: `npm install -g @zed-industries/claude-code-acp`
   (needs a logged-in Claude Code on the same account/HOME).
2. Copy `config.example.toml` to `config.toml`, set `token` to
   `openssl rand -hex 24` output, and define your actions.
3. Run it: `python3 agent_runner.py --config config.toml`
   (or install `agent-runner.service` as a systemd user unit — see the
   comments in that file; make sure the unit's PATH covers node/npx).
4. In plaud-bridge, add a webhook destination/route pointing at the runner,
   e.g. URL `http://<host>:8091/` with auth header
   `X-Runner-Token: <your token>`.

### Reaching the runner from the plaud-bridge container

The runner runs on the Docker **host**, so `127.0.0.1` inside the container
will not reach it. Options:

- Bind the runner to the compose network's gateway IP (find it with
  `docker network inspect <project>_default --format '{{(index .IPAM.Config 0).Gateway}}'`,
  e.g. `172.18.0.1`), and use `http://<gateway-ip>:8091/` as the webhook URL.
- Or add `extra_hosts: ["host.docker.internal:host-gateway"]` to the
  plaud-bridge service, bind the runner to `0.0.0.0` (token-guarded), and use
  `http://host.docker.internal:8091/`.
- Or bind to the host's LAN IP and use that.

Verify from inside the container:

```bash
docker exec plaud-bridge python -c \
  "import httpx; print(httpx.get('http://<ip>:8091/healthz').status_code)"
```

## Setup (container) — self-contained stack

`Dockerfile` builds a node:22-slim image with python3, `claude-code-acp`, and
`codex` preinstalled, running as uid 1000 (`node`, HOME=/home/node). It
expects a config mount at `/config` and your Claude auth (`~/.claude`)
mounted at the container user's HOME:

```yaml
services:
  plaud-bridge:
    # ... existing service ...
    environment:
      PB_WEBHOOK_URL: http://agent-runner:8091/
      PB_WEBHOOK_AUTH_HEADER: "X-Runner-Token: <token>"
      PB_ROUTER_BASE_URL: http://agent-runner:8091/v1
      PB_ROUTER_API_KEY: <token>

  agent-runner:
    build: ./contrib/agent-runner
    restart: unless-stopped
    volumes:
      - ./contrib/agent-runner/runner-config:/config          # config.toml here
      - ~/.claude:/home/node/.claude                          # Claude Code auth
      # - ~/.codex:/home/node/.codex                          # Codex auth, if used
      # - ~/notes:/notes                                      # workdirs your actions touch
```

Set `listen = "0.0.0.0:8091"` in the container's config.toml; the services
share the compose network, so plaud-bridge reaches it as
`http://agent-runner:8091` and nothing needs publishing to the host.

Trade-off: host systemd is the simplest auth story (the agent sees your real
HOME, files land directly on the host); the container makes the whole stack
one `docker compose up`, but the agent's file actions happen inside the
container unless you mount the workdirs you care about.

## Tests

```bash
python3 test_agent_runner.py
```

Covers auth rejection, template-substitution safety (hostile transcript stays
inert), queue-full 503, unknown-route fallback, timeout kill (both plain and
ACP jobs), and the ACP protocol itself — prompt/response, permission
approve/reject, model selection, malformed-line tolerance, and the chat shim
— against `fake_acp_agent.py`, a canned ndjson agent, so no real agent or
network is needed.

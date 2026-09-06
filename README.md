# Plaud Bridge Server

Self-hosted sync target for [Plaud](https://www.plaud.ai) recorders (Note Pro / NotePin S), used together with the [Plaud Bridge Android app](https://github.com/CHANGEME/plaud-bridge-android). Your recordings sync from the device to your phone to your own server, get transcribed by any OpenAI-compatible speech-to-text endpoint you choose, and land as JSON + markdown files you can automate against. No Plaud subscription required.

```
Plaud device ──BLE/WiFi──> Android app ──HTTPS──> plaud-bridge-server
                               │                        │
                        Plaud cloud              your STT endpoint
                       (auth handshake            (/v1/audio/transcriptions)
                          only, no audio)               │
                                                 transcripts: JSON + markdown
                                                        │
                                                 webhook → your automations
```

## What touches Plaud's cloud

Only device authentication. The Plaud Embedded SDK requires a signed user token from Plaud's partner API to complete the encrypted BLE handshake with the device. This server mints those tokens using your (free) developer credentials and hands them to the app. Plaud never receives your audio or transcripts. Where they *do* go is up to your configuration: point transcription and summaries at local endpoints and everything stays on your hardware; point them at hosted APIs (or configure a webhook) and audio/text flows to those services instead.

You need a free account at [portal.plaud.ai](https://portal.plaud.ai): create an **Embedded SDK Application** and copy its Client ID and Secret Key. The free tier covers 50 connected devices; the (paid) Plaud transcription API is not used at all.

## Quick start

```bash
git clone https://github.com/CHANGEME/plaud-bridge-server.git
cd plaud-bridge-server
cp .env.example .env
# edit .env: Plaud credentials, an auth token (openssl rand -hex 32),
# and your transcription endpoint
docker compose up -d --build
curl http://localhost:8090/api/v1/health
```

The container binds to `127.0.0.1:8090` by default. Expose it through a reverse proxy that terminates **HTTPS** — the app authenticates with a static bearer token, so plaintext HTTP on an untrusted network means credential theft. Set a request-body limit and rate limiting at the proxy too. Then install the Android app and point it at your server URL + auth token.

> **Security model:** a single bearer token grants full access — uploads, reads, deletes, and Plaud token minting. That is a deliberate simplification for a personal/self-hosted deployment. Don't share tokens across trust boundaries, rotate via the comma-separated `PB_AUTH_TOKENS`, and keep the service off the open internet unless it's behind TLS.

### Transcription

Two engines, selected with `PB_STT_ENGINE`:

**`local` (default)** — built-in [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CTranslate2). No external services; runs on CPU out of the box with the standard image, or on an NVIDIA GPU with `Dockerfile.cuda`. Pick any model with `PB_STT_MODEL` (`tiny` … `large-v3`, `distil-large-v3`, or any CTranslate2 repo id), tune `PB_STT_DEVICE`/`PB_STT_COMPUTE`. VAD silence-skipping is on by default and audio is decoded as a stream, so multi-hour files (Plaud hardware records up to ~5 h) work within bounded memory; `PB_STT_MAX_DURATION_S` caps accepted length.

**Speaker diarization** (multi-speaker labeling — segments and transcripts get `Speaker 1:` / `Speaker 2:` turns): set `PB_STT_DIARIZE=true` with the CUDA image (or install `requirements-diarization.txt`) and provide `PB_STT_HF_TOKEN` for a Hugging Face account that has accepted the [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1) terms.

**`openai`** — any external OpenAI-compatible `/v1/audio/transcriptions` endpoint ([speaches](https://github.com/speaches-ai/speaches), whisper.cpp server, hosted APIs). Set `PB_TRANSCRIBE_BASE_URL` (including `/v1`), optional `PB_TRANSCRIBE_API_KEY` and `PB_TRANSCRIBE_MODEL`.

### Benchmarking models on your hardware

```bash
docker compose exec plaud-bridge \
  python -m app.benchmark /data/recordings/<some-file>.mp3 \
  --models tiny,base,small,medium,distil-large-v3 [--device cuda] [--diarize]
```

Prints load time, transcription time, speed (audio seconds per wall-clock second), and — with `--reference ref.txt` — word error rate, so you can pick the best model your hardware sustains. `--json out.json` saves the results.

### GPU notes

Build with `docker compose build` after switching the service to `Dockerfile.cuda` (see the comment in `docker-compose.yml`) and grant GPU access (`gpus: all` or `runtime: nvidia`). PyPI CTranslate2 wheels need compute capability ≥ 6.1 (Pascal+); for older cards, build a custom wheel with `CT2_CUDA_ARCH_LIST=<your capability>` and drop it in `wheels-local/` — the CUDA image installs it over the PyPI wheel automatically.

## Web dashboard

The server root (`/`) serves a built-in dashboard: browse, search, and play recordings, read transcripts and AI summaries, re-transcribe, download, and delete. It unlocks with the same bearer token the app uses.

## AI summaries (optional)

Set `PB_SUMMARY_ENABLED=true` plus `PB_SUMMARY_BASE_URL` / `PB_SUMMARY_MODEL` (and `PB_SUMMARY_API_KEY` if needed) to run each transcript through any OpenAI-compatible chat endpoint — a local Ollama/llama.cpp/vLLM, LiteLLM, or a hosted API. The default prompt produces a title, summary, and action items; override it with `PB_SUMMARY_PROMPT`. Summaries appear in the dashboard, the markdown export, the webhook payload, and the transcript JSON.

## API

All endpoints under `/api/v1`. Every route except `/health` requires `Authorization: Bearer <token>` matching `PB_AUTH_TOKENS`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness (no auth) |
| GET | `/auth/check` | 204 if the token is valid |
| POST | `/plaud/user-token` | `{user_id, expires_in?}` → Plaud SDK user token |
| POST | `/recordings` | multipart upload: `file` + `metadata` JSON string |
| GET | `/recordings` | list (`limit`, `offset`, `status`) |
| GET | `/recordings/lookup?device_sn&session_id` | find one |
| GET | `/recordings/{id}` | metadata |
| GET | `/recordings/{id}/audio` | the audio file |
| GET | `/recordings/{id}/transcript` | transcript JSON; `409` while pending |
| POST | `/recordings/{id}/retranscribe` | requeue for the worker |
| DELETE | `/recordings/{id}` | remove recording + transcript |
| GET | `/stats` | counts, total duration, bytes |
| GET/POST | `/routes` | list / create AI routing routes |
| PUT/DELETE | `/routes/{id}` | update / delete a route |
| GET | `/router/status` | `{enabled, configured, model}` |
| GET | `/routing/log?limit=50` | recent router runs with their deliveries |
| GET | `/recordings/{id}/routing` | router runs + deliveries for one recording |
| POST | `/recordings/{id}/route` | rerun the router now (`409` if no transcript yet) |
| POST | `/deliveries/{id}/retry` | re-execute a delivery's action |

Upload `metadata` fields: `session_id` (int), `device_sn` (string), `started_at` (ISO-8601 UTC), `duration_s` (number), `source` (string). Duplicate uploads (same file hash, or same device+session) return `200 {"duplicate": true}` instead of creating a copy — the app can retry uploads safely.

Recording `status` lifecycle: `pending → transcribing → done` (or `failed` after `PB_TRANSCRIBE_MAX_ATTEMPTS`; `stored` if transcription is disabled).

## Automating on new transcripts

Two hooks, use either or both:

- **Webhook** — set `PB_WEBHOOK_URL`; each completed transcription POSTs `{event: "transcription.completed", recording: {...}, transcript: {language, text}}`. Optional static header via `PB_WEBHOOK_AUTH_HEADER` (`Name: value`).
- **Markdown export** — set `PB_MARKDOWN_EXPORT_DIR` (mount it in docker-compose). Each transcript is written as a standalone `.md` with YAML frontmatter (device, session, timestamps, language) — drop it in an Obsidian vault, a syncthing folder, or anywhere a file watcher can pick it up.

Raw data lives under `PB_DATA_DIR`: `recordings/YYYY/MM/<hash>_<name>.mp3` with a sibling `.transcript.json`, and a SQLite index at `plaud-bridge.sqlite3`.

## AI routing (optional)

Where the hooks above fire for *every* transcript, AI routing lets an LLM decide *which* automations each recording should trigger. You define **routes** — each one a name, a free-text description, and an action — and after every transcription (and summary) a router LLM call matches the transcript against the enabled routes. The description doubles as the routing criterion and the downstream instruction, e.g.:

> **Work meetings** — anything that sounds like a work meeting or standup. Log it verbatim and summarized.

Multiple routes can match one recording; zero matches is a normal outcome. Actions:

- **`webhook`** — POST the payload below to `action_config.url`, with an optional static header (`{"auth_header": "Name: value"}`).
- **`markdown`** — write a note (same frontmatter as the markdown export, plus `route:`) into `PB_MARKDOWN_EXPORT_DIR/<action_config.folder>/`. The folder must be a relative subpath of the export root.
- **`none`** — record the decision only (useful for auditing before wiring an action).

Enable with `PB_ROUTER_ENABLED=true` and point `PB_ROUTER_BASE_URL` / `PB_ROUTER_MODEL` (plus `PB_ROUTER_API_KEY` if needed) at any OpenAI-compatible chat endpoint; when unset they fall back to the `PB_SUMMARY_*` values, so a single configured LLM serves both features. `PB_ROUTER_MAX_CHARS` (default 4000) caps how much of the transcript the router sees. The legacy `PB_WEBHOOK_URL` hook is independent and keeps firing regardless of routing.

Routes are managed over the API (see the table above): `GET/POST /routes`, `PUT/DELETE /routes/{id}`. Every decision is recorded as a **router run** and every executed action as a **delivery**, inspectable via `GET /routing/log` and `GET /recordings/{id}/routing`; `POST /recordings/{id}/route` reruns the router for one recording and `POST /deliveries/{id}/retry` re-executes a failed delivery. Router failures never affect a recording's `done` status.

Webhook payload contract (stable — safe to build consumers against):

```json
{
  "event": "route.matched",
  "route": {"name": "Work meetings", "description": "anything that sounds like ..."},
  "recording": {
    "id": "abc123...", "device_sn": "881A...", "session_id": 1,
    "filename": "rec.mp3", "started_at": "2026-09-06T12:00:00Z",
    "duration_s": 123.4, "url": "/api/v1/recordings/abc123..."
  },
  "transcript": {"text": "full transcript ...", "summary": "AI summary or null", "language": "en"}
}
```

## Configuration reference

See [.env.example](.env.example) — every setting is an environment variable with a `PB_` prefix.

## Development & tests

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-stt.txt pytest
PB_DATA_DIR=./data PB_AUTH_TOKENS=dev uvicorn app.main:app --reload --port 8090

pytest -m "not integration"   # unit tests (fast, no models)
pytest                        # + integration tests (real whisper-tiny inference)
```

## Disclaimer

Not affiliated with or endorsed by PLAUD Inc. Uses Plaud's public [Embedded SDK / developer platform](https://docs.plaud.ai). Apache-2.0 licensed.

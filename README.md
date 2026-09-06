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

Only device authentication. The Plaud Embedded SDK requires a signed user token from Plaud's partner API to complete the encrypted BLE handshake with the device. This server mints those tokens using your (free) developer credentials and hands them to the app. Audio, transcripts, and metadata never leave your infrastructure.

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

Expose it with your reverse proxy of choice (HTTPS strongly recommended — the app authenticates with a bearer token). Then install the Android app and point it at your server URL + auth token.

### Transcription endpoint

Anything that speaks the OpenAI audio transcription API works, for example:

- [speaches](https://github.com/speaches-ai/speaches) (successor of faster-whisper-server) — local Whisper on CPU/GPU
- [whisper.cpp server](https://github.com/ggml-org/whisper.cpp) with `--convert` OpenAI-compat mode
- OpenAI's hosted `whisper-1` / `gpt-4o-transcribe` if you don't mind the cloud

Set `PB_TRANSCRIBE_BASE_URL` (including `/v1`), optional `PB_TRANSCRIBE_API_KEY`, and `PB_TRANSCRIBE_MODEL`. The worker asks for `verbose_json` (timestamps + segments) and falls back to plain `json` if the server rejects it.

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

Upload `metadata` fields: `session_id` (int), `device_sn` (string), `started_at` (ISO-8601 UTC), `duration_s` (number), `source` (string). Duplicate uploads (same file hash, or same device+session) return `200 {"duplicate": true}` instead of creating a copy — the app can retry uploads safely.

Recording `status` lifecycle: `pending → transcribing → done` (or `failed` after `PB_TRANSCRIBE_MAX_ATTEMPTS`; `stored` if transcription is disabled).

## Automating on new transcripts

Two hooks, use either or both:

- **Webhook** — set `PB_WEBHOOK_URL`; each completed transcription POSTs `{event: "transcription.completed", recording: {...}, transcript: {language, text}}`. Optional static header via `PB_WEBHOOK_AUTH_HEADER` (`Name: value`).
- **Markdown export** — set `PB_MARKDOWN_EXPORT_DIR` (mount it in docker-compose). Each transcript is written as a standalone `.md` with YAML frontmatter (device, session, timestamps, language) — drop it in an Obsidian vault, a syncthing folder, or anywhere a file watcher can pick it up.

Raw data lives under `PB_DATA_DIR`: `recordings/YYYY/MM/<hash>_<name>.mp3` with a sibling `.transcript.json`, and a SQLite index at `plaud-bridge.sqlite3`.

## Configuration reference

See [.env.example](.env.example) — every setting is an environment variable with a `PB_` prefix.

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
PB_DATA_DIR=./data PB_AUTH_TOKENS=dev uvicorn app.main:app --reload --port 8090
```

## Disclaimer

Not affiliated with or endorsed by PLAUD Inc. Uses Plaud's public [Embedded SDK / developer platform](https://docs.plaud.ai). Apache-2.0 licensed.

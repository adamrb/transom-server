"""UX overhaul API contracts (see /tmp/plaud-ux/CONTRACTS.md sections 1-7):
signed audio links + Range, speaker rename, automations preview, search
snippets + no_speech filter, friendly errors, routing-log fields, and the
summarizer prompt. No network: the router LLM is an httpx.MockTransport."""

import json
import os
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="pb-ux-test-")
os.environ.setdefault("PB_DATA_DIR", _TMP)
os.environ.setdefault("PB_AUTH_TOKENS", "test-token")
os.environ.setdefault("PB_TRANSCRIBE_ENABLED", "false")

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main as appmain
from app.config import Settings, settings as app_settings
from app.db import utcnow_iso
from app.formatting import apply_speaker_renames, segments_text, speaker_labels
from app.main import _snippet, app, friendly_error
from app.router import Router

AUTH = {"Authorization": "Bearer test-token"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "data_dir", tmp_path)
    monkeypatch.setattr(app_settings, "auth_tokens", ["test-token", "second-token"])
    monkeypatch.setattr(app_settings, "transcribe_enabled", False)
    monkeypatch.setattr(app_settings, "router_enabled", True)
    monkeypatch.setattr(app_settings, "router_base_url", "http://llm/v1")
    monkeypatch.setattr(app_settings, "router_api_key", None)
    monkeypatch.setattr(app_settings, "router_model", "router-model")
    monkeypatch.setattr(app_settings, "markdown_export_dir", tmp_path / "notes")
    with TestClient(app) as c:
        yield c


def upload(client, name="rec.mp3", content=b"0123456789abcdef", metadata="{}") -> str:
    r = client.post("/api/v1/recordings", headers=AUTH,
                    files={"file": (name, content)}, data={"metadata": metadata})
    assert r.status_code == 201, r.text
    return r.json()["id"]


SEGMENTS = [
    {"start": 0.0, "end": 1.0, "text": "hello there", "speaker": "Speaker 1"},
    {"start": 1.0, "end": 2.0, "text": "hi, how are you", "speaker": "Speaker 2"},
    {"start": 2.0, "end": 3.0, "text": "fine thanks", "speaker": "Speaker 1"},
]


def finish_transcript(client, rec_id: str, tmp_path, segments=SEGMENTS, marks=(1.5,), **extra) -> str:
    """Write a diarized transcript document for `rec_id` and mark the row done
    (the fake pipeline: no engine in tests)."""
    from app.formatting import build_paragraphs
    from app.highlights import build_highlights

    text = segments_text(segments)
    highlights = build_highlights(list(marks), segments, 3.0) if marks else []
    doc = {"recording_id": rec_id, "text": text, "segments": segments, "duration_s": 3.0,
           "language": "en", "highlights": highlights, "marks": list(marks),
           "paragraphs": build_paragraphs(segments, highlights), **extra}
    rec = appmain.store.get(rec_id)
    path = tmp_path / f"{rec_id}.transcript.json"
    path.write_text(json.dumps(doc))
    appmain.store.update(rec_id, status="done", transcript_path=str(path), transcript_text=text,
                         marks=json.dumps(list(marks)), title=extra.get("title"), summary=extra.get("summary"))
    return text


# ── 1. signed audio links + Range ────────────────────────────────────────────


def test_audio_link_streams_without_a_header(client):
    rec_id = upload(client, content=b"fake-mp3-bytes-here")
    assert client.post(f"/api/v1/recordings/{rec_id}/audio-link").status_code == 401
    assert client.post("/api/v1/recordings/nope/audio-link", headers=AUTH).status_code == 404

    r = client.post(f"/api/v1/recordings/{rec_id}/audio-link", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["url"].startswith(f"/api/v1/recordings/{rec_id}/audio?sig=")
    assert "&exp=" in body["url"]
    now = int(time.time())
    assert now + 3500 <= body["expires_at"] <= now + 3600 + 5

    r = client.get(body["url"])  # no Authorization header at all
    assert r.status_code == 200 and r.content == b"fake-mp3-bytes-here"
    assert r.headers["accept-ranges"] == "bytes"
    assert r.headers["content-type"].startswith("audio/mpeg")
    # The bearer header keeps working unchanged (the Android app).
    assert client.get(f"/api/v1/recordings/{rec_id}/audio", headers=AUTH).status_code == 200
    # A link signed with any configured token verifies (token rotation).
    exp = now + 600
    sig2 = appmain._audio_link_sig(rec_id, exp, "second-token")
    assert client.get(f"/api/v1/recordings/{rec_id}/audio?sig={sig2}&exp={exp}").status_code == 200


def test_audio_link_expired_tampered_or_missing(client):
    rec_id = upload(client)
    other = upload(client, name="other.mp3", content=b"other-bytes")
    past = int(time.time()) - 5
    sig = appmain._audio_link_sig(rec_id, past, "test-token")
    r = client.get(f"/api/v1/recordings/{rec_id}/audio?sig={sig}&exp={past}")
    assert r.status_code == 403 and "expired" in r.json()["detail"]

    exp = int(time.time()) + 600
    good = appmain._audio_link_sig(rec_id, exp, "test-token")
    # Tampered signature, tampered expiry, wrong recording, wrong key.
    flipped = good[:-1] + ("0" if good[-1] != "0" else "1")
    assert client.get(f"/api/v1/recordings/{rec_id}/audio?sig={flipped}&exp={exp}").status_code == 403
    assert client.get(f"/api/v1/recordings/{rec_id}/audio?sig={good}&exp={exp + 1}").status_code == 403
    assert client.get(f"/api/v1/recordings/{other}/audio?sig={good}&exp={exp}").status_code == 403
    bad_key = appmain._audio_link_sig(rec_id, exp, "not-a-server-token")
    assert client.get(f"/api/v1/recordings/{rec_id}/audio?sig={bad_key}&exp={exp}").status_code == 403
    assert client.get(f"/api/v1/recordings/{rec_id}/audio?sig={good}&exp=soon").status_code == 403
    # An expiry further out than the server ever issues is refused too.
    far = int(time.time()) + 7 * 24 * 3600
    assert client.get(f"/api/v1/recordings/{rec_id}/audio?sig={appmain._audio_link_sig(rec_id, far, 'test-token')}&exp={far}").status_code == 403
    # No credentials of any kind: the usual 401.
    r = client.get(f"/api/v1/recordings/{rec_id}/audio")
    assert r.status_code == 401 and r.headers.get("www-authenticate") == "Bearer"
    # A signed link only opens the audio, nothing else.
    assert client.get(f"/api/v1/recordings/{rec_id}?sig={good}&exp={exp}").status_code == 401
    assert client.get(f"/api/v1/recordings/{rec_id}/transcript?sig={good}&exp={exp}").status_code == 401


def test_audio_range_requests(client):
    rec_id = upload(client, name="clip.wav", content=b"0123456789abcdef")
    r = client.get(f"/api/v1/recordings/{rec_id}/audio", headers={**AUTH, "Range": "bytes=2-5"})
    assert r.status_code == 206
    assert r.content == b"2345"
    assert r.headers["content-range"] == "bytes 2-5/16"
    assert r.headers["content-length"] == "4"
    assert r.headers["accept-ranges"] == "bytes"
    assert r.headers["content-type"].startswith("audio/")  # .wav -> audio/x-wav or audio/wav
    # Open-ended range (what players send to resume).
    r = client.get(f"/api/v1/recordings/{rec_id}/audio", headers={**AUTH, "Range": "bytes=12-"})
    assert r.status_code == 206 and r.content == b"cdef"
    assert r.headers["content-range"] == "bytes 12-15/16"
    # Unsatisfiable start.
    r = client.get(f"/api/v1/recordings/{rec_id}/audio", headers={**AUTH, "Range": "bytes=99-120"})
    assert r.status_code == 416 and r.headers["content-range"] == "bytes */16"
    # Range works over a signed link as well (the dashboard's <audio> seeks).
    url = client.post(f"/api/v1/recordings/{rec_id}/audio-link", headers=AUTH).json()["url"]
    r = client.get(url, headers={"Range": "bytes=0-3"})
    assert r.status_code == 206 and r.content == b"0123"


# ── 2. speaker rename ────────────────────────────────────────────────────────


def test_transcript_lists_speakers_in_first_appearance_order(client, tmp_path):
    rec_id = upload(client)
    finish_transcript(client, rec_id, tmp_path)
    t = client.get(f"/api/v1/recordings/{rec_id}/transcript", headers=AUTH).json()
    assert t["speakers"] == ["Speaker 1", "Speaker 2"]
    assert t["speaker_names"] == {}
    # Pre-reader-layout documents (no paragraphs) still get a speaker list.
    path = appmain.store.get(rec_id)["transcript_path"]
    doc = json.loads(open(path).read()); doc.pop("paragraphs"); open(path, "w").write(json.dumps(doc))
    t = client.get(f"/api/v1/recordings/{rec_id}/transcript", headers=AUTH).json()
    assert t["speakers"] == ["Speaker 1", "Speaker 2"] and t["paragraphs"]


def test_rename_speakers_persists_everywhere_and_survives_refresh(client, tmp_path):
    rec_id = upload(client, metadata='{"started_at": "2026-09-06T12:00:00Z"}')
    finish_transcript(client, rec_id, tmp_path, title="Chat")
    r = client.patch(f"/api/v1/recordings/{rec_id}/speakers", headers=AUTH,
                     json={"renames": {"Speaker 1": " Alex ", "Speaker 2": "Morgan", "Speaker 9": "Nobody"}})
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["speakers"] == ["Alex", "Morgan"]
    assert [p["speaker"] for p in t["paragraphs"]] == ["Alex", "Morgan", "Alex"]
    assert [s["speaker"] for s in t["segments"]] == ["Alex", "Morgan", "Alex"]
    assert t["text"] == "Alex: hello there\nMorgan: hi, how are you\nAlex: fine thanks"
    assert t["speaker_names"] == {"Speaker 1": "Alex", "Speaker 2": "Morgan"}
    assert t["highlights"][0]["speakers"] == ["Alex", "Morgan"]
    # Same shape as GET /transcript, and persisted on disk + in the row.
    assert client.get(f"/api/v1/recordings/{rec_id}/transcript", headers=AUTH).json() == t
    rec = appmain.store.get(rec_id)
    assert rec["transcript_text"].startswith("Alex: hello there")
    on_disk = json.loads(open(rec["transcript_path"]).read())
    assert on_disk["speaker_names"] == {"Speaker 1": "Alex", "Speaker 2": "Morgan"}
    # The exported note was rewritten with the names.
    notes = list((tmp_path / "notes").glob("*.md"))
    assert len(notes) == 1
    md = notes[0].read_text()
    assert "**Alex:**" in md and "**Morgan:**" in md and "Speaker 1" not in md
    assert "## Highlights" in md
    # The list search and the list preview see the new names too.
    items = client.get("/api/v1/recordings", headers=AUTH, params={"q": "Morgan"}).json()["recordings"]
    assert [i["id"] for i in items] == [rec_id]

    # Highlights refresh (PATCH /marks re-derives paragraphs + highlights) keeps the names.
    r = client.patch(f"/api/v1/recordings/{rec_id}/marks", headers=AUTH, json={"marks": [0.5, 2.5]})
    assert r.status_code == 200 and len(r.json()["highlights"]) == 2
    t = client.get(f"/api/v1/recordings/{rec_id}/transcript", headers=AUTH).json()
    assert t["speakers"] == ["Alex", "Morgan"]
    assert [p["speaker"] for p in t["paragraphs"]] == ["Alex", "Morgan", "Alex"]
    assert t["speaker_names"] == {"Speaker 1": "Alex", "Speaker 2": "Morgan"}
    assert "**Alex:**" in notes[0].read_text()

    # Renaming a renamed speaker updates the original's mapping, not a chain.
    r = client.patch(f"/api/v1/recordings/{rec_id}/speakers", headers=AUTH, json={"renames": {"Alex": "Alex R"}})
    assert r.json()["speaker_names"] == {"Speaker 1": "Alex R", "Speaker 2": "Morgan"}
    assert r.json()["speakers"] == ["Alex R", "Morgan"]
    # Renaming back to the engine label drops the entry.
    r = client.patch(f"/api/v1/recordings/{rec_id}/speakers", headers=AUTH, json={"renames": {"Alex R": "Speaker 1"}})
    assert r.json()["speaker_names"] == {"Speaker 2": "Morgan"}
    # Swapping two labels in one request works (single pass, no chaining).
    r = client.patch(f"/api/v1/recordings/{rec_id}/speakers", headers=AUTH,
                     json={"renames": {"Speaker 1": "Morgan", "Morgan": "Speaker 1"}})
    t = r.json()
    assert [p["speaker"] for p in t["paragraphs"]] == ["Morgan", "Speaker 1", "Morgan"]
    assert t["speaker_names"] == {"Speaker 1": "Morgan", "Speaker 2": "Speaker 1"}


def test_rename_speakers_validation(client, tmp_path):
    rec_id = upload(client)
    # Not transcribed yet -> 409 with a sentence.
    r = client.patch(f"/api/v1/recordings/{rec_id}/speakers", headers=AUTH, json={"renames": {"Speaker 1": "A"}})
    assert r.status_code == 409 and r.json()["detail"].endswith(".")
    finish_transcript(client, rec_id, tmp_path)
    for bad in ("", "   ", "\t"):
        r = client.patch(f"/api/v1/recordings/{rec_id}/speakers", headers=AUTH, json={"renames": {"Speaker 1": bad}})
        assert r.status_code == 422, bad
    assert client.patch(f"/api/v1/recordings/{rec_id}/speakers", headers=AUTH,
                        json={"renames": {"Speaker 1": "x" * 65}}).status_code == 422
    assert client.patch(f"/api/v1/recordings/{rec_id}/speakers", headers=AUTH, json={"renames": {}}).status_code == 422
    assert client.patch(f"/api/v1/recordings/{rec_id}/speakers", headers=AUTH, json={"names": {}}).status_code == 422
    assert client.patch("/api/v1/recordings/nope/speakers", headers=AUTH, json={"renames": {"a": "b"}}).status_code == 404
    assert client.patch(f"/api/v1/recordings/{rec_id}/speakers", json={"renames": {"a": "b"}}).status_code == 401
    # Unknown labels only: nothing changes, still 200 with the transcript.
    r = client.patch(f"/api/v1/recordings/{rec_id}/speakers", headers=AUTH, json={"renames": {"Speaker 7": "Zed"}})
    assert r.status_code == 200 and r.json()["speakers"] == ["Speaker 1", "Speaker 2"]
    assert r.json()["speaker_names"] == {}


def test_route_payload_reflects_renamed_speakers(client, tmp_path):
    rec_id = upload(client)
    finish_transcript(client, rec_id, tmp_path)
    client.patch(f"/api/v1/recordings/{rec_id}/speakers", headers=AUTH, json={"renames": {"Speaker 1": "Alex"}})
    route = {"id": "r1", "name": "work", "description": "d", "action_type": "webhook", "action_config": "{}"}
    payload = Router(app_settings, appmain.store).build_payload(route, appmain.store.get(rec_id))
    assert payload["transcript"]["text"].startswith("Alex: hello there")
    assert payload["transcript"]["paragraphs"][0]["speaker"] == "Alex"
    assert payload["transcript"]["highlights"][0]["speakers"] == ["Alex", "Speaker 2"]


def test_apply_speaker_renames_unit():
    doc = {"segments": [{"text": "a", "speaker": "S1"}, {"text": "b", "speaker": "S2"}, {"text": "c"}],
           "paragraphs": [{"speaker": "S1", "text": "a"}, {"speaker": "S2", "text": "b"}, {"speaker": "Unknown speaker", "text": "c"}]}
    assert speaker_labels(doc) == ["S1", "S2", "Unknown speaker"]
    assert apply_speaker_renames(doc, {"Nope": "X", "S1": "S1"}) is False
    assert "speaker_names" not in doc
    assert apply_speaker_renames(doc, {"S1": "Alex", "Unknown speaker": "Guest"}) is True
    assert doc["speaker_names"] == {"S1": "Alex", "Unknown speaker": "Guest"}
    # The derived "Unknown speaker" label reaches the unlabeled segment itself, so
    # the flat text and any later re-derivation carry the name.
    assert doc["text"] == "Alex: a\nS2: b\nGuest: c"
    assert doc["segments"][2]["speaker"] == "Guest" and doc["paragraphs"][2]["speaker"] == "Guest"
    from app.formatting import build_paragraphs
    assert [p["speaker"] for p in build_paragraphs(doc["segments"])] == ["Alex", "S2", "Guest"]
    # Undiarized documents: no labels in the text, nothing to rename (not even "Unknown speaker").
    plain = {"segments": [{"text": "just words"}], "paragraphs": [{"speaker": None, "text": "just words"}]}
    assert apply_speaker_renames(plain, {"Speaker 1": "A", "Unknown speaker": "B"}) is False
    assert segments_text(plain["segments"]) == "just words"


def test_apply_speaker_renames_merged_names_move_together():
    """Two engine speakers given the same name are one person to the user:
    renaming that name later must update every original behind it."""
    doc = {"segments": [{"text": "a", "speaker": "S1"}, {"text": "b", "speaker": "S2"}, {"text": "c", "speaker": "S3"}]}
    assert apply_speaker_renames(doc, {"S1": "Alex", "S2": "Alex"})
    assert doc["speaker_names"] == {"S1": "Alex", "S2": "Alex"}
    assert apply_speaker_renames(doc, {"Alex": "Alex R"})
    assert doc["speaker_names"] == {"S1": "Alex R", "S2": "Alex R"}
    assert [s["speaker"] for s in doc["segments"]] == ["Alex R", "Alex R", "S3"]
    # Back to their engine labels: the entries go away rather than mapping to themselves.
    assert apply_speaker_renames(doc, {"Alex R": "S1"})
    assert doc["speaker_names"] == {"S2": "S1"}
    assert [s["speaker"] for s in doc["segments"]] == ["S1", "S1", "S3"]


# ── 3. automations preview ───────────────────────────────────────────────────


def _llm_transport(replies: list[str]):
    seen: list[dict] = []
    replies = list(replies)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "llm":
            seen.append(json.loads(request.content))
            return httpx.Response(200, json={"choices": [{"message": {"content": replies.pop(0)}}]})
        raise AssertionError(f"unexpected request to {request.url}")  # a preview must deliver nothing

    return httpx.MockTransport(handler), seen


def _count(table: str) -> int:
    with appmain.store._lock:
        return appmain.store._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_route_preview_decides_without_side_effects(client, tmp_path, monkeypatch):
    r = client.post("/api/v1/routes", headers=AUTH, json={
        "name": "Work meetings", "description": "work", "action_type": "webhook",
        "action_config": {"url": "http://hook/x"}})
    route_id = r.json()["id"]
    client.post("/api/v1/routes", headers=AUTH, json={
        "name": "Inbox", "description": "inbox", "action_type": "none", "action_config": {}})
    rec_id = upload(client)
    finish_transcript(client, rec_id, tmp_path)
    transport, seen = _llm_transport(['{"routes": [{"name": "Work meetings", "reason": "standup talk"}, "Inbox"]}'])
    appmain.router_engine.transport = transport

    r = client.post(f"/api/v1/recordings/{rec_id}/route/preview", headers=AUTH, json={"instructions": "file as work"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["route_id"] == route_id and body["route_name"] == "Work meetings"
    assert body["reason"] == "standup talk" and body["model"] == "router-model"
    assert [m["route_name"] for m in body["matches"]] == ["Work meetings", "Inbox"]
    assert "file as work" in seen[0]["messages"][1]["content"]
    # Nothing recorded, nothing delivered.
    assert _count("router_runs") == 0 and _count("deliveries") == 0
    assert client.get("/api/v1/routing/log", headers=AUTH).json()["runs"] == []
    assert client.get(f"/api/v1/recordings/{rec_id}/routing", headers=AUTH).json() == {"runs": [], "deliveries": []}

    # Nothing matched.
    appmain.router_engine.transport, _ = _llm_transport(['{"routes": []}'])
    body = client.post(f"/api/v1/recordings/{rec_id}/route/preview", headers=AUTH).json()
    assert body == {"route_id": None, "route_name": None, "reason": None, "model": "router-model", "matches": []}

    # A broken model answer is a plain sentence, not a stack trace.
    appmain.router_engine.transport, _ = _llm_transport(["garbage", "still garbage"])
    r = client.post(f"/api/v1/recordings/{rec_id}/route/preview", headers=AUTH)
    assert r.status_code == 502 and r.json()["detail"] == "Couldn't run automations. Try again."
    assert _count("router_runs") == 0


def test_route_preview_conflicts(client, tmp_path, monkeypatch):
    rec_id = upload(client)
    r = client.post(f"/api/v1/recordings/{rec_id}/route/preview", headers=AUTH)
    assert r.status_code == 409 and r.json()["detail"] == "This recording has no transcript yet."
    assert client.post("/api/v1/recordings/nope/route/preview", headers=AUTH).status_code == 404
    assert client.post(f"/api/v1/recordings/{rec_id}/route/preview").status_code == 401
    finish_transcript(client, rec_id, tmp_path)
    # No enabled routes: a valid empty answer, no model call.
    appmain.router_engine.transport, seen = _llm_transport([])
    r = client.post(f"/api/v1/recordings/{rec_id}/route/preview", headers=AUTH)
    assert r.status_code == 200 and r.json()["route_id"] is None and seen == []
    monkeypatch.setattr(app_settings, "router_enabled", False)
    r = client.post(f"/api/v1/recordings/{rec_id}/route/preview", headers=AUTH)
    assert r.status_code == 409 and r.json()["detail"] == "Automations are turned off on the server"
    monkeypatch.setattr(app_settings, "router_enabled", True)
    monkeypatch.setattr(app_settings, "router_base_url", None)
    r = client.post(f"/api/v1/recordings/{rec_id}/route/preview", headers=AUTH)
    assert r.status_code == 409 and "not set up" in r.json()["detail"]
    assert client.post(f"/api/v1/recordings/{rec_id}/route/preview", headers=AUTH,
                       json={"instructions": "x" * 2001}).status_code == 422


# ── 4. search snippets + no_speech filter ────────────────────────────────────


def test_snippet_unit():
    assert _snippet("", "x") is None and _snippet("abc", "") is None
    assert _snippet("short text here", "TEXT") == "short text here"
    assert _snippet("no hit here", "zzz") is None
    words = " ".join(f"w{i}" for i in range(200))
    s = _snippet(words + " needle " + words, "Needle")
    assert "needle" in s and s.startswith("…") and s.endswith("…")
    assert 120 <= len(s) <= 165
    assert not s[1:-1].startswith(" ") and " w" in s  # cut on word boundaries
    # Hit at the start: no leading ellipsis; at the end: no trailing one.
    assert _snippet("needle " + words, "needle").startswith("needle ")
    assert _snippet(words + " needle", "needle").endswith(" needle")
    # Whitespace (newlines) is flattened so the snippet is one line.
    assert "\n" not in _snippet("a\nb\n" + words + "\nneedle\n" + words, "needle")


def test_list_search_snippets_and_no_speech_filter(client, tmp_path):
    long_text = " ".join(f"word{i}" for i in range(150)) + " the budget meeting ran long " + " ".join(f"tail{i}" for i in range(150))
    a = upload(client, name="a.mp3", content=b"a-bytes")
    finish_transcript(client, a, tmp_path, segments=[{"start": 0, "end": 1, "text": long_text}], marks=(),
                      title="Dentist call", summary="Rescheduled to Friday.")
    b = upload(client, name="b.mp3", content=b"b-bytes")
    finish_transcript(client, b, tmp_path, segments=[{"start": 0, "end": 1, "text": "nothing about money"}], marks=(),
                      title="Budget planning", summary="Numbers.")
    silent = upload(client, name="silent.mp3", content=b"s-bytes")
    finish_transcript(client, silent, tmp_path, segments=[], marks=())
    pending = upload(client, name="p.mp3", content=b"p-bytes")

    items = client.get("/api/v1/recordings", headers=AUTH).json()["recordings"]
    assert all(i["match_field"] is None and i["match_snippet"] is None for i in items)

    items = client.get("/api/v1/recordings", headers=AUTH, params={"q": "budget"}).json()["recordings"]
    by_id = {i["id"]: i for i in items}
    assert set(by_id) == {a, b}
    assert by_id[b]["match_field"] == "title" and by_id[b]["match_snippet"] == "Budget planning"
    assert by_id[a]["match_field"] == "transcript"
    snip = by_id[a]["match_snippet"]
    assert "budget meeting" in snip and snip.startswith("…") and snip.endswith("…") and len(snip) <= 165
    assert "transcript_text" not in by_id[a]

    items = client.get("/api/v1/recordings", headers=AUTH, params={"q": "friday"}).json()["recordings"]
    assert [i["match_field"] for i in items] == ["summary"] and items[0]["match_snippet"] == "Rescheduled to Friday."
    # File-name-only hits read as a title match (that is what the row shows).
    items = client.get("/api/v1/recordings", headers=AUTH, params={"q": "silent.mp"}).json()["recordings"]
    assert [(i["id"], i["match_field"], i["match_snippet"]) for i in items] == [(silent, "title", "silent.mp3")]

    items = client.get("/api/v1/recordings", headers=AUTH, params={"status": "no_speech"}).json()["recordings"]
    assert [i["id"] for i in items] == [silent] and items[0]["no_speech"] is True
    items = client.get("/api/v1/recordings", headers=AUTH, params={"status": "done"}).json()["recordings"]
    assert {i["id"] for i in items} == {a, b, silent}
    assert pending not in {i["id"] for i in items}
    # A transcript of only whitespace (tabs, newlines) is no speech to the filter
    # too, matching what the row itself reports.
    appmain.store.update(silent, transcript_text="\n\t \r\n")
    items = client.get("/api/v1/recordings", headers=AUTH, params={"status": "no_speech"}).json()["recordings"]
    assert [i["id"] for i in items] == [silent] and items[0]["no_speech"] is True


def test_list_search_treats_like_metacharacters_literally(client, tmp_path):
    a = upload(client, name="a.mp3", content=b"a-bytes")
    finish_transcript(client, a, tmp_path, segments=[{"start": 0, "end": 1, "text": "we hit 100% of plan"}], marks=())
    b = upload(client, name="b.mp3", content=b"b-bytes")
    finish_transcript(client, b, tmp_path, segments=[{"start": 0, "end": 1, "text": "we hit 100 of plan"}], marks=())
    c = upload(client, name="c.mp3", content=b"c-bytes")
    finish_transcript(client, c, tmp_path, segments=[{"start": 0, "end": 1, "text": "use snake_case names"}], marks=())

    items = client.get("/api/v1/recordings", headers=AUTH, params={"q": "100%"}).json()["recordings"]
    assert [(i["id"], i["match_field"]) for i in items] == [(a, "transcript")]
    assert "100%" in items[0]["match_snippet"]
    items = client.get("/api/v1/recordings", headers=AUTH, params={"q": "%"}).json()["recordings"]
    assert [i["id"] for i in items] == [a]
    items = client.get("/api/v1/recordings", headers=AUTH, params={"q": "snake_case"}).json()["recordings"]
    assert [i["id"] for i in items] == [c]
    # "_" is a literal underscore, not "any one character".
    assert client.get("/api/v1/recordings", headers=AUTH, params={"q": "snake_ase"}).json()["recordings"] == []
    items = client.get("/api/v1/recordings", headers=AUTH, params={"q": "\\"}).json()["recordings"]
    assert items == []


# ── 5. friendly errors ───────────────────────────────────────────────────────


@pytest.mark.parametrize("raw, sentence", [
    (None, None), ("", None), ("   ", None),
    ("whisper transcription failed: RuntimeError('boom')", "Transcription failed."),
    ("audio is 5.2 h, over the 5.0 h limit (PB_STT_MAX_DURATION_S)", "The recording is too long to transcribe."),
    ("no audio decoded from /data/x.mp3", "Couldn't read the audio file."),
    ("[Errno 2] No such file or directory: '/data/recordings/x.mp3'", "Couldn't read the audio file."),
    ("diarization worker exited unexpectedly", "Couldn't identify speakers."),
    ("endpoint returned 502: upstream", "Couldn't reach the transcription service."),
    ("All connection attempts failed", "Couldn't reach the transcription service."),
    ("ReadTimeout: timed out", "Transcription took too long and was stopped."),
    ("faster-whisper is not installed — install requirements-stt.txt", "Transcription isn't set up on the server."),
    ("CUDA out of memory", "The transcription engine ran out of resources."),
    ("summarization failed", "Summary failed, transcript is ready."),
])
def test_friendly_error_mapping(raw, sentence):
    assert friendly_error(raw) == sentence


def test_public_recording_splits_error_and_error_detail():
    from app.main import _public
    raw = "whisper transcription failed: RuntimeError('boom')"
    pub = _public(dict(id="r", status="failed", transcript_text=None, marks=None, stage=None, progress=None, error=raw))
    assert pub["error"] == "Transcription failed." and pub["error_detail"] == raw
    ok = _public(dict(id="r", status="done", transcript_text="hi", marks=None, stage=None, progress=None, error=None))
    assert ok["error"] is None and ok["error_detail"] is None


def test_failed_recording_shows_friendly_error_on_the_api(client):
    rec_id = upload(client)
    appmain.store.update(rec_id, status="failed", error="no audio decoded from x.mp3")
    detail = client.get(f"/api/v1/recordings/{rec_id}", headers=AUTH).json()
    assert detail["error"] == "Couldn't read the audio file." and detail["error_detail"] == "no audio decoded from x.mp3"
    row = client.get("/api/v1/recordings", headers=AUTH, params={"status": "failed"}).json()["recordings"][0]
    assert row["error"] == "Couldn't read the audio file."
    # 4xx details are sentences, never status words.
    r = client.get(f"/api/v1/recordings/{rec_id}/transcript", headers=AUTH)
    assert r.status_code == 409 and r.json()["detail"] == "The transcript isn't ready yet."
    r = client.get("/api/v1/recordings/nope", headers=AUTH)
    assert r.status_code == 404 and r.json()["detail"] == "Recording not found."


# ── 6. routing log entries name the recording ────────────────────────────────


def test_routing_log_names_recordings_and_flags_deleted_ones(client, tmp_path):
    client.post("/api/v1/routes", headers=AUTH, json={
        "name": "Inbox", "description": "d", "action_type": "none", "action_config": {}})
    rec_id = upload(client, metadata='{"started_at": "2026-09-06T12:00:00Z"}')
    finish_transcript(client, rec_id, tmp_path, title="Dentist call")
    appmain.router_engine.transport, _ = _llm_transport(['{"routes": ["Inbox"]}'])
    assert client.post(f"/api/v1/recordings/{rec_id}/route", headers=AUTH).status_code == 200
    # A run whose recording is gone (pre-cascade databases): flagged, not crashed.
    appmain.store.insert_router_run(recording_id="deadbeef", created_at="2020-01-01T00:00:00Z",
                                    model="m", decision='{"routes": []}', error=None)
    untitled = upload(client, name="memo.mp3", content=b"memo-bytes")
    finish_transcript(client, untitled, tmp_path)
    assert client.post(f"/api/v1/recordings/{untitled}/route", headers=AUTH).status_code == 200

    runs = client.get("/api/v1/routing/log", headers=AUTH).json()["runs"]
    by_rec = {r["recording_id"]: r for r in runs}
    assert len(runs) == 3
    titled = by_rec[rec_id]
    assert titled["recording_title"] == "Dentist call" and titled["recording_deleted"] is False
    assert titled["recorded_at"] == "2026-09-06T12:00:00Z"
    gone = by_rec["deadbeef"]
    assert gone["recording_title"] is None and gone["recording_deleted"] is True and gone["recorded_at"] is None
    assert gone["recording"] is None
    plain = by_rec[untitled]
    assert plain["recording_title"] is None and plain["recording_deleted"] is False
    assert plain["recorded_at"] == appmain.store.get(untitled)["uploaded_at"]  # no started_at: upload time


# ── 7. summarizer prompt ─────────────────────────────────────────────────────


def test_summary_prompt_forbids_heading_and_empty_sections(monkeypatch):
    monkeypatch.delenv("PB_SUMMARY_PROMPT", raising=False)
    prompt = Settings().summary_prompt
    assert "Title: <title>" in prompt  # the title line stays (it is split off server-side)
    assert "do not start it with a 'Summary' heading" in prompt
    assert "never repeat the title" in prompt
    assert "leave the section out entirely" in prompt
    assert "never write 'No action items'" in prompt
    assert "do not write a Highlights section" in prompt

"""API tests. Run with: pytest

Uses a temp data dir and no transcription endpoint configured, so uploads
settle in the 'stored' state (worker skips transcription).
"""

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="pb-test-")
os.environ.update(
    PB_DATA_DIR=_TMP,
    PB_AUTH_TOKENS="test-token-1,test-token-2",
    PB_TRANSCRIBE_ENABLED="false",
    PB_MAX_UPLOAD_MB="1",
)

import pytest
from fastapi.testclient import TestClient

from app.main import app

AUTH = {"Authorization": "Bearer test-token-1"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health_is_public(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_auth_required(client):
    assert client.get("/api/v1/recordings").status_code == 401
    assert client.get("/api/v1/stats").status_code == 401
    r = client.get("/api/v1/auth/check")
    assert r.status_code == 401
    assert r.headers.get("www-authenticate") == "Bearer"


def test_auth_rejects_bad_token(client):
    r = client.get("/api/v1/auth/check", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


def test_auth_accepts_any_configured_token(client):
    for tok in ("test-token-1", "test-token-2"):
        r = client.get("/api/v1/auth/check", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 204


def test_auth_scheme_case_insensitive(client):
    r = client.get("/api/v1/auth/check", headers={"Authorization": "bearer test-token-1"})
    assert r.status_code == 204


def test_unauthenticated_upload_rejected_without_parsing(client):
    r = client.post("/api/v1/recordings", files={"file": ("a.mp3", b"x" * 100)})
    assert r.status_code == 401


def test_upload_dedupe_and_lifecycle(client):
    meta = '{"session_id": 42, "device_sn": "881TEST", "duration_s": 1.5, "source": "test"}'
    r = client.post(
        "/api/v1/recordings", headers=AUTH,
        files={"file": ("rec.mp3", b"fake-audio-bytes")}, data={"metadata": meta},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["duplicate"] is False
    rec_id = body["id"]

    # Same bytes -> duplicate by hash
    r = client.post(
        "/api/v1/recordings", headers=AUTH,
        files={"file": ("rec.mp3", b"fake-audio-bytes")}, data={"metadata": "{}"},
    )
    assert r.status_code == 200 and r.json()["duplicate"] is True

    # Different bytes, same device+session -> duplicate by session
    r = client.post(
        "/api/v1/recordings", headers=AUTH,
        files={"file": ("rec.mp3", b"other-bytes")}, data={"metadata": meta},
    )
    assert r.status_code == 200 and r.json()["duplicate"] is True

    r = client.get("/api/v1/recordings/lookup", headers=AUTH,
                   params={"device_sn": "881TEST", "session_id": 42})
    assert r.status_code == 200 and r.json()["id"] == rec_id
    assert "audio_path" not in r.json()

    # Transcript not ready (no STT configured -> stored)
    r = client.get(f"/api/v1/recordings/{rec_id}/transcript", headers=AUTH)
    assert r.status_code == 409

    r = client.get(f"/api/v1/recordings/{rec_id}/audio", headers=AUTH)
    assert r.status_code == 200 and r.content == b"fake-audio-bytes"

    r = client.delete(f"/api/v1/recordings/{rec_id}", headers=AUTH)
    assert r.status_code == 204
    assert client.get(f"/api/v1/recordings/{rec_id}", headers=AUTH).status_code == 404


def test_title_exposed_on_list_and_detail(client):
    """The Android app and dashboard read `title` from the API; it must be
    present (null until summarization fills it) on both list and detail."""
    r = client.post(
        "/api/v1/recordings", headers=AUTH,
        files={"file": ("titled.mp3", b"title-test-bytes")}, data={"metadata": "{}"},
    )
    assert r.status_code == 201
    rec_id = r.json()["id"]
    try:
        detail = client.get(f"/api/v1/recordings/{rec_id}", headers=AUTH).json()
        assert "title" in detail and detail["title"] is None
        items = client.get("/api/v1/recordings", headers=AUTH).json()["recordings"]
        mine = next(i for i in items if i["id"] == rec_id)
        assert "title" in mine
    finally:
        client.delete(f"/api/v1/recordings/{rec_id}", headers=AUTH)


def test_upload_validation(client):
    def up(metadata, content=b"zz"):
        return client.post(
            "/api/v1/recordings", headers=AUTH,
            files={"file": ("a.mp3", content)}, data={"metadata": metadata},
        )

    assert up("not json").status_code == 400
    assert up("[]").status_code == 400
    assert up('{"session_id": "x"}').status_code == 400
    assert up('{"duration_s": -5}').status_code == 400
    assert up('{"started_at": "not-a-date"}').status_code == 400
    assert up("{}", content=b"").status_code == 400
    # Over the 1 MB test limit
    assert up("{}", content=b"y" * (1024 * 1024 + 1)).status_code == 413


def test_list_pagination_bounds(client):
    assert client.get("/api/v1/recordings", headers=AUTH, params={"limit": -1}).status_code == 422
    assert client.get("/api/v1/recordings", headers=AUTH, params={"limit": 501}).status_code == 422
    assert client.get("/api/v1/recordings", headers=AUTH, params={"offset": -1}).status_code == 422
    r = client.get("/api/v1/recordings", headers=AUTH, params={"limit": 10, "offset": 0})
    assert r.status_code == 200


def test_stats(client):
    r = client.get("/api/v1/stats", headers=AUTH)
    assert r.status_code == 200
    assert set(r.json()) >= {"recordings", "total_bytes", "by_status"}


def test_user_token_unconfigured(client):
    r = client.post("/api/v1/plaud/user-token", headers=AUTH, json={"user_id": "pb_tester"})
    assert r.status_code == 503  # no Plaud credentials in test env


def test_user_token_validation(client):
    r = client.post("/api/v1/plaud/user-token", headers=AUTH, json={"user_id": "abc"})
    assert r.status_code == 422  # too short


def test_dashboard_served(client, tmp_path, monkeypatch):
    """`/` serves the built web app's index.html (never cached, since its asset
    names change per build) and explains itself with a 503 when web/ has not
    been built, instead of crashing."""
    from app import main as m

    built = tmp_path / "static"
    built.mkdir()
    (built / "index.html").write_text("<!doctype html><title>Transom</title><div id=root></div>")
    monkeypatch.setattr(m, "STATIC_DIR", built)
    r = client.get("/")
    assert r.status_code == 200 and "Transom" in r.text
    assert r.headers.get("cache-control") == "no-cache"

    monkeypatch.setattr(m, "STATIC_DIR", tmp_path / "missing")
    r = client.get("/")
    assert r.status_code == 503 and "not been built" in r.text


def test_security_headers(client):
    r = client.get("/api/v1/health")
    assert r.headers.get("x-frame-options") == "DENY"
    assert r.headers.get("x-content-type-options") == "nosniff"


def test_export_markdown_endpoint(client, tmp_path):
    """Export renders the shared markdown layout (same as the Android app) and
    names the download after the title; 409 until the transcript exists."""
    import json as _json
    from app import main as m

    r = client.post(
        "/api/v1/recordings", headers=AUTH,
        files={"file": ("exp.mp3", b"export-bytes")}, data={"metadata": "{}"},
    )
    rec_id = r.json()["id"]
    try:
        assert client.get(f"/api/v1/recordings/{rec_id}/export.md", headers=AUTH).status_code == 409
        tp = tmp_path / "t.json"
        tp.write_text(_json.dumps({"text": "Speaker 1: hello there", "segments": [],
                                   "summary": "Greeting.", "title": "Quick hello: a \"test\"",
                                   "duration_s": 3.0}))
        m.store.update(rec_id, status="done", transcript_path=str(tp),
                       title='Quick hello: a "test"', summary="Greeting.")
        r = client.get(f"/api/v1/recordings/{rec_id}/export.md", headers=AUTH)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/markdown")
        assert 'filename="Quick hello a test.md"' in r.headers["content-disposition"]
        body = r.text
        assert body.startswith('---\ntitle: "Quick hello: a \\"test\\""\n')
        assert "duration_s: \"3\"" in body
        assert "\n# Quick hello: a \"test\"\n" in body
        assert "## Summary\n\nGreeting.\n\n## Transcript\n\n**Speaker 1:** hello there\n" in body
    finally:
        client.delete(f"/api/v1/recordings/{rec_id}", headers=AUTH)


def test_upload_marks_and_patch_marks(client):
    """Marks travel with the upload (normalized) and can be replaced later."""
    r = client.post(
        "/api/v1/recordings", headers=AUTH,
        files={"file": ("m.mp3", b"marks-bytes")},
        data={"metadata": '{"marks": [30.5, 12, 12, -4]}'},
    )
    assert r.status_code == 201
    rec_id = r.json()["id"]
    try:
        detail = client.get(f"/api/v1/recordings/{rec_id}", headers=AUTH).json()
        assert detail["marks"] == [12.0, 30.5]
        r = client.patch(f"/api/v1/recordings/{rec_id}/marks", headers=AUTH, json={"marks": [5, 99.25]})
        assert r.status_code == 200 and r.json()["marks"] == [5.0, 99.25]
        assert r.json()["highlights"] is None  # no transcript yet
        assert client.patch(f"/api/v1/recordings/nope/marks", headers=AUTH, json={"marks": []}).status_code == 404
    finally:
        client.delete(f"/api/v1/recordings/{rec_id}", headers=AUTH)


def test_patch_title_renames_recording(client):
    r = client.post(
        "/api/v1/recordings", headers=AUTH,
        files={"file": ("rn.mp3", b"rename-bytes")}, data={"metadata": "{}"},
    )
    rec_id = r.json()["id"]
    try:
        r = client.patch(f"/api/v1/recordings/{rec_id}", headers=AUTH, json={"title": "  My   renamed  memo "})
        assert r.status_code == 200 and r.json()["title"] == "My renamed memo"
        assert client.get(f"/api/v1/recordings/{rec_id}", headers=AUTH).json()["title"] == "My renamed memo"
        assert client.patch(f"/api/v1/recordings/{rec_id}", headers=AUTH, json={"title": ""}).status_code == 422
        assert client.patch(f"/api/v1/recordings/{rec_id}", headers=AUTH, json={"title": "   "}).status_code == 422
        assert client.patch(f"/api/v1/recordings/{rec_id}", headers=AUTH, json={"status": "done"}).status_code == 422
        assert client.patch("/api/v1/recordings/nope", headers=AUTH, json={"title": "x"}).status_code == 404
    finally:
        client.delete(f"/api/v1/recordings/{rec_id}", headers=AUTH)


def test_vocabulary_endpoints(client):
    r = client.put("/api/v1/vocabulary", headers=AUTH, json={"entries": [
        {"term": "Plaud", "aliases": ["plod"]}, {"term": "Obsidian", "source": "obsidian"}]})
    assert r.status_code == 200 and len(r.json()["entries"]) == 2
    v = client.get("/api/v1/vocabulary", headers=AUTH).json()
    assert v["hotwords"] == "Plaud, Obsidian" and "Plaud = plod" in v["editor_text"]
    r = client.post("/api/v1/vocabulary/import", headers=AUTH, json={"entries": [
        {"term": "plaud", "aliases": ["plot"], "source": "obsidian"}, {"term": "Nora", "source": "obsidian"}]})
    assert r.status_code == 200 and r.json()["added"] == 1
    by = {e["term"]: e for e in r.json()["entries"]}
    assert by["Plaud"]["aliases"] == ["plod", "plot"] and by["Plaud"]["source"] == "manual"
    # Editors PUT without weights: the imported weight must survive the round trip.
    client.post("/api/v1/vocabulary/import", headers=AUTH, json={"entries": [{"term": "Sphere", "source": "obsidian", "weight": 94}]})
    r = client.put("/api/v1/vocabulary", headers=AUTH, json={"entries": [{"term": "Sphere", "source": "obsidian"}]})
    assert r.json()["entries"][0]["weight"] == 94
    assert client.put("/api/v1/vocabulary", headers=AUTH, json={"entries": []}).status_code == 200
    assert client.get("/api/v1/vocabulary", headers=AUTH).json()["entries"] == []


def test_qr_login_handshake_mints_revocable_session(client):
    # Browser (signed out) creates a request and polls: pending.
    r = client.post("/api/v1/login-requests", json={"label": "Chrome on Linux"})
    assert r.status_code == 201
    req_id = r.json()["id"]
    assert client.get(f"/api/v1/login-requests/{req_id}").json() == {"status": "pending"}
    # Approve requires auth.
    assert client.post(f"/api/v1/login-requests/{req_id}/approve").status_code == 401
    # Phone approves with the master token.
    r = client.post(f"/api/v1/login-requests/{req_id}/approve", headers=AUTH, json={"label": "Web · Pixel"})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    # Browser collects the token exactly once.
    r = client.get(f"/api/v1/login-requests/{req_id}")
    assert r.json()["status"] == "approved"
    session_token = r.json()["token"]
    assert session_token and session_token != "test-token-1"
    assert client.get(f"/api/v1/login-requests/{req_id}").json() == {"status": "expired"}
    # The session token works like a real token, is listed, and marks itself current.
    sess_auth = {"Authorization": f"Bearer {session_token}"}
    assert client.get("/api/v1/auth/check", headers=sess_auth).status_code == 204
    sessions = client.get("/api/v1/sessions", headers=sess_auth).json()["sessions"]
    mine = [s for s in sessions if s["current"]]
    assert len(mine) == 1 and mine[0]["label"] == "Web · Pixel"
    # A second approve of the same request is refused.
    assert client.post(f"/api/v1/login-requests/{req_id}/approve", headers=AUTH).status_code == 404
    # Logout revokes only that session.
    assert client.post("/api/v1/auth/logout", headers=sess_auth).status_code == 204
    assert client.get("/api/v1/auth/check", headers=sess_auth).status_code == 401
    assert client.get("/api/v1/auth/check", headers=AUTH).status_code == 204


def test_qr_login_revoke_from_another_client_and_unknown_request(client):
    req_id = client.post("/api/v1/login-requests").json()["id"]
    client.post(f"/api/v1/login-requests/{req_id}/approve", headers=AUTH)
    tok = client.get(f"/api/v1/login-requests/{req_id}").json()["token"]
    sid = [s for s in client.get("/api/v1/sessions", headers=AUTH).json()["sessions"] if s["label"] == "Web browser"][0]["id"]
    assert client.delete(f"/api/v1/sessions/{sid}", headers=AUTH).status_code == 204
    assert client.get("/api/v1/auth/check", headers={"Authorization": f"Bearer {tok}"}).status_code == 401
    assert client.delete(f"/api/v1/sessions/{sid}", headers=AUTH).status_code == 404
    assert client.get("/api/v1/login-requests/nope").json() == {"status": "expired"}
    assert client.post("/api/v1/login-requests/nope/approve", headers=AUTH).status_code == 404
    # The public poll path must not leak into other authenticated GETs.
    assert client.get("/api/v1/sessions").status_code == 401


def test_login_requests_capped_per_client(client, monkeypatch):
    from app import main as m
    # TestClient's peer is "testclient" (not an IP): X-Forwarded-For must be ignored,
    # so every request counts against the same (socket) client...
    ids = []
    r = client.post("/api/v1/login-requests", headers={"X-Forwarded-For": "198.51.100.1"}); ids.append(r.json()["id"])
    r = client.post("/api/v1/login-requests", headers={"X-Forwarded-For": "198.51.100.2"}); ids.append(r.json()["id"])
    assert m.store.count_pending_login_requests("testclient") == 2
    for i in ids: m.store.delete_login_request(i)
    # ...unless the peer is a trusted proxy, in which case its appended (last) hop is the client.
    from app.config import Settings
    monkeypatch.setattr(Settings, "is_trusted_proxy", lambda self, peer: peer == "testclient")
    ids = []
    for i in range(m.MAX_PENDING_PER_CLIENT):
        r = client.post("/api/v1/login-requests", headers={"X-Forwarded-For": "1.2.3.4, 203.0.113.9"})
        assert r.status_code == 201; ids.append(r.json()["id"])
    # a caller rotating the FIRST hop gains nothing: the proxy-appended last hop is what counts
    assert client.post("/api/v1/login-requests", headers={"X-Forwarded-For": "9.9.9.9, 203.0.113.9"}).status_code == 429
    # a genuinely different client (different last hop) is unaffected
    r = client.post("/api/v1/login-requests", headers={"X-Forwarded-For": "203.0.113.10"}); assert r.status_code == 201
    ids.append(r.json()["id"])
    for i in ids:
        m.store.delete_login_request(i)

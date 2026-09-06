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


def test_dashboard_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "Plaud Bridge" in r.text


def test_security_headers(client):
    r = client.get("/api/v1/health")
    assert r.headers.get("x-frame-options") == "DENY"
    assert r.headers.get("x-content-type-options") == "nosniff"

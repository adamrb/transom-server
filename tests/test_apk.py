"""Android APK hosting tests: upload/info/file/delete endpoints, version-code
gating, validation, manifest persistence, and bundled-APK auto-publish at
startup. Run with: pytest
"""

import hashlib
import json
import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="pb-apk-test-")
os.environ.setdefault("PB_DATA_DIR", _TMP)
os.environ.setdefault("PB_AUTH_TOKENS", "test-token-1,test-token-2")
os.environ.setdefault("PB_TRANSCRIBE_ENABLED", "false")

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app, install_bundled_apk

# Another test module may have imported app.config first (env is process-wide),
# so read the effective token/paths from the live settings object.
AUTH = {"Authorization": f"Bearer {settings.auth_tokens[0]}"}

APK_BYTES = b"PK\x03\x04" + b"fake-apk-payload" * 8
APK_BYTES_V2 = b"PK\x03\x04" + b"newer-apk-payload" * 8


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def upload(client, content=APK_BYTES, name="transom.apk", **meta):
    meta.setdefault("version_code", 1)
    meta.setdefault("version_name", "1.0.0")
    return client.post(
        "/api/v1/apk", headers=AUTH,
        files={"file": (name, content)}, data={"metadata": json.dumps(meta)},
    )


def test_auth_required_on_all_endpoints(client):
    assert client.get("/api/v1/apk/info").status_code == 401
    assert client.get("/api/v1/apk/file").status_code == 401
    assert client.delete("/api/v1/apk").status_code == 401
    r = client.post("/api/v1/apk", files={"file": ("a.apk", APK_BYTES)})
    assert r.status_code == 401


def test_404_before_first_upload(client):
    assert client.get("/api/v1/apk/info", headers=AUTH).status_code == 404
    assert client.get("/api/v1/apk/file", headers=AUTH).status_code == 404
    assert client.delete("/api/v1/apk", headers=AUTH).status_code == 404


def test_zip_magic_required(client):
    r = upload(client, content=b"not-a-zip-file")
    assert r.status_code == 400
    assert "ZIP magic" in r.json()["detail"]
    # A rejected upload must not create a manifest
    assert client.get("/api/v1/apk/info", headers=AUTH).status_code == 404


def test_metadata_validation(client):
    def up(metadata):
        return client.post(
            "/api/v1/apk", headers=AUTH,
            files={"file": ("a.apk", APK_BYTES)}, data={"metadata": metadata},
        )

    assert up("not json").status_code == 400
    assert up("{}").status_code == 400  # version_code + version_name required
    assert up('{"version_code": 0, "version_name": "1.0"}').status_code == 400
    assert up('{"version_code": -3, "version_name": "1.0"}').status_code == 400
    assert up('{"version_code": "x", "version_name": "1.0"}').status_code == 400
    assert up('{"version_code": 1}').status_code == 400  # missing version_name
    assert up(json.dumps({"version_code": 1, "version_name": "v" * 51})).status_code == 400
    assert up(json.dumps({"version_code": 1, "version_name": "1.0", "notes": "n" * 2001})).status_code == 400
    assert client.get("/api/v1/apk/info", headers=AUTH).status_code == 404


def test_empty_file_rejected(client):
    r = upload(client, content=b"")
    assert r.status_code == 400


def test_upload_info_file_roundtrip(client):
    r = upload(client, version_code=2, version_name="1.2.0", notes="BLE reconnect fixes")
    assert r.status_code == 201
    manifest = r.json()
    assert manifest["version_code"] == 2
    assert manifest["version_name"] == "1.2.0"
    assert manifest["notes"] == "BLE reconnect fixes"
    assert manifest["sha256"] == hashlib.sha256(APK_BYTES).hexdigest()
    assert manifest["size_bytes"] == len(APK_BYTES)
    assert manifest["filename"] == "2-transom.apk"

    r = client.get("/api/v1/apk/info", headers=AUTH)
    assert r.status_code == 200 and r.json() == manifest

    r = client.get("/api/v1/apk/file", headers=AUTH)
    assert r.status_code == 200
    assert r.content == APK_BYTES
    assert hashlib.sha256(r.content).hexdigest() == manifest["sha256"]
    assert r.headers["content-type"] == "application/vnd.android.package-archive"
    assert "2-transom.apk" in r.headers.get("content-disposition", "")


def test_manifest_survives_re_read(client):
    """The manifest is file-backed (no DB row): a fresh read of latest.json —
    what a restarted server (fresh Store + fresh handlers) would see — must
    match what the API serves."""
    api_view = client.get("/api/v1/apk/info", headers=AUTH).json()
    on_disk = json.loads((settings.apk_dir / "latest.json").read_text())
    assert on_disk == api_view


def test_lower_version_code_conflict(client):
    r = upload(client, version_code=1, version_name="0.9.0")
    assert r.status_code == 409
    # hosted release unchanged
    assert client.get("/api/v1/apk/info", headers=AUTH).json()["version_code"] == 2


def test_equal_version_code_reupload_accepted(client):
    r = upload(client, content=APK_BYTES_V2, version_code=2, version_name="1.2.0-fix")
    assert r.status_code == 201
    info = client.get("/api/v1/apk/info", headers=AUTH).json()
    assert info["version_name"] == "1.2.0-fix"
    assert info["sha256"] == hashlib.sha256(APK_BYTES_V2).hexdigest()


def test_new_version_keeps_prior_apk_on_disk(client):
    r = upload(client, content=APK_BYTES_V2, version_code=3, version_name="1.3.0",
               name="transom-1.3.apk")
    assert r.status_code == 201
    assert (settings.apk_dir / "3-transom-1.3.apk").is_file()
    # Prior release file stays on disk (only the manifest moved on)
    assert (settings.apk_dir / "2-transom.apk").is_file()


def test_oversize_rejected(client, monkeypatch):
    # settings is the live singleton the handlers read; shrink the cap to 0 MB
    monkeypatch.setattr(settings, "apk_max_upload_mb", 0)
    r = upload(client, version_code=4, version_name="1.4.0")
    assert r.status_code == 413
    assert client.get("/api/v1/apk/info", headers=AUTH).json()["version_code"] == 3


def test_filename_sanitized_and_apk_suffix_enforced(client):
    r = upload(client, version_code=4, version_name="1.4.0", name="../we ird$name")
    assert r.status_code == 201
    fname = r.json()["filename"]
    assert fname == "4-.._we_ird_name.apk"
    assert (settings.apk_dir / fname).is_file()
    # no path escape: name component only
    assert "/" not in fname


def test_delete_flow_and_rollback_story(client):
    assert client.delete("/api/v1/apk", headers=AUTH).status_code == 204
    assert client.get("/api/v1/apk/info", headers=AUTH).status_code == 404
    assert client.get("/api/v1/apk/file", headers=AUTH).status_code == 404
    assert client.delete("/api/v1/apk", headers=AUTH).status_code == 404
    # rollback: after DELETE, an older build can be re-uploaded
    r = upload(client, version_code=1, version_name="0.9.0")
    assert r.status_code == 201
    assert client.get("/api/v1/apk/info", headers=AUTH).json()["version_code"] == 1


# ── bundled-APK auto-publish (startup) ───────────────────────────────────────


def bundled_env(tmp_path, monkeypatch, apk=APK_BYTES, meta=None, write_meta=True):
    """Isolated data dir + bundle dir; returns the bundle dir."""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    bundle = tmp_path / "bundled-apk"
    bundle.mkdir(parents=True)
    monkeypatch.setattr(settings, "bundled_apk_dir", bundle)
    if apk is not None:
        (bundle / "transom.apk").write_bytes(apk)
    if write_meta:
        (bundle / "manifest.json").write_text(
            json.dumps(meta or {"version_code": 5, "version_name": "1.5.0", "notes": "bundled"})
        )
    return bundle


def hosted(version_code=1):
    settings.apk_dir.mkdir(parents=True, exist_ok=True)
    (settings.apk_dir / f"{version_code}-old.apk").write_bytes(APK_BYTES)
    manifest = {
        "version_code": version_code, "version_name": "old", "filename": f"{version_code}-old.apk",
        "sha256": hashlib.sha256(APK_BYTES).hexdigest(), "size_bytes": len(APK_BYTES),
        "uploaded_at": "2026-01-01T00:00:00Z", "min_sdk": None, "notes": None,
    }
    (settings.apk_dir / "latest.json").write_text(json.dumps(manifest))
    return manifest


def read_hosted():
    p = settings.apk_dir / "latest.json"
    return json.loads(p.read_text()) if p.exists() else None


def test_bundled_installs_on_empty_state(tmp_path, monkeypatch):
    bundled_env(tmp_path, monkeypatch)
    install_bundled_apk()
    m = read_hosted()
    assert m and m["version_code"] == 5 and m["version_name"] == "1.5.0"
    assert m["sha256"] == hashlib.sha256(APK_BYTES).hexdigest()
    assert (settings.apk_dir / m["filename"]).read_bytes() == APK_BYTES
    # bundle source untouched
    assert (settings.bundled_apk_dir / "transom.apk").is_file()


def test_bundled_skipped_when_hosted_newer_or_equal(tmp_path, monkeypatch):
    bundled_env(tmp_path, monkeypatch)
    before = hosted(version_code=5)  # equal
    install_bundled_apk()
    assert read_hosted() == before
    before = hosted(version_code=9)  # newer
    install_bundled_apk()
    assert read_hosted() == before


def test_bundled_replaces_older_hosted(tmp_path, monkeypatch):
    bundled_env(tmp_path, monkeypatch, apk=APK_BYTES_V2)
    hosted(version_code=2)
    install_bundled_apk()
    m = read_hosted()
    assert m["version_code"] == 5
    assert m["sha256"] == hashlib.sha256(APK_BYTES_V2).hexdigest()
    # old release file kept on disk
    assert (settings.apk_dir / "2-old.apk").is_file()


def test_bundled_malformed_never_crashes(tmp_path, monkeypatch):
    # missing manifest.json
    bundled_env(tmp_path, monkeypatch, write_meta=False)
    install_bundled_apk()
    assert read_hosted() is None

    # unparseable manifest.json
    bundle = bundled_env(tmp_path / "b2", monkeypatch)
    (bundle / "manifest.json").write_text("{nope")
    install_bundled_apk()
    assert read_hosted() is None

    # manifest missing required fields
    bundle = bundled_env(tmp_path / "b3", monkeypatch, meta={"version_name": "x"})
    install_bundled_apk()
    assert read_hosted() is None

    # two apks is ambiguous
    bundle = bundled_env(tmp_path / "b4", monkeypatch)
    (bundle / "second.apk").write_bytes(APK_BYTES)
    install_bundled_apk()
    assert read_hosted() is None

    # apk without zip magic
    bundle = bundled_env(tmp_path / "b5", monkeypatch, apk=b"garbage")
    install_bundled_apk()
    assert read_hosted() is None

    # nonexistent bundle dir is a silent no-op
    monkeypatch.setattr(settings, "bundled_apk_dir", tmp_path / "missing")
    install_bundled_apk()
    assert read_hosted() is None

"""The per-recording `automations` one-liner (app.automations_summary) and its
place in the recordings API."""
import json

import pytest
from fastapi.testclient import TestClient

from app import main as appmain
from app.automations_summary import delivery_state, summarize_automations
from app.config import settings as app_settings
from app.db import utcnow_iso
from app.main import app

AUTH = {"Authorization": "Bearer test-token"}


def d(**kw):
    base = {"id": "d1", "route_name": "Vault notes", "action_type": "webhook", "status": "ok",
            "result_status": None, "result_summary": None, "last_error": None}
    base.update(kw)
    return base


def run(**kw):
    base = {"id": "run-1", "created_at": "2026-09-09T15:28:33Z", "decision": {"routes": [{"name": "Vault notes", "reason": "r"}]}, "error": None}
    base.update(kw)
    return base


# --- delivery_state ---------------------------------------------------------

@pytest.mark.parametrize("delivery, expected", [
    (d(result_status="done"), "done"),
    (d(result_status="failed"), "failed"),
    (d(status="failed"), "failed"),
    (d(result_status="unknown"), "unknown"),
    (d(result_status="queued"), "working"),
    (d(status="pending"), "working"),
    (d(status="ok"), "working"),                       # webhook accepted, no report yet
    (d(status="ok", action_type="markdown"), "done"),  # server-side action, nothing to wait for
    (d(status="ok", action_type="none"), "done"),
])
def test_delivery_state(delivery, expected):
    assert delivery_state(delivery) == expected


# --- summarize_automations --------------------------------------------------

def test_no_run_is_none():
    assert summarize_automations(None, []) is None


def test_done_delivery_reads_route_and_agent_summary():
    s = summarize_automations(run(), [d(result_status="done", result_summary="Filed:  Life/Topics/Dogs.md")])
    assert s["state"] == "done"
    assert s["line"] == "Vault notes: Filed: Life/Topics/Dogs.md"
    assert s["items"] == [{"route_name": "Vault notes", "state": "done", "summary": "Filed: Life/Topics/Dogs.md"}]
    assert s["run_id"] == "run-1" and s["run_at"] == "2026-09-09T15:28:33Z"


def test_worst_state_wins_and_items_are_joined():
    s = summarize_automations(run(), [
        d(id="a", route_name="Work meetings", result_status="done", result_summary="Created: Work/Meetings/x.md"),
        d(id="b", route_name="Ask Claude", result_status="queued", result_summary="Claude session started"),
    ])
    assert s["state"] == "working"
    assert s["line"] == "Work meetings: Created: Work/Meetings/x.md · Ask Claude: Working"
    s2 = summarize_automations(run(), [d(id="a", result_status="done", result_summary="ok"), d(id="b", status="failed", last_error="HTTP 500")])
    assert s2["state"] == "failed"
    assert "Vault notes: HTTP 500" in s2["line"]


def test_unknown_and_failed_wording():
    assert summarize_automations(run(), [d(result_status="unknown")])["line"] == "Vault notes: No result was reported"
    assert summarize_automations(run(), [d(status="failed")])["line"] == "Vault notes: Failed"
    assert summarize_automations(run(), [d(result_status="done")])["line"] == "Vault notes: Done"


def test_nothing_matched_and_router_error():
    s = summarize_automations(run(decision={"routes": []}), [])
    assert s == {"run_id": "run-1", "run_at": "2026-09-09T15:28:33Z", "state": "skipped", "line": "No automation matched", "items": []}
    e = summarize_automations(run(error="Model timed out"), [])
    assert e["state"] == "failed" and e["line"] == "Automations couldn't run: Model timed out"


def test_matched_routes_without_deliveries_yet_is_working():
    s = summarize_automations(run(decision=json.dumps({"routes": [{"name": "Vault notes"}, {"name": "Ask Claude"}]})), [])
    assert s["state"] == "working" and s["line"] == "Vault notes, Ask Claude: Working"


def test_line_is_bounded():
    s = summarize_automations(run(), [d(result_status="done", result_summary="x" * 500)])
    assert len(s["line"]) <= 200


# --- API --------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "data_dir", tmp_path)
    monkeypatch.setattr(app_settings, "auth_tokens", ["test-token"])
    monkeypatch.setattr(app_settings, "transcribe_enabled", False)
    monkeypatch.setattr(app_settings, "router_enabled", False)
    with TestClient(app) as c:
        yield c


def _upload(client, name):
    # Distinct bytes per name: the server deduplicates uploads by content hash.
    r = client.post("/api/v1/recordings", headers=AUTH, files={"file": (name, name.encode() * 4, "audio/mpeg")}, data={"metadata": "{}"})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def test_list_and_detail_carry_the_latest_run_only(client):
    store = appmain.store
    a = _upload(client, "a.mp3")
    b = _upload(client, "b.mp3")
    old = store.insert_router_run(recording_id=a, created_at="2026-09-09T10:00:00Z", model="m",
                                  decision=json.dumps({"routes": [{"name": "Ask Claude", "reason": "r"}]}), error=None)
    store.insert_delivery(recording_id=a, router_run_id=old, route_id="x", route_name="Ask Claude", status="ok", attempts=1,
                          last_error=None, action_type="webhook", action_config="{}", payload="{}", created_at="2026-09-09T10:00:01Z",
                          result_status="done", result_summary="Started session", result_at="2026-09-09T10:00:02Z")
    new = store.insert_router_run(recording_id=a, created_at="2026-09-09T11:00:00Z", model="m",
                                  decision=json.dumps({"routes": [{"name": "Vault notes", "reason": "r"}]}), error=None)
    store.insert_delivery(recording_id=a, router_run_id=new, route_id="y", route_name="Vault notes", status="ok", attempts=1,
                          last_error=None, action_type="webhook", action_config="{}", payload="{}", created_at="2026-09-09T11:00:01Z",
                          result_status="queued", result_summary="Agent started working", result_at=utcnow_iso())

    rows = {r["id"]: r for r in client.get("/api/v1/recordings", headers=AUTH).json()["recordings"]}
    assert rows[b]["automations"] is None
    assert rows[a]["automations"]["state"] == "working"
    assert rows[a]["automations"]["line"] == "Vault notes: Working"
    assert rows[a]["automations"]["run_id"] == new

    one = client.get(f"/api/v1/recordings/{a}", headers=AUTH).json()
    assert one["automations"]["run_id"] == new
    assert one["automations"]["items"][0]["route_name"] == "Vault notes"


def test_silent_hand_off_past_the_deadline_reads_unknown(client):
    store = appmain.store
    a = _upload(client, "a.mp3")
    rid = store.insert_router_run(recording_id=a, created_at="2026-09-09T10:00:00Z", model="m",
                                  decision=json.dumps({"routes": [{"name": "Ask Claude", "reason": "r"}]}), error=None)
    store.insert_delivery(recording_id=a, router_run_id=rid, route_id="x", route_name="Ask Claude", status="ok", attempts=1,
                          last_error=None, action_type="webhook", action_config="{}", payload="{}", created_at="2026-09-09T10:00:01Z",
                          result_status="queued", result_summary="Started", result_at="2020-01-01T00:00:00Z")
    row = client.get("/api/v1/recordings", headers=AUTH).json()["recordings"][0]
    assert row["automations"]["state"] == "unknown"
    assert row["automations"]["line"] == "Ask Claude: No result was reported"

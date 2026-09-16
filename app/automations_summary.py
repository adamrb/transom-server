"""One-line answer to "what happened to this recording?" for list rows.

The detail views (app and dashboard) show every router run with its routes,
reasons and hand-offs. A list row has room for one line, so this folds the
LATEST run and its deliveries into a small dict:

    {"state": "working" | "done" | "failed" | "unknown" | "skipped",
     "line":  "Vault notes: Filed: Notes/Dogs.md",
     "items": [{"route_name": "Vault notes", "state": "done",
                "summary": "Filed: Notes/Dogs.md"}],
     "run_id": "...", "run_at": "2026-09-09T15:28:33Z"}

`None` when the router never ran for the recording. Pure: takes the run row
(decision already parsed) and its deliveries as `_delivery_public` serves them
(so a hand-off the server gave up waiting for already reads 'unknown').
"""
from __future__ import annotations

LINE_MAX = 200

_ORDER = {"failed": 0, "working": 1, "unknown": 2, "done": 3}


def delivery_state(delivery: dict) -> str:
    """working | done | failed | unknown for one hand-off, the agent's report
    first (that is what the user wants to know), the hand-off status only when
    there is no report yet. A server-side action (markdown, none) that went
    through without a report is done; a webhook that was accepted but has not
    reported is still working."""
    result = delivery.get("result_status")
    status = delivery.get("status")
    if result == "failed" or status == "failed":
        return "failed"
    if result == "done":
        return "done"
    if result == "unknown":
        return "unknown"
    if result == "queued" or status == "pending":
        return "working"
    if status == "ok":
        return "working" if delivery.get("action_type") == "webhook" else "done"
    return "working"


def delivery_text(delivery: dict, state: str) -> str:
    """The words next to the route name."""
    summary = " ".join((delivery.get("result_summary") or "").split())
    if state == "done":
        return summary or "Done"
    if state == "failed":
        return " ".join((delivery.get("last_error") or "").split()) or summary or "Failed"
    if state == "unknown":
        return "No result was reported"
    return "Working"


def summarize_automations(run: dict | None, deliveries: list[dict]) -> dict | None:
    if not run:
        return None
    decision = run.get("decision")
    if isinstance(decision, str):
        import json
        try:
            decision = json.loads(decision)
        except ValueError:
            decision = None
    base = {"run_id": run.get("id"), "run_at": run.get("created_at")}
    if run.get("error"):
        return {**base, "state": "failed", "line": f"Automations couldn't run: {run['error']}"[:LINE_MAX], "items": []}
    items = []
    for d in deliveries:
        state = delivery_state(d)
        items.append({
            "route_name": d.get("route_name") or "",
            "state": state,
            "summary": delivery_text(d, state)[:LINE_MAX],
        })
    if not items:
        routes = (decision or {}).get("routes") if isinstance(decision, dict) else None
        if routes:
            # Routes matched but no delivery rows: the run is mid-flight (deliveries are
            # inserted as each action starts) or the routes' actions were 'none'.
            names = ", ".join(r.get("name", "") for r in routes if isinstance(r, dict))
            return {**base, "state": "working", "line": f"{names}: Working"[:LINE_MAX], "items": []}
        return {**base, "state": "skipped", "line": "No automation matched", "items": []}
    state = min((i["state"] for i in items), key=lambda s: _ORDER.get(s, 9))
    line = " · ".join(f"{i['route_name']}: {i['summary']}" if i["route_name"] else i["summary"] for i in items)
    return {**base, "state": state, "line": line[:LINE_MAX], "items": items}

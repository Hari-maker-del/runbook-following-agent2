"""Quick integration test for the runbook agent API."""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8000"


def post(path, data):
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return json.loads(urllib.request.urlopen(req).read().decode())


def get(path):
    return json.loads(urllib.request.urlopen(f"{BASE}{path}").read().decode())


resp = post("/execute", {"filename": "sample-maintenance.md", "continue_on_failure": True})
sid = resp["session_id"]
print("Session:", sid)

state = None
for i in range(30):
    time.sleep(1)
    state = get(f"/execute/state/{sid}")
    print(f"Poll {i}: status={state['status']} step={state['current_step']} progress={state['progress_percent']}")
    if state["status"] in ("waiting_confirmation", "completed", "failed"):
        break

if state and state.get("pending_confirmation"):
    pc = state["pending_confirmation"]
    print("Declining risky step:", pc["command"])
    post("/execute/confirm", {"session_id": sid, "step": pc["step"], "approved": False})
    for i in range(10):
        time.sleep(1)
        state = get(f"/execute/state/{sid}")
        print(f"After confirm poll {i}: status={state['status']}")
        if state["status"] == "completed":
            break

report = get(f"/report?session_id={sid}")
print(
    "Report:",
    {k: report[k] for k in ["total_steps", "successful", "failed", "blocked", "skipped", "overall_status"]},
)

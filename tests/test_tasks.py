from datetime import datetime

from app.models import Task, TaskExecution

BODY = {
    "machine_id": "ETCH-001",
    "start_at": "2026-11-19T08:00:00Z",
    "stop_at": "2026-11-20T08:00:00Z",
    "interval_seconds": 300,
}


def make_task(client, **overrides):
    r = client.post("/v1/tasks", json={**BODY, **overrides})
    assert r.status_code == 201, r.text
    return r.json()


def test_create_task_matches_sample_response(client):
    t = make_task(client)
    assert t["task_id"] == 1
    assert t["status"] == "ACTIVE"
    assert t["last_attempt"] is None
    assert t["last_processed_cursor"] == 0
    assert t["next_attempt"].startswith("2026-11-19T08:00:00")


def test_validation(client):
    assert client.post("/v1/tasks", json={**BODY, "stop_at": BODY["start_at"]}).status_code == 422
    assert client.post("/v1/tasks", json={**BODY, "interval_seconds": 0}).status_code == 422
    assert client.post("/v1/tasks", json={**BODY, "machine_id": "  "}).status_code == 422


def test_naive_datetime_is_treated_as_utc(client):
    t = make_task(client, start_at="2026-11-19T08:00:00", stop_at="2026-11-20T08:00:00")
    assert t["start_at"].startswith("2026-11-19T08:00:00")


def test_pause_and_resume(client):
    t = make_task(client)
    r = client.post(f"/v1/tasks/{t['task_id']}/pause")
    assert r.status_code == 200 and r.json()["status"] == "PAUSED"

    r = client.post(f"/v1/tasks/{t['task_id']}/resume")
    assert r.json()["status"] == "ACTIVE"
    # start_at is in the past, so next_attempt moves to "now"
    assert datetime.fromisoformat(r.json()["next_attempt"]) > datetime.fromisoformat(t["next_attempt"])


def test_invalid_transitions_return_409(client):
    t = make_task(client)
    tid = t["task_id"]
    assert client.post(f"/v1/tasks/{tid}/resume").status_code == 409  # already active
    client.post(f"/v1/tasks/{tid}/pause")
    assert client.post(f"/v1/tasks/{tid}/pause").status_code == 409  # already paused


def test_delete_is_soft(client, db_session):
    t = make_task(client)
    tid = t["task_id"]
    assert client.delete(f"/v1/tasks/{tid}").status_code == 204
    assert client.get(f"/v1/tasks/{tid}").status_code == 404
    assert client.get("/v1/tasks").json() == []
    assert client.post(f"/v1/tasks/{tid}/pause").status_code == 404
    assert db_session.get(Task, tid).status == "DELETED"  # row still exists


def test_list_filters(client):
    make_task(client, machine_id="ETCH-001")
    make_task(client, machine_id="ETCH-002")
    assert len(client.get("/v1/tasks").json()) == 2
    assert len(client.get("/v1/tasks?machine_id=ETCH-002").json()) == 1
    assert client.get("/v1/tasks?status=PAUSED").json() == []


def test_missing_task_returns_404(client):
    assert client.get("/v1/tasks/999").status_code == 404


def test_executions_history_survives_delete(client, db_session):
    t = make_task(client)
    tid = t["task_id"]
    assert client.get(f"/v1/tasks/{tid}/executions").json() == []

    db_session.add(TaskExecution(task_id=tid, status="SUCCESS", events_found=3, events_stored=3))
    db_session.commit()
    client.delete(f"/v1/tasks/{tid}")

    r = client.get(f"/v1/tasks/{tid}/executions")
    assert r.status_code == 200
    assert r.json()[0]["status"] == "SUCCESS"
    assert r.json()[0]["events_stored"] == 3
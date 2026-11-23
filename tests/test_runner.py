from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.models import EventCode, ProcessedEvent, ProcessedFile, Task, TaskExecution, utcnow
from app.services import downloader
from app.timeutil import as_utc
from app.worker.runner import claim_due_tasks, run_task_once

ROWS = [
    {"cursor": 1, "timestamp": "2026-11-19T10:00:00Z", "event_code": "TEMP_HIGH"},
    {"cursor": 2, "timestamp": "2026-11-19T10:00:03Z", "event_code": "MOTOR_FAILURE"},
    {"cursor": 3, "timestamp": "2026-11-19T10:00:07Z", "event_code": "FLOW_LOW"},
    {"cursor": 4, "timestamp": "2026-11-19T10:00:10Z", "event_code": "TEMP_HIGH"},
]
META = {
    "machine_id": "ETCH-001",
    "file_name": "f1.csv",
    "start_cursor": 1,
    "end_cursor": 4,
    "download_url": "/v1/simulator/files/f1.csv",
}


@pytest.fixture
def task(db_session, monkeypatch):
    db_session.add_all([
        EventCode(code="TEMP_HIGH", severity="HIGH"),
        EventCode(code="MOTOR_FAILURE", severity="CRITICAL"),
    ])
    now = utcnow()
    t = Task(
        machine_id="ETCH-001",
        start_at=now - timedelta(hours=1),
        stop_at=now + timedelta(days=1),
        interval_seconds=300,
        next_attempt=now - timedelta(minutes=1),
    )
    db_session.add(t)
    db_session.commit()
    # fake machine: has events up to cursor 4
    monkeypatch.setattr(downloader, "fetch_file_metadata", lambda m, c: META if c < 4 else None)
    monkeypatch.setattr(downloader, "download_rows", lambda url: ROWS)
    return t


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_success_run(db_session, task):
    assert run_task_once(db_session, task.id) == "SUCCESS"
    db_session.refresh(task)
    assert count(db_session, ProcessedEvent) == 3  # FLOW_LOW is not on the watchlist... plus
    assert task.last_processed_cursor == 4
    ex = db_session.scalars(select(TaskExecution)).one()
    assert ex.status == "SUCCESS" and ex.events_found == 3 and ex.events_stored == 3
    gap = as_utc(task.next_attempt) - as_utc(task.last_attempt)
    assert gap == timedelta(seconds=300)


def test_nothing_new_is_skipped(db_session, task):
    run_task_once(db_session, task.id)
    assert run_task_once(db_session, task.id) == "SKIPPED"


def test_same_file_twice_creates_no_duplicates(db_session, task):
    run_task_once(db_session, task.id)
    task.last_processed_cursor = 0  # pretend the cursor update was lost
    db_session.commit()
    assert run_task_once(db_session, task.id) == "SKIPPED"
    db_session.refresh(task)
    assert count(db_session, ProcessedEvent) == 3
    assert task.last_processed_cursor == 4


def test_event_unique_constraint_is_second_safety_net(db_session, task):
    run_task_once(db_session, task.id)
    for f in db_session.scalars(select(ProcessedFile)).all():
        db_session.delete(f)  # file record lost, events remain
    task.last_processed_cursor = 0
    db_session.commit()
    assert run_task_once(db_session, task.id) == "SUCCESS"
    last = db_session.scalars(select(TaskExecution).order_by(TaskExecution.id.desc())).first()
    assert last.events_found == 3 and last.events_stored == 0
    assert count(db_session, ProcessedEvent) == 3


def test_failure_keeps_cursor_and_logs_error(db_session, task, monkeypatch):
    def boom(machine_id, cursor):
        raise RuntimeError("boom")

    monkeypatch.setattr(downloader, "fetch_file_metadata", boom)
    assert run_task_once(db_session, task.id) == "FAILED"
    db_session.refresh(task)
    assert task.last_processed_cursor == 0
    assert task.next_attempt is not None
    ex = db_session.scalars(select(TaskExecution)).one()
    assert ex.status == "FAILED" and "boom" in ex.error_message
    assert count(db_session, ProcessedEvent) == 0


def test_inactive_code_is_ignored(db_session, task):
    db_session.scalar(select(EventCode).where(EventCode.code == "MOTOR_FAILURE")).is_active = False
    db_session.commit()
    run_task_once(db_session, task.id)
    assert count(db_session, ProcessedEvent) == 2


def test_paused_task_does_nothing(db_session, task):
    task.status = "PAUSED"
    db_session.commit()
    assert run_task_once(db_session, task.id) == "SKIPPED"
    assert count(db_session, TaskExecution) == 0


def test_task_completes_after_stop_at(db_session, task):
    task.stop_at = utcnow() - timedelta(minutes=1)
    db_session.commit()
    assert run_task_once(db_session, task.id) == "COMPLETED"
    db_session.refresh(task)
    assert task.status == "COMPLETED"


def test_claim_due_tasks_only_once(db_session, task):
    assert claim_due_tasks(db_session) == [task.id]
    assert claim_due_tasks(db_session) == []  # next_attempt was pushed forward
    task.status = "PAUSED"
    task.next_attempt = utcnow() - timedelta(minutes=1)
    db_session.commit()
    assert claim_due_tasks(db_session) == []
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EventCode, ProcessedFile, Task, TaskExecution, utcnow
from app.services import cursor as cursor_svc
from app.services import downloader, history, idempotency, matcher, storage
from app.timeutil import as_utc


def _schedule_next(task: Task, now) -> None:
    task.last_attempt = now
    task.next_attempt = now + timedelta(seconds=task.interval_seconds)


def run_task_once(db: Session, task_id: int) -> str:
    """One run of one task. Returns SUCCESS, SKIPPED, FAILED or COMPLETED."""
    task = db.get(Task, task_id)
    if task is None or task.status != "ACTIVE":
        return "SKIPPED"

    now = utcnow()
    if now >= as_utc(task.stop_at):
        task.status = "COMPLETED"
        task.next_attempt = None
        db.commit()
        return "COMPLETED"

    execution = history.start_execution(db, task)
    execution_id = execution.id
    try:
        meta = downloader.fetch_file_metadata(task.machine_id, task.last_processed_cursor)

        if meta is None:  # nothing new on the machine
            history.finish_execution(execution, "SKIPPED")
            status = "SKIPPED"

        elif idempotency.file_already_processed(db, task.machine_id, meta["file_name"]):
            cursor_svc.advance_cursor(task, meta["end_cursor"])
            history.finish_execution(
                execution, "SKIPPED",
                file_name=meta["file_name"],
                start_cursor=meta["start_cursor"],
                end_cursor=meta["end_cursor"],
                error_message="file already processed",
            )
            status = "SKIPPED"

        else:
            rows = downloader.download_rows(meta["download_url"])
            active = db.scalars(select(EventCode).where(EventCode.is_active.is_(True))).all()
            codes = {c.code: c.severity for c in active}

            matched = matcher.match_events(rows, codes)
            stored = storage.store_events(db, task, meta["file_name"], matched)

            db.add(
                ProcessedFile(
                    task_id=task.id,
                    machine_id=task.machine_id,
                    file_name=meta["file_name"],
                    start_cursor=meta["start_cursor"],
                    end_cursor=meta["end_cursor"],
                )
            )
            cursor_svc.advance_cursor(task, meta["end_cursor"])
            history.finish_execution(
                execution, "SUCCESS",
                file_name=meta["file_name"],
                start_cursor=meta["start_cursor"],
                end_cursor=meta["end_cursor"],
                events_found=len(matched),
                events_stored=stored,
            )
            status = "SUCCESS"

        _schedule_next(task, now)
        db.commit()  # events + file + cursor + history are saved together or not at all
        return status

    except Exception as exc:
        db.rollback()  # undo everything from this run; the cursor did NOT move
        execution = db.get(TaskExecution, execution_id)
        task = db.get(Task, task_id)
        history.finish_execution(execution, "FAILED", error_message=str(exc)[:1000])
        _schedule_next(task, now)  # try again at the next interval
        db.commit()
        return "FAILED"


def claim_due_tasks(db: Session, now=None) -> list[int]:
    """Find tasks that are due and push their next_attempt forward, so they aren't queued twice."""
    now = now or utcnow()
    due = db.scalars(
        select(Task).where(Task.status == "ACTIVE", Task.next_attempt <= now)
    ).all()
    for task in due:
        task.next_attempt = now + timedelta(seconds=task.interval_seconds)
    db.commit()
    return [t.id for t in due]
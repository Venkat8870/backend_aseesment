from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import ProcessedEvent, Task
from app.services.idempotency import existing_cursors


def _parse_ts(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def store_events(db: Session, task: Task, file_name: str, matched: list[dict]) -> int:
    """Insert new events only. Returns how many were actually stored."""
    seen = existing_cursors(db, task.machine_id, [m["cursor"] for m in matched])
    stored = 0
    for m in matched:
        if m["cursor"] in seen:
            continue
        db.add(
            ProcessedEvent(
                task_id=task.id,
                machine_id=task.machine_id,
                cursor=m["cursor"],
                event_time=_parse_ts(m["timestamp"]),
                event_code=m["event_code"],
                severity=m["severity"],
                file_name=file_name,
            )
        )
        stored += 1
    return stored
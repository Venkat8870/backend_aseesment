from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ProcessedEvent
from app.schemas import EventPage
from app.timeutil import as_utc

router = APIRouter(prefix="/v1/events", tags=["events"])


@router.get("", response_model=EventPage)
def list_events(
    machine_id: str | None = None,
    event_code: str | None = None,
    severity: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    start_time, end_time = as_utc(start_time), as_utc(end_time)
    if start_time and end_time and start_time > end_time:
        raise HTTPException(status_code=422, detail="start_time must not be after end_time")

    filters = []
    if machine_id:
        filters.append(ProcessedEvent.machine_id == machine_id)
    if event_code:
        filters.append(ProcessedEvent.event_code == event_code.strip().upper())
    if severity:
        filters.append(ProcessedEvent.severity == severity.strip().upper())
    if start_time:
        filters.append(ProcessedEvent.event_time >= start_time)
    if end_time:
        filters.append(ProcessedEvent.event_time <= end_time)

    total = db.scalar(select(func.count()).select_from(ProcessedEvent).where(*filters))
    items = db.scalars(
        select(ProcessedEvent)
        .where(*filters)
        .order_by(ProcessedEvent.event_time, ProcessedEvent.cursor)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return EventPage(items=items, page=page, page_size=page_size, total=total)
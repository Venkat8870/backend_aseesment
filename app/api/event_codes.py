from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import EventCode
from app.schemas import EventCodeCreate, EventCodeOut

router = APIRouter(prefix="/v1/event-codes", tags=["event-codes"])


@router.post("", response_model=EventCodeOut, status_code=201)
def create_event_code(body: EventCodeCreate, db: Session = Depends(get_db)):
    exists = db.scalar(select(EventCode).where(EventCode.code == body.code))
    if exists:
        raise HTTPException(status_code=409, detail=f"Event code {body.code} already registered")

    obj = EventCode(
        code=body.code,
        severity=body.severity.value,
        description=body.description,
    )
    db.add(obj)
    try:
        db.commit()
    except IntegrityError:  # two requests raced past the check above
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Event code {body.code} already registered")
    db.refresh(obj)
    return obj


@router.get("", response_model=list[EventCodeOut])
def list_event_codes(db: Session = Depends(get_db)):
    return db.scalars(select(EventCode).order_by(EventCode.id)).all()


@router.delete("/{code}", status_code=204)
def delete_event_code(code: str, db: Session = Depends(get_db)):
    obj = db.scalar(select(EventCode).where(EventCode.code == code.strip().upper()))
    if obj is None:
        raise HTTPException(status_code=404, detail="Event code not found")
    db.delete(obj)
    db.commit()
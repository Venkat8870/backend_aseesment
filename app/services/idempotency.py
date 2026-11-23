from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ProcessedEvent, ProcessedFile


def file_already_processed(db: Session, machine_id: str, file_name: str) -> bool:
    stmt = select(ProcessedFile.id).where(
        ProcessedFile.machine_id == machine_id, ProcessedFile.file_name == file_name
    )
    return db.scalar(stmt) is not None


def existing_cursors(db: Session, machine_id: str, cursors: list[int]) -> set[int]:
    if not cursors:
        return set()
    stmt = select(ProcessedEvent.cursor).where(
        ProcessedEvent.machine_id == machine_id, ProcessedEvent.cursor.in_(cursors)
    )
    return set(db.scalars(stmt).all())
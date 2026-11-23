from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Boolean,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator




def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EventCode(Base):
    __tablename__ = "event_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    severity: Mapped[str] = mapped_column(String(20), default="MEDIUM")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    machine_id: Mapped[str] = mapped_column(String(100), index=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    stop_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    interval_seconds: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")  # ACTIVE, PAUSED, COMPLETED, DELETED
    last_attempt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_processed_cursor: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    executions: Mapped[list["TaskExecution"]] = relationship(back_populates="task")


class ProcessedFile(Base):
    __tablename__ = "processed_files"
    __table_args__ = (
        UniqueConstraint("machine_id", "file_name", name="uq_file_per_machine"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    machine_id: Mapped[str] = mapped_column(String(100))
    file_name: Mapped[str] = mapped_column(String(255))
    start_cursor: Mapped[int] = mapped_column(Integer)
    end_cursor: Mapped[int] = mapped_column(Integer)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProcessedEvent(Base):
    __tablename__ = "processed_events"
    __table_args__ = (
        UniqueConstraint("machine_id", "cursor", name="uq_event_per_machine"),
        Index("ix_events_machine_time", "machine_id", "event_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    machine_id: Mapped[str] = mapped_column(String(100))
    cursor: Mapped[int] = mapped_column(Integer)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    event_code: Mapped[str] = mapped_column(String(100), index=True)
    severity: Mapped[str] = mapped_column(String(20))
    file_name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TaskExecution(Base):
    __tablename__ = "task_executions"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="RUNNING")  # RUNNING, SUCCESS, FAILED, SKIPPED
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_cursor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_cursor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    events_found: Mapped[int] = mapped_column(Integer, default=0)
    events_stored: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    task: Mapped["Task"] = relationship(back_populates="executions")
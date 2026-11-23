from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.timeutil import as_utc


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EventCodeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    severity: Severity = Severity.MEDIUM
    description: str | None = None

    @field_validator("code")
    @classmethod
    def normalize_code(cls, v: str) -> str:
        v = v.strip().upper()
        if not v:
            raise ValueError("code must not be blank")
        return v


class EventCodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    severity: str
    description: str | None
    is_active: bool
    created_at: datetime


class TaskCreate(BaseModel):
    machine_id: str = Field(min_length=1, max_length=100)
    start_at: datetime
    stop_at: datetime
    interval_seconds: int = Field(ge=1, le=86400)

    @field_validator("machine_id")
    @classmethod
    def clean_machine_id(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("machine_id must not be blank")
        return v

    @field_validator("start_at", "stop_at")
    @classmethod
    def to_utc(cls, v: datetime) -> datetime:
        return as_utc(v)

    @model_validator(mode="after")
    def check_range(self):
        if self.stop_at <= self.start_at:
            raise ValueError("stop_at must be after start_at")
        return self


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    task_id: int = Field(validation_alias="id")
    machine_id: str
    status: str
    start_at: datetime
    stop_at: datetime
    interval_seconds: int
    last_attempt: datetime | None
    next_attempt: datetime | None
    last_processed_cursor: int

    @field_validator("start_at", "stop_at", "last_attempt", "next_attempt")
    @classmethod
    def to_utc(cls, v):
        return as_utc(v)


class TaskExecutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    started_at: datetime
    finished_at: datetime | None
    status: str
    file_name: str | None
    start_cursor: int | None
    end_cursor: int | None
    events_found: int
    events_stored: int
    error_message: str | None

    @field_validator("started_at", "finished_at")
    @classmethod
    def to_utc(cls, v):
        return as_utc(v)

class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    machine_id: str
    cursor: int
    event_time: datetime
    event_code: str
    severity: str
    file_name: str

    @field_validator("event_time")
    @classmethod
    def to_utc(cls, v):
        return as_utc(v)


class EventPage(BaseModel):
    items: list[EventOut]
    page: int
    page_size: int
    total: int
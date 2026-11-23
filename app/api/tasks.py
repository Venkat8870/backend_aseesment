from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Task, TaskExecution, utcnow
from app.schemas import TaskCreate, TaskExecutionOut, TaskOut
from app.timeutil import as_utc

router = APIRouter(prefix="/v1/tasks", tags=["tasks"])


def _get_task(db: Session, task_id: int, include_deleted: bool = False) -> Task:
    task = db.get(Task, task_id)
    if task is None or (task.status == "DELETED" and not include_deleted):
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("", response_model=TaskOut, status_code=201)
def create_task(body: TaskCreate, db: Session = Depends(get_db)):
    task = Task(
        machine_id=body.machine_id,
        start_at=body.start_at,
        stop_at=body.stop_at,
        interval_seconds=body.interval_seconds,
        status="ACTIVE",
        next_attempt=body.start_at,
        last_processed_cursor=0,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.get("", response_model=list[TaskOut])
def list_tasks(
    machine_id: str | None = None,
    status: str | None = Query(default=None, description="ACTIVE, PAUSED, COMPLETED or DELETED"),
    db: Session = Depends(get_db),
):
    stmt = select(Task).order_by(Task.id)
    if machine_id:
        stmt = stmt.where(Task.machine_id == machine_id)
    if status:
        stmt = stmt.where(Task.status == status.upper())
    else:
        stmt = stmt.where(Task.status != "DELETED")  # hide deleted by default
    return db.scalars(stmt).all()


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: int, db: Session = Depends(get_db)):
    return _get_task(db, task_id)


@router.post("/{task_id}/pause", response_model=TaskOut)
def pause_task(task_id: int, db: Session = Depends(get_db)):
    task = _get_task(db, task_id)
    if task.status != "ACTIVE":
        raise HTTPException(status_code=409, detail=f"Cannot pause a task that is {task.status}")
    task.status = "PAUSED"
    db.commit()
    db.refresh(task)
    return task


@router.post("/{task_id}/resume", response_model=TaskOut)
def resume_task(task_id: int, db: Session = Depends(get_db)):
    task = _get_task(db, task_id)
    if task.status != "PAUSED":
        raise HTTPException(status_code=409, detail=f"Cannot resume a task that is {task.status}")
    task.status = "ACTIVE"
    task.next_attempt = max(utcnow(), as_utc(task.start_at))  # run right away, cursor is kept
    db.commit()
    db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: int, db: Session = Depends(get_db)):
    task = _get_task(db, task_id)
    task.status = "DELETED"  # soft delete: history stays
    task.next_attempt = None
    db.commit()


@router.get("/{task_id}/executions", response_model=list[TaskExecutionOut])
def task_executions(
    task_id: int,
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    _get_task(db, task_id, include_deleted=True)  # history survives deletion
    stmt = (
        select(TaskExecution)
        .where(TaskExecution.task_id == task_id)
        .order_by(TaskExecution.id.desc())
        .limit(limit)
    )
    return db.scalars(stmt).all()
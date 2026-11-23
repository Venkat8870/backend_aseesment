from sqlalchemy.orm import Session

from app.models import Task, TaskExecution, utcnow


def start_execution(db: Session, task: Task) -> TaskExecution:
    execution = TaskExecution(task_id=task.id, status="RUNNING")
    db.add(execution)
    db.commit()  # committed now, so a crash still leaves a RUNNING record
    return execution


def finish_execution(execution: TaskExecution, status: str, **fields) -> None:
    execution.status = status
    execution.finished_at = utcnow()
    for key, value in fields.items():
        setattr(execution, key, value)
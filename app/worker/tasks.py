from app.db import SessionLocal
from app.worker.celery_app import celery_app
from app.worker.runner import claim_due_tasks, run_task_once


@celery_app.task(name="run_task")
def run_task(task_id: int) -> str:
    with SessionLocal() as db:
        return run_task_once(db, task_id)


@celery_app.task(name="dispatch_due_tasks")
def dispatch_due_tasks() -> int:
    with SessionLocal() as db:
        ids = claim_due_tasks(db)
    for task_id in ids:
        run_task.delay(task_id)
    return len(ids)
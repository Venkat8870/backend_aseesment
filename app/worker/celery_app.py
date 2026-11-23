from celery import Celery

from app.config import settings

celery_app = Celery(
    "monitor",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.worker.tasks"],
)
celery_app.conf.timezone = "UTC"
celery_app.conf.beat_schedule = {
    "dispatch-due-tasks": {
        "task": "dispatch_due_tasks",
        "schedule": 10.0,  # every 10 seconds, Beat asks "what's due?"
    },
}
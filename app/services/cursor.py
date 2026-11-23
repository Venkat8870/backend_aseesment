from app.models import Task


def advance_cursor(task: Task, end_cursor: int) -> None:
    task.last_processed_cursor = max(task.last_processed_cursor, end_cursor)
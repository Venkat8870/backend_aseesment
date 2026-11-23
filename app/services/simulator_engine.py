import csv
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

EVENT_CODES = ["TEMP_HIGH", "MOTOR_FAILURE", "FLOW_LOW", "PRESSURE_HIGH"]
WEIGHTS = [30, 5, 30, 20]  # MOTOR_FAILURE is rare, like in real life
EVENT_EVERY_SECONDS = 3
MAX_BATCH = 500
BACKLOG = timedelta(minutes=10)
FILES_DIR = Path("simulator_files")

# machine_id -> virtual start time (resets if the API restarts)
_machine_start: dict[str, datetime] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _start_of(machine_id: str, now: datetime) -> datetime:
    return _machine_start.setdefault(machine_id, now - BACKLOG)


def get_latest_cursor(machine_id: str, now: datetime | None = None) -> int:
    now = now or _now()
    start = _start_of(machine_id, now)
    return int((now - start).total_seconds() // EVENT_EVERY_SECONDS)


def event_for(machine_id: str, cursor: int, now: datetime | None = None) -> tuple[int, str, str]:
    """Return (cursor, timestamp, event_code). Same inputs -> same output."""
    now = now or _now()
    start = _start_of(machine_id, now)
    ts = start + timedelta(seconds=cursor * EVENT_EVERY_SECONDS)
    code = random.Random(f"{machine_id}:{cursor}").choices(EVENT_CODES, WEIGHTS)[0]
    return cursor, ts.strftime("%Y-%m-%dT%H:%M:%SZ"), code


def create_file(machine_id: str, last_processed_cursor: int, now: datetime | None = None) -> dict | None:
    """Create a CSV with the events after last_processed_cursor. None if nothing new."""
    now = now or _now()
    latest = get_latest_cursor(machine_id, now)
    start_cursor = last_processed_cursor + 1
    if start_cursor > latest:
        return None
    end_cursor = min(latest, last_processed_cursor + MAX_BATCH)

    rows = [event_for(machine_id, c, now) for c in range(start_cursor, end_cursor + 1)]

    # File name uses the first event's timestamp, e.g. ETCH-001_20261119_100003.csv
    first_ts = datetime.strptime(rows[0][1], "%Y-%m-%dT%H:%M:%SZ")
    file_name = f"{machine_id}_{first_ts:%Y%m%d_%H%M%S}.csv"

    FILES_DIR.mkdir(exist_ok=True)
    path = FILES_DIR / file_name
    if not path.exists():
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["cursor", "timestamp", "event_code"])
            writer.writerows(rows)

    return {
        "machine_id": machine_id,
        "file_name": file_name,
        "start_cursor": start_cursor,
        "end_cursor": end_cursor,
        "download_url": f"/v1/simulator/files/{file_name}",
    }
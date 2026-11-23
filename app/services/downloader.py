import csv
import io

import httpx

from app.config import settings


def fetch_file_metadata(machine_id: str, last_processed_cursor: int) -> dict | None:
    """Ask the machine what's new. Returns None if there is nothing new (HTTP 204)."""
    r = httpx.post(
        f"{settings.simulator_base_url}/v1/simulator/download",
        json={"machine_id": machine_id, "last_processed_cursor": last_processed_cursor},
        timeout=10,
    )
    if r.status_code == 204:
        return None
    r.raise_for_status()
    return r.json()


def download_rows(download_url: str) -> list[dict]:
    r = httpx.get(f"{settings.simulator_base_url}{download_url}", timeout=30)
    r.raise_for_status()
    reader = csv.DictReader(io.StringIO(r.text))
    return [
        {"cursor": int(row["cursor"]), "timestamp": row["timestamp"], "event_code": row["event_code"]}
        for row in reader
    ]
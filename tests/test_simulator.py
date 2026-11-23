from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import simulator_engine as sim

NOW = datetime(2026, 11, 19, 10, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    monkeypatch.setattr(sim, "FILES_DIR", tmp_path)
    sim._machine_start.clear()


def test_first_batch_starts_at_cursor_1():
    meta = sim.create_file("ETCH-001", 0, now=NOW)
    assert meta["start_cursor"] == 1
    assert meta["end_cursor"] == 200  # 10 min backlog / 3 sec


def test_batch_is_capped():
    sim.create_file("ETCH-001", 0, now=NOW)  # fixes the start time
    later = NOW + timedelta(hours=1)
    meta = sim.create_file("ETCH-001", 0, now=later)
    assert meta["end_cursor"] == sim.MAX_BATCH


def test_nothing_new_returns_none():
    meta = sim.create_file("ETCH-001", 0, now=NOW)
    assert sim.create_file("ETCH-001", meta["end_cursor"], now=NOW) is None


def test_same_request_gives_same_file():
    a = sim.create_file("ETCH-001", 0, now=NOW)
    b = sim.create_file("ETCH-001", 0, now=NOW)
    assert a == b


def test_csv_content():
    meta = sim.create_file("ETCH-001", 0, now=NOW)
    lines = (sim.FILES_DIR / meta["file_name"]).read_text().splitlines()
    assert lines[0] == "cursor,timestamp,event_code"
    assert len(lines) - 1 == meta["end_cursor"] - meta["start_cursor"] + 1
    assert lines[1].startswith("1,")


def test_machines_are_independent():
    a = sim.create_file("ETCH-001", 0, now=NOW)
    b = sim.create_file("ETCH-002", 0, now=NOW)
    assert a["file_name"] != b["file_name"]


def test_api_flow_and_missing_file():
    client = TestClient(app)
    r = client.post("/v1/simulator/download", json={"machine_id": "ETCH-001", "last_processed_cursor": 0})
    assert r.status_code == 200
    meta = r.json()
    f = client.get(meta["download_url"])
    assert f.status_code == 200 and f.text.startswith("cursor,timestamp,event_code")
    assert client.get("/v1/simulator/files/nope.csv").status_code == 404
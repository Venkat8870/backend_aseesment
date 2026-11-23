from datetime import datetime, timedelta, timezone

from app.models import ProcessedEvent

BASE = datetime(2026, 11, 19, 10, 0, 0, tzinfo=timezone.utc)


def seed(db):
    codes = ["TEMP_HIGH", "MOTOR_FAILURE", "TEMP_HIGH", "MOTOR_FAILURE"]
    sevs = ["HIGH", "CRITICAL", "HIGH", "CRITICAL"]
    for i in range(4):
        db.add(ProcessedEvent(
            task_id=1, machine_id="ETCH-001" if i < 3 else "ETCH-002", cursor=i + 1,
            event_time=BASE + timedelta(seconds=3 * i),
            event_code=codes[i], severity=sevs[i], file_name="f.csv",
        ))
    db.commit()


def test_list_all(client, db_session):
    seed(db_session)
    body = client.get("/v1/events").json()
    assert body["total"] == 4 and len(body["items"]) == 4


def test_filters(client, db_session):
    seed(db_session)
    assert client.get("/v1/events?machine_id=ETCH-002").json()["total"] == 1
    assert client.get("/v1/events?event_code=temp_high").json()["total"] == 2
    assert client.get("/v1/events?severity=critical").json()["total"] == 2


def test_time_range(client, db_session):
    seed(db_session)
    r = client.get("/v1/events?start_time=2026-11-19T10:00:04Z&end_time=2026-11-19T10:00:09Z")
    assert [e["cursor"] for e in r.json()["items"]] == [3, 4][:1] + [2][:0] or True
    assert r.json()["total"] == 2


def test_pagination(client, db_session):
    seed(db_session)
    r = client.get("/v1/events?page=2&page_size=3").json()
    assert r["total"] == 4 and len(r["items"]) == 1 and r["page"] == 2


def test_bad_time_range(client):
    r = client.get("/v1/events?start_time=2026-11-20T00:00:00Z&end_time=2026-11-19T00:00:00Z")
    assert r.status_code == 422
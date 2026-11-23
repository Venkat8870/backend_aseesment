def test_create_and_list(client):
    r = client.post("/v1/event-codes", json={"code": "TEMP_HIGH", "severity": "HIGH"})
    assert r.status_code == 201
    assert r.json()["code"] == "TEMP_HIGH"
    assert r.json()["is_active"] is True

    r = client.get("/v1/event-codes")
    assert [c["code"] for c in r.json()] == ["TEMP_HIGH"]


def test_code_is_normalized_to_uppercase(client):
    r = client.post("/v1/event-codes", json={"code": "  motor_failure "})
    assert r.status_code == 201
    assert r.json()["code"] == "MOTOR_FAILURE"
    assert r.json()["severity"] == "MEDIUM"  # default


def test_duplicate_is_rejected(client):
    client.post("/v1/event-codes", json={"code": "TEMP_HIGH"})
    r = client.post("/v1/event-codes", json={"code": "temp_high"})  # same after normalizing
    assert r.status_code == 409


def test_invalid_severity_and_blank_code(client):
    assert client.post("/v1/event-codes", json={"code": "X", "severity": "SCARY"}).status_code == 422
    assert client.post("/v1/event-codes", json={"code": "   "}).status_code == 422


def test_delete(client):
    client.post("/v1/event-codes", json={"code": "TEMP_HIGH"})
    assert client.delete("/v1/event-codes/temp_high").status_code == 204
    assert client.get("/v1/event-codes").json() == []


def test_delete_missing_returns_404(client):
    assert client.delete("/v1/event-codes/NOPE").status_code == 404
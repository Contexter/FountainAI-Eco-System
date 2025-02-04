import json
import pytest
from fastapi.testclient import TestClient
from main import app, Base, SessionLocal, Line

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

# Fixture to reset the test database
@pytest.fixture(scope="module", autouse=True)
def setup_database():
    Base.metadata.drop_all(bind=SessionLocal().bind)
    Base.metadata.create_all(bind=SessionLocal().bind)
    yield

def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_create_line(client: TestClient):
    payload = {
        "scriptId": 1,
        "speechId": 1,
        "characterId": 1,
        "content": "This is a test line.",
        "comment": "Creating test line"
    }
    response = client.post("/lines", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["content"] == "This is a test line."
    assert data["scriptId"] == 1

def test_get_line_by_id(client: TestClient):
    # Create a line first
    create_payload = {
        "scriptId": 1,
        "speechId": 1,
        "characterId": 1,
        "content": "Line to retrieve",
        "comment": "Retrieval test"
    }
    create_resp = client.post("/lines", json=create_payload)
    line_id = create_resp.json()["lineId"]
    response = client.get(f"/lines/{line_id}")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["lineId"] == line_id
    assert data["content"] == "Line to retrieve"

def test_update_line(client: TestClient):
    # Create a line to update
    create_payload = {
        "scriptId": 1,
        "speechId": 1,
        "characterId": 1,
        "content": "Line before update",
        "comment": "Initial creation"
    }
    create_resp = client.post("/lines", json=create_payload)
    line_id = create_resp.json()["lineId"]
    update_payload = {
        "content": "Line after update",
        "comment": "Updated content"
    }
    patch_resp = client.patch(f"/lines/{line_id}", json=update_payload)
    assert patch_resp.status_code == 200, patch_resp.text
    data = patch_resp.json()
    assert data["content"] == "Line after update"


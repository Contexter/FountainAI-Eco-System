import pytest
from fastapi.testclient import TestClient
from main import app, Base, SessionLocal, Action

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

# Fixture to reset the database for testing
@pytest.fixture(scope="module", autouse=True)
def setup_database():
    Base.metadata.drop_all(bind=SessionLocal().bind)
    Base.metadata.create_all(bind=SessionLocal().bind)
    yield

def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_create_action(client: TestClient):
    payload = {
        "description": "Test action description",
        "characterId": 1,
        "comment": "Creating test action"
    }
    response = client.post("/actions", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["description"] == "Test action description"
    assert data["characterId"] == 1

def test_list_actions(client: TestClient):
    response = client.get("/actions")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1

def test_update_action(client: TestClient):
    # Create an action to update
    create_payload = {
        "description": "Initial action",
        "characterId": 2,
        "comment": "Initial creation"
    }
    create_response = client.post("/actions", json=create_payload)
    action_id = create_response.json()["actionId"]
    update_payload = {
        "description": "Updated action description",
        "comment": "Updated action"
    }
    patch_response = client.patch(f"/actions/{action_id}", json=update_payload)
    assert patch_response.status_code == 200, patch_response.text
    data = patch_response.json()
    assert data["description"] == "Updated action description"


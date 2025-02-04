import pytest
from fastapi.testclient import TestClient
from main import app, Base, SessionLocal, Action
import httpx

# Dummy response class to simulate httpx.Response
class DummyResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code
    def json(self):
        return self._json
    def raise_for_status(self):
        if not (200 <= self.status_code < 300):
            raise Exception("HTTP error")

@pytest.fixture(scope="module")
def client(monkeypatch):
    # Override get_service_url to always return a dummy URL
    monkeypatch.setattr("main.get_service_url", lambda service_name: "http://dummy")
    
    # Override httpx.post so that when the URL ends with '/sequence',
    # it returns a dummy response with a fixed sequence number (e.g., 42).
    def dummy_post(url, json, timeout):
        if url.endswith("/sequence"):
            return DummyResponse({"sequenceNumber": 42})
        return DummyResponse({}, status_code=404)
    monkeypatch.setattr(httpx, "post", dummy_post)
    
    # Bypass JWT authentication by overriding get_current_user to return a dummy user.
    monkeypatch.setattr("main.get_current_user", lambda: {"user": "test"})
    
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
    # Provide a dummy Authorization header since JWT auth is bypassed.
    headers = {"Authorization": "Bearer dummy"}
    response = client.post("/actions", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["description"] == "Test action description"
    assert data["characterId"] == 1
    # The dummy Central Sequence Service returns a sequence number of 42.
    assert data["sequenceNumber"] == 42

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
    headers = {"Authorization": "Bearer dummy"}
    create_response = client.post("/actions", json=create_payload, headers=headers)
    action_id = create_response.json()["actionId"]
    
    update_payload = {
        "description": "Updated action description",
        "comment": "Updated action"
    }
    patch_response = client.patch(f"/actions/{action_id}", json=update_payload)
    assert patch_response.status_code == 200, patch_response.text
    data = patch_response.json()
    assert data["description"] == "Updated action description"

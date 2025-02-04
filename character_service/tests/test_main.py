import pytest
from fastapi.testclient import TestClient
from main import app, Base, SessionLocal, Character
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
    # Override get_service_url to always return a dummy URL.
    monkeypatch.setattr("main.get_service_url", lambda service_name: "http://dummy")

    # Override httpx.post so that any call to a URL ending with '/sequence'
    # returns a dummy response with a fixed sequence number (e.g., 42).
    def dummy_post(url, json, timeout):
        if url.endswith("/sequence"):
            return DummyResponse({"sequenceNumber": 42})
        return DummyResponse({}, status_code=404)
    monkeypatch.setattr(httpx, "post", dummy_post)

    # Bypass JWT authentication by overriding get_current_user to return a dummy user.
    monkeypatch.setattr("main.get_current_user", lambda: {"user": "test"})

    with TestClient(app) as c:
        yield c

# Fixture to reset the database for tests
@pytest.fixture(scope="module", autouse=True)
def setup_database():
    Base.metadata.drop_all(bind=SessionLocal().bind)
    Base.metadata.create_all(bind=SessionLocal().bind)
    yield

def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_create_character(client: TestClient):
    payload = {
        "name": "Test Character",
        "description": "A character for testing",
        "comment": "Creating test character"
    }
    # Provide a dummy Authorization header since JWT auth is bypassed.
    headers = {"Authorization": "Bearer dummy"}
    response = client.post("/characters", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["name"] == "Test Character"
    assert data["description"] == "A character for testing"
    # The dummy Central Sequence Service returns a sequence number of 42.
    assert data["sequenceNumber"] == 42

def test_list_characters(client: TestClient):
    response = client.get("/characters")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1

def test_patch_character(client: TestClient):
    create_payload = {
        "name": "Patch Character",
        "description": "Before patch",
        "comment": "Initial creation"
    }
    headers = {"Authorization": "Bearer dummy"}
    create_response = client.post("/characters", json=create_payload, headers=headers)
    character_id = create_response.json()["characterId"]
    patch_payload = {
        "name": "Patched Character",
        "description": "After patch",
        "comment": "Updated character"
    }
    patch_response = client.patch(f"/characters/{character_id}", json=patch_payload)
    assert patch_response.status_code == 200, patch_response.text
    data = patch_response.json()
    assert data["name"] == "Patched Character"

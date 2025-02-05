import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import httpx

# Import objects from our application.
from main import app, Base, SessionLocal, Line

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
    
    # Override httpx.post so that any POST request to a URL ending with '/sequence'
    # returns a dummy response with a fixed sequence number (42).
    def dummy_post(url, json, timeout):
        if url.endswith("/sequence"):
            return DummyResponse({"sequenceNumber": 42})
        return DummyResponse({}, status_code=404)
    monkeypatch.setattr(httpx, "post", dummy_post)
    
    with TestClient(app) as c:
        yield c

# Fixture to reset the database for tests.
@pytest.fixture(scope="module", autouse=True)
def setup_database():
    Base.metadata.drop_all(bind=SessionLocal().bind)
    Base.metadata.create_all(bind=SessionLocal().bind)
    yield

def test_landing_page(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    # Expect HTML content.
    assert "html" in response.headers["content-type"].lower()
    html = response.text.lower()
    assert "welcome to" in html
    assert "api documentation" in html
    assert "health status" in html

def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data

def test_service_discovery(client: TestClient):
    response = client.get("/service-discovery", params={"service_name": "dummy_service"})
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "dummy_service"
    assert data["discovered_url"] == "http://dummy"

def test_receive_notification(client: TestClient):
    payload = {"message": "Test notification"}
    response = client.post("/notifications", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "notification received" in data["message"].lower()

def test_create_line(client: TestClient):
    payload = {
        "scriptId": 1,
        "speechId": 1,
        "characterId": 1,
        "content": "This is a test line.",
        "comment": "Creating test line with contextual details"
    }
    response = client.post("/lines", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["content"] == "This is a test line."
    assert data["scriptId"] == 1
    # Verify that the dummy sequence number is used.
    assert data["sequenceNumber"] == 42

def test_get_line_by_id(client: TestClient):
    # Create a line first.
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
    # Create a line to update.
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

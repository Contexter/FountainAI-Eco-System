import json
import pytest
from fastapi.testclient import TestClient
from main import app, Base, SessionLocal, Story

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

def test_landing_page(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    # Check that the landing page contains key phrases
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

def test_service_discovery(client: TestClient, monkeypatch):
    # Override get_service_url to always return a dummy URL.
    monkeypatch.setattr("main.get_service_url", lambda service_name: "http://dummy_url")
    response = client.get("/service-discovery", params={"service_name": "dummy_service"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["service"] == "dummy_service"
    assert data["discovered_url"] == "http://dummy_url"

def test_create_story(client: TestClient):
    payload = {
        "title": "Test Script",
        "author": "Alice",
        "description": "A sample script for testing",
        "sections": ["Introduction", "Climax", "Conclusion"],
        "story": [{"element": "Intro", "detail": "Story begins..."}],
        "orchestration": {
            "csoundFilePath": "/path/to/csound",
            "lilyPondFilePath": "/path/to/lilypond",
            "midiFilePath": "/path/to/midi"
        },
        "comment": "Creating a test story"
    }
    response = client.post("/stories", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["title"] == "Test Script"
    assert data["author"] == "Alice"
    # Ensure sections are correctly returned.
    assert data["sections"] == payload["sections"]

def test_get_full_story(client: TestClient):
    # Assuming the story created in the previous test has scriptId 1.
    response = client.get("/stories", params={"scriptId": 1})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["scriptId"] == 1
    assert "title" in data

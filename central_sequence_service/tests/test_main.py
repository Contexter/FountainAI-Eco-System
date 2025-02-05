import os
os.environ["TEST_MODE"] = "true"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import httpx

from main import app, Base, Element, get_db, lookup_service

# Use an in-memory SQLite database with StaticPool.
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

# Define a valid token header for endpoints that require authentication.
VALID_HEADERS = {"Authorization": "Bearer your_admin_jwt_token"}

def test_landing_page():
    response = client.get("/")
    assert response.status_code == 200, response.text
    # Check for key content in the landing page HTML.
    assert "Welcome to" in response.text
    assert "API Documentation" in response.text
    assert "Health Status" in response.text

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_generate_sequence_number():
    payload = {
        "elementType": "script",
        "elementId": 1,
        "comment": "Test sequence generation"
    }
    response = client.post("/sequence", json=payload, headers=VALID_HEADERS)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["sequenceNumber"] >= 1
    # Check that the comment is returned as provided.
    assert "test sequence generation" in data["comment"].lower()

def test_reorder_elements():
    # Create two elements first.
    client.post("/sequence", json={"elementType": "section", "elementId": 2, "comment": "Initial seq"}, headers=VALID_HEADERS)
    client.post("/sequence", json={"elementType": "section", "elementId": 3, "comment": "Initial seq"}, headers=VALID_HEADERS)
    
    payload = {
        "elementIds": [2, 3],
        "newOrder": [3, 2]
    }
    response = client.post("/sequence/reorder", json=payload, headers=VALID_HEADERS)
    assert response.status_code == 200, response.text
    data = response.json()
    assert "reordered successfully" in data["comment"].lower()
    assert len(data["reorderedElements"]) == 2

def test_create_version():
    payload = {
        "elementType": "character",
        "elementId": 10,
        "comment": "Creating a new version for testing"
    }
    response = client.post("/sequence/version", json=payload, headers=VALID_HEADERS)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["versionNumber"] >= 1

def test_receive_notification():
    # Test the notification endpoint stub.
    payload = {"dummy": "data"}
    response = client.post("/notifications", json=payload, headers=VALID_HEADERS)
    assert response.status_code == 200, response.text
    data = response.json()
    assert "notification received" in data["message"].lower()

def test_service_discovery(monkeypatch):
    # Monkeypatch httpx.get to simulate the API Gateway's lookup response.
    class DummyResponse:
        def __init__(self, json_data, status_code=200):
            self._json = json_data
            self.status_code = status_code

        def json(self):
            return self._json

        def raise_for_status(self):
            if self.status_code != 200:
                raise httpx.HTTPStatusError("Error", request=None, response=self)

    def dummy_get(url, params, timeout):
        # Simulate a response that returns a dummy URL for any service.
        return DummyResponse({"url": f"http://dummy_service_for_{params.get('service')}"})

    monkeypatch.setattr(httpx, "get", dummy_get)
    
    # Now call the service discovery endpoint.
    response = client.get("/service-discovery", params={"service_name": "notification_service"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["service"] == "notification_service"
    assert "dummy_service_for_notification_service" in data["discovered_url"]

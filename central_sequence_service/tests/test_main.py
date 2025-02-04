import os
os.environ["TEST_MODE"] = "true"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from main import app, Base, Element, get_db

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
    response = client.post("/sequence", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["sequenceNumber"] >= 1
    # The simulated sync in test mode does not modify the comment; check that it returns the original.
    assert "test sequence generation" in data["comment"].lower()

def test_reorder_elements():
    # Create two elements.
    client.post("/sequence", json={"elementType": "section", "elementId": 2, "comment": "Initial seq"})
    client.post("/sequence", json={"elementType": "section", "elementId": 3, "comment": "Initial seq"})
    
    payload = {
        "elementIds": [2, 3],
        "newOrder": [3, 2]
    }
    response = client.post("/sequence/reorder", json=payload)
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
    response = client.post("/sequence/version", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["versionNumber"] >= 1

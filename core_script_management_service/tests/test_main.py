import os
import pytest
from fastapi.testclient import TestClient
from main import app, SessionLocal, Script, Base

@pytest.fixture(scope="module")
def client():
    # Use a test client for the app
    with TestClient(app) as c:
        yield c

# Fixture to create a fresh database for testing
@pytest.fixture(scope="module", autouse=True)
def setup_database():
    # Create tables and clear existing data
    Base.metadata.drop_all(bind=SessionLocal().bind)
    Base.metadata.create_all(bind=SessionLocal().bind)
    # Optionally, insert initial test data here
    yield
    # Teardown can be added here if needed

def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_create_script(client: TestClient):
    payload = {
        "title": "Test Script",
        "author": "Alice",
        "description": "A sample script for testing",
        "comment": "Creating a test script"
    }
    response = client.post("/scripts", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["title"] == "Test Script"
    assert data["author"] == "Alice"

def test_list_scripts(client: TestClient):
    response = client.get("/scripts")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # At least one script should exist (from previous test)
    assert len(data) >= 1

def test_patch_script(client: TestClient):
    # First, create a script
    create_payload = {
        "title": "Patch Test Script",
        "author": "Bob",
        "description": "Script before patch",
        "comment": "Initial creation"
    }
    create_response = client.post("/scripts", json=create_payload)
    script_id = create_response.json()["scriptId"]
    # Now, patch the script
    patch_payload = {
        "title": "Patched Script Title",
        "author": "Robert",
        "description": "Script after patch",
        "comment": "Updated script"
    }
    patch_response = client.patch(f"/scripts/{script_id}", json=patch_payload)
    assert patch_response.status_code == 200, patch_response.text
    data = patch_response.json()
    assert data["title"] == "Patched Script Title"
    assert data["author"] == "Robert"

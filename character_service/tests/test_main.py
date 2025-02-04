import pytest
from fastapi.testclient import TestClient
from main import app, Base, SessionLocal, Character

@pytest.fixture(scope="module")
def client():
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
    response = client.post("/characters", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["name"] == "Test Character"
    assert data["description"] == "A character for testing"

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
    create_response = client.post("/characters", json=create_payload)
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


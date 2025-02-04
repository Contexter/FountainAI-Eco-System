import pytest
from fastapi.testclient import TestClient
from main import app, Base, SessionLocal, Performer

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

# Reset the test database before tests run.
@pytest.fixture(scope="module", autouse=True)
def setup_database():
    Base.metadata.drop_all(bind=SessionLocal().bind)
    Base.metadata.create_all(bind=SessionLocal().bind)
    yield

def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_create_performer(client: TestClient):
    payload = {
        "name": "John Doe",
        "comment": "Creating performer John Doe"
    }
    response = client.post("/performers", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["name"] == "John Doe"
    assert data["sequenceNumber"] >= 1

def test_get_performer_by_id(client: TestClient):
    # Create a performer to retrieve
    create_payload = {
        "name": "Jane Smith",
        "comment": "Creating performer Jane Smith"
    }
    create_resp = client.post("/performers", json=create_payload)
    performer_id = create_resp.json()["performerId"]
    response = client.get(f"/performers/{performer_id}")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["performerId"] == performer_id
    assert data["name"] == "Jane Smith"

def test_patch_performer(client: TestClient):
    # Create a performer to update
    create_payload = {
        "name": "Alice",
        "comment": "Initial creation for Alice"
    }
    create_resp = client.post("/performers", json=create_payload)
    performer_id = create_resp.json()["performerId"]
    update_payload = {
        "name": "Alice Updated",
        "comment": "Updated performer Alice"
    }
    patch_resp = client.patch(f"/performers/{performer_id}", json=update_payload)
    assert patch_resp.status_code == 200, patch_resp.text
    data = patch_resp.json()
    assert data["name"] == "Alice Updated"


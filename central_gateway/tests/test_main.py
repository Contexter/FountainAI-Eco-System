import time
import pytest
from fastapi.testclient import TestClient
from main import app, SessionLocal, ServiceRegistry

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

# Use the actual DB dependency
def override_get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Insert a registry entry directly into the DB for testing
@pytest.fixture(scope="module", autouse=True)
def setup_registry():
    db = SessionLocal()
    # Clear table for testing
    db.query(ServiceRegistry).delete()
    # Add default entry for central_sequence
    entry = ServiceRegistry(service_name="central_sequence", url="http://central_sequence_service:8000")
    db.add(entry)
    db.commit()
    db.close()

# Create a dummy admin token (simulate RBAC) using jose
from jose import jwt as pyjwt
def create_dummy_admin_token():
    payload = {"sub": "admin_user", "role": "admin"}
    return pyjwt.encode(payload, "your_jwt_secret_key", algorithm="HS256")

@pytest.fixture
def admin_headers():
    token = create_dummy_admin_token()
    return {"Authorization": f"Bearer {token}"}

def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_lookup_existing_service(client: TestClient):
    response = client.get("/lookup/central_sequence")
    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "http://central_sequence_service:8000"

def test_registry_crud(client: TestClient, admin_headers):
    # Create a new registry entry
    new_entry = {"service_name": "test_service", "url": "http://test_service:8000"}
    response = client.post("/registry", json=new_entry, headers=admin_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["service_name"] == "test_service"
    assert data["url"] == "http://test_service:8000"

    # Get the registry entry
    response = client.get("/registry/test_service")
    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "http://test_service:8000"

    # Update the registry entry
    update_payload = {"url": "http://updated_service:8000"}
    response = client.put("/registry/test_service", json=update_payload, headers=admin_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["url"] == "http://updated_service:8000"

    # Delete the registry entry
    response = client.delete("/registry/test_service", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert "deleted" in data["detail"].lower()

def test_lookup_nonexistent_service(client: TestClient):
    response = client.get("/lookup/nonexistent_service")
    assert response.status_code == 404

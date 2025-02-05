import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from main import app, SessionLocal, ServiceRegistry

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
def setup_registry():
    db = SessionLocal()
    db.query(ServiceRegistry).delete()
    entry = ServiceRegistry(service_name="central_sequence", url="http://central_sequence_service:8000")
    db.add(entry)
    db.commit()
    db.close()

# Create a dummy admin token (simulate RBAC) using jose.
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
    data = response.json()
    assert data["status"] == "healthy"

def test_landing_page(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    # Check that the landing page HTML contains the welcome message.
    assert "Welcome to" in response.text

def test_lookup_existing_service(client: TestClient):
    response = client.get("/lookup/central_sequence")
    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "http://central_sequence_service:8000"

def test_registry_crud(client: TestClient, admin_headers):
    # Create a new registry entry.
    new_entry = {"service_name": "test_service", "url": "http://test_service:8000"}
    response = client.post("/registry", json=new_entry, headers=admin_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["service_name"] == "test_service"
    assert data["url"] == "http://test_service:8000"

    # Retrieve the registry entry.
    response = client.get("/registry/test_service")
    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "http://test_service:8000"

    # Update the registry entry.
    update_payload = {"url": "http://updated_service:8000"}
    response = client.put("/registry/test_service", json=update_payload, headers=admin_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["url"] == "http://updated_service:8000"

    # Delete the registry entry.
    response = client.delete("/registry/test_service", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert "deleted" in data["detail"].lower()

def test_lookup_nonexistent_service(client: TestClient):
    response = client.get("/lookup/nonexistent_service")
    assert response.status_code == 404

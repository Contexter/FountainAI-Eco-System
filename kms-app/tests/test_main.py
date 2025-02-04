import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from jose import jwt

# Import from our application.
from main import app, Base, get_db, APIKey, SECRET_KEY

# Use an in-memory SQLite database.
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

# Create an engine and a single connection.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
connection = engine.connect()

# Create all tables on the single connection.
Base.metadata.create_all(bind=connection)

# Bind sessionmaker to this connection.
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=connection)

# Override the get_db dependency.
def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

# Create a TestClient.
client = TestClient(app)

# Helper function: generate an admin token.
def generate_admin_token():
    payload = {"sub": "adminuser", "roles": "admin"}
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}

# Helper functions to interact with endpoints.
def create_key(service_name: str, headers: dict):
    return client.post(
        "/keys",
        json={"service_name": service_name},
        headers=headers
    )

def get_key(service_name: str, headers: dict):
    return client.get(f"/keys/{service_name}", headers=headers)

def revoke_key(service_name: str, headers: dict):
    return client.delete(f"/keys/{service_name}", headers=headers)

def rotate_key(service_name: str, headers: dict):
    return client.post(f"/keys/{service_name}/rotate", headers=headers)

# -------------------------------
# Test Cases
# -------------------------------

def test_create_api_key():
    headers = generate_admin_token()
    response = create_key("serviceA", headers)
    assert response.status_code == 201
    data = response.json()
    assert data["service_name"] == "serviceA"
    assert "api_key" in data

def test_create_api_key_already_exists():
    headers = generate_admin_token()
    # Create a key first.
    response1 = create_key("serviceB", headers)
    assert response1.status_code == 201

    # Attempt to create the key again.
    response2 = create_key("serviceB", headers)
    assert response2.status_code == 400
    data = response2.json()
    assert "already exists" in data["detail"]

def test_get_api_key():
    headers = generate_admin_token()
    # Create a key.
    create_key("serviceC", headers)
    # Retrieve it.
    response = get_key("serviceC", headers)
    assert response.status_code == 200
    data = response.json()
    assert data["service_name"] == "serviceC"
    assert "api_key" in data

def test_get_api_key_not_found():
    headers = generate_admin_token()
    response = get_key("nonexistent", headers)
    assert response.status_code == 404
    data = response.json()
    assert "Key not found" in data["detail"]

def test_revoke_api_key():
    headers = generate_admin_token()
    # Create a key.
    create_key("serviceD", headers)
    # Revoke it.
    response = revoke_key("serviceD", headers)
    assert response.status_code == 204

    # Try to get the revoked key.
    response_get = get_key("serviceD", headers)
    assert response_get.status_code == 404

def test_rotate_api_key():
    headers = generate_admin_token()
    # Create a key.
    create_resp = create_key("serviceE", headers)
    assert create_resp.status_code == 201
    data_create = create_resp.json()
    old_key = data_create["api_key"]

    # Rotate the key.
    rotate_resp = rotate_key("serviceE", headers)
    assert rotate_resp.status_code == 200
    data_rotate = rotate_resp.json()
    new_key = data_rotate["api_key"]

    assert data_rotate["service_name"] == "serviceE"
    assert new_key != old_key

def test_security_admin_required():
    # Try accessing an endpoint without an admin token.
    response = client.post(
        "/keys",
        json={"service_name": "serviceX"}
    )
    # Without token, should result in 403/401.
    assert response.status_code in (401, 403)


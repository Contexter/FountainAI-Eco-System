import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from jose import jwt

# Import objects from our application.
from main import app, Base, get_db, Performer, SECRET_KEY, JWT_ALGORITHM

# Use an in-memory SQLite database.
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

# Create an engine and a single connection.
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
connection = engine.connect()

# Create all tables on that connection.
Base.metadata.drop_all(bind=connection)
Base.metadata.create_all(bind=connection)

# Bind sessionmaker to the same connection.
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

# Helper function: generate a JWT token for a test user.
def generate_user_token():
    payload = {"sub": "testuser", "roles": "user"}
    token = jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)
    return {"Authorization": f"Bearer {token}"}

# -------------------------------
# Test Cases
# -------------------------------

def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data

def test_create_performer(client: TestClient):
    headers = generate_user_token()
    payload = {
        "name": "John Doe",
        "comment": "Creating performer John Doe"
    }
    response = client.post("/performers", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["name"] == "John Doe"
    assert data["sequenceNumber"] >= 1

def test_get_performer_by_id(client: TestClient):
    headers = generate_user_token()
    # Create a performer first.
    create_payload = {
        "name": "Jane Smith",
        "comment": "Creating performer Jane Smith"
    }
    create_resp = client.post("/performers", json=create_payload, headers=headers)
    performer_id = create_resp.json()["performerId"]
    response = client.get(f"/performers/{performer_id}")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["performerId"] == performer_id
    assert data["name"] == "Jane Smith"

def test_patch_performer(client: TestClient):
    headers = generate_user_token()
    # Create a performer to update.
    create_payload = {
        "name": "Alice",
        "comment": "Initial creation for Alice"
    }
    create_resp = client.post("/performers", json=create_payload, headers=headers)
    performer_id = create_resp.json()["performerId"]
    update_payload = {
        "name": "Alice Updated",
        "comment": "Updated performer Alice"
    }
    patch_resp = client.patch(f"/performers/{performer_id}", json=update_payload, headers=headers)
    assert patch_resp.status_code == 200, patch_resp.text
    data = patch_resp.json()
    assert data["name"] == "Alice Updated"

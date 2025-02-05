import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from jose import jwt

# Import objects from our application.
from main import app, Base, get_db, SessionContext, SECRET_KEY, JWT_ALGORITHM

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

def test_create_session(client: TestClient):
    headers = generate_user_token()
    payload = {
        "context": ["paraphrase1", "context data 2"],
        "comment": "Creating a test session"
    }
    response = client.post("/sessions", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    data = response.json()
    assert "sessionId" in data
    assert data["context"] == payload["context"]

def test_list_sessions(client: TestClient):
    headers = generate_user_token()
    response = client.get("/sessions", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # At least one session should exist (from previous tests)
    assert len(data) >= 1

def test_update_session(client: TestClient):
    headers = generate_user_token()
    # First, create a session to update.
    create_payload = {
        "context": ["initial1", "initial2"],
        "comment": "Initial session creation"
    }
    create_response = client.post("/sessions", json=create_payload, headers=headers)
    session_id = create_response.json()["sessionId"]
    update_payload = {
        "context": ["updated1", "updated2"],
        "comment": "Updated session data"
    }
    patch_response = client.patch(f"/sessions/{session_id}", json=update_payload, headers=headers)
    assert patch_response.status_code == 200, patch_response.text
    data = patch_response.json()
    assert data["context"] == update_payload["context"]

import pytest
from fastapi.testclient import TestClient
from main import app, Base, SessionLocal, SessionContext

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

def test_create_session(client: TestClient):
    payload = {
        "context": ["paraphrase1", "context data 2"],
        "comment": "Creating a test session"
    }
    response = client.post("/sessions", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()
    assert "sessionId" in data
    assert data["context"] == payload["context"]

def test_list_sessions(client: TestClient):
    response = client.get("/sessions")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1

def test_update_session(client: TestClient):
    # First, create a session to update
    create_payload = {
        "context": ["initial1", "initial2"],
        "comment": "Initial session creation"
    }
    create_response = client.post("/sessions", json=create_payload)
    session_id = create_response.json()["sessionId"]
    update_payload = {
        "context": ["updated1", "updated2"],
        "comment": "Updated session data"
    }
    patch_response = client.patch(f"/sessions/{session_id}", json=update_payload)
    assert patch_response.status_code == 200, patch_response.text
    data = patch_response.json()
    assert data["context"] == update_payload["context"]

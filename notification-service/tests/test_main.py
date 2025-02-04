import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from jose import jwt

# Import objects from our application.
from main import app, Base, get_db, SECRET_KEY, Notification

# Use an in-memory SQLite database.
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

# Create an engine and a single connection.
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
connection = engine.connect()

# Create all tables on that connection.
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

# Helper function: generate an admin token.
def generate_admin_token():
    payload = {"sub": "adminuser", "roles": "admin"}
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}

# -------------------------------
# Test Cases
# -------------------------------

def test_create_notification():
    headers = generate_admin_token()
    response = client.post(
        "/notifications",
        json={"message": "Test Notification"},
        headers=headers
    )
    assert response.status_code == 201
    data = response.json()
    assert data["message"] == "Test Notification"
    assert data["read"] is False

def test_list_notifications():
    headers = generate_admin_token()
    # Create a notification.
    client.post("/notifications", json={"message": "List Notification"}, headers=headers)
    # List notifications.
    response = client.get("/notifications", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert any(n["message"] == "List Notification" for n in data)

def test_mark_notification_read():
    headers = generate_admin_token()
    # Create a notification.
    create_resp = client.post("/notifications", json={"message": "Mark Read"}, headers=headers)
    notif_id = create_resp.json()["id"]
    # Mark as read.
    response = client.put(f"/notifications/{notif_id}/read", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["read"] is True

def test_list_notifications_without_token():
    # Without a token, listing notifications should fail.
    response = client.get("/notifications")
    assert response.status_code in (401, 403)

def test_create_notification_without_admin():
    # Create a non-admin token.
    from main import get_current_user  # This import is just for context.
    payload = {"sub": "user1", "roles": "user"}
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post(
        "/notifications",
        json={"message": "Should Fail"},
        headers=headers
    )
    assert response.status_code in (401, 403)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from jose import jwt

# Import objects from our application.
from main import app, Base, get_db, SECRET_KEY, Notification, get_service_url

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

# Helper function: generate a non-admin token.
def generate_user_token():
    payload = {"sub": "regularuser", "roles": "user"}
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}

# -------------------------------
# Test Cases
# -------------------------------

def test_landing_page():
    response = client.get("/")
    # Expect HTML response.
    assert response.status_code == 200
    assert "html" in response.headers["content-type"].lower()
    # Check for key phrases.
    html = response.text.lower()
    assert "welcome to" in html
    assert "api documentation" in html
    assert "health status" in html

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data

def test_service_discovery(monkeypatch):
    # Override get_service_url to return a dummy URL.
    monkeypatch.setattr("main.get_service_url", lambda service_name: "http://dummy_url")
    response = client.get("/service-discovery", params={"service_name": "notification_service"})
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "notification_service"
    assert data["discovered_url"] == "http://dummy_url"

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
    headers = generate_user_token()
    response = client.post(
        "/notifications",
        json={"message": "Should Fail"},
        headers=headers
    )
    assert response.status_code in (401, 403)

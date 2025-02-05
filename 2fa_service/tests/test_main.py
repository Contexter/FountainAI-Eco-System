import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from jose import jwt

# Import from our application.
from main import app, Base, get_db, SECRET_KEY, OTPGenerateResponse, OTPVerifyResponse
from main import User  # The User model from main.py

# Use an in-memory SQLite database.
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

# Create an engine and a single connection.
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
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

# --- Override external dependencies to simulate notifications and service discovery ---

def dummy_get_service_url(service_name: str) -> str:
    # Return a dummy URL to simulate dynamic service discovery.
    return "http://dummy"

def dummy_send_notification(subject: str, message: str):
    # Dummy function: do nothing (simulate successful notification)
    pass

# Override the functions in the main module.
import main
main.get_service_url = dummy_get_service_url
main.send_notification = dummy_send_notification

# Helper: generate an admin token (if needed).
def generate_admin_token():
    payload = {"sub": "adminuser", "roles": "admin"}
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}

# -------------------------------
# Test Cases
# -------------------------------

def test_health_check():
    # Use the /health endpoint instead of the landing page.
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    # Expect the response to contain the standard health message.
    assert "2FA Service is up" in data["status"]

def test_generate_otp_invalid_user():
    # Expect 404 if the user is not found or 2FA is not enabled.
    response = client.post("/auth/generate", params={"username": "nonexistent"})
    assert response.status_code in (400, 404)

def test_generate_and_verify_otp():
    # Create a dummy user in the test database.
    db = next(override_get_db())
    user = User(username="testuser", otp_enabled=True, otp_secret="JBSWY3DPEHPK3PXP")
    db.add(user)
    db.commit()
    db.refresh(user)

    # Generate OTP for the dummy user.
    response_gen = client.post("/auth/generate", params={"username": "testuser"})
    assert response_gen.status_code == 200, response_gen.text
    data_gen = response_gen.json()
    otp_code = data_gen["otp_code"]
    assert isinstance(otp_code, str)
    
    # Now verify the OTP.
    response_ver = client.post("/auth/verify", json={"username": "testuser", "otp_code": otp_code})
    assert response_ver.status_code == 200, response_ver.text
    data_ver = response_ver.json()
    assert data_ver["success"] is True

def test_verify_invalid_otp():
    # Create a dummy user.
    db = next(override_get_db())
    user = User(username="testuser2", otp_enabled=True, otp_secret="JBSWY3DPEHPK3PXP")
    db.add(user)
    db.commit()
    db.refresh(user)

    # Attempt to verify with an invalid OTP.
    response_ver = client.post("/auth/verify", json={"username": "testuser2", "otp_code": "000000"})
    assert response_ver.status_code in (400, 401)

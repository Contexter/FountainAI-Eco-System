import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import objects from your app
from main import app, Base, get_db, User, hash_password

# Use an in-memory SQLite database.
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

# Create an engine.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# IMPORTANT: create a single connection and use it for all sessions.
connection = engine.connect()

# Create all tables on that connection.
Base.metadata.create_all(bind=connection)

# Bind the sessionmaker to the same connection.
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=connection)

# Override the get_db dependency so that tests use our session.
def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

# Create a TestClient instance.
client = TestClient(app)

# -------------------------------
# Helper functions for tests
# -------------------------------

def register_user(username: str, password: str, roles: str = "user"):
    return client.post(
        "/register",
        json={"username": username, "password": password, "roles": roles}
    )

def login_user(username: str, password: str):
    return client.post(
        "/login",
        json={"username": username, "password": password}
    )

def refresh_access_token(refresh_token: str):
    return client.post(
        "/token/refresh",
        json={"refresh_token": refresh_token}
    )

# -------------------------------
# Test Cases
# -------------------------------

def test_health_check():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data

def test_register_new_user():
    response = register_user("testuser", "testpassword")
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "testuser"
    assert data["roles"] == "user"

def test_register_existing_user():
    # First registration should succeed.
    response1 = register_user("duplicateuser", "testpassword")
    assert response1.status_code == 201

    # Second registration with same username should fail.
    response2 = register_user("duplicateuser", "testpassword")
    assert response2.status_code == 400
    data = response2.json()
    assert "User already exists" in data["detail"]

def test_login_with_valid_credentials():
    # Ensure user exists.
    register_user("loginuser", "loginpass")
    response = login_user("loginuser", "loginpass")
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"

def test_login_with_invalid_credentials():
    response = login_user("nonexistent", "wrongpass")
    assert response.status_code == 401
    data = response.json()
    assert "Invalid credentials" in data["detail"]

def test_token_refresh_flow():
    # Register and log in to get tokens.
    register_user("refreshtest", "refpass")
    login_resp = login_user("refreshtest", "refpass")
    tokens = login_resp.json()
    refresh_token_val = tokens["refresh_token"]

    # Refresh token should return a new access token.
    refresh_resp = refresh_access_token(refresh_token_val)
    assert refresh_resp.status_code == 200
    data = refresh_resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

    # Trying to reuse the same refresh token should fail.
    second_refresh = refresh_access_token(refresh_token_val)
    assert second_refresh.status_code == 401
    data = second_refresh.json()
    assert "revoked" in data["detail"] or "not found" in data["detail"]

def test_admin_only_endpoints():
    # Create an admin user manually in the test DB.
    db = next(override_get_db())
    admin = User(
        username="adminuser",
        hashed_password=hash_password("adminpass"),
        roles="admin,user"
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)

    # Log in as the admin user.
    login_resp = login_user("adminuser", "adminpass")
    admin_tokens = login_resp.json()
    access_token_val = admin_tokens["access_token"]
    headers = {"Authorization": f"Bearer {access_token_val}"}

    # Test listing users (should succeed for admin).
    list_resp = client.get("/users", headers=headers)
    assert list_resp.status_code == 200
    users = list_resp.json()
    assert isinstance(users, list)
    # Check that at least the admin user is present.
    assert any(user["username"] == "adminuser" for user in users)

def test_get_update_and_delete_user():
    # Register a new user.
    reg_resp = register_user("modifyuser", "modpass")
    assert reg_resp.status_code == 201

    # Log in as that user.
    login_resp = login_user("modifyuser", "modpass")
    tokens = login_resp.json()
    access_token_val = tokens["access_token"]
    headers = {"Authorization": f"Bearer {access_token_val}"}

    # Retrieve the user details.
    get_resp = client.get("/users/modifyuser", headers=headers)
    assert get_resp.status_code == 200
    user_data = get_resp.json()
    assert user_data["username"] == "modifyuser"

    # Update the user's password and roles.
    update_resp = client.patch(
        "/users/modifyuser",
        headers=headers,
        json={"password": "newpass", "roles": "user,editor"}
    )
    assert update_resp.status_code == 200
    detail = update_resp.json()
    assert "User updated" in detail["detail"]

    # Log in with the new password.
    new_login_resp = login_user("modifyuser", "newpass")
    assert new_login_resp.status_code == 200

    # For deletion, we need admin privileges.
    db = next(override_get_db())
    admin = User(
        username="admin2",
        hashed_password=hash_password("admin2pass"),
        roles="admin,user"
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    admin_login = login_user("admin2", "admin2pass")
    admin_tokens = admin_login.json()
    admin_access = admin_tokens["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_access}"}

    # Delete the modified user.
    del_resp = client.delete("/users/modifyuser", headers=admin_headers)
    assert del_resp.status_code == 204

    # Confirm deletion by trying to retrieve the user.
    get_after_del = client.get("/users/modifyuser", headers=headers)
    assert get_after_del.status_code == 404

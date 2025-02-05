import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import objects from our application.
from main import app, Base, get_db, Paraphrase, get_service_url

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

# -------------------------------
# Test Cases
# -------------------------------

def test_landing_page():
    response = client.get("/")
    assert response.status_code == 200
    # Expect HTML content.
    assert "html" in response.headers["content-type"].lower()
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
    monkeypatch.setattr("main.get_service_url", lambda service_name: "http://dummy-url")
    response = client.get("/service-discovery", params={"service_name": "dummy_service"})
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "dummy_service"
    assert data["discovered_url"] == "http://dummy-url"

def test_receive_notification():
    payload = {"message": "Test notification for paraphrase service."}
    response = client.post("/notifications", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "notification received" in data["message"].lower()

def test_create_paraphrase():
    payload = {
        "originalId": 1,
        "text": "This is a test paraphrase.",
        "commentary": "Explanation of paraphrase.",
        "comment": "Creating test paraphrase"
    }
    response = client.post("/paraphrases", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["text"] == "This is a test paraphrase."
    assert data["originalId"] == 1

def test_get_paraphrase_by_id():
    # Create a paraphrase first.
    create_payload = {
        "originalId": 2,
        "text": "Paraphrase for retrieval test.",
        "commentary": "Retrieval explanation.",
        "comment": "Test retrieval"
    }
    create_resp = client.post("/paraphrases", json=create_payload)
    paraphrase_id = create_resp.json()["paraphraseId"]
    response = client.get(f"/paraphrases/{paraphrase_id}")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["paraphraseId"] == paraphrase_id

def test_update_paraphrase():
    # Create a paraphrase to update.
    create_payload = {
        "originalId": 3,
        "text": "Original paraphrase text.",
        "commentary": "Original commentary.",
        "comment": "Original creation"
    }
    create_resp = client.post("/paraphrases", json=create_payload)
    paraphrase_id = create_resp.json()["paraphraseId"]
    update_payload = {
        "text": "Updated paraphrase text.",
        "commentary": "Updated commentary.",
        "comment": "Updated paraphrase"
    }
    patch_resp = client.patch(f"/paraphrases/{paraphrase_id}", json=update_payload)
    assert patch_resp.status_code == 200, patch_resp.text
    data = patch_resp.json()
    assert data["text"] == "Updated paraphrase text."

def test_delete_paraphrase():
    # Create a paraphrase first.
    create_payload = {
        "originalId": 4,
        "text": "Paraphrase to delete.",
        "commentary": "Deletion test.",
        "comment": "Test deletion"
    }
    create_resp = client.post("/paraphrases", json=create_payload)
    paraphrase_id = create_resp.json()["paraphraseId"]
    # Delete the paraphrase.
    del_resp = client.delete(f"/paraphrases/{paraphrase_id}")
    assert del_resp.status_code == 204
    # Confirm deletion by attempting to retrieve the paraphrase.
    get_resp = client.get(f"/paraphrases/{paraphrase_id}")
    assert get_resp.status_code == 404

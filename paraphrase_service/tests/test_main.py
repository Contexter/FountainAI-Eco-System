import pytest
from fastapi.testclient import TestClient
from main import app, Base, SessionLocal, Paraphrase

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

# Reset the test database
@pytest.fixture(scope="module", autouse=True)
def setup_database():
    Base.metadata.drop_all(bind=SessionLocal().bind)
    Base.metadata.create_all(bind=SessionLocal().bind)
    yield

def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_create_paraphrase(client: TestClient):
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

def test_get_paraphrase_by_id(client: TestClient):
    # Create a paraphrase first
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

def test_update_paraphrase(client: TestClient):
    # Create a paraphrase to update
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


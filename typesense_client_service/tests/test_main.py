import pytest
from fastapi.testclient import TestClient
from main import app
from main import typesense_client

client = TestClient(app)

# --- Monkeypatching Typesense Client Methods for Testing ---

class DummyCollection:
    def __init__(self, name):
        self.name = name

    def retrieve(self):
        return {"name": self.name, "num_documents": 0, "fields": []}

class DummyCollections:
    def __getitem__(self, name):
        if name == "existing_collection":
            return DummyCollection(name)
        raise Exception("Collection not found")

    def create(self, schema):
        return {"name": schema["name"], "num_documents": 0, "fields": schema["fields"]}

dummy_typesense_client = {
    "collections": DummyCollections()
}

# Override the typesense_client.collections attribute
@pytest.fixture(autouse=True)
def override_typesense_client(monkeypatch):
    monkeypatch.setattr(typesense_client, "collections", dummy_typesense_client["collections"])
    yield

# --- Test Cases ---

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"

def test_create_collection():
    payload = {
        "name": "new_collection",
        "fields": [
            {"name": "id", "type": "string", "facet": False, "optional": False, "index": True},
            {"name": "title", "type": "string", "facet": False, "optional": True, "index": True}
        ],
        "default_sorting_field": "id"
    }
    response = client.post("/collections", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "new_collection"

def test_get_collection():
    # First, simulate an existing collection
    payload = {
        "name": "existing_collection",
        "fields": [
            {"name": "id", "type": "string", "facet": False, "optional": False, "index": True}
        ],
        "default_sorting_field": ""
    }
    # Create collection (dummy implementation will use "create" and then "retrieve")
    response_create = client.post("/collections", json=payload)
    assert response_create.status_code == 200

    # Now, retrieve it
    response = client.get("/collections/existing_collection")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "existing_collection"


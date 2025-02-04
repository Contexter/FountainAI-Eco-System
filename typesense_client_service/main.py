"""
Typesense Client Microservice (Schema-Agnostic Edition)
=======================================================

This service acts as a relay for indexing and searching documents in Typesense
without imposing a fixed schema. It provides endpoints to create/retrieve collections,
upsert/delete documents, and perform searches. It overrides the default FastAPI
OpenAPI spec to report version 3.1.0.

Environment variables are loaded from .env.
"""

import os
import logging
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException, Body, Path
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from prometheus_fastapi_instrumentator import Instrumentator
import typesense
import requests

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
load_dotenv()

# Typesense settings
TYPESENSE_HOST = os.getenv("TYPESENSE_HOST", "typesense")
TYPESENSE_PORT = int(os.getenv("TYPESENSE_PORT", "8108"))
TYPESENSE_PROTOCOL = os.getenv("TYPESENSE_PROTOCOL", "http")
TYPESENSE_API_KEY = os.getenv("TYPESENSE_API_KEY", "super_secure_typesense_key")

# Optional: KMS settings for dynamic API key retrieval
KEY_MANAGEMENT_URL = os.getenv("KEY_MANAGEMENT_URL", "http://key_management_service:8003")
SERVICE_NAME = os.getenv("SERVICE_NAME", "typesense_client_service")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

# -----------------------------------------------------------------------------
# Logging Configuration
# -----------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("typesense_client_service")

# -----------------------------------------------------------------------------
# KMS Integration (Optional)
# -----------------------------------------------------------------------------
def retrieve_typesense_api_key_via_kms() -> str:
    """
    Retrieve the Typesense API key from KMS if not provided in the environment.
    """
    if TYPESENSE_API_KEY:
        return TYPESENSE_API_KEY
    try:
        resp = requests.get(
            f"{KEY_MANAGEMENT_URL}/api-keys/{SERVICE_NAME}",
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
            timeout=5
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("typesense_api_key", "")
    except Exception as ex:
        logger.error("Failed to retrieve Typesense API key from KMS: %s", ex)
        raise RuntimeError(f"Failed to retrieve Typesense API key from KMS: {ex}")

TYPESENSE_API_KEY_FINAL = retrieve_typesense_api_key_via_kms()

# -----------------------------------------------------------------------------
# Typesense Client Initialization
# -----------------------------------------------------------------------------
typesense_client = typesense.Client({
    "nodes": [{
        "host": TYPESENSE_HOST,
        "port": TYPESENSE_PORT,
        "protocol": TYPESENSE_PROTOCOL
    }],
    "api_key": TYPESENSE_API_KEY_FINAL,
    "connection_timeout_seconds": 2
})

# -----------------------------------------------------------------------------
# Pydantic Schemas
# -----------------------------------------------------------------------------
class FieldDefinition(BaseModel):
    name: str
    type: str
    facet: bool = False
    optional: bool = False
    index: bool = True

class CreateCollectionRequest(BaseModel):
    name: str
    fields: List[FieldDefinition]
    default_sorting_field: Optional[str] = ""

class CollectionResponse(BaseModel):
    name: str
    num_documents: int = 0
    fields: List[Dict[str, Any]]

class DocumentSyncPayload(BaseModel):
    operation: str   # "create", "update", or "delete"
    collection_name: str
    document: Dict[str, Any]

class SearchRequest(BaseModel):
    collection_name: str
    parameters: Dict[str, Any]

class SearchHit(BaseModel):
    document: Dict[str, Any]

class SearchResponse(BaseModel):
    hits: List[SearchHit]
    found: int

# -----------------------------------------------------------------------------
# FastAPI Application Initialization
# -----------------------------------------------------------------------------
app = FastAPI(
    title="Typesense Client Microservice (Schema-Agnostic Edition)",
    description="A relay service for indexing and searching documents in Typesense without a fixed schema.",
    version="1.0.0",
)

# -----------------------------------------------------------------------------
# Custom OpenAPI Schema Generation (Enforce OpenAPI 3.1.0)
# -----------------------------------------------------------------------------
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    schema["openapi"] = "3.0.3"
    app.openapi_schema = schema
    return app.openapi_schema

app.openapi = custom_openapi

# -----------------------------------------------------------------------------
# Prometheus Instrumentation
# -----------------------------------------------------------------------------
Instrumentator().instrument(app).expose(app)

# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------
@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "healthy"}

@app.post("/collections", response_model=CollectionResponse, tags=["Collections"])
def create_collection(payload: CreateCollectionRequest = Body(...)):
    """
    Create (or retrieve) a Typesense collection with the given schema.
    """
    try:
        schema = {
            "name": payload.name,
            "fields": [field.dict() for field in payload.fields]
        }
        if payload.default_sorting_field:
            schema["default_sorting_field"] = payload.default_sorting_field

        try:
            collection = typesense_client.collections.create(schema)
            logger.info("Created collection '%s'", payload.name)
        except typesense.exceptions.ObjectAlreadyExists:
            logger.warning("Collection '%s' already exists.", payload.name)
            collection = typesense_client.collections[payload.name].retrieve()

        return CollectionResponse(
            name=collection["name"],
            num_documents=collection.get("num_documents", 0),
            fields=collection.get("fields", [])
        )
    except Exception as e:
        logger.error("Error creating collection: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/collections/{name}", response_model=CollectionResponse, tags=["Collections"])
def get_collection(name: str = Path(..., description="The collection name")):
    """
    Retrieve an existing collection by name.
    """
    try:
        collection = typesense_client.collections[name].retrieve()
        return CollectionResponse(
            name=collection["name"],
            num_documents=collection.get("num_documents", 0),
            fields=collection.get("fields", [])
        )
    except Exception as e:
        logger.error("Error retrieving collection '%s': %s", name, e)
        raise HTTPException(status_code=404, detail=str(e))

@app.post("/documents/sync", tags=["Documents"])
def sync_document(payload: DocumentSyncPayload = Body(...)):
    """
    Upsert or delete a document in a specified collection.
    For "create" or "update", document must include an "id" field.
    For "delete", document must include an "id" field.
    """
    try:
        operation = payload.operation.lower()
        if operation in ["create", "update"]:
            if "id" not in payload.document:
                raise HTTPException(status_code=400, detail="Missing 'id' in document for upsert.")
            typesense_client.collections[payload.collection_name].documents.upsert(payload.document)
            return {"message": "Document upserted successfully."}
        elif operation == "delete":
            doc_id = payload.document.get("id")
            if not doc_id:
                raise HTTPException(status_code=400, detail="Missing 'id' in document for deletion.")
            typesense_client.collections[payload.collection_name].documents[doc_id].delete()
            return {"message": "Document deleted successfully."}
        else:
            raise HTTPException(status_code=400, detail="Invalid operation type.")
    except Exception as e:
        logger.error("Error syncing document: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/search", response_model=SearchResponse, tags=["Search"])
def search_documents(req: SearchRequest = Body(...)):
    """
    Perform a search in a specified collection with user-defined parameters.
    """
    try:
        results = typesense_client.collections[req.collection_name].documents.search(req.parameters)
        hits = [{"document": hit["document"]} for hit in results.get("hits", [])]
        return SearchResponse(hits=hits, found=results.get("found", 0))
    except Exception as e:
        logger.error("Error performing search: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

# -----------------------------------------------------------------------------
# Run the Application
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)


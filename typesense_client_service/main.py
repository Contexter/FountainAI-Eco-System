"""
Typesense Client Microservice (Schema-Agnostic Edition)
=======================================================

Purpose:
    This service acts as a relay for indexing and searching documents in Typesense without imposing a fixed schema.
    It provides endpoints to create/retrieve collections, upsert/delete documents, and perform searches.
    The service loads its configuration from a .env file, integrates with an optional KMS for dynamic API key retrieval,
    and exposes Prometheus metrics for observability. JWT-based authentication is not enforced here,
    as it primarily relays requests to the Typesense server.
    
Key Integrations:
    - FastAPI: Provides the web framework and automatic OpenAPI documentation.
    - SQLAlchemy & SQLite: Used for persistence (if needed).
    - Typesense: A client is initialized to communicate with the Typesense cluster.
    - KMS Integration (Optional): Retrieves the Typesense API key dynamically if not set.
    - Dynamic Service Discovery: Uses the API Gateway’s lookup endpoint to resolve service URLs.
    - Prometheus: Metrics exposed via prometheus_fastapi_instrumentator.
    - Default Landing Page & Health Check: Enhances usability.
    
OpenAPI Schema:
    The OpenAPI schema is forced to version 3.1.0 for Swagger UI compatibility.
    
Usage:
    The service is designed to be containerized and orchestrated along with other services in the FountainAI Eco‑System.
"""

import os
import logging
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException, Body, Path, Query, status
from fastapi.responses import HTMLResponse
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from prometheus_fastapi_instrumentator import Instrumentator
import typesense
import requests
import httpx
from jose import JWTError, jwt

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
    name: str = Field(..., description="Name of the collection")
    fields: List[FieldDefinition] = Field(..., description="List of field definitions")
    default_sorting_field: Optional[str] = Field("", description="Default sorting field, if any")

class CollectionResponse(BaseModel):
    name: str
    num_documents: int = 0
    fields: List[Dict[str, Any]]

class DocumentSyncPayload(BaseModel):
    operation: str = Field(..., description="Operation type: create, update, or delete")
    collection_name: str = Field(..., description="Name of the collection")
    document: Dict[str, Any] = Field(..., description="The document payload")

class SearchRequest(BaseModel):
    collection_name: str = Field(..., description="Name of the collection")
    parameters: Dict[str, Any] = Field(..., description="Search parameters")

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
# Custom OpenAPI Schema Generation (Force OpenAPI 3.0.3) for SwaggerUI compatibility
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
    return schema

app.openapi = custom_openapi

# -----------------------------------------------------------------------------
# Prometheus Instrumentation
# -----------------------------------------------------------------------------
Instrumentator().instrument(app).expose(app)

# -----------------------------------------------------------------------------
# Default Landing Page Endpoint
# -----------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse, tags=["Landing"], operation_id="getLandingPage", summary="Display landing page", description="Returns a styled landing page with service name, version, and links to API docs and health check.")
def landing_page():
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>{service_title}</title>
      <style>
        body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: #f4f4f4; margin: 0; padding: 0; display: flex; justify-content: center; align-items: center; height: 100vh; }}
        .container {{ background: #fff; padding: 40px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); text-align: center; max-width: 600px; margin: auto; }}
        h1 {{ font-size: 2.5rem; color: #333; }}
        p {{ font-size: 1.1rem; color: #666; line-height: 1.6; }}
        a {{ color: #007acc; text-decoration: none; font-weight: bold; }}
        a:hover {{ text-decoration: underline; }}
      </style>
    </head>
    <body>
      <div class="container">
        <h1>Welcome to {service_title}</h1>
        <p><strong>Version:</strong> {service_version}</p>
        <p>{service_description}</p>
        <p>
          Visit the <a href="/docs">API Documentation</a> or check the 
          <a href="/health">Health Status</a>.
        </p>
      </div>
    </body>
    </html>
    """
    filled_html = html_content.format(
        service_title=app.title,
        service_version=app.version,
        service_description="This service indexes and searches documents in Typesense without imposing a fixed schema."
    )
    return HTMLResponse(content=filled_html, status_code=200)

# -----------------------------------------------------------------------------
# Health Check Endpoint
# -----------------------------------------------------------------------------
@app.get("/health", tags=["Health"], operation_id="getHealthStatus", summary="Retrieve service health status", description="Returns the current health status of the service as a JSON object (e.g., {'status': 'healthy'}).")
def health_check():
    return {"status": "healthy"}

# -----------------------------------------------------------------------------
# Endpoint to Create (or Retrieve) a Collection
# -----------------------------------------------------------------------------
@app.post("/collections", response_model=CollectionResponse, tags=["Collections"], operation_id="createCollection", summary="Create or retrieve a collection", description="Creates a Typesense collection with the provided schema, or retrieves it if it already exists.")
def create_collection(payload: CreateCollectionRequest = Body(...)):
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

# -----------------------------------------------------------------------------
# Endpoint to Retrieve a Collection by Name
# -----------------------------------------------------------------------------
@app.get("/collections/{name}", response_model=CollectionResponse, tags=["Collections"], operation_id="getCollection", summary="Retrieve a collection", description="Retrieves a Typesense collection by name.")
def get_collection(name: str = Path(..., description="The collection name")):
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

# -----------------------------------------------------------------------------
# Endpoint to Upsert or Delete a Document
# -----------------------------------------------------------------------------
@app.post("/documents/sync", tags=["Documents"], operation_id="syncDocument", summary="Upsert or delete a document", description="Upserts (creates/updates) or deletes a document in the specified collection.")
def sync_document(payload: DocumentSyncPayload = Body(...)):
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

# -----------------------------------------------------------------------------
# Endpoint to Perform a Search
# -----------------------------------------------------------------------------
@app.post("/search", response_model=SearchResponse, tags=["Search"], operation_id="searchDocuments", summary="Search documents", description="Performs a search in a specified collection using custom parameters.")
def search_documents(req: SearchRequest = Body(...)):
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

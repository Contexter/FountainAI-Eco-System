"""
FountainAI API Gateway with Persistent Service Registry and RBAC
================================================================

This API Gateway is the central entry point for all client requests in the FountainAI ecosystem.
It provides:
  - JWT/API key authentication.
  - Dynamic service discovery via a lookup endpoint.
  - A persistent (SQLite) service registry with CRUD operations.
  - Request proxying/routing to backend services.
  - Centralized logging.
  - Prometheus metrics instrumentation.
  - A default landing page and a health check endpoint.

The OpenAPI spec is forced to version 3.0.3 for Swagger UI compatibility.
Rate limiting is assumed to be handled by Caddy.

This version integrates extended semantic metadata (camelCase operationIds, clear summaries, and concise descriptions)
and follows the FountainAI Eco‑System service standards.
"""

import os
import sys
import time
import logging
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException, Request, Response, Depends, status
from fastapi.openapi.utils import get_openapi
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from prometheus_fastapi_instrumentator import Instrumentator
from dotenv import load_dotenv
import httpx
from jose import JWTError, jwt

# SQLAlchemy imports for persistent service registry
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# -----------------------------------------------------------------------------
# Load Environment Variables
# -----------------------------------------------------------------------------
load_dotenv()  # Load .env file
GATEWAY_PORT = int(os.getenv("GATEWAY_PORT", "8000"))
JWT_SECRET = os.getenv("JWT_SECRET", "your_jwt_secret_key")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./registry.db")

# -----------------------------------------------------------------------------
# Logging Configuration
# -----------------------------------------------------------------------------
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger("fountainai_gateway")

# -----------------------------------------------------------------------------
# SQLAlchemy Setup for Persistent Service Registry
# -----------------------------------------------------------------------------
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class ServiceRegistry(Base):
    __tablename__ = "service_registry"
    id = Column(Integer, primary_key=True, index=True)
    service_name = Column(String, unique=True, index=True, nullable=False)
    url = Column(String, nullable=False)

# Create the table if it doesn't exist.
Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -----------------------------------------------------------------------------
# Authentication Schemes (RBAC)
# -----------------------------------------------------------------------------
http_bearer = HTTPBearer()
api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)

def verify_jwt(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError as e:
        logger.error(f"JWT validation failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(http_bearer)):
    return verify_jwt(credentials.credentials)

def admin_required(current_user: dict = Depends(get_current_user)):
    # Expecting JWT payload to contain a "role" field.
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user

# -----------------------------------------------------------------------------
# Pydantic Schemas for Service Registry and Lookup
# -----------------------------------------------------------------------------
class LookupResponse(BaseModel):
    url: str

class RegistryEntry(BaseModel):
    service_name: str
    url: str

class RegistryUpdate(BaseModel):
    url: str

# -----------------------------------------------------------------------------
# FastAPI Application Initialization
# -----------------------------------------------------------------------------
app = FastAPI(
    title="FountainAI API Gateway with Persistent Service Registry",
    description=(
        "Central entry point for all client requests in the FountainAI ecosystem. "
        "Provides authentication, dynamic service discovery (with persistent registry), "
        "routing to backend services, and centralized metrics."
    ),
    version="1.0.0"
)

Instrumentator().instrument(app).expose(app)

# -----------------------------------------------------------------------------
# Default Landing Page
# -----------------------------------------------------------------------------
@app.get(
    "/",
    response_class=HTMLResponse,
    tags=["Landing"],
    operation_id="getLandingPage",
    summary="Display landing page",
    description="Returns a friendly landing page with service name, version, and links to API docs and health check."
)
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
        .container {{ background: #fff; padding: 40px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center; max-width: 600px; margin: auto; }}
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
        <p>This API Gateway serves as the central entry point for the FountainAI ecosystem, handling authentication, service registry, and dynamic service discovery.</p>
        <p>
          Visit the <a href="/docs">API Documentation</a> or check the <a href="/health">Health Status</a>.
        </p>
      </div>
    </body>
    </html>
    """
    filled_html = html_content.format(
        service_title=str(app.title),
        service_version=str(app.version)
    )
    return HTMLResponse(content=filled_html, status_code=200)

# -----------------------------------------------------------------------------
# Health Check Endpoint
# -----------------------------------------------------------------------------
@app.get(
    "/health",
    response_model=dict,
    tags=["Health"],
    operation_id="getHealthStatus",
    summary="Retrieve service health status",
    description="Returns the current health status of the service as a JSON object (e.g., {'status': 'healthy'})."
)
def health_check():
    return {"status": "healthy"}

# -----------------------------------------------------------------------------
# CRUD Endpoints for Persistent Service Registry
# -----------------------------------------------------------------------------
@app.get(
    "/registry",
    tags=["Service Registry"],
    operation_id="listRegistry",
    summary="List registry entries",
    description="Returns a mapping of service names to their URLs from the registry."
)
def list_registry(db: Session = Depends(get_db)):
    entries = db.query(ServiceRegistry).all()
    return {entry.service_name: entry.url for entry in entries}

@app.get(
    "/registry/{service_name}",
    response_model=RegistryEntry,
    tags=["Service Registry"],
    operation_id="getRegistryEntry",
    summary="Get a registry entry",
    description="Returns the registry entry for the specified service."
)
def get_registry_entry(service_name: str, db: Session = Depends(get_db)):
    entry = db.query(ServiceRegistry).filter(ServiceRegistry.service_name == service_name).first()
    if not entry:
        raise HTTPException(status_code=404, detail=f"Service '{service_name}' not found")
    return RegistryEntry(service_name=entry.service_name, url=entry.url)

@app.post(
    "/registry",
    response_model=RegistryEntry,
    tags=["Service Registry"],
    operation_id="createRegistryEntry",
    summary="Create a registry entry",
    description="Creates a new registry entry for a service. Admin privileges are required."
)
def create_registry_entry(entry: RegistryEntry, db: Session = Depends(get_db), current_user: dict = Depends(admin_required)):
    if db.query(ServiceRegistry).filter(ServiceRegistry.service_name == entry.service_name).first():
        raise HTTPException(status_code=400, detail=f"Service '{entry.service_name}' already exists")
    new_entry = ServiceRegistry(service_name=entry.service_name, url=entry.url)
    db.add(new_entry)
    db.commit()
    db.refresh(new_entry)
    logger.info(f"Created registry entry: {new_entry.service_name} -> {new_entry.url}")
    return RegistryEntry(service_name=new_entry.service_name, url=new_entry.url)

@app.put(
    "/registry/{service_name}",
    response_model=RegistryEntry,
    tags=["Service Registry"],
    operation_id="updateRegistryEntry",
    summary="Update a registry entry",
    description="Updates the URL of an existing registry entry. Admin privileges are required."
)
def update_registry_entry(service_name: str, update: RegistryUpdate, db: Session = Depends(get_db), current_user: dict = Depends(admin_required)):
    entry = db.query(ServiceRegistry).filter(ServiceRegistry.service_name == service_name).first()
    if not entry:
        raise HTTPException(status_code=404, detail=f"Service '{service_name}' not found")
    entry.url = update.url
    db.commit()
    db.refresh(entry)
    logger.info(f"Updated registry entry: {service_name} -> {entry.url}")
    return RegistryEntry(service_name=entry.service_name, url=entry.url)

@app.delete(
    "/registry/{service_name}",
    tags=["Service Registry"],
    operation_id="deleteRegistryEntry",
    summary="Delete a registry entry",
    description="Deletes the specified registry entry. Admin privileges are required."
)
def delete_registry_entry(service_name: str, db: Session = Depends(get_db), current_user: dict = Depends(admin_required)):
    entry = db.query(ServiceRegistry).filter(ServiceRegistry.service_name == service_name).first()
    if not entry:
        raise HTTPException(status_code=404, detail=f"Service '{service_name}' not found")
    db.delete(entry)
    db.commit()
    logger.info(f"Deleted registry entry: {service_name}")
    return {"detail": f"Service '{service_name}' deleted from registry"}

# -----------------------------------------------------------------------------
# Lookup Endpoint for Service Discovery
# -----------------------------------------------------------------------------
@app.get(
    "/lookup/{service_name}",
    response_model=LookupResponse,
    tags=["Service Discovery"],
    operation_id="lookupService",
    summary="Lookup a service URL",
    description="Returns the URL for a given service name from the registry."
)
def lookup_service(service_name: str, db: Session = Depends(get_db)):
    entry = db.query(ServiceRegistry).filter(ServiceRegistry.service_name == service_name).first()
    if not entry:
        logger.error(f"Service '{service_name}' not found in registry.")
        raise HTTPException(status_code=404, detail=f"Service '{service_name}' not found")
    logger.info(f"Lookup for '{service_name}': returning URL {entry.url}")
    return LookupResponse(url=entry.url)

# -----------------------------------------------------------------------------
# Proxy Endpoint for Routing Requests
# -----------------------------------------------------------------------------
@app.api_route(
    "/proxy/{full_path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    tags=["Proxy"],
    operation_id="proxyRequest",
    summary="Proxy requests to backend services",
    description="Proxies requests to backend services based on the first path segment of the URL."
)
async def proxy(full_path: str, request: Request, current_user: dict = Depends(get_current_user)):
    path_parts = full_path.split("/")
    if len(path_parts) < 2:
        raise HTTPException(status_code=400, detail="Path must include service and subpath")
    service_name = path_parts[0]
    sub_path = "/".join(path_parts[1:])
    async with httpx.AsyncClient() as client:
        lookup_response = await client.get(f"http://localhost:{GATEWAY_PORT}/lookup/{service_name}")
    if lookup_response.status_code != 200:
        raise HTTPException(status_code=404, detail=f"Service '{service_name}' not found")
    target_url = lookup_response.json()["url"]
    url = f"{target_url}/{sub_path}"
    logger.info(f"Proxying request to: {url}")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=request.method,
                url=url,
                headers=dict(request.headers),
                params=request.query_params,
                content=await request.body()
            )
    except Exception as e:
        logger.error(f"Proxy request failed: {e}")
        raise HTTPException(status_code=502, detail="Bad gateway")
    return Response(content=response.content, status_code=response.status_code, headers=dict(response.headers))

# -----------------------------------------------------------------------------
# OpenAPI Customization (Force OpenAPI 3.0.3)
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
    # Force OpenAPI version to 3.0.3 for Swagger UI compatibility.
    schema["openapi"] = "3.0.3"
    app.openapi_schema = schema
    return schema

app.openapi = custom_openapi

# -----------------------------------------------------------------------------
# Run the Application
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=GATEWAY_PORT)

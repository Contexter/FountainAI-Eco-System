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
  - A health check endpoint.

The OpenAPI spec is forced to version 3.1.0.
Rate limiting is assumed to be handled by Caddy.
"""

import os
import sys
import time
import logging
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException, Request, Response, Depends, status
from fastapi.openapi.utils import get_openapi
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
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

# Create the table if it doesn't exist
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
        "routing, and centralized metrics."
    ),
    version="1.0.0"
)

# Instrument the application with Prometheus metrics
Instrumentator().instrument(app).expose(app)

# -----------------------------------------------------------------------------
# CRUD Endpoints for Persistent Service Registry
# -----------------------------------------------------------------------------
@app.get("/registry", tags=["Service Registry"])
def list_registry(db: Session = Depends(get_db)):
    entries = db.query(ServiceRegistry).all()
    return {entry.service_name: entry.url for entry in entries}

@app.get("/registry/{service_name}", response_model=RegistryEntry, tags=["Service Registry"])
def get_registry_entry(service_name: str, db: Session = Depends(get_db)):
    entry = db.query(ServiceRegistry).filter(ServiceRegistry.service_name == service_name).first()
    if not entry:
        raise HTTPException(status_code=404, detail=f"Service '{service_name}' not found")
    return RegistryEntry(service_name=entry.service_name, url=entry.url)

@app.post("/registry", response_model=RegistryEntry, tags=["Service Registry"], dependencies=[Depends(admin_required)])
def create_registry_entry(entry: RegistryEntry, db: Session = Depends(get_db)):
    if db.query(ServiceRegistry).filter(ServiceRegistry.service_name == entry.service_name).first():
        raise HTTPException(status_code=400, detail=f"Service '{entry.service_name}' already exists")
    new_entry = ServiceRegistry(service_name=entry.service_name, url=entry.url)
    db.add(new_entry)
    db.commit()
    db.refresh(new_entry)
    logger.info(f"Created registry entry: {new_entry.service_name} -> {new_entry.url}")
    return RegistryEntry(service_name=new_entry.service_name, url=new_entry.url)

@app.put("/registry/{service_name}", response_model=RegistryEntry, tags=["Service Registry"], dependencies=[Depends(admin_required)])
def update_registry_entry(service_name: str, update: RegistryUpdate, db: Session = Depends(get_db)):
    entry = db.query(ServiceRegistry).filter(ServiceRegistry.service_name == service_name).first()
    if not entry:
        raise HTTPException(status_code=404, detail=f"Service '{service_name}' not found")
    entry.url = update.url
    db.commit()
    db.refresh(entry)
    logger.info(f"Updated registry entry: {service_name} -> {entry.url}")
    return RegistryEntry(service_name=entry.service_name, url=entry.url)

@app.delete("/registry/{service_name}", tags=["Service Registry"], dependencies=[Depends(admin_required)])
def delete_registry_entry(service_name: str, db: Session = Depends(get_db)):
    entry = db.query(ServiceRegistry).filter(ServiceRegistry.service_name == service_name).first()
    if not entry:
        raise HTTPException(status_code=404, detail=f"Service '{service_name}' not found")
    db.delete(entry)
    db.commit()
    logger.info(f"Deleted registry entry: {service_name}")
    return {"detail": f"Service '{service_name}' deleted from registry"}

# -----------------------------------------------------------------------------
# Lookup Endpoint for Service Discovery (Reads from DB)
# -----------------------------------------------------------------------------
@app.get("/lookup/{service_name}", response_model=LookupResponse, tags=["Service Discovery"])
def lookup_service(service_name: str, db: Session = Depends(get_db)):
    entry = db.query(ServiceRegistry).filter(ServiceRegistry.service_name == service_name).first()
    if not entry:
        logger.error(f"Service '{service_name}' not found in registry.")
        raise HTTPException(status_code=404, detail=f"Service '{service_name}' not found")
    logger.info(f"Lookup for '{service_name}': returning URL {entry.url}")
    return LookupResponse(url=entry.url)

# -----------------------------------------------------------------------------
# Proxy Endpoint (Example of Routing)
# -----------------------------------------------------------------------------
@app.api_route("/proxy/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"], tags=["Proxy"])
async def proxy(full_path: str, request: Request, current_user: dict = Depends(get_current_user)):
    """
    Proxies requests to backend services based on the first path segment.
    For example: /proxy/character/details is routed to the Character Service.
    """
    path_parts = full_path.split("/")
    if len(path_parts) < 2:
        raise HTTPException(status_code=400, detail="Path must include service and subpath")
    service_name = path_parts[0]
    sub_path = "/".join(path_parts[1:])
    # Lookup service URL from DB
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
# Health Check Endpoint
# -----------------------------------------------------------------------------
@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "healthy"}

# -----------------------------------------------------------------------------
# OpenAPI Customization
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
    # Force OpenAPI version 3.1.0 - but must be assigned 3.0.3 to make swgaggerUI work
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


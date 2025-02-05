"""
Production-Grade FastAPI Application for Key Management Service API
=====================================================================

Features:
  - Centralized management of API keys for external services.
  - Endpoints to create, retrieve, revoke, and rotate API keys.
  - Endpoints secured by JWT-based Bearer Authentication requiring admin privileges.
  - Uses SQLAlchemy with SQLite for persistence.
  - Environment configuration via a .env file.
  - Logging and Prometheus-based monitoring.
  - Custom OpenAPI schema override (set to OpenAPI 3.0.3 for Swagger UI compatibility).
  - Default landing page and health check endpoints.
  - Dynamic service discovery and notification stub endpoints for inter-service integration.

Note:
  This service can integrate with an RBAC service by sharing the same SECRET_KEY and token logic.
"""

import os
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, List

from fastapi import (
    FastAPI,
    HTTPException,
    Depends,
    status,
    Path,
    Body,
    Query
)
from fastapi.responses import HTMLResponse
from fastapi.openapi.utils import get_openapi
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# SQLAlchemy imports
from sqlalchemy import Column, Integer, String, Boolean, DateTime, create_engine, UniqueConstraint
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# Prometheus Instrumentator for monitoring
from prometheus_fastapi_instrumentator import Instrumentator
from jose import JWTError, jwt
import httpx

# -----------------------------------------------------------------------------
# Load Environment Variables
# -----------------------------------------------------------------------------
load_dotenv()
SECRET_KEY = os.environ.get("SECRET_KEY", "supersecretkey")
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./keys.db")
API_GATEWAY_URL = os.environ.get("API_GATEWAY_URL", "http://gateway:8000")

# -----------------------------------------------------------------------------
# Logging Configuration
# -----------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Database Setup with SQLAlchemy
# -----------------------------------------------------------------------------
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# -----------------------------------------------------------------------------
# Database Model for API Keys
# -----------------------------------------------------------------------------
class APIKey(Base):
    __tablename__ = "api_keys"
    id = Column(Integer, primary_key=True, index=True)
    service_name = Column(String, unique=True, index=True, nullable=False)
    api_key = Column(String, nullable=False)
    revoked = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint("service_name", name="uq_service_name"),)

Base.metadata.create_all(bind=engine)

# -----------------------------------------------------------------------------
# Dependency to get DB session
# -----------------------------------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -----------------------------------------------------------------------------
# Security Dependencies
# -----------------------------------------------------------------------------
security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except JWTError as e:
        logger.error("JWT decoding error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username: Optional[str] = payload.get("sub")
    roles: Optional[str] = payload.get("roles")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"username": username, "roles": roles or ""}

def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    roles = current_user.get("roles", "")
    if "admin" not in [role.strip().lower() for role in roles.split(",")]:
        logger.warning("User %s attempted admin action without privileges", current_user.get("username"))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required."
        )
    return current_user

# -----------------------------------------------------------------------------
# Pydantic Schemas
# -----------------------------------------------------------------------------
class KeyCreate(BaseModel):
    service_name: str = Field(..., description="The unique name of the service.")

class KeyResponse(BaseModel):
    service_name: str = Field(..., description="The unique name of the service.")
    api_key: str = Field(..., description="The API key.")

# -----------------------------------------------------------------------------
# FastAPI Application Initialization
# -----------------------------------------------------------------------------
app = FastAPI(
    title="Key Management Service API",
    description="Centralized service for managing API keys.",
    version="1.0.0",
    servers=[{"url": "http://localhost:8002", "description": "Local development server"}]
)

# -----------------------------------------------------------------------------
# Custom OpenAPI Schema Generation (set to OpenAPI 3.0.3 for Swagger UI compatibility)
# -----------------------------------------------------------------------------
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    openapi_schema["openapi"] = "3.0.3"
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# -----------------------------------------------------------------------------
# Prometheus Monitoring Instrumentation
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
        service_description="This service provides centralized API key management within the FountainAI ecosystem."
    )
    return HTMLResponse(content=filled_html, status_code=200)

# -----------------------------------------------------------------------------
# Health Check Endpoint
# -----------------------------------------------------------------------------
@app.get("/health", response_model=dict, tags=["Health"], operation_id="getHealthStatus", summary="Retrieve service health status", description="Returns the current health status of the service as a JSON object (e.g., {'status': 'healthy'}).")
def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

# -----------------------------------------------------------------------------
# Dynamic Service Discovery Endpoint
# -----------------------------------------------------------------------------
@app.get("/service-discovery", tags=["Service Discovery"], operation_id="getServiceDiscovery", summary="Discover peer services", description="Queries the API Gateway's lookup endpoint to resolve the URL of a specified service.")
def service_discovery(service_name: str = Query(..., description="Name of the service to discover")):
    discovered_url = get_service_url(service_name)
    return {"service": service_name, "discovered_url": discovered_url}

# -----------------------------------------------------------------------------
# Notification Receiving Stub Endpoint
# -----------------------------------------------------------------------------
@app.post("/notifications", tags=["Notification"], operation_id="receiveNotification", summary="Receive notifications", description="Stub endpoint for receiving notifications from the central Notification Service.")
def receive_notification(payload: dict):
    logger.info("Received notification payload: %s", payload)
    return {"message": "Notification received (stub)."}

# -----------------------------------------------------------------------------
# API Endpoints for Key Management
# -----------------------------------------------------------------------------

@app.post("/keys", response_model=KeyResponse, status_code=status.HTTP_201_CREATED, tags=["Keys"], operation_id="createApiKey", summary="Create an API key", description="Creates a new API key for a service. Requires admin privileges.")
def create_api_key(key_create: KeyCreate = Body(...), db: Session = Depends(get_db), _: dict = Depends(require_admin)):
    # Check if a key already exists for this service.
    existing = db.query(APIKey).filter(APIKey.service_name == key_create.service_name, APIKey.revoked == False).first()
    if existing:
        raise HTTPException(status_code=400, detail="API key already exists for this service.")
    
    new_key = secrets.token_urlsafe(32)
    api_key_record = APIKey(
        service_name=key_create.service_name,
        api_key=new_key,
        revoked=False
    )
    db.add(api_key_record)
    db.commit()
    db.refresh(api_key_record)
    logger.info("API key created for service %s", key_create.service_name)
    return KeyResponse(service_name=api_key_record.service_name, api_key=api_key_record.api_key)

@app.get("/keys/{service_name}", response_model=KeyResponse, tags=["Keys"], operation_id="getApiKey", summary="Retrieve an API key", description="Retrieves the API key for a specified service. Requires admin privileges.")
def get_api_key(service_name: str = Path(..., description="The name of the service."), db: Session = Depends(get_db), _: dict = Depends(require_admin)):
    key_record = db.query(APIKey).filter(APIKey.service_name == service_name, APIKey.revoked == False).first()
    if not key_record:
        raise HTTPException(status_code=404, detail="Key not found.")
    return KeyResponse(service_name=key_record.service_name, api_key=key_record.api_key)

@app.delete("/keys/{service_name}", status_code=status.HTTP_204_NO_CONTENT, tags=["Keys"], operation_id="revokeApiKey", summary="Revoke an API key", description="Revokes the API key for a specified service. Requires admin privileges.")
def revoke_api_key(service_name: str = Path(..., description="The name of the service."), db: Session = Depends(get_db), _: dict = Depends(require_admin)):
    key_record = db.query(APIKey).filter(APIKey.service_name == service_name, APIKey.revoked == False).first()
    if not key_record:
        raise HTTPException(status_code=404, detail="Key not found.")
    key_record.revoked = True
    db.commit()
    logger.info("API key for service %s revoked", service_name)
    return

@app.post("/keys/{service_name}/rotate", response_model=KeyResponse, tags=["Keys"], operation_id="rotateApiKey", summary="Rotate an API key", description="Rotates (replaces) the API key for a specified service. Requires admin privileges.")
def rotate_api_key(service_name: str = Path(..., description="The name of the service."), db: Session = Depends(get_db), _: dict = Depends(require_admin)):
    key_record = db.query(APIKey).filter(APIKey.service_name == service_name, APIKey.revoked == False).first()
    if not key_record:
        raise HTTPException(status_code=404, detail="Key not found.")
    new_key = secrets.token_urlsafe(32)
    key_record.api_key = new_key
    db.commit()
    db.refresh(key_record)
    logger.info("API key for service %s rotated", service_name)
    return KeyResponse(service_name=key_record.service_name, api_key=key_record.api_key)

# -----------------------------------------------------------------------------
# Run the Application
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)

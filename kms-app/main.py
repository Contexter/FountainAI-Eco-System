"""
main.py

Production-Grade FastAPI Application for Key Management Service API

Features:
  - Centralized management of API keys for external services.
  - Endpoints to create, retrieve, revoke, and rotate API keys.
  - Endpoints secured by JWT-based Bearer Authentication requiring admin privileges.
  - Uses SQLAlchemy with SQLite for persistence.
  - Environment configuration via a .env file.
  - Logging and Prometheus-based monitoring.
  - Custom OpenAPI schema override (set to OpenAPI 3.0.3 for Swagger UI compatibility).

Note:
  This service can integrate with an RBAC service by sharing the same SECRET_KEY and token logic.
"""

import os
import logging
import secrets
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, status, Path, Body
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

# -----------------------------------------------------------------------------
# Load Environment Variables
# -----------------------------------------------------------------------------
load_dotenv()
SECRET_KEY = os.environ.get("SECRET_KEY", "supersecretkey")
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./keys.db")

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

# Create tables if not already created.
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
    # Set a Swagger-supported version.
    openapi_schema["openapi"] = "3.0.3"
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# -----------------------------------------------------------------------------
# Prometheus Monitoring Instrumentation
# -----------------------------------------------------------------------------
Instrumentator().instrument(app).expose(app)

# -----------------------------------------------------------------------------
# API Endpoints
# -----------------------------------------------------------------------------

@app.post("/keys", response_model=KeyResponse, status_code=status.HTTP_201_CREATED, tags=["Keys"], operation_id="create_api_key")
def create_api_key(key_create: KeyCreate = Body(...), db: Session = Depends(get_db), _: dict = Depends(require_admin)):
    """
    Create an API key.
    
    Requires admin privileges.
    """
    # Check if a key already exists for this service.
    existing = db.query(APIKey).filter(APIKey.service_name == key_create.service_name).first()
    if existing and not existing.revoked:
        raise HTTPException(status_code=400, detail="API key already exists for this service.")
    
    # Generate a new API key.
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

@app.get("/keys/{service_name}", response_model=KeyResponse, tags=["Keys"], operation_id="get_api_key")
def get_api_key(service_name: str = Path(..., description="The name of the service."), db: Session = Depends(get_db), _: dict = Depends(require_admin)):
    """
    Retrieve an API key.
    """
    key_record = db.query(APIKey).filter(APIKey.service_name == service_name, APIKey.revoked == False).first()
    if not key_record:
        raise HTTPException(status_code=404, detail="Key not found.")
    return KeyResponse(service_name=key_record.service_name, api_key=key_record.api_key)

@app.delete("/keys/{service_name}", status_code=status.HTTP_204_NO_CONTENT, tags=["Keys"], operation_id="revoke_api_key")
def revoke_api_key(service_name: str = Path(..., description="The name of the service."), db: Session = Depends(get_db), _: dict = Depends(require_admin)):
    """
    Revoke an API key.
    """
    key_record = db.query(APIKey).filter(APIKey.service_name == service_name, APIKey.revoked == False).first()
    if not key_record:
        raise HTTPException(status_code=404, detail="Key not found.")
    key_record.revoked = True
    db.commit()
    logger.info("API key for service %s revoked", service_name)
    return

@app.post("/keys/{service_name}/rotate", response_model=KeyResponse, tags=["Keys"], operation_id="rotate_api_key")
def rotate_api_key(service_name: str = Path(..., description="The name of the service."), db: Session = Depends(get_db), _: dict = Depends(require_admin)):
    """
    Rotate an API key.
    """
    key_record = db.query(APIKey).filter(APIKey.service_name == service_name, APIKey.revoked == False).first()
    if not key_record:
        raise HTTPException(status_code=404, detail="Key not found.")
    # Generate a new API key.
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


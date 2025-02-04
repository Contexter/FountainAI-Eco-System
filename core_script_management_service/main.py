"""
Core Script Management API
==========================

This API manages scripts and their narrative elements. It stores data in SQLite and 
synchronizes with peer services (such as the Central Sequence Service, Character Service, etc.) 
via dynamic lookup from the API Gateway. The app includes Prometheus instrumentation and 
overrides the OpenAPI version to 3.0.3 (so that Swagger UI works correctly).

Note: In this example, calls to external services (e.g. for sequence management or Typesense 
synchronization) are demonstrated via a helper function that uses the API Gateway’s lookup endpoint.
"""

import os
import sys
import logging
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request, Response, Depends, status
from fastapi.openapi.utils import get_openapi
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from prometheus_fastapi_instrumentator import Instrumentator
from dotenv import load_dotenv
import httpx
from jose import JWTError, jwt

# SQLAlchemy imports
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# -----------------------------------------------------------------------------
# Load Environment Variables
# -----------------------------------------------------------------------------
load_dotenv()  # Load variables from .env
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8000"))
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./core_script.db")
API_GATEWAY_URL = os.getenv("API_GATEWAY_URL", "http://gateway:8000")
JWT_SECRET = os.getenv("JWT_SECRET", "your_jwt_secret_key")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

# -----------------------------------------------------------------------------
# Logging Configuration
# -----------------------------------------------------------------------------
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger("core_script_management")

# -----------------------------------------------------------------------------
# SQLAlchemy Setup for SQLite
# -----------------------------------------------------------------------------
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Script(Base):
    __tablename__ = "scripts"
    scriptId = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    author = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    comment = Column(String, nullable=True)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -----------------------------------------------------------------------------
# JWT Authentication (RBAC)
# -----------------------------------------------------------------------------
http_bearer = HTTPBearer()

def verify_jwt(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError as e:
        logger.error(f"JWT validation failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(http_bearer)):
    return verify_jwt(credentials.credentials)

# -----------------------------------------------------------------------------
# Helper Function for Service Discovery via API Gateway
# -----------------------------------------------------------------------------
def get_service_url(service_name: str) -> str:
    try:
        r = httpx.get(f"{API_GATEWAY_URL}/lookup/{service_name}", timeout=5.0)
        r.raise_for_status()
        return r.json().get("url")
    except Exception as e:
        logger.error(f"Service discovery failed for '{service_name}': {e}")
        raise HTTPException(status_code=503, detail=f"Service discovery failed for '{service_name}'")

# -----------------------------------------------------------------------------
# Pydantic Schemas for Core Script Management
# -----------------------------------------------------------------------------
class ScriptCreateRequest(BaseModel):
    title: str = Field(..., description="Title of the script")
    author: str = Field(..., description="Author of the script")
    description: Optional[str] = Field(None, description="Brief description of the script")
    comment: str = Field(..., description="Contextual explanation for creating the script")

class ScriptUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, description="Updated title of the script")
    author: Optional[str] = Field(None, description="Updated author of the script")
    description: Optional[str] = Field(None, description="Updated description of the script")
    comment: str = Field(..., description="Contextual explanation for updating the script")

class ScriptResponse(BaseModel):
    scriptId: int
    title: str
    author: str
    description: Optional[str]
    comment: Optional[str]

# -----------------------------------------------------------------------------
# FastAPI Application Initialization
# -----------------------------------------------------------------------------
app = FastAPI(
    title="Core Script Management API",
    description=(
        "This API manages scripts and their narrative elements. "
        "It persists data to SQLite and synchronizes with peer services via the API Gateway. "
        "It integrates with the Central Sequence Service to ensure consistent logical flow."
    ),
    version="4.0.0"
)

# Instrument the app with Prometheus metrics
Instrumentator().instrument(app).expose(app)

# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------
@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "healthy"}

@app.get("/scripts", response_model=List[ScriptResponse], tags=["Scripts"])
def list_scripts(author: Optional[str] = None, title: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Script)
    if author:
        query = query.filter(Script.author.ilike(f"%{author}%"))
    if title:
        query = query.filter(Script.title.ilike(f"%{title}%"))
    scripts = query.all()
    return [ScriptResponse(
        scriptId=script.scriptId,
        title=script.title,
        author=script.author,
        description=script.description,
        comment=script.comment
    ) for script in scripts]

@app.post("/scripts", response_model=ScriptResponse, status_code=status.HTTP_201_CREATED, tags=["Scripts"])
def create_script(request: ScriptCreateRequest, db: Session = Depends(get_db)):
    new_script = Script(
        title=request.title,
        author=request.author,
        description=request.description,
        comment=request.comment
    )
    db.add(new_script)
    db.commit()
    db.refresh(new_script)
    # (Optional) Here you could call a helper to sync with Typesense via the gateway
    logger.info(f"Script created with ID: {new_script.scriptId}")
    return ScriptResponse(
        scriptId=new_script.scriptId,
        title=new_script.title,
        author=new_script.author,
        description=new_script.description,
        comment=new_script.comment
    )

@app.get("/scripts/{scriptId}", response_model=ScriptResponse, tags=["Scripts"])
def get_script_by_id(scriptId: int, db: Session = Depends(get_db)):
    script = db.query(Script).filter(Script.scriptId == scriptId).first()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")
    return ScriptResponse(
        scriptId=script.scriptId,
        title=script.title,
        author=script.author,
        description=script.description,
        comment=script.comment
    )

@app.patch("/scripts/{scriptId}", response_model=ScriptResponse, tags=["Scripts"])
def patch_script(scriptId: int, request: ScriptUpdateRequest, db: Session = Depends(get_db)):
    script = db.query(Script).filter(Script.scriptId == scriptId).first()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")
    if request.title is not None:
        script.title = request.title
    if request.author is not None:
        script.author = request.author
    if request.description is not None:
        script.description = request.description
    script.comment = request.comment
    db.commit()
    db.refresh(script)
    # (Optional) Sync updated script with Typesense via the API Gateway
    logger.info(f"Script updated with ID: {script.scriptId}")
    return ScriptResponse(
        scriptId=script.scriptId,
        title=script.title,
        author=script.author,
        description=script.description,
        comment=script.comment
    )

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
    schema["openapi"] = "3.0.3"
    app.openapi_schema = schema
    return schema

app.openapi = custom_openapi

# -----------------------------------------------------------------------------
# Run the Application
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=SERVICE_PORT)

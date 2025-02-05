"""
Core Script Management API
==========================

Purpose:
    This API manages scripts and their narrative elements. It stores data in SQLite and 
    synchronizes with peer services (such as the Central Sequence Service, Character Service, etc.) 
    via dynamic lookup from the API Gateway. The app includes Prometheus instrumentation and 
    overrides the OpenAPI version to 3.0.3 so that Swagger UI works correctly.

Integrations:
    - Dynamic Service Discovery: External calls (e.g., for sequence management or Typesense synchronization) 
      are demonstrated via a helper function that uses the API Gateway’s lookup endpoint.
    - Prometheus: Instrumentation is provided via prometheus_fastapi_instrumentator.
    - JWT Authentication (RBAC): Endpoints may leverage JWT security.
    - Notification Integration: A stub endpoint is provided for future notification service integration.
"""

import os
import sys
import logging
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request, Response, Depends, status, Query
from fastapi.openapi.utils import get_openapi
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import HTMLResponse
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

def get_db() -> Session:
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
        url = r.json().get("url")
        if not url:
            raise ValueError("No URL returned")
        return url
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

# Default Landing Page Endpoint
@app.get("/", response_class=HTMLResponse, tags=["Landing"], operation_id="getLandingPage", summary="Display landing page", description="Returns a styled landing page with service title, version, and links to API documentation and health check.")
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
        service_description="Manage scripts and narrative elements within the FountainAI ecosystem."
    )
    return HTMLResponse(content=filled_html, status_code=200)

# Health Endpoint
@app.get("/health", tags=["Health"], operation_id="getHealthStatus", summary="Retrieve service health status", description="Returns the current health status of the Core Script Management API as a JSON object.")
def health_check():
    return {"status": "healthy"}

# List Scripts Endpoint
@app.get("/scripts", response_model=List[ScriptResponse], tags=["Scripts"], operation_id="listScripts", summary="List scripts", description="Retrieves a list of scripts, optionally filtering by author or title.")
def list_scripts(author: Optional[str] = None, title: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Script)
    if author:
        query = query.filter(Script.author.ilike(f"%{author}%"))
    if title:
        query = query.filter(Script.title.ilike(f"%{title}%"))
    scripts = query.all()
    return [
        ScriptResponse(
            scriptId=script.scriptId,
            title=script.title,
            author=script.author,
            description=script.description,
            comment=script.comment
        ) for script in scripts
    ]

# Create Script Endpoint
@app.post("/scripts", response_model=ScriptResponse, status_code=status.HTTP_201_CREATED, tags=["Scripts"], operation_id="createScript", summary="Create a new script", description="Creates a new script and optionally synchronizes with peer services via the API Gateway.")
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
    logger.info(f"Script created with ID: {new_script.scriptId}")
    return ScriptResponse(
        scriptId=new_script.scriptId,
        title=new_script.title,
        author=new_script.author,
        description=new_script.description,
        comment=new_script.comment
    )

# Get Script by ID Endpoint
@app.get("/scripts/{scriptId}", response_model=ScriptResponse, tags=["Scripts"], operation_id="getScriptById", summary="Retrieve a script", description="Retrieves a script by its ID.")
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

# Patch Script Endpoint
@app.patch("/scripts/{scriptId}", response_model=ScriptResponse, tags=["Scripts"], operation_id="patchScript", summary="Patch a script", description="Updates selected fields of a script.")
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
    logger.info(f"Script patched with ID: {script.scriptId}")
    return ScriptResponse(
        scriptId=script.scriptId,
        title=script.title,
        author=script.author,
        description=script.description,
        comment=script.comment
    )

# Dynamic Service Discovery Endpoint
@app.get("/service-discovery", tags=["Service Discovery"], operation_id="getServiceDiscovery", summary="Discover peer services", description="Queries the API Gateway's lookup endpoint to resolve the URL of a specified service.")
def service_discovery(service_name: str = Query(..., description="Name of the service to discover")):
    discovered_url = get_service_url(service_name)
    return {"service": service_name, "discovered_url": discovered_url}

# Notification Receiving Stub Endpoint
@app.post("/notifications", tags=["Notification"], operation_id="receiveNotification", summary="Receive notifications", description="Endpoint stub for receiving notifications from a central notification service.")
def receive_notification(payload: dict):
    logger.info("Received notification payload: %s", payload)
    return {"message": "Notification received (stub)."}

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

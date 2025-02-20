"""
Story Factory API
=================

Purpose:
    This API integrates data from the Core Script Management, Character, and 
    Session/Context Management APIs to assemble and manage a complete story.
    Data is persisted to SQLite and the service uses dynamic service discovery via the API Gateway 
    for any outbound calls. JWT-based RBAC is enforced, Prometheus metrics are exposed, and the 
    OpenAPI version is forced to 3.0.3 to ensure Swagger UI compatibility.

Key Integrations:
    - FastAPI: Provides the web framework and automatic OpenAPI documentation.
    - SQLAlchemy & SQLite: Used for data persistence.
    - JWT Authentication: Secures endpoints via Bearer token authentication.
    - Dynamic Service Discovery: Enables runtime resolution of peer service URLs via the API Gateway.
    - Prometheus: Metrics exposed via prometheus_fastapi_instrumentator.
    - Default Landing Page & Health Endpoint: Provides a friendly UI and service status.
    
Usage:
    Configuration is loaded from a .env file. The service is containerized and is designed to 
    integrate seamlessly with other services in the FountainAI Eco‑System.
"""

import os
import sys
import logging
from typing import List, Optional, Dict
from fastapi import FastAPI, HTTPException, Depends, Query, status, Response, Path, Body
from fastapi.responses import HTMLResponse
from fastapi.openapi.utils import get_openapi
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from prometheus_fastapi_instrumentator import Instrumentator
from dotenv import load_dotenv
import httpx
from jose import JWTError, jwt

# SQLAlchemy imports for SQLite persistence
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# -----------------------------------------------------------------------------
# Load Environment Variables
# -----------------------------------------------------------------------------
load_dotenv()
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8000"))
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./story_factory.db")
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
logger = logging.getLogger("story_factory_service")

# -----------------------------------------------------------------------------
# SQLAlchemy Database Setup
# -----------------------------------------------------------------------------
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Story(Base):
    __tablename__ = "stories"
    scriptId = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    author = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    sections = Column(Text, nullable=True)       # JSON string or CSV of section headings
    story = Column(Text, nullable=True)            # JSON string representing the story elements
    orchestration = Column(Text, nullable=True)    # JSON string for file paths (csound, LilyPond, MIDI)
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

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(http_bearer)) -> dict:
    return verify_jwt(credentials.credentials)

# -----------------------------------------------------------------------------
# Pydantic Schemas for Story Factory API
# -----------------------------------------------------------------------------
class FullStory(BaseModel):
    scriptId: int = Field(..., description="Unique identifier of the script")
    title: str = Field(..., description="Title of the script")
    author: str = Field(..., description="Author of the script")
    description: Optional[str] = Field(None, description="Brief description or summary of the script")
    sections: List[str] = Field(..., description="List of section headings")
    story: List[dict] = Field(..., description="List of story elements")
    orchestration: dict = Field(..., description="Paths to generated files (csound, LilyPond, MIDI)")
    comment: Optional[str] = Field(None, description="Contextual explanation for the story assembly")

class ScriptCreateRequest(BaseModel):
    title: str = Field(..., description="Title of the script")
    author: str = Field(..., description="Author of the script")
    description: Optional[str] = Field(None, description="Brief description or summary of the script")
    sections: List[str] = Field(..., description="Section headings for the script")
    story: List[dict] = Field(..., description="Story elements (each element is a dict)")
    orchestration: dict = Field(..., description="File paths for csound, LilyPond, MIDI")
    comment: str = Field(..., description="Contextual explanation for creating the story")

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
# FastAPI Application Initialization
# -----------------------------------------------------------------------------
app = FastAPI(
    title="Story Factory API",
    description=(
        "This API integrates data from the Core Script Management, Character, and Session/Context Management APIs "
        "to assemble and manage the logical flow of stories. It persists data to SQLite and synchronizes with peer "
        "services via dynamic service discovery from the API Gateway."
    ),
    version="4.0.0"
)

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
        service_description="This API assembles and manages complete stories by integrating data from multiple services."
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
# Endpoints for Story Factory API
# -----------------------------------------------------------------------------
@app.get("/stories", response_model=FullStory, tags=["Stories"], operation_id="getFullStory", summary="Retrieve full story", description="Retrieves a complete story by script ID.")
def get_full_story(scriptId: int, filterByContext: Optional[str] = None, db: Session = Depends(get_db)):
    story = db.query(Story).filter(Story.scriptId == scriptId).first()
    if not story:
        raise HTTPException(status_code=404, detail="Script not found")
    import json
    return FullStory(
        scriptId=story.scriptId,
        title=story.title,
        author=story.author,
        description=story.description,
        sections=json.loads(story.sections) if story.sections else [],
        story=json.loads(story.story) if story.story else [],
        orchestration=json.loads(story.orchestration) if story.orchestration else {},
        comment=story.comment
    )

@app.post("/stories", response_model=FullStory, status_code=status.HTTP_201_CREATED, tags=["Stories"], operation_id="createScript", summary="Create a story", description="Creates a new story using provided script data.")
def create_script(request: ScriptCreateRequest, db: Session = Depends(get_db)):
    import json
    new_story = Story(
        title=request.title,
        author=request.author,
        description=request.description,
        sections=json.dumps(request.sections),
        story=json.dumps(request.story),
        orchestration=json.dumps(request.orchestration),
        comment=request.comment
    )
    db.add(new_story)
    db.commit()
    db.refresh(new_story)
    logger.info(f"Story created with scriptId: {new_story.scriptId}")
    return FullStory(
        scriptId=new_story.scriptId,
        title=new_story.title,
        author=new_story.author,
        description=new_story.description,
        sections=request.sections,
        story=request.story,
        orchestration=request.orchestration,
        comment=new_story.comment
    )

@app.get("/stories/sequences", tags=["Stories"], operation_id="getStorySequences", summary="Retrieve story sequences", description="Not implemented: Retrieves a subset of story elements by sequence numbers.")
def get_story_sequences(scriptId: int, startSequence: int, endSequence: int, filterByContext: Optional[str] = None):
    raise HTTPException(status_code=501, detail="Not implemented")

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

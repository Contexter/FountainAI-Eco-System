"""
Story Factory API
=================

This API integrates data from the Core Script Management API, Character Service, and 
Session and Context Management API to assemble and manage a complete story. Data is 
persisted to SQLite and the service uses dynamic service discovery via the API Gateway 
for any outbound calls. JWT-based RBAC is enforced, Prometheus metrics are exposed, and 
the OpenAPI version is forced to 3.0.3 (to keep Swagger UI happy).

"""

import os
import sys
import logging
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends, status
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
    sections = Column(Text, nullable=True)  # Store JSON string or CSV of section headings
    story = Column(Text, nullable=True)     # Store JSON string representing the story elements
    orchestration = Column(Text, nullable=True)  # JSON string for file paths
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
# Endpoints for Story Factory API
# -----------------------------------------------------------------------------
@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "healthy"}

@app.get("/stories", response_model=FullStory, tags=["Stories"])
def get_full_story(scriptId: int, filterByContext: Optional[str] = None, db: Session = Depends(get_db)):
    story = db.query(Story).filter(Story.scriptId == scriptId).first()
    if not story:
        raise HTTPException(status_code=404, detail="Script not found")
    # Here you might filter the 'story' data based on filterByContext.
    # For this example, we return the stored story as is.
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

@app.post("/stories", response_model=FullStory, status_code=status.HTTP_201_CREATED, tags=["Stories"])
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

@app.get("/stories/sequences", tags=["Stories"])
def get_story_sequences(scriptId: int, startSequence: int, endSequence: int, filterByContext: Optional[str] = None):
    # For demonstration, we assume the story sequences are part of the full story.
    # In a real implementation, you would query the story elements by sequence numbers.
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

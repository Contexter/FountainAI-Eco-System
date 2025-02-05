"""
Spoken Word Service API
=======================

Purpose:
    This service manages lines of spoken words within a story. Lines are grouped into speeches and 
    can be interspersed with actions. The service supports CRUD operations on lines, which are persisted 
    to SQLite and synchronized with search systems via dynamic service discovery from the API Gateway.
    JWT-based authentication is enforced on endpoints that modify data. Prometheus instrumentation is integrated,
    and the OpenAPI schema is forced to version 3.0.3 for Swagger UI compatibility.

Key Integrations:
    - FastAPI: Provides the framework and automatic OpenAPI documentation.
    - SQLAlchemy & SQLite: Used for data persistence.
    - JWT Authentication: Enforces security using HTTPBearer.
    - Dynamic Service Discovery: Resolves peer service URLs via the API Gateway.
    - Prometheus: Metrics exposed via prometheus_fastapi_instrumentator.
    - Default Landing Page & Health Check: Enhances user-friendliness.

Usage:
    Configuration is loaded via a .env file. Endpoints are secured as needed with JWT-based authentication.
"""

import os
import sys
import logging
from datetime import datetime
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
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./spokenword.db")
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
logger = logging.getLogger("spokenword_service")

# -----------------------------------------------------------------------------
# SQLAlchemy Database Setup
# -----------------------------------------------------------------------------
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Line(Base):
    __tablename__ = "lines"
    lineId = Column(Integer, primary_key=True, index=True)
    scriptId = Column(Integer, nullable=False)
    speechId = Column(Integer, nullable=False)
    characterId = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    sequenceNumber = Column(Integer, nullable=False)
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

def verify_jwt(token: str) -> Dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError as e:
        logger.error(f"JWT validation failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(http_bearer)) -> Dict:
    return verify_jwt(credentials.credentials)

# -----------------------------------------------------------------------------
# Pydantic Schemas for Spoken Word Service
# -----------------------------------------------------------------------------
class LineCreateRequest(BaseModel):
    scriptId: int = Field(..., description="Unique identifier of the script")
    speechId: int = Field(..., description="ID of the speech this line belongs to")
    characterId: int = Field(..., description="ID of the character delivering this line")
    content: str = Field(..., description="Content of the spoken word line")
    comment: str = Field(..., description="Contextual explanation for creating the line")

class LineUpdateRequest(BaseModel):
    content: str = Field(..., description="Updated content of the line")
    comment: str = Field(..., description="Contextual explanation for updating the line")

class LineResponse(BaseModel):
    lineId: int
    scriptId: int
    speechId: int
    characterId: int
    content: str
    sequenceNumber: int
    comment: Optional[str]

    class Config:
        orm_mode = True

class StandardError(BaseModel):
    errorCode: str
    message: str
    details: Optional[str]

# -----------------------------------------------------------------------------
# Helper Function for Dynamic Service Discovery
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
# FastAPI Application Initialization
# -----------------------------------------------------------------------------
app = FastAPI(
    title="Spoken Word Service",
    description=(
        "This service manages lines of spoken words within a story. Lines are grouped into speeches and may be interspersed with actions. "
        "It supports CRUD operations on lines, which are persisted to SQLite and synchronized with search systems via dynamic service discovery from the API Gateway. "
        "JWT-based authentication is enforced on endpoints that modify data."
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
        service_description="Manage spoken word lines within the FountainAI ecosystem."
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
# Endpoints for Spoken Word Lines
# -----------------------------------------------------------------------------
@app.get("/lines", response_model=List[LineResponse], tags=["Lines"], operation_id="listLines", summary="List lines", description="Retrieves a list of spoken word lines filtered by script ID and optional parameters.")
def list_lines(
    scriptId: int = Query(..., description="Unique identifier of the script"),
    characterId: Optional[int] = Query(None, description="Filter by character ID"),
    speechId: Optional[int] = Query(None, description="Filter by speech ID"),
    keyword: Optional[str] = Query(None, description="Search for lines containing specific keywords"),
    db: Session = Depends(get_db)
):
    query = db.query(Line).filter(Line.scriptId == scriptId)
    if characterId is not None:
        query = query.filter(Line.characterId == characterId)
    if speechId is not None:
        query = query.filter(Line.speechId == speechId)
    if keyword:
        query = query.filter(Line.content.ilike(f"%{keyword}%"))
    lines = query.all()
    return [
        LineResponse(
            lineId=l.lineId,
            scriptId=l.scriptId,
            speechId=l.speechId,
            characterId=l.characterId,
            content=l.content,
            sequenceNumber=l.sequenceNumber,
            comment=l.comment
        ) for l in lines
    ]

@app.post("/lines", response_model=LineResponse, status_code=status.HTTP_201_CREATED, tags=["Lines"], operation_id="createLine", summary="Create a line", description="Creates a new spoken word line. JWT authentication is enforced.")
def create_line(request: LineCreateRequest, db: Session = Depends(get_db), current_user: Dict = Depends(get_current_user)):
    # Integrate with the Central Sequence Service to obtain the next sequence number.
    try:
        central_sequence_url = get_service_url("central_sequence_service")
    except Exception as e:
        logger.error(f"Central Sequence Service lookup failed: {e}")
        raise HTTPException(status_code=503, detail="Central Sequence Service unavailable")
    
    sequence_payload = {
        "elementType": "spokenWord",
        "elementId": 0,
        "comment": request.comment
    }
    try:
        seq_response = httpx.post(f"{central_sequence_url}/sequence", json=sequence_payload, timeout=5.0)
        seq_response.raise_for_status()
        seq_data = seq_response.json()
        next_seq = seq_data.get("sequenceNumber")
        if next_seq is None:
            raise ValueError("No sequenceNumber returned")
    except Exception as e:
        logger.error(f"Failed to obtain sequence number: {e}")
        raise HTTPException(status_code=503, detail="Failed to obtain sequence number")
    
    new_line = Line(
        scriptId=request.scriptId,
        speechId=request.speechId,
        characterId=request.characterId,
        content=request.content,
        sequenceNumber=next_seq,
        comment=request.comment
    )
    db.add(new_line)
    db.commit()
    db.refresh(new_line)
    logger.info(f"Line created with ID: {new_line.lineId}")
    return LineResponse(
        lineId=new_line.lineId,
        scriptId=new_line.scriptId,
        speechId=new_line.speechId,
        characterId=new_line.characterId,
        content=new_line.content,
        sequenceNumber=new_line.sequenceNumber,
        comment=new_line.comment
    )

@app.get("/lines/{lineId}", response_model=LineResponse, tags=["Lines"], operation_id="getLineById", summary="Retrieve a line", description="Retrieves a spoken word line by its ID.")
def get_line_by_id(lineId: int, db: Session = Depends(get_db)):
    line = db.query(Line).filter(Line.lineId == lineId).first()
    if not line:
        raise HTTPException(status_code=404, detail="Line not found")
    return LineResponse(
        lineId=line.lineId,
        scriptId=line.scriptId,
        speechId=line.speechId,
        characterId=line.characterId,
        content=line.content,
        sequenceNumber=line.sequenceNumber,
        comment=line.comment
    )

@app.patch("/lines/{lineId}", response_model=LineResponse, tags=["Lines"], operation_id="updateLine", summary="Update a line", description="Updates a spoken word line's content and comment. JWT authentication is enforced.")
def update_line(lineId: int, request: LineUpdateRequest, db: Session = Depends(get_db), current_user: Dict = Depends(get_current_user)):
    line = db.query(Line).filter(Line.lineId == lineId).first()
    if not line:
        raise HTTPException(status_code=404, detail="Line not found")
    line.content = request.content
    line.comment = request.comment
    db.commit()
    db.refresh(line)
    logger.info(f"Line updated with ID: {line.lineId}")
    return LineResponse(
        lineId=line.lineId,
        scriptId=line.scriptId,
        speechId=line.speechId,
        characterId=line.characterId,
        content=line.content,
        sequenceNumber=line.sequenceNumber,
        comment=line.comment
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

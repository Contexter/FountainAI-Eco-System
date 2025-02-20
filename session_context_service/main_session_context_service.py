"""
Session and Context Management API
==================================

Purpose:
    This API manages user sessions and context data for narrative elements.
    Session data is persisted to SQLite and may optionally be synchronized with search systems.
    The service integrates with other FountainAI services via dynamic lookup from the API Gateway.
    JWT-based RBAC is used to secure endpoints, ensuring that only authenticated users can create, update, or view session data.

Key Integrations:
    - FastAPI: Provides a modern web framework with automatic OpenAPI documentation.
    - SQLAlchemy & SQLite: Used for persistent storage.
    - JWT Authentication: Enforces security using JWT tokens.
    - Dynamic Service Discovery: Enables runtime resolution of peer service URLs via the API Gateway.
    - Prometheus: Exposes metrics via prometheus_fastapi_instrumentator.
    - Custom OpenAPI: Forces the OpenAPI schema version to 3.0.3 for Swagger UI compatibility.
    - Default Landing Page & Health Check: Provides user-friendly endpoints for basic service information.

Usage:
    Configuration is loaded from a .env file. Endpoints are secured via JWT, and dynamic service discovery
    enables inter-service communication in the FountainAI Eco‑System.
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
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./session_context.db")
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
logger = logging.getLogger("session_context_service")

# -----------------------------------------------------------------------------
# SQLAlchemy Database Setup
# -----------------------------------------------------------------------------
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class SessionContext(Base):
    __tablename__ = "sessions"
    sessionId = Column(Integer, primary_key=True, index=True)
    # For simplicity, context is stored as a comma-separated string.
    context = Column(String, nullable=False)
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
        logger.error("JWT validation failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(http_bearer)) -> Dict:
    return verify_jwt(credentials.credentials)

# -----------------------------------------------------------------------------
# Pydantic Schemas for Session and Context Management
# -----------------------------------------------------------------------------
class SessionCreateRequest(BaseModel):
    context: List[str] = Field(..., description="Array of context strings to attach to the new session")
    comment: str = Field(..., description="Contextual explanation for creating the session")

class SessionUpdateRequest(BaseModel):
    context: List[str] = Field(..., description="Updated array of context strings for the session")
    comment: str = Field(..., description="Contextual explanation for updating the session")

class SessionResponse(BaseModel):
    sessionId: int
    context: List[str]
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
            raise ValueError("No URL returned from service lookup.")
        return url
    except Exception as e:
        logger.error("Service discovery failed for '%s': %s", service_name, e)
        raise HTTPException(status_code=503, detail=f"Service discovery failed for '{service_name}'")

# -----------------------------------------------------------------------------
# FastAPI Application Initialization
# -----------------------------------------------------------------------------
app = FastAPI(
    title="Session and Context Management API",
    description=(
        "This API manages user sessions and context data for narrative elements. "
        "It integrates with other FountainAI services via dynamic service discovery from the API Gateway. "
        "Data is persisted to SQLite and may be synchronized with search services. "
        "JWT-based RBAC secures all endpoints."
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
        service_description="This service manages user sessions and context data for narrative elements."
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
# Session Management Endpoints (Secured with JWT)
# -----------------------------------------------------------------------------

@app.get("/sessions", response_model=List[SessionResponse], tags=["Sessions"], operation_id="listSessions", summary="List sessions", description="Retrieves a list of sessions. Requires JWT authentication.")
def list_sessions(db: Session = Depends(get_db), current_user: Dict = Depends(get_current_user)):
    query = db.query(SessionContext)
    sessions = query.all()
    result = []
    for s in sessions:
        context_list = s.context.split(",") if s.context else []
        result.append(SessionResponse(sessionId=s.sessionId, context=context_list, comment=s.comment))
    return result

@app.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED, tags=["Sessions"], operation_id="createSession", summary="Create a session", description="Creates a new session with context data. Requires JWT authentication.")
def create_session(request: SessionCreateRequest, db: Session = Depends(get_db), current_user: Dict = Depends(get_current_user)):
    new_session = SessionContext(
        context=",".join(request.context),
        comment=request.comment
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    logger.info(f"Session created with ID: {new_session.sessionId}")
    return SessionResponse(sessionId=new_session.sessionId, context=request.context, comment=new_session.comment)

@app.get("/sessions/{sessionId}", response_model=SessionResponse, tags=["Sessions"], operation_id="getSessionById", summary="Retrieve a session", description="Retrieves a session by its ID. Requires JWT authentication.")
def get_session_by_id(sessionId: int, db: Session = Depends(get_db), current_user: Dict = Depends(get_current_user)):
    session_obj = db.query(SessionContext).filter(SessionContext.sessionId == sessionId).first()
    if not session_obj:
        raise HTTPException(status_code=404, detail="Session not found")
    context_list = session_obj.context.split(",") if session_obj.context else []
    return SessionResponse(sessionId=session_obj.sessionId, context=context_list, comment=session_obj.comment)

@app.patch("/sessions/{sessionId}", response_model=SessionResponse, tags=["Sessions"], operation_id="updateSession", summary="Update a session", description="Updates a session's context and comment. Requires JWT authentication.")
def update_session(sessionId: int, request: SessionUpdateRequest, db: Session = Depends(get_db), current_user: Dict = Depends(get_current_user)):
    session_obj = db.query(SessionContext).filter(SessionContext.sessionId == sessionId).first()
    if not session_obj:
        raise HTTPException(status_code=404, detail="Session not found")
    session_obj.context = ",".join(request.context)
    session_obj.comment = request.comment
    db.commit()
    db.refresh(session_obj)
    logger.info(f"Session updated with ID: {session_obj.sessionId}")
    return SessionResponse(sessionId=session_obj.sessionId, context=request.context, comment=session_obj.comment)

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

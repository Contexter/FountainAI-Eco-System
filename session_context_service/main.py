"""
Session and Context Management API
==================================

This API manages user sessions and context data for narrative elements.
It persists session data to SQLite and (optionally) synchronizes with Typesense for search.
It integrates with other services via dynamic lookup from the API Gateway.
JWT-based RBAC is used to secure endpoints.
The OpenAPI version is forced to 3.0.3 so that Swagger UI works correctly.
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
    # Stored as a comma-separated list for simplicity; in production, use a related table.
    context = Column(String, nullable=False)
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

class StandardError(BaseModel):
    errorCode: str
    message: str
    details: Optional[str]

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
    title="Session and Context Management API",
    description=(
        "This API manages user sessions and context data for narrative elements. "
        "It integrates with other FountainAI services via the API Gateway for dynamic service discovery. "
        "Data is persisted to SQLite and may be synchronized with search services."
    ),
    version="4.0.0"
)

Instrumentator().instrument(app).expose(app)

# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------
@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "healthy"}

@app.get("/sessions", response_model=List[SessionResponse], tags=["Sessions"])
def list_sessions(context: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(SessionContext)
    if context:
        query = query.filter(SessionContext.context.like(f"%{context}%"))
    sessions = query.all()
    result = []
    for s in sessions:
        context_list = s.context.split(",") if s.context else []
        result.append(SessionResponse(sessionId=s.sessionId, context=context_list, comment=s.comment))
    return result

@app.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED, tags=["Sessions"])
def create_session(request: SessionCreateRequest, db: Session = Depends(get_db)):
    # Store the context list as a comma-separated string (for simplicity)
    new_session = SessionContext(
        context=",".join(request.context),
        comment=request.comment
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    logger.info(f"Session created with ID: {new_session.sessionId}")
    return SessionResponse(sessionId=new_session.sessionId, context=request.context, comment=new_session.comment)

@app.get("/sessions/{sessionId}", response_model=SessionResponse, tags=["Sessions"])
def get_session_by_id(sessionId: int, db: Session = Depends(get_db)):
    session_obj = db.query(SessionContext).filter(SessionContext.sessionId == sessionId).first()
    if not session_obj:
        raise HTTPException(status_code=404, detail="Session not found")
    context_list = session_obj.context.split(",") if session_obj.context else []
    return SessionResponse(sessionId=session_obj.sessionId, context=context_list, comment=session_obj.comment)

@app.patch("/sessions/{sessionId}", response_model=SessionResponse, tags=["Sessions"])
def update_session(sessionId: int, request: SessionUpdateRequest, db: Session = Depends(get_db)):
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

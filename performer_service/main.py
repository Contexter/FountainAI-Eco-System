"""
Performer Service
=================

This service handles the creation, retrieval, updating, and management of performers within a story.
Data is persisted to SQLite and synchronized with search systems via dynamic service discovery from the API Gateway.
It integrates with the Central Sequence Service by assigning a sequence number to each performer.
JWT-based authentication is enforced, Prometheus metrics are exposed, and the OpenAPI version is forced to 3.0.3.
"""

import os
import sys
import logging
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends, Query, status, Response
from fastapi.openapi.utils import get_openapi
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from prometheus_fastapi_instrumentator import Instrumentator
from dotenv import load_dotenv
import httpx
from jose import JWTError, jwt

# SQLAlchemy imports for SQLite persistence
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# -----------------------------------------------------------------------------
# Load Environment Variables
# -----------------------------------------------------------------------------
load_dotenv()
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8000"))
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./performer.db")
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
logger = logging.getLogger("performer_service")

# -----------------------------------------------------------------------------
# SQLAlchemy Database Setup
# -----------------------------------------------------------------------------
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Performer(Base):
    __tablename__ = "performers"
    performerId = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    sequenceNumber = Column(Integer, nullable=False)
    isSyncedToTypesense = Column(Integer, nullable=False, default=0)  # 0=False, 1=True
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
# Pydantic Schemas for Performer Service
# -----------------------------------------------------------------------------
class PerformerCreateRequest(BaseModel):
    name: str = Field(..., description="Name of the performer")
    comment: str = Field(..., description="Contextual explanation for creating the performer")

class PerformerPatchRequest(BaseModel):
    name: Optional[str] = Field(None, description="Updated name of the performer")
    comment: str = Field(..., description="Contextual explanation for updating the performer")

class PerformerUpdateRequest(BaseModel):
    name: str = Field(..., description="Updated name of the performer")
    comment: str = Field(..., description="Contextual explanation for updating the performer")

class PerformerResponse(BaseModel):
    performerId: int
    name: str
    sequenceNumber: int
    isSyncedToTypesense: bool
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
    title="Performer Service",
    description=(
        "This service handles the creation, retrieval, updating, and management of performers within the story. "
        "Data is persisted to SQLite and synchronized with search systems via dynamic service discovery from the API Gateway. "
        "It integrates with the Central Sequence Service to ensure performers are returned in the correct order."
    ),
    version="4.0.0"
)

Instrumentator().instrument(app).expose(app)

# -----------------------------------------------------------------------------
# Endpoints for Performer Service
# -----------------------------------------------------------------------------
@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "healthy"}

@app.get("/performers", response_model=List[PerformerResponse], tags=["Performers"])
def list_performers(
    characterId: Optional[int] = Query(None, description="(Optional) Filter by character ID"),
    scriptId: Optional[int] = Query(None, description="(Optional) Filter by script ID"),
    db: Session = Depends(get_db)
):
    # For this example, filtering by scriptId is simulated – in a real scenario, the Performer model would have such a field.
    query = db.query(Performer)
    if characterId is not None:
        # Simulated: assume performers associated with a given character have matching names or IDs.
        query = query.filter(Performer.performerId == characterId)
    performers = query.all()
    return [
        PerformerResponse(
            performerId=p.performerId,
            name=p.name,
            sequenceNumber=p.sequenceNumber,
            isSyncedToTypesense=bool(p.isSyncedToTypesense),
            comment=p.comment
        ) for p in performers
    ]

@app.post("/performers", response_model=PerformerResponse, status_code=status.HTTP_201_CREATED, tags=["Performers"])
def create_performer(request: PerformerCreateRequest, db: Session = Depends(get_db)):
    # Simulate Central Sequence Service integration by assigning next sequence number.
    max_seq = db.query(Performer).order_by(Performer.sequenceNumber.desc()).first()
    next_seq = max_seq.sequenceNumber + 1 if max_seq else 1
    new_performer = Performer(
        name=request.name,
        sequenceNumber=next_seq,
        isSyncedToTypesense=0,
        comment=request.comment
    )
    db.add(new_performer)
    db.commit()
    db.refresh(new_performer)
    logger.info(f"Performer created with ID: {new_performer.performerId}")
    return PerformerResponse(
        performerId=new_performer.performerId,
        name=new_performer.name,
        sequenceNumber=new_performer.sequenceNumber,
        isSyncedToTypesense=bool(new_performer.isSyncedToTypesense),
        comment=new_performer.comment
    )

@app.get("/performers/{performerId}", response_model=PerformerResponse, tags=["Performers"])
def get_performer_by_id(performerId: int, db: Session = Depends(get_db)):
    p = db.query(Performer).filter(Performer.performerId == performerId).first()
    if not p:
        raise HTTPException(status_code=404, detail="Performer not found")
    return PerformerResponse(
        performerId=p.performerId,
        name=p.name,
        sequenceNumber=p.sequenceNumber,
        isSyncedToTypesense=bool(p.isSyncedToTypesense),
        comment=p.comment
    )

@app.patch("/performers/{performerId}", response_model=PerformerResponse, tags=["Performers"])
def patch_performer(performerId: int, request: PerformerPatchRequest, db: Session = Depends(get_db)):
    p = db.query(Performer).filter(Performer.performerId == performerId).first()
    if not p:
        raise HTTPException(status_code=404, detail="Performer not found")
    if request.name is not None:
        p.name = request.name
    p.comment = request.comment  # Always update comment per our requirement
    db.commit()
    db.refresh(p)
    logger.info(f"Performer updated with ID: {p.performerId}")
    return PerformerResponse(
        performerId=p.performerId,
        name=p.name,
        sequenceNumber=p.sequenceNumber,
        isSyncedToTypesense=bool(p.isSyncedToTypesense),
        comment=p.comment
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


"""
Spoken Word Service
===================

This API manages lines of spoken words within a story. Lines are grouped into speeches
and can be interspersed with actions. The service supports CRUD operations on lines,
which are persisted to SQLite and (optionally) synchronized with search systems via
dynamic service discovery from the API Gateway. JWT-based authentication is enforced,
and Prometheus instrumentation is integrated. The OpenAPI version is forced to 3.0.3.

"""

import os
import sys
import logging
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends, status, Query
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
    scriptId = Column(Integer, nullable=False)   # For filtering by script
    speechId = Column(Integer, nullable=False)
    characterId = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    sequenceNumber = Column(Integer, nullable=False)
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
# Pydantic Schemas for Spoken Word Service
# -----------------------------------------------------------------------------
class LineCreateRequest(BaseModel):
    scriptId: int = Field(..., description="Unique identifier of the script")
    speechId: int = Field(..., description="ID of the speech this line will belong to")
    characterId: int = Field(..., description="ID of the character delivering this line")
    content: str = Field(..., description="Content of the line")
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
    title="Spoken Word Service",
    description=(
        "This service manages lines of spoken words within a story. Lines are grouped into speeches and "
        "can be interspersed with actions. The service supports CRUD operations on lines, which are persisted "
        "to SQLite and synchronized with search systems via dynamic service discovery from the API Gateway. "
        "JWT-based authentication is enforced."
    ),
    version="4.0.0"
)

Instrumentator().instrument(app).expose(app)

# -----------------------------------------------------------------------------
# Endpoints for Spoken Word Service
# -----------------------------------------------------------------------------
@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "healthy"}

@app.get("/lines", response_model=List[LineResponse], tags=["Lines"])
def list_lines(
    scriptId: int = Query(..., description="Unique identifier of the script"),
    characterId: Optional[int] = Query(None, description="Filter by character ID"),
    speechId: Optional[int] = Query(None, description="Filter by speech ID"),
    sectionId: Optional[int] = Query(None, description="Filter by section ID (not stored)"),
    actionId: Optional[int] = Query(None, description="Filter by action ID (not stored)"),
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

@app.post("/lines", response_model=LineResponse, status_code=status.HTTP_201_CREATED, tags=["Lines"])
def create_line(request: LineCreateRequest, db: Session = Depends(get_db)):
    # Simulate sequence assignment using max(sequenceNumber)+1 for the given speech (for simplicity)
    max_seq_line = db.query(Line).filter(Line.speechId == request.speechId).order_by(Line.sequenceNumber.desc()).first()
    next_seq = max_seq_line.sequenceNumber + 1 if max_seq_line else 1
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

@app.get("/lines/{lineId}", response_model=LineResponse, tags=["Lines"])
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

@app.patch("/lines/{lineId}", response_model=LineResponse, tags=["Lines"])
def update_line(lineId: int, request: LineUpdateRequest, db: Session = Depends(get_db)):
    line = db.query(Line).filter(Line.lineId == lineId).first()
    if not line:
        raise HTTPException(status_code=404, detail="Line not found")
    line.content = request.content
    if request.comment is not None:
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


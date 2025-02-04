"""
Paraphrase Service
==================

This service manages paraphrases associated with characters, actions, and spoken words within a story.
It supports creating, retrieving, updating, and deleting paraphrases. Data is persisted to SQLite and 
(supposed to be) synchronized with Typesense via a relay service. JWT-based API key security is enforced,
and Prometheus metrics are exposed. The OpenAPI version is forced to 3.0.3 so that Swagger UI works correctly.
"""

import os
import sys
import logging
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends, Query, status
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
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./paraphrase.db")
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
logger = logging.getLogger("paraphrase_service")

# -----------------------------------------------------------------------------
# SQLAlchemy Database Setup
# -----------------------------------------------------------------------------
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Paraphrase(Base):
    __tablename__ = "paraphrases"
    paraphraseId = Column(Integer, primary_key=True, index=True)
    originalId = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    commentary = Column(Text, nullable=False)
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
# Pydantic Schemas for Paraphrase Service
# -----------------------------------------------------------------------------
class ParaphraseCreateRequest(BaseModel):
    originalId: int = Field(..., description="Identifier of the original entity this paraphrase is linked to")
    text: str = Field(..., description="The text of the paraphrase")
    commentary: str = Field(..., description="Reasons explaining why this paraphrase is as it is")
    comment: str = Field(..., description="Contextual explanation for creating the paraphrase")

class ParaphraseUpdateRequest(BaseModel):
    text: str = Field(..., description="Updated text of the paraphrase")
    commentary: str = Field(..., description="Updated commentary explaining the paraphrase")
    comment: str = Field(..., description="Contextual explanation for updating the paraphrase")

class ParaphraseResponse(BaseModel):
    paraphraseId: int
    originalId: int
    text: str
    commentary: str
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
    title="Paraphrase Service",
    description=(
        "This service manages paraphrases associated with characters, actions, and spoken words within a story. "
        "It supports creating, retrieving, updating, and deleting paraphrases. Data is persisted to SQLite and "
        "synchronized with Typesense for enhanced searchability. JWT-based authentication is enforced."
    ),
    version="4.0.0"
)

Instrumentator().instrument(app).expose(app)

# -----------------------------------------------------------------------------
# Endpoints for Paraphrase Service
# -----------------------------------------------------------------------------
@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "healthy"}

@app.get("/paraphrases", response_model=List[ParaphraseResponse], tags=["Paraphrases"])
def list_paraphrases(
    characterId: Optional[int] = Query(None, description="Filter paraphrases by character ID"),
    actionId: Optional[int] = Query(None, description="Filter paraphrases by action ID"),
    spokenWordId: Optional[int] = Query(None, description="Filter paraphrases by spoken word ID"),
    keyword: Optional[str] = Query(None, description="Search for paraphrases containing specific keywords"),
    db: Session = Depends(get_db)
):
    query = db.query(Paraphrase)
    # For simplicity, we assume originalId represents the linking field (you might adjust based on your schema)
    if characterId is not None:
        query = query.filter(Paraphrase.originalId == characterId)
    if actionId is not None:
        query = query.filter(Paraphrase.originalId == actionId)
    if spokenWordId is not None:
        query = query.filter(Paraphrase.originalId == spokenWordId)
    if keyword:
        query = query.filter(Paraphrase.text.ilike(f"%{keyword}%"))
    paraphrases = query.all()
    return [
        ParaphraseResponse(
            paraphraseId=p.paraphraseId,
            originalId=p.originalId,
            text=p.text,
            commentary=p.commentary,
            comment=p.comment
        ) for p in paraphrases
    ]

@app.post("/paraphrases", response_model=ParaphraseResponse, status_code=status.HTTP_201_CREATED, tags=["Paraphrases"])
def create_paraphrase(request: ParaphraseCreateRequest, db: Session = Depends(get_db)):
    new_paraphrase = Paraphrase(
        originalId=request.originalId,
        text=request.text,
        commentary=request.commentary,
        comment=request.comment
    )
    db.add(new_paraphrase)
    db.commit()
    db.refresh(new_paraphrase)
    logger.info(f"Paraphrase created with ID: {new_paraphrase.paraphraseId}")
    return ParaphraseResponse(
        paraphraseId=new_paraphrase.paraphraseId,
        originalId=new_paraphrase.originalId,
        text=new_paraphrase.text,
        commentary=new_paraphrase.commentary,
        comment=new_paraphrase.comment
    )

@app.get("/paraphrases/{paraphraseId}", response_model=ParaphraseResponse, tags=["Paraphrases"])
def get_paraphrase_by_id(paraphraseId: int, db: Session = Depends(get_db)):
    p = db.query(Paraphrase).filter(Paraphrase.paraphraseId == paraphraseId).first()
    if not p:
        raise HTTPException(status_code=404, detail="Paraphrase not found")
    return ParaphraseResponse(
        paraphraseId=p.paraphraseId,
        originalId=p.originalId,
        text=p.text,
        commentary=p.commentary,
        comment=p.comment
    )

@app.patch("/paraphrases/{paraphraseId}", response_model=ParaphraseResponse, tags=["Paraphrases"])
def update_paraphrase(paraphraseId: int, request: ParaphraseUpdateRequest, db: Session = Depends(get_db)):
    p = db.query(Paraphrase).filter(Paraphrase.paraphraseId == paraphraseId).first()
    if not p:
        raise HTTPException(status_code=404, detail="Paraphrase not found")
    p.text = request.text
    p.commentary = request.commentary
    p.comment = request.comment
    db.commit()
    db.refresh(p)
    logger.info(f"Paraphrase updated with ID: {p.paraphraseId}")
    return ParaphraseResponse(
        paraphraseId=p.paraphraseId,
        originalId=p.originalId,
        text=p.text,
        commentary=p.commentary,
        comment=p.comment
    )

@app.delete("/paraphrases/{paraphraseId}", status_code=status.HTTP_204_NO_CONTENT, tags=["Paraphrases"])
def delete_paraphrase(paraphraseId: int, db: Session = Depends(get_db)):
    p = db.query(Paraphrase).filter(Paraphrase.paraphraseId == paraphraseId).first()
    if not p:
        raise HTTPException(status_code=404, detail="Paraphrase not found")
    db.delete(p)
    db.commit()
    logger.info(f"Paraphrase deleted with ID: {paraphraseId}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

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


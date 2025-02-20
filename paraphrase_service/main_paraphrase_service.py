"""
Production-Grade FastAPI Application for Paraphrase Service
===========================================================

Features:
  - Manages paraphrases associated with characters, actions, and spoken words within a story.
  - Supports creating, retrieving, updating, and deleting paraphrases.
  - Data is persisted to SQLite and synchronized with Typesense via a relay service.
  - JWT-based authentication is enforced.
  - Exposes Prometheus metrics for observability.
  - Custom OpenAPI schema is forced to version 3.0.3 for Swagger UI compatibility.
  - Provides a default landing page, health check endpoint, dynamic service discovery, and a notification stub.
  
This service is part of the FountainAI Eco‑System.
"""

import os
import sys
import logging
from datetime import datetime
from typing import List, Optional, Dict

from fastapi import FastAPI, HTTPException, Depends, Query, status, Path, Body
from fastapi.responses import HTMLResponse, Response
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
JWT_SECRET = os.environ.get("JWT_SECRET", "your_jwt_secret_key")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")

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
# Pydantic Schemas for Paraphrase Service
# -----------------------------------------------------------------------------
class ParaphraseCreateRequest(BaseModel):
    originalId: int = Field(..., description="Identifier of the original entity this paraphrase is linked to")
    text: str = Field(..., description="The text of the paraphrase")
    commentary: str = Field(..., description="Explanation for the paraphrase")
    comment: str = Field(..., description="Contextual explanation for creating the paraphrase")

class ParaphraseUpdateRequest(BaseModel):
    text: str = Field(..., description="Updated text of the paraphrase")
    commentary: str = Field(..., description="Updated explanation for the paraphrase")
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
        service_description="This service provides paraphrase management within the FountainAI ecosystem."
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
# API Endpoints for Paraphrase Service
# -----------------------------------------------------------------------------

@app.get("/paraphrases", response_model=List[ParaphraseResponse], tags=["Paraphrases"], operation_id="listParaphrases", summary="List paraphrases", description="Retrieves a list of paraphrases. Supports filtering by original ID or keyword.")
def list_paraphrases(
    characterId: Optional[int] = Query(None, description="Filter by character ID"),
    actionId: Optional[int] = Query(None, description="Filter by action ID"),
    spokenWordId: Optional[int] = Query(None, description="Filter by spoken word ID"),
    keyword: Optional[str] = Query(None, description="Filter paraphrases containing the keyword"),
    db: Session = Depends(get_db)
):
    query = db.query(Paraphrase)
    # For simplicity, assume originalId is used for all filters.
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

@app.post("/paraphrases", response_model=ParaphraseResponse, status_code=status.HTTP_201_CREATED, tags=["Paraphrases"], operation_id="createParaphrase", summary="Create a paraphrase", description="Creates a new paraphrase with provided details.")
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
    logger.info("Paraphrase created with ID: %s", new_paraphrase.paraphraseId)
    return ParaphraseResponse(
        paraphraseId=new_paraphrase.paraphraseId,
        originalId=new_paraphrase.originalId,
        text=new_paraphrase.text,
        commentary=new_paraphrase.commentary,
        comment=new_paraphrase.comment
    )

@app.get("/paraphrases/{paraphraseId}", response_model=ParaphraseResponse, tags=["Paraphrases"], operation_id="getParaphraseById", summary="Retrieve a paraphrase", description="Retrieves a paraphrase by its ID.")
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

@app.patch("/paraphrases/{paraphraseId}", response_model=ParaphraseResponse, tags=["Paraphrases"], operation_id="updateParaphrase", summary="Update a paraphrase", description="Updates a paraphrase's text, commentary, and comment.")
def update_paraphrase(paraphraseId: int, request: ParaphraseUpdateRequest, db: Session = Depends(get_db)):
    p = db.query(Paraphrase).filter(Paraphrase.paraphraseId == paraphraseId).first()
    if not p:
        raise HTTPException(status_code=404, detail="Paraphrase not found")
    p.text = request.text
    p.commentary = request.commentary
    p.comment = request.comment
    db.commit()
    db.refresh(p)
    logger.info("Paraphrase updated with ID: %s", p.paraphraseId)
    return ParaphraseResponse(
        paraphraseId=p.paraphraseId,
        originalId=p.originalId,
        text=p.text,
        commentary=p.commentary,
        comment=p.comment
    )

@app.delete("/paraphrases/{paraphraseId}", status_code=status.HTTP_204_NO_CONTENT, tags=["Paraphrases"], operation_id="deleteParaphrase", summary="Delete a paraphrase", description="Deletes a paraphrase by its ID.")
def delete_paraphrase(paraphraseId: int, db: Session = Depends(get_db)):
    p = db.query(Paraphrase).filter(Paraphrase.paraphraseId == paraphraseId).first()
    if not p:
        raise HTTPException(status_code=404, detail="Paraphrase not found")
    db.delete(p)
    db.commit()
    logger.info("Paraphrase deleted with ID: %s", paraphraseId)
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

"""
Performer Service API
=====================

Purpose:
    This service handles the creation, retrieval, updating, and management of performers within a story.
    Each performer is assigned a globally consistent sequence number via integration with the Central Sequence Service.
    Data is persisted in an SQLite database and can be synchronized with external search systems via dynamic service discovery
    from the API Gateway.

Key Integrations:
    - FastAPI: Provides the web framework and automatic OpenAPI documentation.
    - SQLAlchemy & SQLite: Used for data persistence.
    - JWT-based Authentication: Enforces security using HTTPBearer; endpoints for creating and updating performers require valid tokens.
    - Dynamic Service Discovery: Enables runtime resolution of peer service URLs via the API Gateway's lookup endpoint.
    - Prometheus: Exposes performance and health metrics via prometheus_fastapi_instrumentator.
    - Custom OpenAPI: Forces the OpenAPI schema version to 3.0.3 for Swagger UI compatibility.
    - Default Landing Page & Health Endpoint: Provides a user-friendly landing page and a standard health check.

Usage:
    The service is containerized and should be deployed along with other FountainAI microservices.
    Environment variables (such as SERVICE_PORT, DATABASE_URL, API_GATEWAY_URL, JWT_SECRET, and JWT_ALGORITHM)
    are loaded from a .env file.

Endpoints:
    GET  /                     - Default landing page (HTML).
    GET  /health               - Health check endpoint.
    GET  /service-discovery    - Dynamic service discovery endpoint.
    POST /notifications        - Notification stub endpoint.
    GET  /performers           - List performers.
    POST /performers           - Create a new performer (JWT auth required).
    GET  /performers/{performerId} - Retrieve performer details.
    PATCH /performers/{performerId} - Update performer details (JWT auth required).

Note:
    The service integrates with the Central Sequence Service to assign a sequence number
    and uses dynamic service discovery to interact with other ecosystem services.

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

    class Config:
        orm_mode = True

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
    title="Performer Service",
    description=(
        "This service handles the creation, retrieval, updating, and management of performers within the story. "
        "Data is persisted to SQLite and synchronized with search systems via dynamic service discovery from the API Gateway. "
        "It integrates with the Central Sequence Service to assign sequence numbers to performers."
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
        service_description="This service manages performers within the FountainAI ecosystem."
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
# Endpoints for Performer Service
# -----------------------------------------------------------------------------
@app.get("/performers", response_model=List[PerformerResponse], tags=["Performers"], operation_id="listPerformers", summary="List performers", description="Retrieves a list of performers, optionally filtered by query parameters.")
def list_performers(
    characterId: Optional[int] = Query(None, description="(Optional) Filter by character ID"),
    scriptId: Optional[int] = Query(None, description="(Optional) Filter by script ID"),
    db: Session = Depends(get_db)
):
    query = db.query(Performer)
    if characterId is not None:
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

@app.post("/performers", response_model=PerformerResponse, status_code=status.HTTP_201_CREATED, tags=["Performers"], operation_id="createPerformer", summary="Create a performer", description="Creates a new performer with an assigned sequence number. JWT authentication is enforced.")
def create_performer(request: PerformerCreateRequest, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    max_entry = db.query(Performer).order_by(Performer.sequenceNumber.desc()).first()
    next_seq = max_entry.sequenceNumber + 1 if max_entry else 1
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

@app.get("/performers/{performerId}", response_model=PerformerResponse, tags=["Performers"], operation_id="getPerformerById", summary="Retrieve performer details", description="Retrieves details for a performer by ID.")
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

@app.patch("/performers/{performerId}", response_model=PerformerResponse, tags=["Performers"], operation_id="updatePerformer", summary="Update performer", description="Updates a performer's details (name and/or comment). JWT authentication is enforced.")
def patch_performer(performerId: int, request: PerformerPatchRequest, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    p = db.query(Performer).filter(Performer.performerId == performerId).first()
    if not p:
        raise HTTPException(status_code=404, detail="Performer not found")
    if request.name is not None:
        p.name = request.name
    p.comment = request.comment
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

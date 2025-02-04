"""
Action Service
==============

This API manages actions associated with characters and spoken words within a story.
Data is persisted to SQLite and synchronized with peer services (via dynamic lookup from the API Gateway).
JWT-based authentication is enforced and Prometheus metrics are exposed.
The OpenAPI version is forced to 3.0.3 so that Swagger UI renders correctly.
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
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./action.db")
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
logger = logging.getLogger("action_service")

# -----------------------------------------------------------------------------
# SQLAlchemy Database Setup
# -----------------------------------------------------------------------------
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Action(Base):
    __tablename__ = "actions"
    actionId = Column(Integer, primary_key=True, index=True)
    description = Column(Text, nullable=False)
    characterId = Column(Integer, nullable=False)
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
# Pydantic Schemas for Action Service
# -----------------------------------------------------------------------------
class ActionCreateRequest(BaseModel):
    description: str = Field(..., description="Description of the action")
    characterId: int = Field(..., description="ID of the character associated with this action")
    comment: Optional[str] = Field(None, description="Contextual explanation for creating the action")

class ActionUpdateRequest(BaseModel):
    description: str = Field(..., description="Updated description of the action")
    comment: Optional[str] = Field(None, description="Contextual explanation for updating the action")

class ActionResponse(BaseModel):
    actionId: int
    description: str
    characterId: int
    sequenceNumber: int
    comment: Optional[str]

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
    title="Action Service",
    description=(
        "This service manages actions associated with characters and spoken words within a story. "
        "Data is persisted to SQLite and synchronized with search systems via dynamic service discovery from the API Gateway. "
        "It integrates with the Central Sequence Service to maintain action order."
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

@app.get("/actions", response_model=List[ActionResponse], tags=["Actions"])
def list_actions(
    characterId: Optional[int] = None,
    scriptId: Optional[int] = None,
    sectionId: Optional[int] = None,
    speechId: Optional[int] = None,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Action)
    if characterId:
        query = query.filter(Action.characterId == characterId)
    # For this example, scriptId, sectionId, and speechId filtering are not implemented,
    # as the Action model does not contain those fields.
    if keyword:
        query = query.filter(Action.description.ilike(f"%{keyword}%"))
    actions = query.all()
    return [
        ActionResponse(
            actionId=a.actionId,
            description=a.description,
            characterId=a.characterId,
            sequenceNumber=a.sequenceNumber,
            comment=a.comment
        ) for a in actions
    ]

@app.post("/actions", response_model=ActionResponse, status_code=status.HTTP_201_CREATED, tags=["Actions"])
def create_action(request: ActionCreateRequest, db: Session = Depends(get_db)):
    # For demonstration, we simulate sequence assignment: next sequence is max + 1.
    max_seq = db.query(Action).order_by(Action.sequenceNumber.desc()).first()
    next_seq = max_seq.sequenceNumber + 1 if max_seq else 1
    new_action = Action(
        description=request.description,
        characterId=request.characterId,
        sequenceNumber=next_seq,
        comment=request.comment
    )
    db.add(new_action)
    db.commit()
    db.refresh(new_action)
    logger.info(f"Action created with ID: {new_action.actionId}")
    return ActionResponse(
        actionId=new_action.actionId,
        description=new_action.description,
        characterId=new_action.characterId,
        sequenceNumber=new_action.sequenceNumber,
        comment=new_action.comment
    )

@app.get("/actions/{actionId}", response_model=ActionResponse, tags=["Actions"])
def get_action_by_id(actionId: int, db: Session = Depends(get_db)):
    action = db.query(Action).filter(Action.actionId == actionId).first()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    return ActionResponse(
        actionId=action.actionId,
        description=action.description,
        characterId=action.characterId,
        sequenceNumber=action.sequenceNumber,
        comment=action.comment
    )

@app.patch("/actions/{actionId}", response_model=ActionResponse, tags=["Actions"])
def update_action(actionId: int, request: ActionUpdateRequest, db: Session = Depends(get_db)):
    action = db.query(Action).filter(Action.actionId == actionId).first()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    action.description = request.description
    if request.comment is not None:
        action.comment = request.comment
    db.commit()
    db.refresh(action)
    logger.info(f"Action updated with ID: {action.actionId}")
    return ActionResponse(
        actionId=action.actionId,
        description=action.description,
        characterId=action.characterId,
        sequenceNumber=action.sequenceNumber,
        comment=action.comment
    )

@app.delete("/actions/{actionId}", status_code=status.HTTP_204_NO_CONTENT, tags=["Actions"])
def delete_action(actionId: int, db: Session = Depends(get_db)):
    action = db.query(Action).filter(Action.actionId == actionId).first()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    db.delete(action)
    db.commit()
    logger.info(f"Action deleted with ID: {actionId}")
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


"""
Action Service
==============
This API manages actions associated with characters and spoken words within a story.
Data is persisted to SQLite and synchronized with peer services (via dynamic lookup from the API Gateway).
JWT-based authentication is enforced and Prometheus metrics are exposed.
The OpenAPI version is forced to 3.0.3 for Swagger UI compatibility.

Enhancements in this version:
- Implements dynamic service discovery via the API Gateway.
- Integrates with the Notification Service for both sending and (stub for) receiving notifications.
- Provides a default landing page and a standardized health endpoint.
- Uses semantic API metadata (camelCase operationIds, clear summaries, and concise descriptions).
"""

import os
import sys
import logging
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends, Response, status
from fastapi.openapi.utils import get_openapi
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import HTMLResponse
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
CENTRAL_SEQUENCE_SERVICE_NAME = os.getenv("CENTRAL_SEQUENCE_SERVICE_NAME", "central_sequence_service")

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
# Helper Functions for Service Discovery & Notification
# -----------------------------------------------------------------------------
def get_service_url(service_name: str) -> str:
    """
    Lookup the URL for a given service using the API Gateway's lookup endpoint.
    """
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

def send_notification(subject: str, message: str):
    """
    Sends a notification via the Notification Service.
    This stub currently sends notifications and is designed to be extended for receiving notifications.
    """
    try:
        notification_url = get_service_url("notification_service")
        payload = {"subject": subject, "message": message}
        response = httpx.post(f"{notification_url}/notifications", json=payload, timeout=5.0)
        response.raise_for_status()
        logger.info("Notification sent: %s", subject)
    except Exception as e:
        logger.error("Failed to send notification: %s", e)
        # Do not block core functionality on notification failure.

# -----------------------------------------------------------------------------
# FastAPI Application Initialization
# -----------------------------------------------------------------------------
app = FastAPI(
    title="Action Service",
    description=(
        "This service manages actions associated with characters and spoken words within a story. "
        "Data is persisted to SQLite and synchronized with peer services via dynamic service discovery from the API Gateway. "
        "It integrates with the Central Sequence Service to maintain action order."
    ),
    version="4.0.0"
)

Instrumentator().instrument(app).expose(app)

# -----------------------------------------------------------------------------
# Default Landing Page
# -----------------------------------------------------------------------------
@app.get(
    "/",
    response_class=HTMLResponse,
    tags=["Landing"],
    operation_id="getLandingPage",
    summary="Display landing page",
    description="Returns a styled landing page with service name, version, and links to API docs and health check."
)
def landing_page():
    try:
        html_content = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <title>{service_title}</title>
          <style>
            body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: #f4f4f4; margin: 0; padding: 0; display: flex; justify-content: center; align-items: center; height: 100vh; }}
            .container {{ background: #fff; padding: 40px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center; max-width: 600px; margin: auto; }}
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
            <p>This service manages actions associated with characters and spoken words.</p>
            <p>
              Visit the <a href="/docs">API Documentation</a> or check the <a href="/health">Health Status</a>.
            </p>
          </div>
        </body>
        </html>
        """
        filled_html = html_content.format(
            service_title=str(app.title),
            service_version=str(app.version)
        )
        return HTMLResponse(content=filled_html, status_code=200)
    except Exception as e:
        logger.error("Error generating landing page: %s", e)
        raise HTTPException(status_code=500, detail="Internal Server Error")

# -----------------------------------------------------------------------------
# Health Endpoint
# -----------------------------------------------------------------------------
@app.get(
    "/health",
    response_model=dict,
    tags=["Health"],
    operation_id="getHealthStatus",
    summary="Retrieve service health status",
    description="Returns the current health status of the service as a JSON object (e.g., {'status': 'healthy'})."
)
def health_check():
    return {"status": "healthy"}

# -----------------------------------------------------------------------------
# Action Endpoints
# -----------------------------------------------------------------------------
@app.get(
    "/actions",
    response_model=List[ActionResponse],
    tags=["Actions"],
    operation_id="listActions",
    summary="List actions",
    description="Returns a list of actions, optionally filtered by characterId or keyword."
)
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

@app.post(
    "/actions",
    response_model=ActionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Actions"],
    operation_id="createAction",
    summary="Create a new action",
    description="Creates a new action by obtaining a global sequence number from the Central Sequence Service and storing it in the database."
)
def create_action(
    request: ActionCreateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    # Discover the Central Sequence Service URL.
    try:
        central_sequence_url = get_service_url(CENTRAL_SEQUENCE_SERVICE_NAME)
    except Exception as e:
        logger.error(f"Central Sequence Service lookup failed: {e}")
        raise HTTPException(status_code=503, detail="Central Sequence Service unavailable")

    # Prepare payload for the Central Sequence Service.
    sequence_payload = {
        "elementType": "action",
        "elementId": request.characterId,
        "comment": "Action creation sequence assignment"
    }

    try:
        # Call the Central Sequence Service to get the next sequence number.
        response = httpx.post(f"{central_sequence_url}/sequence", json=sequence_payload, timeout=5.0)
        response.raise_for_status()
        sequence_data = response.json()
        next_seq = sequence_data.get("sequenceNumber")
        if next_seq is None:
            raise ValueError("No sequenceNumber returned")
    except Exception as e:
        logger.error(f"Failed to obtain sequence number: {e}")
        raise HTTPException(status_code=503, detail="Failed to obtain sequence number")

    # Create the new action using the obtained sequence number.
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

    # Send a notification about action creation.
    send_notification("Action Created", f"Action ID {new_action.actionId} created with sequence number {next_seq}.")

    return ActionResponse(
        actionId=new_action.actionId,
        description=new_action.description,
        characterId=new_action.characterId,
        sequenceNumber=new_action.sequenceNumber,
        comment=new_action.comment
    )

@app.get(
    "/actions/{actionId}",
    response_model=ActionResponse,
    tags=["Actions"],
    operation_id="getActionById",
    summary="Retrieve action by ID",
    description="Returns the action details for the specified actionId."
)
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

@app.patch(
    "/actions/{actionId}",
    response_model=ActionResponse,
    tags=["Actions"],
    operation_id="updateAction",
    summary="Update an action",
    description="Updates an existing action's description and comment."
)
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

@app.delete(
    "/actions/{actionId}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Actions"],
    operation_id="deleteAction",
    summary="Delete an action",
    description="Deletes the specified action from the database."
)
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

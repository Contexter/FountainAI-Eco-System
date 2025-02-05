"""
Production-Grade FastAPI Application for Notification Service API
=====================================================================

Features:
  - Manage notifications (create, list, mark as read).
  - Endpoints secured with JWT-based Bearer authentication; admin access required for creation.
  - Uses SQLAlchemy with SQLite for persistence.
  - Environment configuration via a .env file.
  - Logging and Prometheus instrumentation.
  - Custom OpenAPI schema override (set to OpenAPI 3.0.3 for Swagger UI compatibility).
  - Default landing page and health check endpoints.
  - Dynamic service discovery endpoint for inter-service integration.

Note:
  This service may integrate with other authentication services (sharing SECRET_KEY, etc.).
"""

import os
import logging
from datetime import datetime
from typing import List, Optional, Dict

from fastapi import FastAPI, HTTPException, Depends, status, Path, Body, Query
from fastapi.responses import HTMLResponse
from fastapi.openapi.utils import get_openapi
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# SQLAlchemy imports
from sqlalchemy import Column, Integer, String, Boolean, DateTime, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# Prometheus Instrumentator for monitoring
from prometheus_fastapi_instrumentator import Instrumentator
from jose import JWTError, jwt
import httpx

# -----------------------------------------------------------------------------
# Load Environment Variables
# -----------------------------------------------------------------------------
load_dotenv()
SECRET_KEY = os.environ.get("SECRET_KEY", "supersecretkey")
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./notifications.db")
API_GATEWAY_URL = os.environ.get("API_GATEWAY_URL", "http://gateway:8000")

# -----------------------------------------------------------------------------
# Logging Configuration
# -----------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Database Setup with SQLAlchemy
# -----------------------------------------------------------------------------
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# -----------------------------------------------------------------------------
# Database Model for Notifications
# -----------------------------------------------------------------------------
class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    message = Column(String, nullable=False)
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# -----------------------------------------------------------------------------
# Dependency: get DB session
# -----------------------------------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -----------------------------------------------------------------------------
# Security Dependencies
# -----------------------------------------------------------------------------
security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except JWTError as e:
        logger.error("JWT decoding error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username: Optional[str] = payload.get("sub")
    roles: Optional[str] = payload.get("roles")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"username": username, "roles": roles or ""}

def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    roles = current_user.get("roles", "")
    if "admin" not in [role.strip().lower() for role in roles.split(",")]:
        logger.warning("User %s attempted admin action without privileges", current_user.get("username"))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required."
        )
    return current_user

# -----------------------------------------------------------------------------
# Helper Function for Dynamic Service Discovery
# -----------------------------------------------------------------------------
def get_service_url(service_name: str) -> str:
    """
    Queries the API Gateway's lookup endpoint to resolve the URL of the given service.
    """
    try:
        response = httpx.get(f"{API_GATEWAY_URL}/lookup/{service_name}", timeout=5.0)
        response.raise_for_status()
        url = response.json().get("url")
        if not url:
            raise ValueError("No URL returned from service lookup.")
        return url
    except Exception as e:
        logger.error("Service discovery failed for '%s': %s", service_name, e)
        raise HTTPException(status_code=503, detail=f"Service discovery failed for '{service_name}'")

# -----------------------------------------------------------------------------
# Pydantic Schemas
# -----------------------------------------------------------------------------
class NotificationCreate(BaseModel):
    message: str = Field(..., description="The notification message.")

class NotificationResponse(BaseModel):
    id: int
    message: str
    read: bool
    created_at: datetime

    class Config:
        orm_mode = True

# -----------------------------------------------------------------------------
# FastAPI Application Initialization
# -----------------------------------------------------------------------------
app = FastAPI(
    title="Notification Service API",
    description="Service for managing notifications.",
    version="1.0.0",
    servers=[{"url": "http://localhost:8003", "description": "Local development server"}]
)

# -----------------------------------------------------------------------------
# Custom OpenAPI Schema Generation (set to OpenAPI 3.0.3 for Swagger UI compatibility)
# -----------------------------------------------------------------------------
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    openapi_schema["openapi"] = "3.0.3"
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# -----------------------------------------------------------------------------
# Prometheus Monitoring Instrumentation
# -----------------------------------------------------------------------------
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
        service_description="This service provides its core notification management within the FountainAI ecosystem."
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
# Notification Receiving Endpoints
# -----------------------------------------------------------------------------

@app.post("/notifications", response_model=NotificationResponse, status_code=status.HTTP_201_CREATED, tags=["Notifications"], operation_id="createNotification", summary="Create a notification", description="Creates a new notification. Admin privileges are required.")
def create_notification(notification: NotificationCreate = Body(...), db: Session = Depends(get_db), _: dict = Depends(require_admin)):
    new_notification = Notification(message=notification.message)
    db.add(new_notification)
    db.commit()
    db.refresh(new_notification)
    logger.info("Notification created with id %s", new_notification.id)
    return new_notification

@app.get("/notifications", response_model=List[NotificationResponse], tags=["Notifications"], operation_id="listNotifications", summary="List notifications", description="Lists all notifications.")
def list_notifications(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    notifications = db.query(Notification).order_by(Notification.created_at.desc()).all()
    return notifications

@app.put("/notifications/{notification_id}/read", response_model=NotificationResponse, tags=["Notifications"], operation_id="markNotificationRead", summary="Mark notification as read", description="Marks a notification as read.")
def mark_notification_read(notification_id: int = Path(..., description="The ID of the notification."), db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    notif = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found.")
    notif.read = True
    db.commit()
    db.refresh(notif)
    logger.info("Notification id %s marked as read", notification_id)
    return notif

# -----------------------------------------------------------------------------
# Run the Application
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)

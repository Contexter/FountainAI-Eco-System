"""
main.py

Production-Grade FastAPI Application for Notification Service API

Features:
  - Manage notifications (create, list, mark as read)
  - Endpoints secured with JWT-based Bearer authentication; admin access required for creation.
  - Uses SQLAlchemy with SQLite for persistence.
  - Environment configuration via a .env file.
  - Logging and Prometheus instrumentation.
  - Custom OpenAPI schema override (set to 3.0.3 for Swagger UI compatibility).

Note:
  This service may integrate with other authentication services (sharing SECRET_KEY, etc.)
"""

import os
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends, status, Path, Body
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

# -----------------------------------------------------------------------------
# Load Environment Variables
# -----------------------------------------------------------------------------
load_dotenv()
SECRET_KEY = os.environ.get("SECRET_KEY", "supersecretkey")
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./notifications.db")

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

# Create tables.
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
        orm_mode = True  # This enables conversion from ORM objects to dict

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
# Custom OpenAPI Schema Generation (Swagger-compatible)
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
# API Endpoints
# -----------------------------------------------------------------------------

@app.post("/notifications", response_model=NotificationResponse, status_code=status.HTTP_201_CREATED, tags=["Notifications"], operation_id="create_notification")
def create_notification(notification: NotificationCreate = Body(...), db: Session = Depends(get_db), _: dict = Depends(require_admin)):
    """
    Create a new notification.
    Admin privileges are required.
    """
    new_notification = Notification(message=notification.message)
    db.add(new_notification)
    db.commit()
    db.refresh(new_notification)
    logger.info("Notification created with id %s", new_notification.id)
    return new_notification

@app.get("/notifications", response_model=List[NotificationResponse], tags=["Notifications"], operation_id="list_notifications")
def list_notifications(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """
    List all notifications.
    """
    notifications = db.query(Notification).order_by(Notification.created_at.desc()).all()
    return notifications

@app.put("/notifications/{notification_id}/read", response_model=NotificationResponse, tags=["Notifications"], operation_id="mark_notification_read")
def mark_notification_read(notification_id: int = Path(..., description="The ID of the notification."), db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """
    Mark a notification as read.
    """
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

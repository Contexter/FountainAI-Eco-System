"""
FountainAI 2FA Service
=======================

This self-contained FastAPI application implements two-factor authentication (2FA)
for the FountainAI ecosystem. It provides endpoints to generate and verify time-based OTPs (TOTP)
using a per-user OTP secret.

For demonstration purposes, the OTP code is returned in the response.
In production, OTP delivery should be handled via email or SMS, and sensitive values (like SECRET_KEY)
must be managed securely.

Enhancements in this version:
- Implements dynamic service discovery via the API Gateway.
- Integrates with the Notification Service for sending (and future receiving) notifications.
- Provides a default landing page and a standardized health endpoint.
- Uses semantic API metadata (camelCase operationIds, clear summaries, and concise descriptions).
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, status, Body
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import pyotp
from jose import JWTError, jwt
import httpx
from prometheus_fastapi_instrumentator import Instrumentator

# --- SQLAlchemy Setup ---
from sqlalchemy import Column, Integer, String, Boolean, DateTime, create_engine, func
from sqlalchemy.orm import sessionmaker, declarative_base, Session

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
load_dotenv()  # Load environment variables from .env

SECRET_KEY = os.getenv("SECRET_KEY", "your_super_secret_key")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./2fa.db")
OTP_EXPIRATION_MINUTES = int(os.getenv("OTP_EXPIRATION_MINUTES", "5"))
ALGORITHM = "HS256"

# API Gateway URL for dynamic service discovery.
API_GATEWAY_URL = os.getenv("API_GATEWAY_URL", "http://gateway:8000")

# -----------------------------------------------------------------------------
# Logging Configuration
# -----------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("2FAService")

# -----------------------------------------------------------------------------
# SQLAlchemy Database Setup
# -----------------------------------------------------------------------------
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Models
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    otp_secret = Column(String, nullable=True)
    otp_enabled = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class OTPLog(Base):
    __tablename__ = "otp_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    otp_code = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    verified = Column(Boolean, default=False)

Base.metadata.create_all(bind=engine)

def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -----------------------------------------------------------------------------
# Dynamic Service Discovery & Notification Integration
# -----------------------------------------------------------------------------
def get_service_url(service_name: str) -> str:
    """
    Lookup the URL for a given service using the API Gateway's lookup endpoint.
    """
    try:
        response = httpx.get(f"{API_GATEWAY_URL}/lookup/{service_name}", timeout=5.0)
        response.raise_for_status()
        url = response.json().get("url")
        if not url:
            raise ValueError("No URL returned")
        return url
    except Exception as e:
        logger.error(f"Service discovery failed for '{service_name}': {e}")
        raise HTTPException(status_code=503, detail=f"Service discovery failed for '{service_name}'")

def send_notification(subject: str, message: str):
    """
    Sends a notification via the Notification Service.
    This stub currently sends notifications and is designed to be extended to receive notifications in the future.
    """
    try:
        notification_url = get_service_url("notification_service")
        payload = {"subject": subject, "message": message}
        response = httpx.post(f"{notification_url}/notifications", json=payload, timeout=5.0)
        response.raise_for_status()
        logger.info("Notification sent: %s", subject)
    except Exception as e:
        logger.error("Failed to send notification: %s", e)
        # Notification failures should not block core functionality.

# -----------------------------------------------------------------------------
# Pydantic Schemas
# -----------------------------------------------------------------------------
class OTPGenerateResponse(BaseModel):
    otp_code: str
    expires_at: datetime

    class Config:
        orm_mode = True

class OTPVerifyRequest(BaseModel):
    username: str = Field(..., description="The username for OTP verification")
    otp_code: str = Field(..., description="The OTP code to verify")

class OTPVerifyResponse(BaseModel):
    success: bool

# -----------------------------------------------------------------------------
# Core OTP Functions
# -----------------------------------------------------------------------------
def generate_user_otp(username: str, db: Session) -> OTPGenerateResponse:
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.otp_enabled:
        raise HTTPException(status_code=404, detail="User not found or 2FA not enabled.")
    if not user.otp_secret:
        raise HTTPException(status_code=400, detail="User OTP secret not configured.")

    totp = pyotp.TOTP(user.otp_secret)
    otp_code = totp.now()
    expires_at = datetime.utcnow() + timedelta(minutes=OTP_EXPIRATION_MINUTES)

    otp_log = OTPLog(
        user_id=user.id,
        otp_code=otp_code,
        expires_at=expires_at,
        verified=False
    )
    db.add(otp_log)
    db.commit()
    db.refresh(otp_log)
    logger.info("Generated OTP for user %s", username)
    
    # Send a notification about OTP generation.
    send_notification("OTP Generated", f"OTP for user '{username}' generated; expires at {expires_at.isoformat()}.")

    return OTPGenerateResponse(otp_code=otp_code, expires_at=expires_at)

def verify_user_otp(username: str, otp_code: str, db: Session) -> bool:
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    totp = pyotp.TOTP(user.otp_secret)
    if not totp.verify(otp_code):
        raise HTTPException(status_code=401, detail="Invalid OTP or expired.")

    otp_log = db.query(OTPLog).filter(
        OTPLog.user_id == user.id,
        OTPLog.otp_code == otp_code
    ).first()

    if not otp_log or otp_log.verified:
        raise HTTPException(status_code=400, detail="OTP already used or not found.")

    otp_log.verified = True
    db.commit()
    logger.info("OTP verified for user %s", username)
    return True

# -----------------------------------------------------------------------------
# FastAPI Application Initialization
# -----------------------------------------------------------------------------
app = FastAPI(
    title="FountainAI 2FA Service",
    version="1.0.0",
    description=(
        "A standalone microservice providing two-factor authentication (2FA) using time-based OTP (TOTP) "
        "to enhance security in the FountainAI ecosystem. Integrates dynamic service discovery and supports notifications."
    )
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
            <p>This service provides two-factor authentication via OTP generation and verification.</p>
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
    return {"status": "2FA Service is up and running!"}

# -----------------------------------------------------------------------------
# 2FA Endpoints
# -----------------------------------------------------------------------------
@app.post(
    "/auth/generate",
    response_model=OTPGenerateResponse,
    tags=["2FA Authentication"],
    operation_id="generateOtp",
    summary="Generate an OTP",
    description="Generates a time-based OTP for the specified user and returns the OTP code along with its expiration time."
)
def generate_otp_endpoint(username: str, db: Session = Depends(get_db)):
    return generate_user_otp(username, db)

@app.post(
    "/auth/verify",
    response_model=OTPVerifyResponse,
    tags=["2FA Authentication"],
    operation_id="verifyOtp",
    summary="Verify an OTP",
    description="Verifies the provided OTP for the specified user and returns a success status."
)
def verify_otp_endpoint(payload: OTPVerifyRequest, db: Session = Depends(get_db)):
    success = verify_user_otp(payload.username, payload.otp_code, db)
    return OTPVerifyResponse(success=success)

# -----------------------------------------------------------------------------
# Custom OpenAPI Schema Generation
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
    # Force OpenAPI version 3.0.3 for Swagger UI compatibility.
    schema["openapi"] = "3.0.3"
    app.openapi_schema = schema
    return schema

app.openapi = custom_openapi

# -----------------------------------------------------------------------------
# Run the Application
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)

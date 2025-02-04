"""
FountainAI 2FA Service
=======================

This self-contained FastAPI application implements a Two-Factor Authentication (2FA)
service for the FountainAI ecosystem. It provides endpoints to generate and verify
time-based OTPs (TOTP) using a per-user OTP secret.

For demonstration purposes, the OTP code is returned in the response.
In production, you would deliver the OTP via email or SMS.

Note: In production, sensitive values (like SECRET_KEY) should be managed securely.
"""

import os
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, status, Path, Body
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, Field
from dotenv import load_dotenv

import pyotp
from jose import JWTError, jwt

# --- SQLAlchemy Setup ---
from sqlalchemy import Column, Integer, String, Boolean, DateTime, create_engine, func
from sqlalchemy.orm import sessionmaker, declarative_base, Session

# --- Prometheus Instrumentation ---
from prometheus_fastapi_instrumentator import Instrumentator

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
load_dotenv()  # Load .env file if available

SECRET_KEY = os.getenv("SECRET_KEY", "your_super_secret_key")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./2fa.db")
OTP_EXPIRATION_MINUTES = int(os.getenv("OTP_EXPIRATION_MINUTES", "5"))
ALGORITHM = "HS256"

# -----------------------------------------------------------------------------
# Logging Configuration
# -----------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("2FA-Service")

# -----------------------------------------------------------------------------
# Database Setup (SQLAlchemy)
# -----------------------------------------------------------------------------
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------
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

# Create tables if they don't exist.
Base.metadata.create_all(bind=engine)

# -----------------------------------------------------------------------------
# Dependency: get DB session
# -----------------------------------------------------------------------------
def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -----------------------------------------------------------------------------
# Pydantic Schemas
# -----------------------------------------------------------------------------
class OTPGenerateResponse(BaseModel):
    otp_code: str
    expires_at: datetime

    class Config:
        orm_mode = True

class OTPVerifyRequest(BaseModel):
    username: str
    otp_code: str

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
app = FastAPI()

# -----------------------------------------------------------------------------
# Custom OpenAPI Schema Generation (Set to 3.1.0)
# -----------------------------------------------------------------------------
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title="FountainAI 2FA Service",
        version="1.0.0",
        description=(
            "A standalone microservice providing two-factor authentication (2FA) "
            "using time-based OTP (TOTP) to enhance security in the FountainAI ecosystem."
        ),
        routes=app.routes,
    )
    schema["openapi"] = "3.0.3"
    app.openapi_schema = schema
    return app.openapi_schema

app.openapi = custom_openapi

# -----------------------------------------------------------------------------
# Prometheus Instrumentation
# -----------------------------------------------------------------------------
Instrumentator().instrument(app).expose(app)

# -----------------------------------------------------------------------------
# API Endpoints
# -----------------------------------------------------------------------------
@app.get("/", tags=["Health Check"])
def health_check():
    return {"status": "2FA Service is up and running!"}

@app.post("/auth/generate", response_model=OTPGenerateResponse, tags=["2FA Authentication"], summary="Generate an OTP")
def generate_otp_endpoint(username: str, db: Session = Depends(get_db)):
    """
    Generate a time-based OTP for the specified user.
    Query Parameter:
      - username: the username for which to generate the OTP.
    Returns the OTP code and its expiration time.
    """
    return generate_user_otp(username, db)

@app.post("/auth/verify", response_model=OTPVerifyResponse, tags=["2FA Authentication"], summary="Verify an OTP")
def verify_otp_endpoint(payload: OTPVerifyRequest, db: Session = Depends(get_db)):
    """
    Verify the OTP for the specified user.
    Request Body:
      - username: the user's username.
      - otp_code: the OTP code to verify.
    Returns success status.
    """
    success = verify_user_otp(payload.username, payload.otp_code, db)
    return OTPVerifyResponse(success=success)

# -----------------------------------------------------------------------------
# Run the Application
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)


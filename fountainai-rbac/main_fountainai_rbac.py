"""
Production-Grade FastAPI Application for Authentication & RBAC Service API
=========================================================================

Features:
    - Secure user registration and login with SQLite persistent storage.
    - JWT-based access and refresh tokens with token revocation.
    - Role-based access control.
    - Password hashing using PassLib.
    - Environment configuration via .env.
    - Default landing page at the root with API documentation links.
    - Separate health check endpoint.
    - Detailed logging and Prometheus-based monitoring.
    - Custom OpenAPI schema version (3.1.0).

Endpoints:
    GET  /                 - Default landing page (HTML).
    GET  /health           - Health check endpoint.
    POST /register         - Register a new user.
    POST /login            - User login (returns access and refresh tokens).
    POST /token/refresh    - Refresh an access token using a refresh token.
    GET  /users            - List all users (admin only).
    GET  /users/{username} - Retrieve a specific user's details.
    PATCH /users/{username} - Update user information.
    DELETE /users/{username} - Delete a user (admin only).
    GET  /service-discovery - Dynamic service discovery endpoint.
    POST /notifications    - Notification receiving stub.

Notes:
    - Replace SQLite with a production-grade database when needed.
    - In production, ensure SECRET_KEY and other sensitive settings are set via environment variables.
"""

import os
import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import (
    FastAPI,
    HTTPException,
    Depends,
    status,
    Path,
    Body,
    Query
)
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.openapi.utils import get_openapi
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# SQLAlchemy imports
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship
from sqlalchemy import create_engine

# Prometheus Instrumentator for monitoring
from prometheus_fastapi_instrumentator import Instrumentator
import httpx

# -----------------------------------------------------------------------------
# Load Environment Variables and Configure Logging
# -----------------------------------------------------------------------------
load_dotenv()  # Loads the .env file
SECRET_KEY = os.environ.get("SECRET_KEY", "fallback_secret_key")
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./app.db")
API_GATEWAY_URL = os.environ.get("API_GATEWAY_URL", "http://gateway:8000")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Database Setup with SQLAlchemy
# -----------------------------------------------------------------------------
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# -----------------------------------------------------------------------------
# Database Models
# -----------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    roles = Column(String, nullable=False)
    
    refresh_tokens = relationship("RefreshToken", back_populates="owner", cascade="all, delete-orphan")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    
    id = Column(Integer, primary_key=True, index=True)
    token_id = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    revoked = Column(Boolean, default=False)
    expires = Column(DateTime, nullable=False)
    
    owner = relationship("User", back_populates="refresh_tokens")

Base.metadata.create_all(bind=engine)

# -----------------------------------------------------------------------------
# Dependency to Get DB Session
# -----------------------------------------------------------------------------
def get_db():
    """Yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -----------------------------------------------------------------------------
# Password Hashing Configuration using PassLib
# -----------------------------------------------------------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    """Hash a plain-text password."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a hashed version."""
    return pwd_context.verify(plain_password, hashed_password)

# -----------------------------------------------------------------------------
# JWT Token Utilities
# -----------------------------------------------------------------------------
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_MINUTES = 1440  # 24 hours

def create_access_token(subject: str, roles: str, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode = {"sub": subject, "roles": roles, "exp": expire, "type": "access"}
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(subject: str, db: Session, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT refresh token with a unique ID (jti) and store it in the database.
    """
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES))
    jti = str(uuid.uuid4())
    to_encode = {"sub": subject, "exp": expire, "type": "refresh", "jti": jti}
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    
    user = db.query(User).filter(User.username == subject).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found for refresh token creation.")
    
    new_refresh_token = RefreshToken(
        token_id=jti,
        user_id=user.id,
        revoked=False,
        expires=expire
    )
    db.add(new_refresh_token)
    db.commit()
    db.refresh(new_refresh_token)
    logger.info("Refresh token created with jti %s for user %s", jti, subject)
    return encoded_jwt

def decode_token(token: str) -> Dict:
    """Decode a JWT token. Raises HTTPException if token is invalid or expired."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        logger.error("JWT decoding failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

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
# Notification Service Integration (Stub)
# -----------------------------------------------------------------------------
# This stub endpoint will serve as the interface for receiving notifications.
# Future enhancements will implement full two-way communication.
# Note: This endpoint is defined before the API endpoints.
from fastapi import APIRouter
notification_router = APIRouter()

@notification_router.post("/notifications", tags=["Notification"], operation_id="receiveNotification", summary="Receive notifications", description="Stub endpoint for receiving notifications from the central Notification Service.")
def receive_notification(payload: dict):
    logger.info("Received notification payload: %s", payload)
    return {"message": "Notification received (stub)."}

# -----------------------------------------------------------------------------
# Pydantic Models for Request and Response Schemas
# -----------------------------------------------------------------------------

class UserCreate(BaseModel):
    username: str = Field(..., description="The user's username.")
    password: str = Field(..., description="The user's password.")
    roles: str = Field(..., description="Comma-separated roles.")

class UserResponse(BaseModel):
    username: str = Field(..., description="The user's username.")
    roles: str = Field(..., description="Comma-separated roles assigned to the user.")

class UserLogin(BaseModel):
    username: str = Field(..., description="The user's username.")
    password: str = Field(..., description="The user's password.")

class UserUpdate(BaseModel):
    password: Optional[str] = Field(None, description="The new password for the user.")
    roles: Optional[str] = Field(None, description="Updated comma-separated roles.")

class Token(BaseModel):
    access_token: str = Field(..., description="JWT access token.")
    refresh_token: str = Field(..., description="JWT refresh token.")
    token_type: str = Field(..., description="Type of the token, e.g., 'bearer'.")

class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT access token.")
    token_type: str = Field(..., description="Type of the token, e.g., 'bearer'.")

class TokenRefresh(BaseModel):
    refresh_token: str = Field(..., description="Refresh token to obtain a new access token.")

# -----------------------------------------------------------------------------
# Security Dependencies
# -----------------------------------------------------------------------------
security = HTTPBearer()

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> Dict:
    """
    Verify JWT from Bearer token and return user payload.
    """
    token = credentials.credentials
    payload = decode_token(token)
    if payload.get("type") != "access":
        logger.warning("Token is not an access token.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username: str = payload.get("sub")
    if username is None:
        logger.error("Token payload missing 'sub'.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.query(User).filter(User.username == username).first()
    if not user:
        logger.error("User not found: %s", username)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return {"username": username, "roles": payload.get("roles", "")}

def require_admin(current_user: Dict = Depends(get_current_user)) -> Dict:
    """
    Ensure the current user has admin privileges.
    """
    roles = current_user.get("roles", "")
    if "admin" not in [r.strip().lower() for r in roles.split(",")]:
        logger.warning("User %s attempted admin-only action.", current_user.get("username"))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required."
        )
    return current_user

# -----------------------------------------------------------------------------
# FastAPI Application Initialization
# -----------------------------------------------------------------------------
app = FastAPI(
    title="Authentication & RBAC Service API",
    description="Handles user authentication, token management, and role-based access control.",
    version="1.0.0",
    servers=[{"url": "http://localhost:8001", "description": "Local development server"}]
)

# Include the notification router
app.include_router(notification_router)

# -----------------------------------------------------------------------------
# Custom OpenAPI Schema Generation to Override OpenAPI Version to 3.0.3
# -----------------------------------------------------------------------------
def custom_openapi():
    """
    Generate a custom OpenAPI schema with version set to 3.0.3.
    """
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

# Default Landing Page Endpoint
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
        service_description="This service provides its core authentication and RBAC functionality within the FountainAI ecosystem."
    )
    return HTMLResponse(content=filled_html, status_code=200)

# Health Check Endpoint
@app.get("/health", response_model=dict, tags=["Health"], operation_id="getHealthStatus", summary="Retrieve service health status", description="Returns the current health status of the service as a JSON object (e.g., {'status': 'healthy'}).")
def health_check():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

# User Registration Endpoint
@app.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED, tags=["Users"], operation_id="registerUser", summary="Register a new user", description="Registers a new user with a hashed password and assigned roles.")
async def register_user(user: UserCreate = Body(...), db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == user.username).first():
        logger.info("Attempted to register an existing user: %s", user.username)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already exists.")
    
    hashed_pw = hash_password(user.password)
    new_user = User(username=user.username, hashed_password=hashed_pw, roles=user.roles)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    logger.info("User registered successfully: %s", user.username)
    return UserResponse(username=new_user.username, roles=new_user.roles)

# User Login Endpoint
@app.post("/login", response_model=Token, tags=["Users"], operation_id="loginUser", summary="User login", description="Authenticates user and returns access and refresh tokens.")
async def login_user(user: UserLogin = Body(...), db: Session = Depends(get_db)):
    stored_user = db.query(User).filter(User.username == user.username).first()
    if not stored_user or not verify_password(user.password, stored_user.hashed_password):
        logger.warning("Invalid login attempt for user: %s", user.username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")
    
    roles = stored_user.roles
    access_token = create_access_token(subject=user.username, roles=roles)
    refresh_token = create_refresh_token(subject=user.username, db=db)
    logger.info("User logged in successfully: %s", user.username)
    return Token(access_token=access_token, refresh_token=refresh_token, token_type="bearer")

# Token Refresh Endpoint
@app.post("/token/refresh", response_model=TokenResponse, tags=["Users"], operation_id="refreshToken", summary="Refresh access token", description="Refreshes an access token using a valid refresh token, and revokes the used refresh token.")
async def refresh_token(token_refresh: TokenRefresh = Body(...), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token_refresh.refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as e:
        logger.error("Refresh token invalid: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token.")
    
    if payload.get("type") != "refresh":
        logger.error("Provided token is not a refresh token.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type.")
    
    username: str = payload.get("sub")
    jti: str = payload.get("jti")
    if not username or not jti:
        logger.error("Refresh token payload missing required claims.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.")
    
    token_record = db.query(RefreshToken).filter(RefreshToken.token_id == jti).first()
    if not token_record:
        logger.error("Refresh token record not found: %s", jti)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token not found.")
    if token_record.revoked:
        logger.error("Refresh token has been revoked: %s", jti)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked.")
    if token_record.expires < datetime.utcnow():
        logger.error("Refresh token expired: %s", jti)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired.")
    
    token_record.revoked = True
    db.commit()
    
    user = db.query(User).filter(User.username == username).first()
    if not user:
        logger.error("User not found for refresh token: %s", username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
    
    new_access_token = create_access_token(subject=username, roles=user.roles)
    logger.info("Access token refreshed for user: %s", username)
    return TokenResponse(access_token=new_access_token, token_type="bearer")

# List Users Endpoint (Admin Only)
@app.get("/users", response_model=List[UserResponse], tags=["Users"], operation_id="listUsers", summary="List all users", description="Lists all registered users. Requires admin privileges.")
async def list_users(admin: Dict = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).all()
    logger.info("Admin %s retrieved user list.", admin.get("username"))
    return [UserResponse(username=user.username, roles=user.roles) for user in users]

# Get User Details Endpoint
@app.get("/users/{username}", response_model=UserResponse, tags=["Users"], operation_id="getUser", summary="Retrieve user details", description="Retrieves details of a specified user.")
async def get_user(
    username: str = Path(..., description="The username of the user to retrieve."),
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        logger.warning("User not found: %s", username)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    logger.info("User details retrieved for: %s", username)
    return UserResponse(username=user.username, roles=user.roles)

# Update User Endpoint
@app.patch("/users/{username}", tags=["Users"], operation_id="updateUser", summary="Update user information", description="Updates a user's password and/or roles.")
async def update_user(
    username: str = Path(..., description="The username of the user to update."),
    update: UserUpdate = Body(...),
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        logger.warning("Attempt to update non-existent user: %s", username)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    
    if update.password is not None:
        user.hashed_password = hash_password(update.password)
    if update.roles is not None:
        user.roles = update.roles
    db.commit()
    logger.info("User updated: %s", username)
    return {"detail": "User updated."}

# Delete User Endpoint (Admin Only)
@app.delete("/users/{username}", status_code=status.HTTP_204_NO_CONTENT, tags=["Users"], operation_id="deleteUser", summary="Delete a user", description="Deletes a specified user. Requires admin privileges.")
async def delete_user(
    username: str = Path(..., description="The username of the user to delete."),
    admin: Dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        logger.warning("Attempt to delete non-existent user: %s", username)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    db.delete(user)
    db.commit()
    logger.info("User deleted: %s by admin: %s", username, admin.get("username"))
    return  # 204 No Content

# Dynamic Service Discovery Endpoint
@app.get("/service-discovery", tags=["Service Discovery"], operation_id="getServiceDiscovery", summary="Discover peer services", description="Queries the API Gateway's lookup endpoint to resolve the URL of a specified service.")
def service_discovery(service_name: str = Query(..., description="Name of the service to discover")):
    discovered_url = get_service_url(service_name)
    return {"service": service_name, "discovered_url": discovered_url}

# -----------------------------------------------------------------------------
# Run the Application
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    # Run the application on localhost:8001 as specified.
    uvicorn.run(app, host="0.0.0.0", port=8001)

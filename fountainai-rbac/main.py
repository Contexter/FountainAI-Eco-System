"""
main.py

Production-Grade FastAPI Application for Authentication & RBAC Service API

Features:
    - Secure user registration and login with SQLite persistent storage.
    - JWT-based access and refresh tokens with token revocation.
    - Role-based access control.
    - Password hashing using PassLib.
    - Environment configuration via .env.
    - Health check endpoint at the root.
    - Detailed logging and Prometheus-based monitoring.
    - Custom OpenAPI schema version (3.1.0).

Endpoints:
    GET  /                 - Health check endpoint.
    POST /register         - Register a new user.
    POST /login            - User login (returns access and refresh tokens).
    POST /token/refresh    - Refresh an access token using a refresh token.
    GET  /users            - List all users (admin only).
    GET  /users/{username} - Retrieve a specific user's details.
    PATCH /users/{username} - Update user information.
    DELETE /users/{username} - Delete a user (admin only).

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
    Body
)
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

# -----------------------------------------------------------------------------
# Load Environment Variables
# -----------------------------------------------------------------------------
load_dotenv()  # Loads the .env file
SECRET_KEY = os.environ.get("SECRET_KEY", "fallback_secret_key")
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./app.db")

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


# Create tables if they don't exist
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
    
    # Retrieve the user to store refresh token; assume user exists.
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

# -----------------------------------------------------------------------------
# Custom OpenAPI Schema Generation to Override OpenAPI Version to 3.1.0
# -----------------------------------------------------------------------------
def custom_openapi():
    """
    Generate a custom OpenAPI schema with version set to 3.1.0.
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
# Health Check Endpoint
# -----------------------------------------------------------------------------
@app.get("/", tags=["Health"], summary="Health Check")
async def health_check():
    """
    Basic health check endpoint.
    
    Returns a simple JSON response indicating that the service is running.
    """
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

# -----------------------------------------------------------------------------
# API Endpoints
# -----------------------------------------------------------------------------

@app.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED, tags=["Users"], operation_id="register_user")
async def register_user(user: UserCreate = Body(...), db: Session = Depends(get_db)):
    """
    Register a new user.

    Creates a new user with the provided username, hashed password, and roles.
    Returns the created user's information.
    """
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

@app.post("/login", response_model=Token, tags=["Users"], operation_id="login_user")
async def login_user(user: UserLogin = Body(...), db: Session = Depends(get_db)):
    """
    User login.

    Authenticates the user by verifying the username and password.
    Returns an access token and a refresh token if credentials are valid.
    """
    stored_user = db.query(User).filter(User.username == user.username).first()
    if not stored_user or not verify_password(user.password, stored_user.hashed_password):
        logger.warning("Invalid login attempt for user: %s", user.username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")
    
    roles = stored_user.roles
    access_token = create_access_token(subject=user.username, roles=roles)
    refresh_token = create_refresh_token(subject=user.username, db=db)
    logger.info("User logged in successfully: %s", user.username)
    return Token(access_token=access_token, refresh_token=refresh_token, token_type="bearer")

@app.post("/token/refresh", response_model=TokenResponse, tags=["Users"], operation_id="refresh_token")
async def refresh_token(token_refresh: TokenRefresh = Body(...), db: Session = Depends(get_db)):
    """
    Refresh an access token.

    Validates the provided refresh token and issues a new access token.
    Implements token revocation to prevent reuse.
    """
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
    
    # Retrieve the refresh token record from the DB.
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
    
    # Mark the refresh token as revoked to prevent reuse.
    token_record.revoked = True
    db.commit()
    
    # Generate a new access token.
    user = db.query(User).filter(User.username == username).first()
    if not user:
        logger.error("User not found for refresh token: %s", username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
    
    new_access_token = create_access_token(subject=username, roles=user.roles)
    logger.info("Access token refreshed for user: %s", username)
    return TokenResponse(access_token=new_access_token, token_type="bearer")

@app.get("/users", response_model=List[UserResponse], tags=["Users"], operation_id="list_users")
async def list_users(admin: Dict = Depends(require_admin), db: Session = Depends(get_db)):
    """
    List all users.

    Requires admin privileges.
    Returns a list of all registered users.
    """
    users = db.query(User).all()
    logger.info("Admin %s retrieved user list.", admin.get("username"))
    return [UserResponse(username=user.username, roles=user.roles) for user in users]

@app.get("/users/{username}", response_model=UserResponse, tags=["Users"], operation_id="get_user")
async def get_user(
    username: str = Path(..., description="The username of the user to retrieve."),
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve user details.

    Returns the details of the specified user.
    """
    user = db.query(User).filter(User.username == username).first()
    if not user:
        logger.warning("User not found: %s", username)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    logger.info("User details retrieved for: %s", username)
    return UserResponse(username=user.username, roles=user.roles)

@app.patch("/users/{username}", tags=["Users"], operation_id="update_user")
async def update_user(
    username: str = Path(..., description="The username of the user to update."),
    update: UserUpdate = Body(...),
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update user information.

    Updates the user's password and/or roles.
    """
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

@app.delete("/users/{username}", status_code=status.HTTP_204_NO_CONTENT, tags=["Users"], operation_id="delete_user")
async def delete_user(
    username: str = Path(..., description="The username of the user to delete."),
    admin: Dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Delete a user.

    Requires admin privileges.
    Deletes the specified user.
    """
    user = db.query(User).filter(User.username == username).first()
    if not user:
        logger.warning("Attempt to delete non-existent user: %s", username)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    db.delete(user)
    db.commit()
    logger.info("User deleted: %s by admin: %s", username, admin.get("username"))
    return  # Returns 204 No Content

# -----------------------------------------------------------------------------
# Run the Application
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    # Run the application on localhost:8001 as specified in the OpenAPI servers section.
    uvicorn.run(app, host="0.0.0.0", port=8001)

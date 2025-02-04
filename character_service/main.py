"""
Character Service
=================

This service handles the creation, retrieval, updating, and management of characters 
within the FountainAI ecosystem. Character data is persisted to an SQLite database and 
synchronized with Typesense for real-time search and retrieval.

Integration with Central Sequence Service:
When creating a new character, instead of calculating the sequence number locally, 
this service calls the Central Sequence Service to obtain a globally consistent sequence number.
The payload sent to the Central Sequence Service includes:
  - elementType: "character"
  - elementId: 0   (since the character ID is auto-generated)
  - comment: "Character creation sequence assignment"

The OpenAPI documentation is forced to version 3.0.3 for Swagger UI compatibility.
"""

import os
import sys
import logging
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request, Response, Depends, status
from fastapi.openapi.utils import get_openapi
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from prometheus_fastapi_instrumentator import Instrumentator
from dotenv import load_dotenv
import httpx
from jose import JWTError, jwt

# SQLAlchemy setup
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# Load environment variables
load_dotenv()
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8000"))
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./character.db")
API_GATEWAY_URL = os.getenv("API_GATEWAY_URL", "http://gateway:8000")
JWT_SECRET = os.getenv("JWT_SECRET", "your_jwt_secret_key")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
# The name under which the Central Sequence Service is registered in the API Gateway.
CENTRAL_SEQUENCE_SERVICE_NAME = os.getenv("CENTRAL_SEQUENCE_SERVICE_NAME", "central_sequence_service")

# Logging configuration
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger("character_service")

# SQLAlchemy database
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Character(Base):
    __tablename__ = "characters"
    characterId = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    sequenceNumber = Column(Integer, nullable=False)
    isSyncedToTypesense = Column(Integer, default=0)  # 0 for False, 1 for True
    comment = Column(String, nullable=True)

Base.metadata.create_all(bind=engine)

def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# JWT authentication
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

# Pydantic schemas
class CharacterCreateRequest(BaseModel):
    name: str = Field(..., description="Name of the character")
    description: str = Field(..., description="Brief description of the character")
    comment: str = Field(..., description="Contextual explanation for creating the character")

class CharacterPatchRequest(BaseModel):
    name: Optional[str] = Field(None, description="Updated name of the character")
    description: Optional[str] = Field(None, description="Updated description of the character")
    comment: str = Field(..., description="Contextual explanation for updating the character")

class CharacterUpdateRequest(BaseModel):
    name: str = Field(..., description="Updated name of the character")
    description: str = Field(..., description="Updated description of the character")
    comment: str = Field(..., description="Contextual explanation for updating the character")

class CharacterResponse(BaseModel):
    characterId: int
    name: str
    description: str
    sequenceNumber: int
    isSyncedToTypesense: bool
    comment: Optional[str]

# Helper function for service discovery via the API Gateway
def get_service_url(service_name: str) -> str:
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

# FastAPI app initialization
app = FastAPI(
    title="Character Service",
    description=(
        "This service handles the creation, retrieval, updating, and management of characters within the story. "
        "Data is persisted to SQLite and synchronized with Typesense for real-time search and retrieval. "
        "It integrates with the Central Sequence Service to obtain a globally consistent sequence number during character creation."
    ),
    version="4.0.0"
)

Instrumentator().instrument(app).expose(app)

# Endpoints
@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "healthy"}

@app.get("/characters", response_model=List[CharacterResponse], tags=["Characters"])
def list_characters(db: Session = Depends(get_db)):
    characters = db.query(Character).all()
    return [
        CharacterResponse(
            characterId=c.characterId,
            name=c.name,
            description=c.description,
            sequenceNumber=c.sequenceNumber,
            isSyncedToTypesense=bool(c.isSyncedToTypesense),
            comment=c.comment
        ) for c in characters
    ]

@app.post("/characters", response_model=CharacterResponse, status_code=status.HTTP_201_CREATED, tags=["Characters"])
def create_character(
    request: CharacterCreateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Creates a new character. This endpoint calls the Central Sequence Service to obtain a globally consistent
    sequence number rather than calculating it locally.
    """
    # Discover the URL for the Central Sequence Service via the API Gateway.
    try:
        central_sequence_url = get_service_url(CENTRAL_SEQUENCE_SERVICE_NAME)
    except Exception as e:
        logger.error(f"Central Sequence Service lookup failed: {e}")
        raise HTTPException(status_code=503, detail="Central Sequence Service unavailable")

    # Construct payload for the Central Sequence Service.
    # Since characterId is auto-generated, we pass a dummy value (0) for elementId.
    sequence_payload = {
        "elementType": "character",
        "elementId": 0,
        "comment": "Character creation sequence assignment"
    }

    try:
        response = httpx.post(f"{central_sequence_url}/sequence", json=sequence_payload, timeout=5.0)
        response.raise_for_status()
        sequence_data = response.json()
        next_seq = sequence_data.get("sequenceNumber")
        if next_seq is None:
            raise ValueError("No sequenceNumber returned")
    except Exception as e:
        logger.error(f"Failed to obtain sequence number from Central Sequence Service: {e}")
        raise HTTPException(status_code=503, detail="Failed to obtain sequence number")

    # Create the new character using the sequence number from the Central Sequence Service.
    new_character = Character(
        name=request.name,
        description=request.description,
        sequenceNumber=next_seq,
        isSyncedToTypesense=0,
        comment=request.comment
    )
    db.add(new_character)
    db.commit()
    db.refresh(new_character)
    logger.info(f"Character created with ID: {new_character.characterId}")
    return CharacterResponse(
        characterId=new_character.characterId,
        name=new_character.name,
        description=new_character.description,
        sequenceNumber=new_character.sequenceNumber,
        isSyncedToTypesense=bool(new_character.isSyncedToTypesense),
        comment=new_character.comment
    )

@app.get("/characters/{characterId}", response_model=CharacterResponse, tags=["Characters"])
def get_character_by_id(characterId: int, db: Session = Depends(get_db)):
    character = db.query(Character).filter(Character.characterId == characterId).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    return CharacterResponse(
        characterId=character.characterId,
        name=character.name,
        description=character.description,
        sequenceNumber=character.sequenceNumber,
        isSyncedToTypesense=bool(character.isSyncedToTypesense),
        comment=character.comment
    )

@app.patch("/characters/{characterId}", response_model=CharacterResponse, tags=["Characters"])
def patch_character(characterId: int, request: CharacterPatchRequest, db: Session = Depends(get_db)):
    character = db.query(Character).filter(Character.characterId == characterId).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    if request.name is not None:
        character.name = request.name
    if request.description is not None:
        character.description = request.description
    character.comment = request.comment
    db.commit()
    db.refresh(character)
    logger.info(f"Character patched with ID: {character.characterId}")
    return CharacterResponse(
        characterId=character.characterId,
        name=character.name,
        description=character.description,
        sequenceNumber=character.sequenceNumber,
        isSyncedToTypesense=bool(character.isSyncedToTypesense),
        comment=character.comment
    )

@app.put("/characters/{characterId}", response_model=CharacterResponse, tags=["Characters"])
def update_character(characterId: int, request: CharacterUpdateRequest, db: Session = Depends(get_db)):
    character = db.query(Character).filter(Character.characterId == characterId).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    character.name = request.name
    character.description = request.description
    character.comment = request.comment
    db.commit()
    db.refresh(character)
    logger.info(f"Character updated with ID: {character.characterId}")
    return CharacterResponse(
        characterId=character.characterId,
        name=character.name,
        description=character.description,
        sequenceNumber=character.sequenceNumber,
        isSyncedToTypesense=bool(character.isSyncedToTypesense),
        comment=character.comment
    )

@app.get("/characters/scripts/{scriptId}", response_model=List[CharacterResponse], tags=["Characters"])
def list_characters_by_script(scriptId: int, db: Session = Depends(get_db)):
    # Since the Character model does not include a scriptId field, we use a simple rule:
    # If scriptId equals 1, return all characters; otherwise, return 404.
    if scriptId != 1:
        raise HTTPException(status_code=404, detail="Script not found")
    characters = db.query(Character).all()
    return [
        CharacterResponse(
            characterId=c.characterId,
            name=c.name,
            description=c.description,
            sequenceNumber=c.sequenceNumber,
            isSyncedToTypesense=bool(c.isSyncedToTypesense),
            comment=c.comment
        ) for c in characters
    ]

# OpenAPI customization: Force OpenAPI version to 3.0.3
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=SERVICE_PORT)

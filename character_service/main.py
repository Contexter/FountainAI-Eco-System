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

def get_db():
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
        return r.json().get("url")
    except Exception as e:
        logger.error(f"Service discovery failed for '{service_name}': {e}")
        raise HTTPException(status_code=503, detail=f"Service discovery failed for '{service_name}'")

# FastAPI app initialization
app = FastAPI(
    title="Character Service",
    description=(
        "This service handles the creation, retrieval, updating, and management of characters "
        "within the story. Data is persisted to SQLite and synchronized with Typesense for real-time "
        "search and retrieval. It integrates with the Central Sequence Service for sequence numbers."
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
def create_character(request: CharacterCreateRequest, db: Session = Depends(get_db)):
    max_seq = db.query(Character).order_by(Character.sequenceNumber.desc()).first()
    next_seq = max_seq.sequenceNumber + 1 if max_seq else 1
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
    # In a real implementation, Character would include a scriptId field.
    # For this example, if scriptId == 1, return all characters; otherwise, 404.
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


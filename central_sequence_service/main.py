"""
Central Sequence Service
========================

This service manages sequence numbers for various elements (script, section, character, action, spokenWord)
within a story. It persists data to an SQLite database and synchronizes data with the central FountainAI Typesense Service.
Collection creation is mandatory: on startup the service ensures the Typesense collection schema exists.
The generated OpenAPI spec is forced to version 3.0.3 for Swagger UI compatibility.
"""

import os
import sys
import logging
from typing import List, Optional
from enum import Enum

from fastapi import FastAPI, HTTPException, Depends
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from prometheus_fastapi_instrumentator import Instrumentator

# --- SQLAlchemy Imports ---
from sqlalchemy import create_engine, Column, Integer, String, DateTime, func
from sqlalchemy.orm import sessionmaker, declarative_base, Session

import httpx

# -----------------------------------------------------------------------------
# Configuration and Environment
# -----------------------------------------------------------------------------
load_dotenv()  # Load environment variables from .env

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./database.db")
# This URL should point to the FountainAI Typesense Client microservice.
TYPESENSE_CLIENT_URL = os.getenv("TYPESENSE_CLIENT_URL", "http://fountainai-typesense-service:8001")
SERVICE_NAME = os.getenv("SERVICE_NAME", "central_sequence_service")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "your_admin_jwt_token")

# -----------------------------------------------------------------------------
# Logging Configuration
# -----------------------------------------------------------------------------
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger("central_sequence_service")

# -----------------------------------------------------------------------------
# Database Setup (SQLAlchemy)
# -----------------------------------------------------------------------------
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Element(Base):
    __tablename__ = "elements"
    id = Column(Integer, primary_key=True, index=True)
    element_type = Column(String, nullable=False)
    element_id = Column(Integer, nullable=False)
    sequence_number = Column(Integer, nullable=False)
    version_number = Column(Integer, nullable=False)
    comment = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

Base.metadata.create_all(bind=engine)

def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -----------------------------------------------------------------------------
# Pydantic Schemas and Enums
# -----------------------------------------------------------------------------
class ElementTypeEnum(str, Enum):
    script = "script"
    section = "section"
    character = "character"
    action = "action"
    spokenWord = "spokenWord"

class SequenceRequest(BaseModel):
    elementType: ElementTypeEnum = Field(..., description="Type of the element")
    elementId: int = Field(..., ge=1, description="Unique identifier of the element")
    comment: str = Field(..., description="Context for generating a sequence number")

class SequenceResponse(BaseModel):
    sequenceNumber: int = Field(..., description="The generated sequence number", ge=1)
    comment: str = Field(..., description="Explanation for the generated sequence")

class ReorderRequest(BaseModel):
    elementIds: List[int] = Field(..., description="List of element IDs to reorder")
    newOrder: List[int] = Field(..., description="New sequence order (list of element IDs in desired order)")

class ReorderResponseElement(BaseModel):
    elementId: int
    oldSequenceNumber: int
    newSequenceNumber: int

class ReorderResponse(BaseModel):
    reorderedElements: List[ReorderResponseElement]
    comment: str

class VersionRequest(BaseModel):
    elementType: ElementTypeEnum
    elementId: int
    comment: str = ""

class VersionResponse(BaseModel):
    versionNumber: int = Field(..., description="The new version number", ge=1)
    comment: str

class ErrorResponse(BaseModel):
    errorCode: str
    message: str
    details: Optional[str] = None

class TypesenseErrorResponse(BaseModel):
    errorCode: str
    retryAttempt: int
    message: str
    details: Optional[str] = None

# -----------------------------------------------------------------------------
# FountainAI Typesense Service Integration
# -----------------------------------------------------------------------------
class FountainAITypesenseService:
    """
    Integration with the FountainAI Typesense Client microservice.
    This class calls the central Typesense Service endpoints:
      - POST /collections to create or verify a collection.
      - POST /documents/sync to upsert or delete a document.
    """
    def __init__(self):
        self.client = httpx.Client(base_url=TYPESENSE_CLIENT_URL, timeout=10.0)

    def create_or_update_collection(self, collection_definition: dict) -> dict:
        try:
            # Call the /collections endpoint of the Typesense Client microservice.
            response = self.client.post("/collections", json=collection_definition)
            response.raise_for_status()
            logger.info(f"Collection '{collection_definition.get('name')}' created/verified successfully.")
            return response.json()
        except Exception as e:
            logger.error("Failed to create/update collection: %s", e)
            raise RuntimeError("Typesense collection update failed.")

    def sync_document(self, payload: dict):
        try:
            # Call the /documents/sync endpoint to upsert/delete a document.
            response = self.client.post("/documents/sync", json=payload)
            response.raise_for_status()
            logger.info("Document synced successfully: %s", payload.get("document", {}).get("id"))
        except Exception as e:
            logger.error("Failed to sync document: %s", e)
            raise RuntimeError("Typesense document sync failed.")

typesense_service = FountainAITypesenseService()
# Updated collection name for the central sequence service.
COLLECTION_NAME = "central_sequence_elements"

# -----------------------------------------------------------------------------
# FastAPI Application Initialization
# -----------------------------------------------------------------------------
app = FastAPI(
    title="Central Sequence Service",
    description=(
        "This API manages the assignment and updating of sequence numbers for various elements within a story, "
        "ensuring logical order and consistency. Data is persisted in an SQLite database and synchronized with the central "
        "FountainAI Typesense Service. Collection creation is mandatory and verified at startup."
    ),
    version="1.0.0",
)

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    schema["openapi"] = "3.0.3"  # Force OpenAPI version 3.0.3 for Swagger UI compatibility.
    app.openapi_schema = schema
    return schema

app.openapi = custom_openapi

Instrumentator().instrument(app).expose(app)

# -----------------------------------------------------------------------------
# Startup: Enforce Mandatory Collection Creation
# -----------------------------------------------------------------------------
@app.on_event("startup")
def ensure_typesense_collection():
    try:
        collection_def = {
            "name": COLLECTION_NAME,
            "fields": [
                {"name": "id", "type": "string"},
                {"name": "element_type", "type": "string"},
                {"name": "element_id", "type": "int32"},
                {"name": "sequence_number", "type": "int32"},
                {"name": "version_number", "type": "int32"},
                {"name": "comment", "type": "string"}
            ],
            "default_sorting_field": "sequence_number"
        }
        typesense_service.create_or_update_collection(collection_def)
    except Exception as e:
        logger.error(f"Failed to ensure Typesense collection: {e}")

# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------
@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "healthy"}

@app.post("/sequence", response_model=SequenceResponse, status_code=201, tags=["Sequence Management"])
def generate_sequence_number(request: SequenceRequest, db: Session = Depends(get_db)):
    try:
        max_elem = (
            db.query(Element)
            .filter(Element.element_type == request.elementType.value)
            .order_by(Element.sequence_number.desc())
            .first()
        )
        next_seq = max_elem.sequence_number + 1 if max_elem else 1

        new_element = Element(
            element_type=request.elementType.value,
            element_id=request.elementId,
            sequence_number=next_seq,
            version_number=1,
            comment=request.comment
        )
        db.add(new_element)
        db.commit()
        db.refresh(new_element)

        sync_payload = {
            "operation": "create",
            "collection_name": COLLECTION_NAME,
            "document": {
                "id": f"{new_element.element_id}_{new_element.version_number}",
                "element_type": new_element.element_type,
                "element_id": new_element.element_id,
                "sequence_number": new_element.sequence_number,
                "version_number": new_element.version_number,
                "comment": new_element.comment or ""
            }
        }
        typesense_service.sync_document(sync_payload)

        return SequenceResponse(
            sequenceNumber=new_element.sequence_number,
            comment=new_element.comment
        )
    except Exception as e:
        logger.error(f"Failed to generate sequence number: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/sequence/reorder", response_model=ReorderResponse, status_code=200, tags=["Sequence Management"])
def reorder_elements(request: ReorderRequest, db: Session = Depends(get_db)):
    try:
        elements = db.query(Element).filter(Element.element_id.in_(request.elementIds)).all()
        if len(elements) != len(request.elementIds):
            raise HTTPException(status_code=404, detail="Some elements not found.")

        element_map = {elem.element_id: elem for elem in elements}
        reordered_elements = []

        for new_seq, element_id in enumerate(request.newOrder, start=1):
            elem = element_map.get(element_id)
            old_seq = elem.sequence_number
            if old_seq != new_seq:
                elem.sequence_number = new_seq
                db.commit()
                db.refresh(elem)

                sync_payload = {
                    "operation": "update",
                    "collection_name": COLLECTION_NAME,
                    "document": {
                        "id": f"{elem.element_id}_{elem.version_number}",
                        "element_type": elem.element_type,
                        "element_id": elem.element_id,
                        "sequence_number": elem.sequence_number,
                        "version_number": elem.version_number,
                        "comment": elem.comment or ""
                    }
                }
                typesense_service.sync_document(sync_payload)

                reordered_elements.append({
                    "elementId": elem.element_id,
                    "oldSequenceNumber": old_seq,
                    "newSequenceNumber": new_seq
                })

        return ReorderResponse(
            reorderedElements=reordered_elements,
            comment="Elements reordered successfully."
        )
    except Exception as e:
        logger.error(f"Failed to reorder elements: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/sequence/version", response_model=VersionResponse, status_code=201, tags=["Version Management"])
def create_new_version(request: VersionRequest, db: Session = Depends(get_db)):
    try:
        max_elem = (
            db.query(Element)
            .filter(
                Element.element_type == request.elementType.value,
                Element.element_id == request.elementId
            )
            .order_by(Element.version_number.desc())
            .first()
        )
        new_version = max_elem.version_number + 1 if max_elem else 1
        sequence_num = max_elem.sequence_number if max_elem else 1

        new_element = Element(
            element_type=request.elementType.value,
            element_id=request.elementId,
            sequence_number=sequence_num,
            version_number=new_version,
            comment=request.comment
        )
        db.add(new_element)
        db.commit()
        db.refresh(new_element)

        sync_payload = {
            "operation": "create",
            "collection_name": COLLECTION_NAME,
            "document": {
                "id": f"{new_element.element_id}_{new_element.version_number}",
                "element_type": new_element.element_type,
                "element_id": new_element.element_id,
                "sequence_number": new_element.sequence_number,
                "version_number": new_element.version_number,
                "comment": new_element.comment or ""
            }
        }
        typesense_service.sync_document(sync_payload)

        return VersionResponse(
            versionNumber=new_element.version_number,
            comment=new_element.comment
        )
    except Exception as e:
        logger.error(f"Failed to create new version: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# -----------------------------------------------------------------------------
# Run the Application
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

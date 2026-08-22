import logging
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CV
from app.schemas import CVResponse, ParsedCV
from app.services.extractor import ExtractionError, UnsupportedFormatError, extract_text_from_file
from app.services.parser import parse_cv_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/cvs", tags=["cvs"])

ALLOWED_EXTENSIONS = {".pdf", ".docx"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post("/upload", response_model=CVResponse, status_code=201)
async def upload_cv(file: UploadFile, db: Session = Depends(get_db)):
    # Validate filename and extension
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format: '{ext}'. Only .pdf and .docx are allowed.",
        )

    # Read and validate size
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="File is empty")
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File exceeds 10 MB limit")

    # Extract text
    try:
        raw_text = extract_text_from_file(file_bytes, file.filename)
    except UnsupportedFormatError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ExtractionError as exc:
        raise HTTPException(status_code=422, detail=f"Cannot extract text: {exc}")

    if not raw_text or not raw_text.strip():
        raise HTTPException(status_code=422, detail="No text could be extracted from the file")

    # Parse CV
    try:
        parsed_data = parse_cv_text(raw_text)
    except Exception as exc:
        logger.error("CV parsing failed: %s", exc, exc_info=True)
        # Fallback: store raw text with empty parsed structure
        parsed_data = ParsedCV().model_dump()

    # Extract candidate name for denormalized column
    candidate_name = None
    personal_info = parsed_data.get("personal_info")
    if personal_info and isinstance(personal_info, dict):
        candidate_name = personal_info.get("full_name")

    # Save to DB
    cv = CV(
        id=uuid.uuid4(),
        filename=file.filename,
        raw_text=raw_text,
        parsed_data=parsed_data,
        candidate_name=candidate_name,
    )
    db.add(cv)
    db.commit()
    db.refresh(cv)

    return cv


@router.get("/{cv_id}", response_model=CVResponse)
async def get_cv(cv_id: uuid.UUID, db: Session = Depends(get_db)):
    cv = db.query(CV).filter(CV.id == cv_id).first()
    if not cv:
        raise HTTPException(status_code=404, detail="CV not found")
    return cv

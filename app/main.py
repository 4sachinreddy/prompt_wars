"""
MedLens FastAPI Application Entrypoint.

Provides API endpoints for patient intake, medical report processing,
zero-hallucination range evaluation, clinical conflict detection,
and human-in-the-loop (HITL) verification workflows.
"""

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Load environment variables
load_dotenv()

from app.models.schemas import (
    ClinicalRecord,
    PatientIntake,
    ProvenanceType,
    VerifyItemRequest,
)
from app.services.extractor import process_medical_report
from app.services.inconsistency_engine import detect_clinical_inconsistencies
from app.services.range_evaluator import process_lab_item_ranges
from app.services.summarizer import generate_ai_summary

app = FastAPI(
    title="MedLens — AI-Powered Clinical Information Intelligence",
    description="Transforms unstructured medical records into reviewable, traceable, and structured clinical intelligence.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Enable CORS for development flexibility with specific header security
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next: Any) -> Response:
    """Inject robust Security HTTP Headers to protect against common web vulnerabilities."""
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self' https: data: 'unsafe-inline' 'unsafe-eval'; "
        "img-src 'self' https: data:; font-src 'self' https: data:;"
    )
    return response


# Maximum upload size limit: 10 MB
MAX_UPLOAD_SIZE = 10 * 1024 * 1024


# In-memory unified clinical record store for session
current_record: ClinicalRecord = ClinicalRecord()

BASE_DIR: Path = Path(__file__).resolve().parent
STATIC_DIR: Path = BASE_DIR / "static"
SAMPLE_DATA_DIR: Path = BASE_DIR.parent / "sample_data"

# Ensure static directory exists
STATIC_DIR.mkdir(exist_ok=True)


def recalculate_record_intelligence() -> None:
    """Recalculates clinical inconsistencies and generates updated AI summaries.
    
    Ensures that any state modification triggers deterministic conflict re-checking
    and provenance updates across the record.
    """
    global current_record
    if current_record.patient and current_record.lab_tests:
        current_record.inconsistencies = detect_clinical_inconsistencies(
            patient=current_record.patient,
            lab_tests=current_record.lab_tests,
        )
    else:
        current_record.inconsistencies = []

    current_record.summary = generate_ai_summary(
        patient=current_record.patient,
        lab_tests=current_record.lab_tests,
        inconsistencies=current_record.inconsistencies,
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Custom exception handler for structured HTTP error responses."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "status_code": exc.status_code,
            "detail": exc.detail,
            "path": str(request.url.path),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Custom exception handler for Pydantic validation errors."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": True,
            "status_code": 422,
            "detail": "Input validation failed.",
            "errors": exc.errors(),
            "path": str(request.url.path),
        },
    )


@app.get("/health", tags=["System"])
async def health_check() -> dict[str, Any]:
    """Cloud Run & system health check probe.
    
    Returns:
        Dict[str, Any]: Operational status and Gemini API key configuration state.
    """
    return {
        "status": "healthy",
        "service": "medlens",
        "version": "1.0.0",
        "gemini_api_configured": bool(os.environ.get("GEMINI_API_KEY", "").strip()),
    }


@app.get("/api/record", response_model=ClinicalRecord, tags=["Clinical Record"])
async def get_clinical_record() -> ClinicalRecord:
    """Retrieve current consolidated clinical record.
    
    Returns:
        ClinicalRecord: Full active clinical session state.
    """
    return current_record


@app.post("/api/intake", response_model=ClinicalRecord, tags=["Patient Intake"])
async def submit_patient_intake(intake: PatientIntake) -> ClinicalRecord:
    """Save or update patient intake details tagged as USER_PROVIDED provenance.
    
    Args:
        intake (PatientIntake): Demographics, symptoms, allergies, and medication data.
        
    Returns:
        ClinicalRecord: Updated active clinical record with re-evaluated intelligence.
    """
    global current_record
    intake.provenance = ProvenanceType.USER_PROVIDED
    current_record.patient = intake
    recalculate_record_intelligence()
    return current_record


@app.post("/api/upload-report", response_model=ClinicalRecord, tags=["Report Processing"])
async def upload_medical_report(file: UploadFile = File(...)) -> ClinicalRecord:
    """Upload and process PDF or text medical reports with strict size validation.
    
    Args:
        file (UploadFile): PDF or plain text file containing laboratory observations.
        
    Returns:
        ClinicalRecord: Consolidated record containing parsed observations and range evaluations.
    """
    global current_record
    content: bytes = await file.read()

    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Uploaded file exceeds maximum allowed size limit of 10 MB.",
        )

    # Sanitize filename to prevent path traversal issues
    safe_filename: str = Path(file.filename or "uploaded_report.txt").name

    metadata, new_tests = process_medical_report(
        filename=safe_filename,
        raw_content=content,
        content_type=file.content_type or "text/plain",
    )

    current_record.reports.append(metadata)

    # Merge tests without duplicate entries
    existing_names: dict[str, int] = {t.test_name.lower(): idx for idx, t in enumerate(current_record.lab_tests)}
    for test in new_tests:
        name_key: str = test.test_name.lower()
        if name_key in existing_names:
            idx: int = existing_names[name_key]
            current_record.lab_tests[idx] = test
        else:
            current_record.lab_tests.append(test)
            existing_names[name_key] = len(current_record.lab_tests) - 1

    recalculate_record_intelligence()
    return current_record


@app.post("/api/verify-item", response_model=ClinicalRecord, tags=["Human In The Loop"])
async def verify_lab_item(req: VerifyItemRequest) -> ClinicalRecord:
    """Human-in-the-loop endpoint: clinician edits/verifies an extracted observation.
    
    Args:
        req (VerifyItemRequest): Identification and updated values for target observation.
        
    Returns:
        ClinicalRecord: Record reflecting HUMAN_VERIFIED status and re-evaluated ranges.
    """
    global current_record
    found: bool = False
    for item in current_record.lab_tests:
        if item.id == req.item_id:
            found = True
            if req.test_name is not None:
                item.test_name = req.test_name
            if req.value is not None:
                item.value = req.value
            if req.value_text is not None:
                item.value_text = req.value_text
            if req.unit is not None:
                item.unit = req.unit
            if req.ref_range_low is not None:
                item.ref_range_low = req.ref_range_low
            if req.ref_range_high is not None:
                item.ref_range_high = req.ref_range_high

            # Re-evaluate reference range deterministically
            process_lab_item_ranges(item)

            item.is_verified = True
            item.provenance = ProvenanceType.HUMAN_VERIFIED
            item.verified_by = req.verified_by or "Attending Clinician"
            break

    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lab test item with ID '{req.item_id}' not found.",
        )

    recalculate_record_intelligence()
    return current_record


@app.post("/api/load-sample", response_model=ClinicalRecord, tags=["Demo"])
async def load_sample_case() -> ClinicalRecord:
    """1-Click Demo loader: populates realistic clinical case with patient intake,
    laboratory report with flagged biomarkers, detected conflicts, and AI summary.
    
    Returns:
        ClinicalRecord: Populated sample clinical record.
    """
    global current_record
    current_record = ClinicalRecord()

    # 1. Populate realistic patient intake
    sample_intake: PatientIntake = PatientIntake(
        name="Marcus Sterling",
        age=54,
        sex="Male",
        symptoms=["Generalized chronic fatigue", "Mild exertion dyspnea", "Episodes of lightheadedness"],
        existing_conditions=["Essential Hypertension", "Mild Osteoarthritis"],
        allergies=["Penicillin (hives)"],
        current_medications=["Lisinopril 10mg daily", "Metformin 500mg daily", "Multivitamin"],
        notes="Patient reports feeling sluggish for past 3 months. Denies known history of diabetes or renal disease.",
        provenance=ProvenanceType.USER_PROVIDED,
    )
    current_record.patient = sample_intake

    # 2. Read sample lab report file
    cbc_path: Path = SAMPLE_DATA_DIR / "sample_cbc_metabolic.txt"
    if cbc_path.exists():
        with open(cbc_path, "rb") as f:
            content: bytes = f.read()
        metadata, tests = process_medical_report(
            filename="MetroPath_CBC_CMP_MarcusSterling.txt",
            raw_content=content,
            content_type="text/plain",
        )
        current_record.reports.append(metadata)
        current_record.lab_tests.extend(tests)

    # 3. Recalculate intelligence
    recalculate_record_intelligence()
    return current_record


@app.post("/api/clear", response_model=ClinicalRecord, tags=["Session"])
async def clear_record() -> ClinicalRecord:
    """Reset active clinical session record.
    
    Returns:
        ClinicalRecord: Fresh empty clinical record.
    """
    global current_record
    current_record = ClinicalRecord()
    return current_record


# Mount static assets
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse, tags=["UI"])
async def serve_dashboard() -> HTMLResponse:
    """Serve the MedLens single-page user interface.
    
    Returns:
        HTMLResponse: Main dashboard HTML file content.
    """
    index_file: Path = STATIC_DIR / "index.html"
    if index_file.exists():
        with open(index_file, encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>MedLens API is running. UI is initializing...</h1>")

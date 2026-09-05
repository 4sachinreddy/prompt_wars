import os
import io
from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from app.models.schemas import (
    ClinicalRecord,
    PatientIntake,
    LabTestItem,
    InconsistencyItem,
    ProvenanceType,
    VerifyItemRequest,
    BiomarkerStatus,
)
from app.services.range_evaluator import process_lab_item_ranges
from app.services.extractor import process_medical_report
from app.services.inconsistency_engine import detect_clinical_inconsistencies
from app.services.summarizer import generate_ai_summary, generate_deterministic_summary

app = FastAPI(
    title="MedLens — AI-Powered Clinical Information Intelligence",
    description="Transforms unstructured medical records into reviewable, traceable, and structured clinical intelligence.",
    version="1.0.0",
)

# Enable CORS for development flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory unified clinical record store for session
current_record = ClinicalRecord()

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
SAMPLE_DATA_DIR = BASE_DIR.parent / "sample_data"

# Ensure static dir exists
STATIC_DIR.mkdir(exist_ok=True)


def recalculate_record_intelligence():
    """Recalculates inconsistencies and generates updated summary."""
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


@app.get("/health", tags=["System"])
async def health_check():
    """Cloud Run health check probe."""
    return {
        "status": "healthy",
        "service": "medlens",
        "gemini_api_configured": bool(os.environ.get("GEMINI_API_KEY", "").strip()),
    }


@app.get("/api/record", response_model=ClinicalRecord, tags=["Clinical Record"])
async def get_clinical_record():
    """Retrieve current consolidated clinical record."""
    return current_record


@app.post("/api/intake", response_model=ClinicalRecord, tags=["Patient Intake"])
async def submit_patient_intake(intake: PatientIntake):
    """Save or update patient intake details (tagged as USER_PROVIDED)."""
    global current_record
    intake.provenance = ProvenanceType.USER_PROVIDED
    current_record.patient = intake
    recalculate_record_intelligence()
    return current_record


@app.post("/api/upload-report", response_model=ClinicalRecord, tags=["Report Processing"])
async def upload_medical_report(file: UploadFile = File(...)):
    """Upload and process PDF or text medical reports."""
    global current_record
    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    metadata, new_tests = process_medical_report(
        filename=file.filename or "uploaded_report.txt",
        raw_content=content,
        content_type=file.content_type or "text/plain",
    )

    current_record.reports.append(metadata)

    # Merge tests without duplicate entries
    existing_names = {t.test_name.lower(): idx for idx, t in enumerate(current_record.lab_tests)}
    for test in new_tests:
        name_key = test.test_name.lower()
        if name_key in existing_names:
            # Update with new reading
            idx = existing_names[name_key]
            current_record.lab_tests[idx] = test
        else:
            current_record.lab_tests.append(test)
            existing_names[name_key] = len(current_record.lab_tests) - 1

    recalculate_record_intelligence()
    return current_record


@app.post("/api/verify-item", response_model=ClinicalRecord, tags=["Human In The Loop"])
async def verify_lab_item(req: VerifyItemRequest):
    """Human-in-the-loop endpoint: clinician edits/verifies an extracted observation."""
    global current_record
    found = False
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
        raise HTTPException(status_code=404, detail="Lab test item not found.")

    recalculate_record_intelligence()
    return current_record


@app.post("/api/load-sample", response_model=ClinicalRecord, tags=["Demo"])
async def load_sample_case():
    """
    1-Click Demo loader: populates realistic clinical case with patient intake,
    laboratory report with flagged biomarkers, detected conflicts, and AI summary.
    """
    global current_record
    current_record = ClinicalRecord()

    # 1. Populate realistic patient intake
    sample_intake = PatientIntake(
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
    cbc_path = SAMPLE_DATA_DIR / "sample_cbc_metabolic.txt"
    if cbc_path.exists():
        with open(cbc_path, "rb") as f:
            content = f.read()
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
async def clear_record():
    """Reset current session record."""
    global current_record
    current_record = ClinicalRecord()
    return current_record


# Mount static assets
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse, tags=["UI"])
async def serve_dashboard():
    """Serve the MedLens single-page UI."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>MedLens API is running. UI is initializing...</h1>")

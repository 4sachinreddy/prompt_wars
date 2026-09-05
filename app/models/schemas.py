from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
import uuid
from datetime import datetime


class ProvenanceType(str, Enum):
    USER_PROVIDED = "USER_PROVIDED"
    AI_EXTRACTED = "AI_EXTRACTED"
    AI_INFERRED = "AI_INFERRED"
    HUMAN_VERIFIED = "HUMAN_VERIFIED"


class BiomarkerStatus(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


class SeverityLevel(str, Enum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


class PatientIntake(BaseModel):
    patient_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = Field(..., description="Patient full name")
    age: int = Field(..., ge=0, le=130, description="Age in years")
    sex: str = Field(..., description="Sex / Gender (e.g. Male, Female, Other)")
    symptoms: List[str] = Field(default_factory=list, description="Current reported symptoms")
    existing_conditions: List[str] = Field(default_factory=list, description="Known diagnosed conditions")
    allergies: List[str] = Field(default_factory=list, description="Known allergies")
    current_medications: List[str] = Field(default_factory=list, description="Current prescription and OTC medications")
    notes: Optional[str] = Field(default="", description="Additional clinical or intake notes")
    provenance: ProvenanceType = Field(default=ProvenanceType.USER_PROVIDED)
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class LabTestItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    test_name: str = Field(..., description="Standardized name of the laboratory test")
    value: Optional[float] = Field(None, description="Numeric test result value")
    value_text: Optional[str] = Field(None, description="Textual result if qualitative (e.g. 'Negative')")
    unit: Optional[str] = Field(None, description="Unit of measurement, e.g. mg/dL, g/dL, %")
    ref_range_low: Optional[float] = Field(None, description="Lower bound of reference range from report")
    ref_range_high: Optional[float] = Field(None, description="Upper bound of reference range from report")
    raw_ref_range: Optional[str] = Field(None, description="Raw reference range string verbatim from source")
    status: BiomarkerStatus = Field(default=BiomarkerStatus.UNKNOWN, description="Evaluated status against reported range")
    source_snippet: str = Field(..., description="Exact line/text in document where this test was found")
    provenance: ProvenanceType = Field(default=ProvenanceType.AI_EXTRACTED)
    confidence: float = Field(default=0.95, ge=0.0, le=1.0, description="Extraction confidence score")
    observation_date: Optional[str] = Field(None, description="Date of lab specimen or report")
    category: Optional[str] = Field(None, description="Test panel or category (e.g., CBC, BMP, Lipid)")
    is_verified: bool = Field(default=False, description="Whether a human clinician verified/edited this item")
    verified_by: Optional[str] = Field(None, description="Name or role of person who verified")
    clinical_flag_note: Optional[str] = Field(None, description="Descriptive non-diagnostic observation")


class InconsistencyItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    severity: SeverityLevel = Field(..., description="Severity of inconsistency")
    title: str = Field(..., description="Short summary title of conflict")
    explanation: str = Field(..., description="Detailed explanation of the discrepancy")
    conflicting_points: List[str] = Field(..., description="Points of evidence in conflict")
    suggested_clarification: str = Field(..., description="Suggested clarifying question for physician/patient")


class ReportMetadata(BaseModel):
    filename: str
    upload_time: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    lab_name: Optional[str] = None
    collection_date: Optional[str] = None
    raw_text: Optional[str] = None


class VerifyItemRequest(BaseModel):
    item_id: str
    test_name: Optional[str] = None
    value: Optional[float] = None
    value_text: Optional[str] = None
    unit: Optional[str] = None
    ref_range_low: Optional[float] = None
    ref_range_high: Optional[float] = None
    status: Optional[BiomarkerStatus] = None
    verified_by: Optional[str] = "Attending Clinician"


class ClinicalRecord(BaseModel):
    record_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    patient: Optional[PatientIntake] = None
    reports: List[ReportMetadata] = Field(default_factory=list)
    lab_tests: List[LabTestItem] = Field(default_factory=list)
    inconsistencies: List[InconsistencyItem] = Field(default_factory=list)
    summary: Optional[str] = None
    disclaimer: str = (
        "MedLens is an information organization and intelligence tool for clinical review. "
        "It does NOT provide medical diagnoses, treatment recommendations, or prescriptions. "
        "All observations and extracted data must be reviewed and verified by a qualified healthcare professional."
    )

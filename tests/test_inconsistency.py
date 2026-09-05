"""
Comprehensive unit tests for the Clinical Inconsistency & Conflict Detection Engine.
"""

from app.models.schemas import (
    BiomarkerStatus,
    LabTestItem,
    PatientIntake,
    SeverityLevel,
)
from app.services.inconsistency_engine import detect_clinical_inconsistencies


def test_detect_hyperglycemia_without_diabetes_history():
    """Verify detection when glucose >= 126 and diabetes is not reported."""
    patient = PatientIntake(
        name="John Doe",
        age=45,
        sex="Male",
        symptoms=["Fatigue"],
        existing_conditions=["Mild Hypertension"],
        allergies=[],
        current_medications=["Amlodipine 5mg"],
    )

    lab_tests = [
        LabTestItem(
            test_name="Fasting Blood Glucose",
            value=162.0,
            unit="mg/dL",
            ref_range_low=70.0,
            ref_range_high=99.0,
            status=BiomarkerStatus.HIGH,
            source_snippet="Fasting Blood Glucose 162 mg/dL 70-99 HIGH",
        )
    ]

    conflicts = detect_clinical_inconsistencies(patient, lab_tests)
    assert len(conflicts) >= 1
    assert any("Hyperglycemia" in c.title or "Diabetes" in c.title for c in conflicts)
    assert any(c.severity == SeverityLevel.WARNING for c in conflicts)


def test_detect_hba1c_without_diabetes_history():
    """Verify detection when HbA1c >= 6.5 without recorded diabetes."""
    patient = PatientIntake(name="Alice", age=50, sex="Female", existing_conditions=[])
    lab_tests = [
        LabTestItem(
            test_name="HbA1c",
            value=7.4,
            unit="%",
            status=BiomarkerStatus.HIGH,
            source_snippet="HbA1c 7.4 % (4.0 - 5.6)",
        )
    ]
    conflicts = detect_clinical_inconsistencies(patient, lab_tests)
    assert any("HbA1c" in c.title for c in conflicts)


def test_detect_diabetes_med_without_diagnosis():
    """Verify info alert when patient takes Metformin but has no diabetes listed."""
    patient = PatientIntake(
        name="Charlie",
        age=52,
        sex="Male",
        current_medications=["Metformin 500mg"],
        existing_conditions=["Hypertension"],
    )
    conflicts = detect_clinical_inconsistencies(patient, [])
    assert any("Antidiabetic Medication" in c.title for c in conflicts)


def test_detect_renal_impairment_conflicts():
    """Verify warning when creatinine >= 1.5 or eGFR < 60 without kidney history."""
    patient = PatientIntake(
        name="David",
        age=68,
        sex="Male",
        existing_conditions=["Gout"],
    )
    lab_tests = [
        LabTestItem(
            test_name="Creatinine",
            value=1.8,
            unit="mg/dL",
            status=BiomarkerStatus.HIGH,
            source_snippet="Creatinine 1.8 mg/dL (0.7 - 1.3)",
        ),
        LabTestItem(
            test_name="eGFR",
            value=45.0,
            unit="mL/min",
            status=BiomarkerStatus.LOW,
            source_snippet="eGFR 45 mL/min (> 60)",
        ),
    ]
    conflicts = detect_clinical_inconsistencies(patient, lab_tests)
    assert any("Creatinine" in c.title for c in conflicts)
    assert any("GFR" in c.title for c in conflicts)


def test_detect_anemia_fatigue_correlation():
    """Verify observation when Hemoglobin is low and patient reports fatigue."""
    patient = PatientIntake(
        name="Eva",
        age=34,
        sex="Female",
        symptoms=["Severe chronic fatigue", "Lightheadedness"],
        existing_conditions=[],
    )
    lab_tests = [
        LabTestItem(
            test_name="Hemoglobin",
            value=10.1,
            unit="g/dL",
            status=BiomarkerStatus.LOW,
            source_snippet="Hemoglobin 10.1 g/dL (12.0 - 15.5)",
        )
    ]
    conflicts = detect_clinical_inconsistencies(patient, lab_tests)
    assert any("Hemoglobin Correlating with Reported Fatigue" in c.title for c in conflicts)


def test_detect_allergy_contraindications():
    """Verify critical alerts for Penicillin and NSAID allergies."""
    patient = PatientIntake(
        name="Jane Doe",
        age=32,
        sex="Female",
        allergies=["Penicillin (Anaphylaxis)", "NSAID allergy"],
        current_medications=["Amoxicillin 500mg", "Ibuprofen 400mg"],
    )

    conflicts = detect_clinical_inconsistencies(patient, [])
    assert len(conflicts) == 2
    critical_alerts = [c for c in conflicts if c.severity == SeverityLevel.CRITICAL]
    assert len(critical_alerts) == 2
    assert any("Penicillin" in c.title for c in critical_alerts)
    assert any("NSAID" in c.title for c in critical_alerts)

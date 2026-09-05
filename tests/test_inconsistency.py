from app.models.schemas import (
    BiomarkerStatus,
    LabTestItem,
    PatientIntake,
    SeverityLevel,
)
from app.services.inconsistency_engine import detect_clinical_inconsistencies


def test_detect_hyperglycemia_without_diabetes_history():
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


def test_detect_allergy_contraindication():
    patient = PatientIntake(
        name="Jane Doe",
        age=32,
        sex="Female",
        symptoms=["Ear pain"],
        existing_conditions=[],
        allergies=["Penicillin (Anaphylaxis)"],
        current_medications=["Amoxicillin 500mg"],
    )

    conflicts = detect_clinical_inconsistencies(patient, [])
    assert len(conflicts) >= 1
    crit = [c for c in conflicts if c.severity == SeverityLevel.CRITICAL]
    assert len(crit) == 1
    assert "Penicillin" in crit[0].title

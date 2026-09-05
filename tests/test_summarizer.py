"""
Comprehensive unit tests for Clinical Review & Summarizer module.
"""

from unittest.mock import MagicMock, patch

from app.models.schemas import (
    BiomarkerStatus,
    InconsistencyItem,
    LabTestItem,
    PatientIntake,
    SeverityLevel,
)
from app.services.summarizer import (
    generate_ai_summary,
    generate_deterministic_summary,
)


def test_generate_deterministic_summary_complete_case():
    """Verify deterministic summary generation with patient, mixed lab tests, and conflicts."""
    patient = PatientIntake(
        name="Eleanor Vance",
        age=61,
        sex="Female",
        symptoms=["Shortness of breath", "Fatigue"],
        existing_conditions=["Type 2 Diabetes"],
        allergies=["Aspirin"],
        current_medications=["Metformin 1000mg"],
    )

    lab_tests = [
        LabTestItem(
            test_name="Hemoglobin",
            value=9.8,
            unit="g/dL",
            ref_range_low=12.0,
            ref_range_high=15.5,
            status=BiomarkerStatus.LOW,
            source_snippet="Hemoglobin 9.8 g/dL (12.0 - 15.5)",
        ),
        LabTestItem(
            test_name="Fasting Blood Glucose",
            value=175.0,
            unit="mg/dL",
            ref_range_low=70.0,
            ref_range_high=99.0,
            status=BiomarkerStatus.HIGH,
            source_snippet="Fasting Glucose 175 mg/dL (70 - 99)",
        ),
        LabTestItem(
            test_name="Sodium",
            value=140.0,
            unit="mmol/L",
            ref_range_low=135.0,
            ref_range_high=145.0,
            status=BiomarkerStatus.NORMAL,
            source_snippet="Sodium 140 mmol/L (135 - 145)",
        ),
        LabTestItem(
            test_name="Vitamin D",
            value_text="Pending",
            status=BiomarkerStatus.UNKNOWN,
            source_snippet="Vitamin D: Pending",
        ),
    ]

    inconsistencies = [
        InconsistencyItem(
            severity=SeverityLevel.WARNING,
            title="Marked Hyperglycemia",
            explanation="Glucose elevated above target range.",
            conflicting_points=["Glucose = 175 mg/dL"],
            suggested_clarification="Review recent dietary intake and compliance.",
        )
    ]

    summary = generate_deterministic_summary(patient, lab_tests, inconsistencies)
    assert "Eleanor Vance" in summary
    assert "Flagged HIGH" in summary
    assert "Flagged LOW" in summary
    assert "Within Source Reference Range" in summary
    assert "Status UNKNOWN" in summary
    assert "Clinical Discrepancies & Items for Clarification" in summary
    assert "Clinical Notice" in summary


def test_generate_deterministic_summary_empty():
    """Verify fallback text when no data is provided."""
    summary = generate_deterministic_summary(None, [], [])
    assert "- No patient intake profile provided." in summary


def test_generate_ai_summary_mocked():
    """Verify AI summary invokes Gemini and returns markdown synthesis."""
    patient = PatientIntake(name="Bob Smith", age=50, sex="Male")
    mock_response = MagicMock()
    mock_response.text = "### Patient Overview\nBob is 50."

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with (
        patch.dict("os.environ", {"GEMINI_API_KEY": "dummy_key"}),
        patch("google.genai.Client", return_value=mock_client),
    ):
        res = generate_ai_summary(patient, [], [])
        assert "Bob is 50" in res

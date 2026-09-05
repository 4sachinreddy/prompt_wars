from app.models.schemas import BiomarkerStatus, LabTestItem
from app.services.range_evaluator import (
    evaluate_biomarker_status,
    parse_reference_range,
    process_lab_item_ranges,
)


def test_parse_reference_range_standard():
    low, high = parse_reference_range("13.5 - 17.5")
    assert low == 13.5
    assert high == 17.5

    low, high = parse_reference_range("70 to 99 mg/dL")
    assert low == 70.0
    assert high == 99.0


def test_parse_reference_range_inequalities():
    low, high = parse_reference_range("< 200")
    assert low is None
    assert high == 200.0

    low, high = parse_reference_range("> 60")
    assert low == 60.0
    assert high is None


def test_deterministic_range_evaluation_bounds():
    # Normal
    status, note = evaluate_biomarker_status(14.2, 13.5, 17.5, "g/dL")
    assert status == BiomarkerStatus.NORMAL
    assert "within source reference range" in note

    # Low
    status, note = evaluate_biomarker_status(10.4, 13.5, 17.5, "g/dL")
    assert status == BiomarkerStatus.LOW
    assert "below source reference minimum" in note

    # High
    status, note = evaluate_biomarker_status(158.0, 70.0, 99.0, "mg/dL")
    assert status == BiomarkerStatus.HIGH
    assert "exceeds source reference maximum" in note


def test_zero_hallucination_rule():
    """
    CRITICAL REQUIREMENT:
    If source report does NOT contain a reference range,
    the system must NOT invent one. Status must be UNKNOWN.
    """
    status, note = evaluate_biomarker_status(42.0, None, None, "U/L")
    assert status == BiomarkerStatus.UNKNOWN
    assert "Range not invented" in note


def test_process_lab_item_ranges_integration():
    item = LabTestItem(
        test_name="Hemoglobin",
        value=10.2,
        unit="g/dL",
        raw_ref_range="12.0 - 15.5",
        source_snippet="Hemoglobin 10.2 g/dL (12.0 - 15.5)",
    )
    processed = process_lab_item_ranges(item)
    assert processed.ref_range_low == 12.0
    assert processed.ref_range_high == 15.5
    assert processed.status == BiomarkerStatus.LOW

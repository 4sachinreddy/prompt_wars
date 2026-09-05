"""
Comprehensive unit tests for Document and Lab Extractor module.
Ensures near-100% code coverage across PDF parsing, regex rule engine, and Gemini extraction.
"""

from unittest.mock import MagicMock, patch

from app.services.extractor import (
    extract_text_from_pdf,
    extract_with_gemini,
    process_medical_report,
    rule_based_fallback_parser,
)


def test_extract_text_from_invalid_pdf():
    """Verify that corrupt or invalid PDF bytes return an error string without crashing."""
    result = extract_text_from_pdf(b"not a valid pdf content")
    assert "[Error reading PDF pages" in result


def test_rule_based_fallback_parser_biomarkers():
    """Verify extraction of known biomarkers, units, and ranges from raw text."""
    sample_text = """
    Metropolitan Hospital Clinical Laboratory
    Collection Date: 2026-05-12
    --------------------------------------------------
    Hemoglobin           14.2 g/dL     13.5 - 17.5    NORMAL
    Fasting Blood Glucose 158 mg/dL    70 - 99        HIGH
    Total Cholesterol    240 mg/dL     < 200          HIGH
    eGFR                 55 mL/min     > 60           LOW
    Platelets            250 x10^3/uL  150 - 450      NORMAL
    Serum Creatinine     1.4 mg/dL     0.7 - 1.3      HIGH
    HbA1c                7.2 %         4.0 - 5.6      HIGH
    WBC                  6.8 x10^3/uL  4.5 - 11.0     NORMAL
    Sodium               140 mmol/L    136 - 145      NORMAL
    Potassium            4.2 mmol/L    3.5 - 5.1      NORMAL
    Calcium              9.5 mg/dL     8.5 - 10.5     NORMAL
    Albumin              4.1 g/dL      3.5 - 5.0      NORMAL
    Total Bilirubin      0.8 mg/dL     0.2 - 1.2      NORMAL
    AST                  28 U/L        10 - 40        NORMAL
    ALT                  32 U/L        10 - 45        NORMAL
    TSH                  2.4 mIU/L     0.4 - 4.0      NORMAL
    --------------------------------------------------
    """
    report = rule_based_fallback_parser(sample_text)
    assert report.lab_name is not None
    assert "Metropolitan Hospital" in report.lab_name
    assert report.collection_date == "2026-05-12"
    assert len(report.tests) >= 10

    test_names = [t.test_name for t in report.tests]
    assert "Hemoglobin" in test_names
    assert "Fasting Blood Glucose" in test_names
    assert "Total Cholesterol" in test_names
    assert "eGFR" in test_names


def test_rule_based_fallback_parser_empty_and_short_lines():
    """Verify parser gracefully ignores empty or whitespace-only lines."""
    sample_text = "   \n\n\n   a\n12\n"
    report = rule_based_fallback_parser(sample_text)
    assert len(report.tests) == 0


def test_process_medical_report_text_and_deduplication():
    """Verify processing text file and updating existing test entries."""
    content = b"""
    Hemoglobin 11.2 g/dL 12.0 - 15.5
    Hemoglobin 11.5 g/dL 12.0 - 15.5
    """
    metadata, items = process_medical_report(
        filename="report.txt",
        raw_content=content,
        content_type="text/plain",
    )
    assert metadata.filename == "report.txt"
    assert len(items) == 1
    assert items[0].test_name == "Hemoglobin"
    assert items[0].value == 11.2


def test_extract_with_gemini_mocked():
    """Verify extract_with_gemini correctly parses response schema when API key is provided."""
    mock_report_json = """{
        "lab_name": "Quest Diagnostics",
        "collection_date": "2026-08-01",
        "tests": [
            {
                "test_name": "Hemoglobin",
                "value": 14.5,
                "value_text": null,
                "unit": "g/dL",
                "ref_range_low": 13.5,
                "ref_range_high": 17.5,
                "raw_ref_range": "13.5 - 17.5",
                "source_snippet": "Hemoglobin 14.5 g/dL (13.5 - 17.5)",
                "category": "CBC"
            }
        ]
    }"""

    mock_response = MagicMock()
    mock_response.text = mock_report_json

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("google.genai.Client", return_value=mock_client):
        result = extract_with_gemini("Sample raw text", api_key="fake_test_key")
        assert result.lab_name == "Quest Diagnostics"
        assert len(result.tests) == 1
        assert result.tests[0].test_name == "Hemoglobin"
        assert result.tests[0].value == 14.5

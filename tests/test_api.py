"""
Comprehensive API integration tests for MedLens FastAPI application.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint():
    """Verify health probe endpoint returns 200 OK and service metadata."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "medlens"
    assert data["version"] == "1.0.0"


def test_serve_dashboard_ui():
    """Verify root / serves HTML dashboard."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "MedLens" in response.text


def test_patient_intake_flow():
    """Verify patient intake submission and calculation."""
    payload = {
        "name": "Sarah Connor",
        "age": 42,
        "sex": "Female",
        "symptoms": ["Mild joint pain"],
        "existing_conditions": ["Hypothyroidism"],
        "allergies": ["Sulfa"],
        "current_medications": ["Levothyroxine 50mcg"],
        "notes": "Routine checkup",
        "provenance": "USER_PROVIDED",
    }
    response = client.post("/api/intake", json=payload)
    assert response.status_code == 200
    record = response.json()
    assert record["patient"]["name"] == "Sarah Connor"
    assert record["patient"]["provenance"] == "USER_PROVIDED"


def test_upload_medical_report_valid_file():
    """Verify uploading a valid laboratory text file populates clinical record."""
    file_content = b"""
    Metropolitan Hospital Laboratory
    Hemoglobin 14.2 g/dL 13.5 - 17.5
    Fasting Blood Glucose 158 mg/dL 70 - 99
    """
    files = {"file": ("patient_lab.txt", file_content, "text/plain")}
    response = client.post("/api/upload-report", files=files)
    assert response.status_code == 200
    record = response.json()
    assert len(record["reports"]) > 0
    assert len(record["lab_tests"]) >= 2


def test_load_sample_case_flow():
    """Verify 1-click sample demo case loads full patient and lab data."""
    response = client.post("/api/load-sample")
    assert response.status_code == 200
    record = response.json()
    assert record["patient"] is not None
    assert record["patient"]["name"] == "Marcus Sterling"
    assert len(record["lab_tests"]) > 0
    assert len(record["inconsistencies"]) > 0
    assert record["summary"] is not None


def test_human_in_the_loop_verification():
    """Verify HITL verification updates observation to HUMAN_VERIFIED."""
    # 1. Load sample data
    client.post("/api/load-sample")
    rec = client.get("/api/record").json()
    first_test = rec["lab_tests"][0]
    test_id = first_test["id"]

    # 2. Verify and edit item
    verify_payload = {
        "item_id": test_id,
        "test_name": "Hemoglobin (Adjusted)",
        "value": 11.5,
        "unit": "g/dL",
        "ref_range_low": 12.0,
        "ref_range_high": 16.0,
        "verified_by": "Dr. Vance, MD",
    }
    response = client.post("/api/verify-item", json=verify_payload)
    assert response.status_code == 200
    updated_rec = response.json()

    # Find the verified item
    matching = [t for t in updated_rec["lab_tests"] if t["id"] == test_id][0]
    assert matching["is_verified"] is True
    assert matching["provenance"] == "HUMAN_VERIFIED"
    assert matching["verified_by"] == "Dr. Vance, MD"
    assert matching["value"] == 11.5

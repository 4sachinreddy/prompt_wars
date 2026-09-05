"""
Automated unit tests for MedLens security headers, input validation, and upload boundaries.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_security_headers_present():
    """Verify all critical Security HTTP headers are returned in API responses."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-XSS-Protection"] == "1; mode=block"
    assert "strict-origin-when-cross-origin" in response.headers["Referrer-Policy"]
    assert "default-src" in response.headers["Content-Security-Policy"]


def test_upload_empty_file():
    """Verify that uploading an empty file returns a 400 Bad Request error."""
    files = {"file": ("empty.txt", b"", "text/plain")}
    response = client.post("/api/upload-report", files=files)
    assert response.status_code == 400
    data = response.json()
    assert data["error"] is True
    assert "empty" in data["detail"].lower()


def test_upload_oversized_file():
    """Verify that uploading a file larger than 10MB returns 413 Request Entity Too Large."""
    # Create 10.1 MB dummy content
    large_content = b"A" * (10 * 1024 * 1024 + 1024)
    files = {"file": ("huge_report.txt", large_content, "text/plain")}
    response = client.post("/api/upload-report", files=files)
    assert response.status_code == 413
    data = response.json()
    assert data["error"] is True
    assert "exceeds" in data["detail"].lower()


def test_verify_nonexistent_item():
    """Verify that attempting to verify a non-existent lab item ID returns 404 Not Found."""
    payload = {
        "item_id": "non_existent_id_999",
        "test_name": "Ghost Test",
    }
    response = client.post("/api/verify-item", json=payload)
    assert response.status_code == 404
    data = response.json()
    assert data["error"] is True


def test_clear_session():
    """Verify session reset endpoint."""
    response = client.post("/api/clear")
    assert response.status_code == 200
    data = response.json()
    assert data["patient"] is None
    assert len(data["lab_tests"]) == 0

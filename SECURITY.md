# Security Policy & Vulnerability Reporting

## Overview
MedLens is built with security, privacy, and clinical data integrity as core priorities. We follow defensive engineering standards to protect healthcare data against zero-day vulnerabilities, unauthorized access, and prompt injection attacks.

## Security Controls Implemented

1. **Zero Data Persistence for Credentials**: API keys (such as `GEMINI_API_KEY`) are read strictly from environment variables and never logged or serialized.
2. **HTTP Security Headers**:
   - `Content-Security-Policy`: Restricts resource loading to trusted origins.
   - `X-Frame-Options: DENY`: Prevents clickjacking attacks.
   - `X-Content-Type-Options: nosniff`: Prevents MIME-type sniffing.
   - `X-XSS-Protection: 1; mode=block`: Enables browser XSS filtering.
   - `Referrer-Policy: strict-origin-when-cross-origin`: Protects clinical URL privacy.
3. **Input Sanitization & Upload Boundaries**:
   - File uploads are validated against maximum size limits (10 MB).
   - Filename paths are sanitized to prevent Path Traversal vulnerabilities.
4. **Deterministic Validation (Zero Hallucination)**:
   - Numerical clinical laboratory values are evaluated deterministically against parsed reference ranges, preventing AI hallucinations from influencing clinical risk output.

## Reporting a Vulnerability

If you discover a security vulnerability within MedLens, please submit a report to `security@medlens.ai` or create a confidential issue. 

We will acknowledge receipt within 24 hours and aim to provide a resolution within 72 hours.

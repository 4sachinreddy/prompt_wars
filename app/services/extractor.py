import os
import io
import re
import json
from typing import List, Optional, Tuple
from pypdf import PdfReader
from pydantic import BaseModel, Field

from app.models.schemas import (
    LabTestItem,
    ProvenanceType,
    BiomarkerStatus,
    ReportMetadata,
)
from app.services.range_evaluator import process_lab_item_ranges


class LLMExtractedItem(BaseModel):
    test_name: str = Field(description="Name of the test, e.g. Hemoglobin, Glucose, Creatinine")
    value: Optional[float] = Field(None, description="Numeric result value")
    value_text: Optional[str] = Field(None, description="Textual result if qualitative (e.g., Negative, Trace)")
    unit: Optional[str] = Field(None, description="Unit of measurement, e.g. g/dL, mg/dL, %")
    ref_range_low: Optional[float] = Field(None, description="Lower bound of reference range explicitly in document. Null if not stated.")
    ref_range_high: Optional[float] = Field(None, description="Upper bound of reference range explicitly in document. Null if not stated.")
    raw_ref_range: Optional[str] = Field(None, description="Raw reference range verbatim from source")
    source_snippet: str = Field(description="Exact snippet or line from report containing this observation")
    category: Optional[str] = Field(None, description="Panel name, e.g. Complete Blood Count, Metabolic Panel")


class LLMExtractedReport(BaseModel):
    lab_name: Optional[str] = Field(None, description="Name of the medical laboratory or clinic")
    collection_date: Optional[str] = Field(None, description="Date of specimen collection or report")
    tests: List[LLMExtractedItem] = Field(default_factory=list)


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extracts plain text from a PDF file using pypdf."""
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        text = ""
        for page_idx, page in enumerate(reader.pages):
            page_text = page.extract_text()
            if page_text:
                text += f"\n--- Page {page_idx + 1} ---\n" + page_text
        return text.strip()
    except Exception as e:
        return f"[Error reading PDF pages: {str(e)}]"


def rule_based_fallback_parser(raw_text: str) -> LLMExtractedReport:
    """
    High-precision tabular regex parser for clinical lab reports.
    Serves as an offline fallback when GEMINI_API_KEY is not configured.
    """
    tests: List[LLMExtractedItem] = []
    lines = raw_text.splitlines()

    lab_name = "Clinical Pathology Laboratory"
    collection_date = None

    # Detect header details
    for line in lines[:15]:
        if "lab" in line.lower() or "hospital" in line.lower() or "clinic" in line.lower():
            if len(line.strip()) < 60:
                lab_name = line.strip()
        date_match = re.search(r"\b(\d{1,4}[-/]\d{1,2}[-/]\d{1,4})\b", line)
        if date_match and not collection_date:
            collection_date = date_match.group(1)

    # Common known lab tests for tabular parsing
    known_biomarkers = [
        ("Hemoglobin", r"(?:Hemoglobin|Hgb|Hb)\b"),
        ("Hematocrit", r"(?:Hematocrit|Hct)\b"),
        ("WBC", r"(?:WBC|White Blood Cell Count|Leukocytes)\b"),
        ("RBC", r"(?:RBC|Red Blood Cell Count|Erythrocytes)\b"),
        ("Platelets", r"(?:Platelets|Platelet Count|PLT)\b"),
        ("MCV", r"\bMCV\b"),
        ("MCH", r"\bMCH\b"),
        ("MCHC", r"\bMCHC\b"),
        ("RDW", r"\bRDW\b"),
        ("Fasting Blood Glucose", r"(?:Glucose|Fasting Glucose|Blood Sugar)\b"),
        ("HbA1c", r"(?:HbA1c|Hemoglobin A1c|Glycated Hemoglobin)\b"),
        ("Creatinine", r"(?:Creatinine|Serum Creatinine)\b"),
        ("Blood Urea Nitrogen", r"(?:BUN|Blood Urea Nitrogen|Urea)\b"),
        ("eGFR", r"(?:eGFR|Estimated GFR|Glomerular Filtration)\b"),
        ("Sodium", r"(?:Sodium|Na\+?)\b"),
        ("Potassium", r"(?:Potassium|K\+?)\b"),
        ("Chloride", r"(?:Chloride|Cl\-?)\b"),
        ("Calcium", r"(?:Calcium|Ca\+?)\b"),
        ("Total Protein", r"(?:Total Protein)\b"),
        ("Albumin", r"(?:Albumin)\b"),
        ("Total Bilirubin", r"(?:Total Bilirubin|Bilirubin Total)\b"),
        ("AST", r"(?:AST|SGOT|Aspartate Aminotransferase)\b"),
        ("ALT", r"(?:ALT|SGPT|Alanine Aminotransferase)\b"),
        ("Alkaline Phosphatase", r"(?:Alkaline Phosphatase|ALP)\b"),
        ("Total Cholesterol", r"(?:Total Cholesterol|Cholesterol Total)\b"),
        ("Triglycerides", r"(?:Triglycerides|Triglyceride)\b"),
        ("HDL Cholesterol", r"(?:HDL|HDL Cholesterol)\b"),
        ("LDL Cholesterol", r"(?:LDL|LDL Cholesterol)\b"),
        ("TSH", r"(?:TSH|Thyroid Stimulating Hormone)\b"),
    ]

    for line in lines:
        line_clean = line.strip()
        if not line_clean or len(line_clean) < 4:
            continue

        for test_canonical, pattern in known_biomarkers:
            match = re.search(pattern, line_clean, re.IGNORECASE)
            if match:
                # Find all numbers on this line
                nums = re.findall(r"[-+]?[0-9]*\.?[0-9]+", line_clean)
                if not nums:
                    continue

                value = float(nums[0])
                
                # Check for unit
                unit = None
                unit_candidates = ["g/dL", "mg/dL", "mmol/L", "x10^3/uL", "x10^6/uL", "uL", "fL", "pg", "%", "U/L", "mIU/L", "mL/min/1.73m2"]
                for u in unit_candidates:
                    if u.lower() in line_clean.lower():
                        unit = u
                        break

                # Extract reference range
                ref_low = None
                ref_high = None
                raw_ref = None

                # Look for patterns like (12.0 - 15.5) or 13.5 - 17.5
                range_match = re.search(r"([0-9]+\.?[0-9]*)\s*[-–to]\s*([0-9]+\.?[0-9]*)", line_clean)
                if range_match:
                    try:
                        cand_low = float(range_match.group(1))
                        cand_high = float(range_match.group(2))
                        # Make sure cand_low and cand_high are not the test value itself
                        if cand_low != value or len(nums) > 2:
                            ref_low = cand_low
                            ref_high = cand_high
                            raw_ref = f"{ref_low} - {ref_high}"
                    except ValueError:
                        pass
                
                # Look for < 200 or > 60
                if not ref_low and not ref_high:
                    less_m = re.search(r"<\s*([0-9]+\.?[0-9]*)", line_clean)
                    if less_m:
                        ref_high = float(less_m.group(1))
                        raw_ref = f"< {ref_high}"
                    great_m = re.search(r">\s*([0-9]+\.?[0-9]*)", line_clean)
                    if great_m:
                        ref_low = float(great_m.group(1))
                        raw_ref = f"> {ref_low}"

                # Avoid duplicate extraction of same test
                if not any(t.test_name == test_canonical for t in tests):
                    tests.append(
                        LLMExtractedItem(
                            test_name=test_canonical,
                            value=value,
                            unit=unit,
                            ref_range_low=ref_low,
                            ref_range_high=ref_high,
                            raw_ref_range=raw_ref,
                            source_snippet=line_clean,
                            category="General Clinical Panel",
                        )
                    )
                break

    return LLMExtractedReport(
        lab_name=lab_name,
        collection_date=collection_date,
        tests=tests,
    )


def extract_with_gemini(raw_text: str, api_key: str) -> LLMExtractedReport:
    """
    Extracts structured lab results using Google Gemini API (gemini-2.5-flash).
    Follows strict guidelines: never invent reference ranges, keep exact snippets.
    """
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    system_instruction = """
    You are MedLens Clinical Information Intelligence.
    Extract laboratory test observations and reference ranges from medical reports with 100% fidelity.

    CRITICAL RULES:
    1. STRICT REFERENCE RANGE ADHERENCE:
       - Extract numerical values, units, and reference ranges EXACTLY as they appear in the source.
       - NEVER invent, assume, or insert standard medical reference ranges.
       - If a reference range is absent from the report, populate ref_range_low and ref_range_high as null.
    2. TRACEABILITY & SNIPPETS:
       - Every test must include the exact line or text snippet where the value was found.
    3. NON-DIAGNOSTIC:
       - Do not diagnose diseases. Extract purely observational lab facts.
    """

    prompt = f"""
    Please extract all laboratory tests, numeric results, units, source-provided reference ranges,
    and exact text snippets from the following clinical document text:

    DOCUMENT:
    {raw_text}
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_json_schema=LLMExtractedReport.model_json_schema(),
            temperature=0.0,
        ),
    )

    result_data = json.loads(response.text)
    return LLMExtractedReport(**result_data)


def process_medical_report(
    filename: str,
    raw_content: bytes,
    content_type: str = "text/plain",
) -> Tuple[ReportMetadata, List[LabTestItem]]:
    """
    Main pipeline entry for document ingestion.
    Extracts text, invokes Gemini or fallback parser, and evaluates deterministic ranges.
    """
    # 1. Text extraction
    if filename.lower().endswith(".pdf") or "pdf" in content_type:
        raw_text = extract_text_from_pdf(raw_content)
    else:
        try:
            raw_text = raw_content.decode("utf-8")
        except UnicodeDecodeError:
            raw_text = raw_content.decode("latin-1", errors="ignore")

    # 2. Information Extraction
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    extracted_report: LLMExtractedReport

    if gemini_key:
        try:
            extracted_report = extract_with_gemini(raw_text, gemini_key)
        except Exception as e:
            # If API call fails or rate limited, gracefully fall back to local clinical parser
            extracted_report = rule_based_fallback_parser(raw_text)
    else:
        extracted_report = rule_based_fallback_parser(raw_text)

    # 3. Create domain items and evaluate ranges deterministically
    report_metadata = ReportMetadata(
        filename=filename,
        lab_name=extracted_report.lab_name,
        collection_date=extracted_report.collection_date,
        raw_text=raw_text,
    )

    items: List[LabTestItem] = []
    for item in extracted_report.tests:
        lab_item = LabTestItem(
            test_name=item.test_name,
            value=item.value,
            value_text=item.value_text,
            unit=item.unit,
            ref_range_low=item.ref_range_low,
            ref_range_high=item.ref_range_high,
            raw_ref_range=item.raw_ref_range,
            source_snippet=item.source_snippet,
            provenance=ProvenanceType.AI_EXTRACTED,
            confidence=0.95,
            observation_date=extracted_report.collection_date,
            category=item.category,
        )
        # Deterministically calculate status: LOW / HIGH / NORMAL / UNKNOWN
        lab_item = process_lab_item_ranges(lab_item)
        items.append(lab_item)

    return report_metadata, items

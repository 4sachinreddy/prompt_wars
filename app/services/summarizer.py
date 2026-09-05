import os
from typing import List, Optional
from app.models.schemas import (
    PatientIntake,
    LabTestItem,
    InconsistencyItem,
    BiomarkerStatus,
)


def generate_deterministic_summary(
    patient: Optional[PatientIntake],
    lab_tests: List[LabTestItem],
    inconsistencies: List[InconsistencyItem],
) -> str:
    """
    Generates a structured, non-diagnostic, patient-friendly clinical summary.
    Adheres strictly to Responsible AI safety guidelines (no diagnosis, no prescription).
    """
    lines: List[str] = []

    # 1. Patient Profile Overview
    lines.append("### 📋 Patient Overview & Reported Intake")
    if patient:
        lines.append(f"- **Patient**: {patient.name}, {patient.age} y/o ({patient.sex})")
        lines.append(f"- **Reported Symptoms**: {', '.join(patient.symptoms) if patient.symptoms else 'None reported'}")
        lines.append(f"- **Documented Conditions**: {', '.join(patient.existing_conditions) if patient.existing_conditions else 'None listed'}")
        lines.append(f"- **Current Medications**: {', '.join(patient.current_medications) if patient.current_medications else 'None listed'}")
        lines.append(f"- **Documented Allergies**: {', '.join(patient.allergies) if patient.allergies else 'No known drug allergies'}")
    else:
        lines.append("- No patient intake profile provided.")

    lines.append("")

    # 2. Laboratory Observations Breakdown
    lines.append("### 🔬 Laboratory Report Findings")
    if not lab_tests:
        lines.append("- No laboratory tests uploaded yet.")
    else:
        low_items = [t for t in lab_tests if t.status == BiomarkerStatus.LOW]
        high_items = [t for t in lab_tests if t.status == BiomarkerStatus.HIGH]
        normal_items = [t for t in lab_tests if t.status == BiomarkerStatus.NORMAL]
        unknown_items = [t for t in lab_tests if t.status == BiomarkerStatus.UNKNOWN]

        if high_items:
            lines.append("#### 🔺 Values Above Source Reference Range:")
            for item in high_items:
                ref_str = f" (Reported Ref: {item.ref_range_low or '-'} - {item.ref_range_high or '-'})" if (item.ref_range_low or item.ref_range_high) else ""
                lines.append(f"- **{item.test_name}**: {item.value} {item.unit or ''}{ref_str} — *Flagged HIGH*")

        if low_items:
            lines.append("#### 🔻 Values Below Source Reference Range:")
            for item in low_items:
                ref_str = f" (Reported Ref: {item.ref_range_low or '-'} - {item.ref_range_high or '-'})" if (item.ref_range_low or item.ref_range_high) else ""
                lines.append(f"- **{item.test_name}**: {item.value} {item.unit or ''}{ref_str} — *Flagged LOW*")

        if normal_items:
            lines.append(f"#### ✅ Values Within Source Reference Range ({len(normal_items)} tests):")
            normal_names = [f"{t.test_name} ({t.value} {t.unit or ''})" for t in normal_items]
            lines.append(f"- {', '.join(normal_names)}")

        if unknown_items:
            lines.append(f"#### ❓ Tests Without Source Reference Range ({len(unknown_items)} tests):")
            for item in unknown_items:
                val = item.value if item.value is not None else item.value_text
                lines.append(f"- **{item.test_name}**: {val} {item.unit or ''} — *Status UNKNOWN (No reference range was stated in the source report)*")

    lines.append("")

    # 3. Clinical Inconsistencies & Reconciliations
    if inconsistencies:
        lines.append("### ⚠️ Clinical Discrepancies & Items for Clarification")
        for inc in inconsistencies:
            lines.append(f"- **[{inc.severity.value}] {inc.title}**")
            lines.append(f"  - *Observation*: {inc.explanation}")
            lines.append(f"  - *Suggested Clarification*: {inc.suggested_clarification}")
        lines.append("")

    # 4. Responsible AI Safety Notice
    lines.append("---")
    lines.append(
        "> ⚠️ **Clinical Notice**: This summary is an observational data organization synthesis. "
        "MedLens does not formulate clinical diagnoses, prescribe treatments, or suggest medication adjustments. "
        "All values and observations must be formally reviewed by an attending physician or licensed practitioner."
    )

    return "\n".join(lines)


def generate_ai_summary(
    patient: Optional[PatientIntake],
    lab_tests: List[LabTestItem],
    inconsistencies: List[InconsistencyItem],
) -> str:
    """
    Generates summary via Gemini 2.5 Flash if available, with strict prompt constraints,
    or falls back to the deterministic synthesizer.
    """
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not gemini_key:
        return generate_deterministic_summary(patient, lab_tests, inconsistencies)

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=gemini_key)

        data_payload = {
            "patient": patient.model_dump() if patient else None,
            "lab_tests": [t.model_dump() for t in lab_tests],
            "inconsistencies": [i.model_dump() for i in inconsistencies],
        }

        system_instruction = """
        You are MedLens Clinical Information Intelligence.
        Generate a patient-friendly, professional, and clear clinical review summary of the provided structured health data.

        MANDATORY CLINICAL SAFETY RULES:
        1. DO NOT DIAGNOSE: Never say "Patient has X" or "This confirms disease Y". Use purely observational language (e.g. "Hemoglobin is flagged below reported reference range").
        2. DO NOT PRESCRIBE OR SUGGEST DOSING: Never suggest treatments, medications, or changing existing therapies.
        3. REFERENCE RANGE HONESTY: Only mention high/low flags based strictly on the extracted source ranges. If unknown, state that the report did not specify a reference range.
        4. STRUCTURE: Use clear markdown sections (Patient Overview, Flagged Lab Findings, Normal Findings, Clinical Discrepancies to Clarify, and Disclaimer).
        """

        prompt = f"Please synthesize the following clinical record into an organized clinical review summary:\n\n{data_payload}"

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
            ),
        )
        return response.text
    except Exception:
        return generate_deterministic_summary(patient, lab_tests, inconsistencies)

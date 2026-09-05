from typing import List
from app.models.schemas import (
    PatientIntake,
    LabTestItem,
    InconsistencyItem,
    SeverityLevel,
    BiomarkerStatus,
)


def detect_clinical_inconsistencies(
    patient: PatientIntake,
    lab_tests: List[LabTestItem],
) -> List[InconsistencyItem]:
    """
    Identifies clinical conflicts and discrepancies between user-provided intake data
    (symptoms, pre-existing conditions, medications, allergies) and extracted laboratory findings.
    """
    inconsistencies: List[InconsistencyItem] = []

    # Helper to look up test by name
    tests_by_name = {t.test_name.lower(): t for t in lab_tests}

    conditions_text = " ".join(patient.existing_conditions).lower()
    meds_text = " ".join(patient.current_medications).lower()
    symptoms_text = " ".join(patient.symptoms).lower()
    allergies_text = " ".join(patient.allergies).lower()

    # 1. Glycemic / Diabetes Conflict
    glucose_test = tests_by_name.get("fasting blood glucose") or tests_by_name.get("glucose")
    hba1c_test = tests_by_name.get("hba1c")

    has_diabetes_reported = any(d in conditions_text for d in ["diabetes", "hyperglycemia", "diabetic", "t2d", "t1d"])
    has_diabetes_med = any(m in meds_text for m in ["metformin", "glipizide", "insulin", "januvia", "ozempic", "jardiance"])

    if not has_diabetes_reported:
        if glucose_test and glucose_test.value and glucose_test.value >= 126.0:
            inconsistencies.append(
                InconsistencyItem(
                    severity=SeverityLevel.WARNING,
                    title="Marked Hyperglycemia without Documented Diabetes History",
                    explanation=(
                        f"Fasting Blood Glucose is significantly elevated at {glucose_test.value} {glucose_test.unit or 'mg/dL'} "
                        f"(Ref: {glucose_test.ref_range_low or 70} - {glucose_test.ref_range_high or 99}), "
                        "yet the patient's reported medical conditions do not include diabetes or impaired fasting glucose."
                    ),
                    conflicting_points=[
                        f"Reported Conditions: {', '.join(patient.existing_conditions) or 'None documented'}",
                        f"Lab Observation: Fasting Blood Glucose = {glucose_test.value} {glucose_test.unit or 'mg/dL'} ({glucose_test.status.value})",
                    ],
                    suggested_clarification="Confirm fasting status for this blood draw and inquire whether the patient has previously had an HbA1c or pre-diabetes evaluation.",
                )
            )

        if hba1c_test and hba1c_test.value and hba1c_test.value >= 6.5:
            inconsistencies.append(
                InconsistencyItem(
                    severity=SeverityLevel.WARNING,
                    title="Elevated Glycated Hemoglobin (HbA1c) without Recorded Diagnosis",
                    explanation=(
                        f"HbA1c level is recorded at {hba1c_test.value}%, which is flagged above typical reference limits, "
                        "without any patient-reported history of diabetes mellitus."
                    ),
                    conflicting_points=[
                        f"Reported Conditions: {', '.join(patient.existing_conditions) or 'None'}",
                        f"Lab Observation: HbA1c = {hba1c_test.value}%",
                    ],
                    suggested_clarification="Check if patient has an existing diabetes diagnosis that was omitted from intake, or if repeat diagnostic testing is indicated.",
                )
            )

    # 2. Medication / Diagnosis Mismatch (Taking diabetes med without diabetes diagnosis)
    if has_diabetes_med and not has_diabetes_reported:
        inconsistencies.append(
            InconsistencyItem(
                severity=SeverityLevel.INFO,
                title="Antidiabetic Medication Prescribed without Recorded Diagnostic Indication",
                explanation="Patient reports taking antidiabetic medication(s) (e.g. Metformin), but diabetes is not listed under existing medical conditions.",
                conflicting_points=[
                    f"Reported Medications: {', '.join(patient.current_medications)}",
                    f"Reported Conditions: {', '.join(patient.existing_conditions) or 'None'}",
                ],
                suggested_clarification="Verify whether medication is taken for pre-diabetes, insulin resistance, PCOS, or unrecorded Type 2 Diabetes.",
            )
        )

    # 3. Renal Impairment Conflict
    creat_test = tests_by_name.get("creatinine")
    egfr_test = tests_by_name.get("egfr")

    has_kidney_reported = any(k in conditions_text for k in ["kidney", "renal", "ckd", "nephropathy"])
    if not has_kidney_reported:
        if creat_test and creat_test.value and creat_test.value >= 1.5:
            inconsistencies.append(
                InconsistencyItem(
                    severity=SeverityLevel.WARNING,
                    title="Elevated Serum Creatinine without Documented Renal History",
                    explanation=(
                        f"Serum Creatinine is recorded at {creat_test.value} {creat_test.unit or 'mg/dL'} (Flagged {creat_test.status.value}), "
                        "which may suggest decreased renal filtration, without documented kidney conditions."
                    ),
                    conflicting_points=[
                        f"Reported Conditions: {', '.join(patient.existing_conditions) or 'None'}",
                        f"Lab Observation: Creatinine = {creat_test.value} {creat_test.unit or 'mg/dL'}",
                    ],
                    suggested_clarification="Review hydration state, recent NSAID or nephrotoxic medication use, and compare with baseline renal function panels.",
                )
            )

        if egfr_test and egfr_test.value and egfr_test.value < 60.0:
            inconsistencies.append(
                InconsistencyItem(
                    severity=SeverityLevel.WARNING,
                    title="Reduced Estimated GFR (< 60 mL/min/1.73m2) without Documented CKD",
                    explanation=f"eGFR is reported at {egfr_test.value} mL/min/1.73m2, which indicates reduced filtration efficiency.",
                    conflicting_points=[
                        f"Reported Conditions: {', '.join(patient.existing_conditions) or 'None'}",
                        f"Lab Observation: eGFR = {egfr_test.value} mL/min/1.73m2",
                    ],
                    suggested_clarification="Verify chronicity (>3 months) to differentiate acute kidney stress from chronic renal reduction.",
                )
            )

    # 4. Anemia / Fatigue Correlation & Unreported Cytopenia
    hemo_test = tests_by_name.get("hemoglobin")
    has_anemia_reported = any(a in conditions_text for a in ["anemia", "iron deficiency"])
    has_fatigue_symptom = any(f in symptoms_text for f in ["fatigue", "tired", "weakness", "exhaustion", "dizziness"])

    if hemo_test and hemo_test.status == BiomarkerStatus.LOW:
        if has_fatigue_symptom and not has_anemia_reported:
            inconsistencies.append(
                InconsistencyItem(
                    severity=SeverityLevel.INFO,
                    title="Low Hemoglobin Correlating with Reported Fatigue Symptoms",
                    explanation=(
                        f"Patient reports symptoms of fatigue/weakness, and Hemoglobin is flagged below source reference range "
                        f"at {hemo_test.value} {hemo_test.unit or 'g/dL'}."
                    ),
                    conflicting_points=[
                        f"Reported Symptoms: {', '.join(patient.symptoms)}",
                        f"Lab Observation: Hemoglobin = {hemo_test.value} {hemo_test.unit or 'g/dL'} (LOW)",
                    ],
                    suggested_clarification="Inquire about dietary iron intake, blood loss history, or consider checking serum ferritin and iron saturation.",
                )
            )

    # 5. Medication Contraindication / Allergy Cross-Check
    for med in patient.current_medications:
        med_lower = med.lower()
        if "penicillin" in med_lower or "amoxicillin" in med_lower or "augmentin" in med_lower:
            if "penicillin" in allergies_text:
                inconsistencies.append(
                    InconsistencyItem(
                        severity=SeverityLevel.CRITICAL,
                        title="Critical Allergy Alert: Penicillin Class Medication Reported with Known Allergy",
                        explanation=f"Patient reports allergy to Penicillin, but is documented as currently taking '{med}'.",
                        conflicting_points=[
                            f"Recorded Allergies: {', '.join(patient.allergies)}",
                            f"Active Medication: {med}",
                        ],
                        suggested_clarification="URGENT: Immediately confirm with the patient and prescribing provider whether this medication is actively being consumed.",
                    )
                )

        if "aspirin" in med_lower or "ibuprofen" in med_lower or "naproxen" in med_lower:
            if "nsaid" in allergies_text or "aspirin" in allergies_text:
                inconsistencies.append(
                    InconsistencyItem(
                        severity=SeverityLevel.CRITICAL,
                        title="Allergy Alert: NSAID / Aspirin Class Medication Prescribed with Allergy",
                        explanation=f"Patient has recorded NSAID/Aspirin allergy, but intake lists '{med}'.",
                        conflicting_points=[
                            f"Recorded Allergies: {', '.join(patient.allergies)}",
                            f"Active Medication: {med}",
                        ],
                        suggested_clarification="Clarify previous allergic reaction severity (rash, anaphylaxis) and discontinue if inappropriate.",
                    )
                )

    return inconsistencies

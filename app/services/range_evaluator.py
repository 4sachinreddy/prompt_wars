import re
from typing import Optional, Tuple
from app.models.schemas import BiomarkerStatus, LabTestItem


def parse_reference_range(raw_range: Optional[str]) -> Tuple[Optional[float], Optional[float]]:
    """
    Parses common reference range patterns from text without guessing standards.
    Examples:
      "12.0 - 15.5" -> (12.0, 15.5)
      "70 - 99 mg/dL" -> (70.0, 99.0)
      "< 200" -> (None, 200.0)
      "<= 100" -> (None, 100.0)
      "> 60" -> (60.0, None)
      ">= 60" -> (60.0, None)
    """
    if not raw_range or not isinstance(raw_range, str):
        return None, None

    cleaned = raw_range.strip()

    # Pattern: Min - Max (e.g. 13.5 - 17.5, 4.0-11.0, 0.7 - 1.3)
    range_match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(?:-|to|–|—)\s*([0-9]+(?:\.[0-9]+)?)", cleaned)
    if range_match:
        try:
            low = float(range_match.group(1))
            high = float(range_match.group(2))
            return low, high
        except ValueError:
            pass

    # Pattern: < Max or <= Max
    less_match = re.search(r"(?:<|<=|less than)\s*([0-9]+(?:\.[0-9]+)?)", cleaned, re.IGNORECASE)
    if less_match:
        try:
            return None, float(less_match.group(1))
        except ValueError:
            pass

    # Pattern: > Min or >= Min
    greater_match = re.search(r"(?:>|>=|greater than)\s*([0-9]+(?:\.[0-9]+)?)", cleaned, re.IGNORECASE)
    if greater_match:
        try:
            return float(greater_match.group(1)), None
        except ValueError:
            pass

    return None, None


def evaluate_biomarker_status(
    value: Optional[float],
    ref_low: Optional[float],
    ref_high: Optional[float],
    unit: Optional[str] = "",
) -> Tuple[BiomarkerStatus, str]:
    """
    Strict deterministic evaluation of lab test status against source-provided reference ranges.
    Rule: Never invent reference ranges. If no range is in source, mark UNKNOWN.
    """
    if value is None:
        return BiomarkerStatus.UNKNOWN, "Observation has no numeric measurement."

    # If neither boundary exists, we strictly do NOT invent standard ranges
    if ref_low is None and ref_high is None:
        return (
            BiomarkerStatus.UNKNOWN,
            "Reference range not specified in source report. Range not invented.",
        )

    # Check lower boundary
    if ref_low is not None and value < ref_low:
        unit_str = f" {unit}" if unit else ""
        return (
            BiomarkerStatus.LOW,
            f"Observed value ({value}{unit_str}) is below source reference minimum ({ref_low}{unit_str}).",
        )

    # Check upper boundary
    if ref_high is not None and value > ref_high:
        unit_str = f" {unit}" if unit else ""
        return (
            BiomarkerStatus.HIGH,
            f"Observed value ({value}{unit_str}) exceeds source reference maximum ({ref_high}{unit_str}).",
        )

    # Within range
    low_str = str(ref_low) if ref_low is not None else "0"
    high_str = str(ref_high) if ref_high is not None else "∞"
    unit_str = f" {unit}" if unit else ""
    return (
        BiomarkerStatus.NORMAL,
        f"Observed value ({value}{unit_str}) is within source reference range ({low_str} - {high_str}{unit_str}).",
    )


def process_lab_item_ranges(item: LabTestItem) -> LabTestItem:
    """
    Enriches a LabTestItem by evaluating its status deterministically.
    """
    # If explicit bounds were missing but raw string exists, try parsing
    if item.ref_range_low is None and item.ref_range_high is None and item.raw_ref_range:
        parsed_low, parsed_high = parse_reference_range(item.raw_ref_range)
        item.ref_range_low = parsed_low
        item.ref_range_high = parsed_high

    status, note = evaluate_biomarker_status(
        value=item.value,
        ref_low=item.ref_range_low,
        ref_high=item.ref_range_high,
        unit=item.unit,
    )
    item.status = status
    item.clinical_flag_note = note
    return item

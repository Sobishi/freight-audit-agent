"""Load delivery evidence from supported Excel worksheets."""

from pathlib import Path

import pandas as pd


EVIDENCE_SHEETS = {
    "Internal Tracker": (
        "internal_tracker",
        {"Status"},
    ),
    "Carrier Tracking": (
        "carrier_tracking",
        {"Status", "Delivery Status"},
    ),
    "Alt POD": (
        "alt_pod",
        {"Status", "Last Scan Text"},
    ),
}


def _detect_header_row(preview, sheet_name, status_fields):
    candidates = []

    for index, row in preview.iterrows():
        values = [
            str(value).strip()
            for value in row.tolist()
            if pd.notna(value)
        ]

        columns = set(values)

        if "AWB" in columns and columns.intersection(status_fields):
            candidates.append(index)

    if not candidates:
        raise ValueError(
            f"Cannot identify delivery evidence headers: {sheet_name}"
        )

    if len(candidates) > 1:
        raise ValueError(
            f"Ambiguous delivery evidence headers: {sheet_name}"
        )

    return candidates[0]


def load_delivery_evidence_workbook(file_path):
    """Return normalized source names mapped to raw evidence DataFrames."""

    file_path = Path(file_path)

    if not file_path.is_file():
        raise FileNotFoundError(
            f"Delivery evidence file not found: {file_path}"
        )

    if file_path.suffix.lower() not in {".xlsx", ".xls"}:
        raise ValueError(
            "Unsupported delivery evidence format. Use Excel."
        )

    results = {}

    with pd.ExcelFile(file_path) as workbook:
        available = [
            sheet
            for sheet in EVIDENCE_SHEETS
            if sheet in workbook.sheet_names
        ]

        if not available:
            raise ValueError(
                "No recognized delivery evidence worksheets found."
            )

        for sheet in available:
            source_name, status_fields = EVIDENCE_SHEETS[sheet]

            preview = pd.read_excel(
                workbook,
                sheet_name=sheet,
                header=None,
                nrows=20,
                dtype=str,
            )

            header_row = _detect_header_row(
                preview,
                sheet,
                status_fields,
            )

            results[source_name] = pd.read_excel(
                workbook,
                sheet_name=sheet,
                header=header_row,
                dtype=str,
            )

    return results

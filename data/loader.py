from pathlib import Path
import pandas as pd
from data.schema import (
    identify_columns,
    normalize_columns,
    normalize_invoice_data,
    validate_required_columns,
    validate_invoice_data,
)

# Locate the main project directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Locate the Excel workbook
WORKBOOK_PATH = (
    PROJECT_ROOT / "sample_data" / "freight_audit_demo.xlsx"
)

# Worksheets required for freight auditing
REQUIRED_SHEETS = [
    "Invoice",
    "Config",
    "Rate Card",
    "Internal Tracker",
    "Carrier Tracking",
    "Alt POD",
    "Test Key",
    "Audit",
]


def load_workbook(file_path=WORKBOOK_PATH):
    """
    Load the required Excel worksheets into pandas DataFrames.
    """

    file_path = Path(file_path)

    # Check that the workbook exists
    if not file_path.exists():
        raise FileNotFoundError(
            f"Workbook not found: {file_path}"
        )

    # Open the Excel workbook
    workbook = pd.ExcelFile(file_path)

    # Check for missing worksheets
    missing_sheets = [
        sheet
        for sheet in REQUIRED_SHEETS
        if sheet not in workbook.sheet_names
    ]

    if missing_sheets:
        raise ValueError(
            f"Missing required worksheets: {missing_sheets}"
        )

    # Store each worksheet in a dictionary
    data = {}

    for sheet in REQUIRED_SHEETS:
        data[sheet] = pd.read_excel(
            workbook,
            sheet_name=sheet,
            header=3,
        )

    return data

def load_invoice(file_path, sheet_name=None, header_row=None):
    """
    Load an invoice from Excel or CSV.

    Automatically identifies the invoice worksheet and
    header row unless explicitly provided.
    """

    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(
            f"Invoice file not found: {file_path}"
        )

    extension = file_path.suffix.lower()

    if extension == ".csv":

        if header_row is None:
            header_row = detect_header_row(file_path)

        invoice = pd.read_csv(
            file_path,
            header=header_row,
            dtype=str,
        )

    elif extension in {".xlsx", ".xls"}:

        if sheet_name is None:
            sheet_name = detect_invoice_sheet(file_path)

        if header_row is None:
            header_row = detect_header_row(
                file_path,
                sheet_name=sheet_name,
            )

        invoice = pd.read_excel(
            file_path,
            sheet_name=sheet_name,
            header=header_row,
            dtype=str,
        )

    else:
        raise ValueError(
            f"Unsupported file format: {extension}"
        )

    # Confirm that the loaded invoice is a DataFrame.
    if not isinstance(invoice, pd.DataFrame):
        raise TypeError(
            "Expected a DataFrame when loading the invoice."
        )

    # Standardize recognized customer column names.
    invoice = normalize_columns(invoice)

    validate_required_columns(invoice, ["AWB"])

    validate_invoice_data(invoice)

    invoice = normalize_invoice_data(invoice)
    # Assign a unique identifier to each invoice line.
    invoice = invoice.reset_index(drop=True)

    invoice.insert(
        0,
        "Invoice Line ID",
        range(1, len(invoice) + 1),
    )
    return invoice

def detect_header_row(file_path, sheet_name=0, max_rows=20):
    """
    Detect the most likely invoice header row.
    Returns a zero-based row number.
    """

    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    extension = file_path.suffix.lower()

    if extension == ".csv":
        preview = pd.read_csv(
            file_path,
            header=None,
            nrows=max_rows,
        )

    elif extension in {".xlsx", ".xls"}:
        preview = pd.read_excel(
            file_path,
            sheet_name=sheet_name,
            header=None,
            nrows=max_rows,
        )

    else:
        raise ValueError(
            f"Unsupported file format: {extension}"
        )

    if not isinstance(preview, pd.DataFrame):
        raise TypeError(
            "Expected a DataFrame when reading invoice headers."
        )

    candidates = []
    ambiguous_headers = []

    for row_index, row in preview.iterrows():

        column_names = row.dropna().tolist()

        if not column_names:
            continue

        try:
            matches = identify_columns(column_names)

        except ValueError as error:
            ambiguous_headers.append(
                f"Row {row_index + 1}: {error}"
            )
            continue

        if "AWB" not in matches or len(matches) < 2:
            continue

        candidates.append({
            "row": row_index,
            "score": len(matches),
        })

    # Do not silently ignore conflicting header candidates.
    if ambiguous_headers:
        raise ValueError(
            "Ambiguous column mapping: "
            + "; ".join(ambiguous_headers)
        )

    if not candidates:
        raise ValueError(
            "Unable to identify an invoice header row. "
            "Please confirm the header location."
        )

    best_score = max(
        candidate["score"]
        for candidate in candidates
    )

    best_candidates = [
        candidate
        for candidate in candidates
        if candidate["score"] == best_score
    ]

    if len(best_candidates) > 1:
        raise ValueError(
            "Multiple possible invoice header rows detected. "
            "Please confirm the correct header."
        )

    return best_candidates[0]["row"]

def detect_invoice_sheet(file_path):
    """
    Identify the most likely invoice worksheet
    based on recognized invoice columns.

    Returns the worksheet name.

    Raises an error if no suitable worksheet is found
    or multiple worksheets are equally plausible.
    """

    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(
            f"Workbook not found: {file_path}"
        )

    if file_path.suffix.lower() not in {".xlsx", ".xls"}:
        raise ValueError(
            "Automatic worksheet detection requires an Excel file."
        )

    workbook = pd.ExcelFile(file_path)
    candidates = []

    for sheet_name in workbook.sheet_names:

        try:
            header_row = detect_header_row(
                file_path,
                sheet_name=sheet_name,
            )

            preview = pd.read_excel(
                workbook,
                sheet_name=sheet_name,
                header=header_row,
                nrows=5,
            )

            if not isinstance(preview, pd.DataFrame):
                raise TypeError(
                    "Expected a DataFrame when reading worksheet headers."
                )

            matches = identify_columns(preview.columns)

        except ValueError:
            # This sheet is not a valid invoice candidate.
            continue

        candidates.append({
            "sheet": sheet_name,
            "header_row": header_row,
            "score": len(matches),
        })

    if not candidates:
        raise ValueError(
            "Unable to identify an invoice worksheet. "
            "Please select the correct worksheet manually."
        )

    best_score = max(
        candidate["score"]
        for candidate in candidates
    )

    best_candidates = [
        candidate
        for candidate in candidates
        if candidate["score"] == best_score
    ]

    if len(best_candidates) > 1:
        raise ValueError(
            "Multiple possible invoice worksheets detected. "
            "Please select the correct worksheet manually."
        )

    return best_candidates[0]["sheet"]
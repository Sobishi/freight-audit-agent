from pathlib import Path

import pandas as pd


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


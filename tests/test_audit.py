import pandas as pd

from audit_engine.audit import detect_duplicates
from data.loader import load_workbook


def test_duplicate_detection():
    """
    Verify that repeated AWBs are correctly identified.
    """

    invoice = pd.DataFrame(
        {
            "Carrier": [
                "Carrier A",
                "Carrier A",
                "Carrier B",
                "Carrier A",
            ],
            "AWB": [
                "AWB001",
                "AWB002",
                "AWB003",
                "AWB001",
            ],
            "Total": [
                100.00,
                200.00,
                150.00,
                100.00,
            ],
        }
    )

    result = detect_duplicates(invoice)

    assert result["Occurrence"].tolist() == [1, 1, 1, 2]

    assert result["Is Duplicate"].tolist() == [
        False,
        False,
        False,
        True,
    ]


def test_duplicate_detection_matches_excel():
    """
    Compare Python occurrence calculations against
    all 1,240 records in the Excel workbook.
    """

    data = load_workbook()

    invoice = data["Invoice"]
    workbook_audit = data["Audit"]

    result = detect_duplicates(invoice)

    # Compare occurrence counts row by row.
    actual = result["Occurrence"].reset_index(drop=True)

    expected = workbook_audit["Occurrence"].reset_index(drop=True)

    assert len(actual) == 1240

    assert actual.equals(expected)


def test_duplicate_count():
    """
    Verify the expected number of duplicate billing lines.
    """

    data = load_workbook()

    invoice = data["Invoice"]

    result = detect_duplicates(invoice)

    duplicate_count = result["Is Duplicate"].sum()

    assert duplicate_count == 14
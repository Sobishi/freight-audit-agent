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

def test_generates_structured_duplicate_findings():
    """
    Repeated AWBs should produce structured findings
    with supporting invoice details.
    """

    import pandas as pd

    from audit_engine.audit import (
        detect_duplicates,
        generate_duplicate_findings,
    )

    invoice = pd.DataFrame({
        "AWB": ["ABC123", "XYZ456", "ABC123"],
        "Carrier": ["DHL", "FedEx", "DHL"],
        "Invoice Ref": ["INV001", "INV002", "INV003"],
        "Total": [15000, 22000, 15000],
    })

    audited = detect_duplicates(invoice)

    findings = generate_duplicate_findings(audited)

    assert len(findings) == 1

    finding = findings.iloc[0]

    assert finding["Finding Type"] == "Potential Duplicate Billing"
    assert finding["AWB"] == "ABC123"
    assert finding["Carrier"] == "DHL"
    assert finding["Invoice Ref"] == "INV003"
    assert finding["Occurrence"] == 2
    assert finding["Billed Amount"] == 15000
    assert finding["Potential Exposure"] == 15000
    assert finding["Status"] == "Requires Review"

def test_duplicate_financial_classification():
    import pandas as pd

    from audit_engine.audit import (
        detect_duplicates,
        generate_duplicate_findings,
    )

    invoice = pd.DataFrame({
        "AWB": ["ABC123", "ABC123", "ABC123", "ABC123"],
        "Carrier": ["DHL"] * 4,
        "Invoice Ref": ["INV001", "INV002", "INV003", "INV004"],
        "Total": [15000, 15000, -15000, 0],
    })

    audited = detect_duplicates(invoice)
    findings = generate_duplicate_findings(audited)

    assert len(findings) == 3

    assert findings["Classification"].tolist() == [
        "Potential Duplicate Charge",
        "Credit or Reversal",
        "Zero-Value Adjustment",
    ]

    assert findings["Potential Exposure"].tolist() == [
        15000,
        0,
        0,
    ]

def test_generate_audit_summary():
    import pandas as pd

    from audit_engine.audit import (
        detect_duplicates,
        generate_duplicate_findings,
        generate_audit_summary,
    )

    invoice = pd.DataFrame({
        "AWB": ["ABC123", "ABC123", "ABC123", "ABC123"],
        "Carrier": ["DHL"] * 4,
        "Invoice Ref": ["INV001", "INV002", "INV003", "INV004"],
        "Total": [15000, 15000, -15000, 0],
    })

    audited = detect_duplicates(invoice)
    findings = generate_duplicate_findings(audited)
    summary = generate_audit_summary(audited, findings)

    assert summary["Total Invoice Lines"] == 4
    assert summary["Total Findings"] == 3
    assert summary["Potential Duplicate Charges"] == 1
    assert summary["Credits or Reversals"] == 1
    assert summary["Zero-Value Adjustments"] == 1
    assert summary["Gross Potential Exposure"] == 15000.0

def test_detect_exact_duplicate_charges():
    import pandas as pd

    from audit_engine.audit import detect_exact_duplicate_charges

    invoice = pd.DataFrame({
        "AWB": [
            "ABC123",
            "ABC123",
            "ABC123",
            "ABC123",
            "XYZ456",
            "XYZ456",
        ],
        "Carrier": [
            "DHL",
            "dhl",
            "DHL",
            "DHL",
            "FedEx",
            "FedEx",
        ],
        "Total": [
            15000,
            15000,
            -15000,
            5000,
            20000,
            20000,
        ],
    })

    result = detect_exact_duplicate_charges(invoice)

    assert result["Is Exact Duplicate Charge"].tolist() == [
        False,
        True,
        False,
        False,
        False,
        True,
    ]

def test_investigation_priority():
    import pandas as pd

    from audit_engine.audit import (
        detect_duplicates,
        detect_exact_duplicate_charges,
        generate_duplicate_findings,
    )

    invoice = pd.DataFrame({
        "AWB": [
            "ABC123", "ABC123",
            "XYZ456", "XYZ456",
            "DEF789", "DEF789",
            "GHI012", "GHI012",
        ],
        "Carrier": ["DHL"] * 8,
        "Invoice Ref": [
            "INV001", "INV002",
            "INV003", "INV004",
            "INV005", "INV006",
            "INV007", "INV008",
        ],
        "Total": [
            15000, 15000,
            20000, 5000,
            10000, -10000,
            8000, 0,
        ],
    })

    audited = detect_duplicates(invoice)
    audited = detect_exact_duplicate_charges(audited)

    findings = generate_duplicate_findings(audited)

    priorities = dict(zip(
        findings["AWB"],
        findings["Priority"],
    ))

    assert priorities == {
        "ABC123": "High",
        "XYZ456": "Medium",
        "DEF789": "Review",
        "GHI012": "Low",
    }
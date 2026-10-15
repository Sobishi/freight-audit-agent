import pandas as pd
from audit_engine.rate_validation import validate_freight_rates
from reporting.excel_report import generate_excel_report
from audit_engine.audit import (
    detect_duplicates,
    generate_duplicate_findings,
    generate_audit_summary,
)

from reporting.excel_report import generate_excel_report


def test_generate_excel_report(tmp_path):

    invoice = pd.DataFrame({
        "AWB": ["ABC123", "XYZ456", "ABC123"],
        "Carrier": ["DHL", "FedEx", "DHL"],
        "Invoice Ref": ["INV001", "INV002", "INV003"],
        "Total": [15000, 22000, 15000],
    })

    audited = detect_duplicates(invoice)
    findings = generate_duplicate_findings(audited)
    summary = generate_audit_summary(audited, findings)

    output_file = tmp_path / "test_audit_report.xlsx"

    generate_excel_report(
        audited_invoice=audited,
        findings=findings,
        summary=summary,
        output_path=str(output_file),
    )

    assert output_file.exists()

    workbook = pd.ExcelFile(output_file)

    assert workbook.sheet_names == [
        "Audit Summary",
        "Audit Findings",
        "Invoice Data",
    ]

    summary_df = pd.read_excel(
        output_file,
        sheet_name="Audit Summary",
    )

    findings_df = pd.read_excel(
        output_file,
        sheet_name="Audit Findings",
    )

    invoice_df = pd.read_excel(
        output_file,
        sheet_name="Invoice Data",
    )
    # Validate the six financial summary metrics.
    expected_metrics = {
        "Total Invoice Lines",
        "Total Findings",
        "Potential Duplicate Charges",
        "Credits or Reversals",
        "Zero-Value Adjustments",
        "Gross Potential Exposure",
    }

    actual_metrics = set(summary_df["Metric"].dropna())

    assert expected_metrics.issubset(actual_metrics)
    assert "AUDIT DISCLAIMER" in summary_df["Metric"].values
    assert len(findings_df) == 1
    assert len(invoice_df) == 3

    assert findings_df.iloc[0]["AWB"] == "ABC123"

    assert (
        findings_df.iloc[0]["Classification"]
        == "Potential Duplicate Charge"
    )

    assert findings_df.iloc[0]["Potential Exposure"] == 15000

    exposure = summary_df.loc[
        summary_df["Metric"] == "Gross Potential Exposure",
        "Value",
    ].iloc[0]

    assert float(exposure) == 15000.0

def test_excel_report_includes_rate_validation(tmp_path):
    import pandas as pd

    from reporting.excel_report import generate_excel_report

    audited_invoice = pd.DataFrame({
        "AWB": ["ABC123"],
        "Carrier": ["DHL"],
        "Total": [15000],
    })

    findings = pd.DataFrame({
        "AWB": ["ABC123"],
        "Classification": ["Potential Duplicate Charge"],
        "Potential Exposure": [15000],
    })

    summary = {
        "Total Invoice Lines": 1,
        "Total Findings": 1,
        "Gross Potential Exposure": 15000,
    }

    rate_results = pd.DataFrame({
        "AWB": ["ABC123"],
        "Carrier": ["DHL"],
        "Invoice Ref": ["INV001"],
        "Service Type": ["Express"],
        "Total": [15000],
        "Agreed Rate": [12000],
        "Rate Difference": [3000],
        "Potential Rate Overcharge": [3000],
        "Rate Status": ["Potential Overcharge"],
    })

    output_path = tmp_path / "freight_audit_report.xlsx"

    generate_excel_report(
        audited_invoice=audited_invoice,
        findings=findings,
        summary=summary,
        output_path=str(output_path),
        rate_results=rate_results,
    )

    workbook = pd.ExcelFile(output_path)

    assert workbook.sheet_names == [
        "Audit Summary",
        "Audit Findings",
        "Invoice Data",
        "Rate Validation",
    ]

    rate_sheet = pd.read_excel(
        output_path,
        sheet_name="Rate Validation",
    )

    assert len(rate_sheet) == 1
    assert rate_sheet.loc[0, "AWB"] == "ABC123"
    assert rate_sheet.loc[0, "Agreed Rate"] == 12000
    assert rate_sheet.loc[0, "Potential Rate Overcharge"] == 3000
    assert rate_sheet.loc[0, "Rate Status"] == "Potential Overcharge"

def test_excel_report_includes_rate_summary_metrics(tmp_path):
    import pandas as pd

    from reporting.excel_report import generate_excel_report

    audited_invoice = pd.DataFrame({
        "AWB": ["ABC123", "XYZ456"],
        "Carrier": ["DHL", "FedEx"],
        "Total": [15000, 22000],
    })

    findings = pd.DataFrame({
        "AWB": ["ABC123"],
        "Classification": ["Potential Duplicate Charge"],
        "Potential Exposure": [15000],
    })

    summary = {
        "Total Invoice Lines": 2,
        "Total Findings": 1,
        "Gross Potential Exposure": 15000,
    }

    rate_results = pd.DataFrame({
        "AWB": ["ABC123", "XYZ456"],
        "Carrier": ["DHL", "FedEx"],
        "Total": [15000, 22000],
        "Agreed Rate": [12000, 18000],
        "Rate Difference": [3000, 4000],
        "Potential Rate Overcharge": [3000, 4000],
        "Rate Status": [
            "Potential Overcharge",
            "Potential Overcharge",
        ],
    })

    output_path = tmp_path / "combined_audit.xlsx"

    generate_excel_report(
        audited_invoice=audited_invoice,
        findings=findings,
        summary=summary,
        output_path=str(output_path),
        rate_results=rate_results,
    )

    report_summary = pd.read_excel(
        output_path,
        sheet_name="Audit Summary",
    )

    metrics = dict(zip(
        report_summary["Metric"],
        report_summary["Value"],
    ))

    assert metrics["Total Invoice Lines"] == 2
    assert metrics["Total Findings"] == 1
    assert metrics["Gross Potential Exposure"] == 15000

    assert metrics["Potential Rate Overcharges"] == 2
    assert metrics["Missing Contractual Rates"] == 0
    assert metrics["Gross Potential Rate Exposure"] == 7000

    # Generating the report must not modify the original summary.
    assert "Potential Rate Overcharges" not in summary

def test_excel_report_reconciliation_matches_summary(tmp_path):
    import pandas as pd

    from reporting.excel_report import generate_excel_report

    audited_invoice = pd.DataFrame({
        "Invoice Line ID": [1, 2, 3],
        "AWB": ["ABC123", "XYZ456", "ABC123"],
        "Carrier": ["DHL", "FedEx", "DHL"],
        "Invoice Ref": ["INV001", "INV002", "INV003"],
        "Total": [15000, 22000, 15000],
        "Is Exact Duplicate Charge": [False, False, True],
    })

    findings = pd.DataFrame({
        "AWB": ["ABC123"],
        "Classification": ["Potential Duplicate Charge"],
        "Potential Exposure": [15000],
    })

    summary = {
        "Total Invoice Lines": 3,
        "Total Findings": 1,
        "Gross Potential Exposure": 15000,
    }

    rate_results = pd.DataFrame({
        "Invoice Line ID": [1, 2, 3],
        "AWB": ["ABC123", "XYZ456", "ABC123"],
        "Carrier": ["DHL", "FedEx", "DHL"],
        "Total": [15000, 22000, 15000],
        "Agreed Rate": [12000, 18000, 12000],
        "Rate Difference": [3000, 4000, 3000],
        "Potential Rate Overcharge": [3000, 4000, 3000],
        "Rate Status": [
            "Potential Overcharge",
            "Potential Overcharge",
            "Potential Overcharge",
        ],
    })

    combined_exposure = pd.DataFrame({
        "Invoice Line ID": [1, 2, 3],
        "AWB": ["ABC123", "XYZ456", "ABC123"],
        "Carrier": ["DHL", "FedEx", "DHL"],
        "Invoice Ref": ["INV001", "INV002", "INV003"],
        "Total": [15000, 22000, 15000],
        "Is Exact Duplicate Charge": [False, False, True],
        "Duplicate Exposure": [0, 0, 15000],
        "Rate Exposure": [3000, 4000, 3000],
        "Combined Potential Exposure": [3000, 4000, 15000],
    })

    output_path = tmp_path / "reconciliation_report.xlsx"

    generate_excel_report(
        audited_invoice=audited_invoice,
        findings=findings,
        summary=summary,
        output_path=output_path,
        rate_results=rate_results,
        combined_exposure=combined_exposure,
    )

    report_summary = pd.read_excel(
        output_path,
        sheet_name="Audit Summary",
    )

    reconciliation = pd.read_excel(
        output_path,
        sheet_name="Exposure Reconciliation",
    )

    metrics = dict(zip(
        report_summary["Metric"],
        report_summary["Value"],
    ))

    assert len(reconciliation) == 3

    assert reconciliation["Invoice Line ID"].tolist() == [1, 2, 3]

    assert reconciliation["Combined Potential Exposure"].tolist() == [
        3000, 4000, 15000
    ]

    assert (
        reconciliation["Combined Potential Exposure"].sum()
        == metrics["Combined Potential Exposure"]
    )

    assert metrics["Combined Potential Exposure"] == 22000

def test_excel_report_counts_missing_rate_validation_information(tmp_path):
    invoice = pd.DataFrame({
        "Invoice Line ID": [1, 2, 3],
        "AWB": ["ABC123", "XYZ456", "DEF789"],
        "Carrier": [None, None, "DHL"],
        "Service Type": ["Express", "Express", "Express"],
        "Base Freight": [None, 15000, None],
        "Total": [15000, 18000, 20000],
    })

    rate_card = pd.DataFrame({
        "Carrier": ["DHL"],
        "Service Type": ["Express"],
        "Agreed Rate": [12000],
    })

    rate_results = validate_freight_rates(invoice, rate_card)

    summary = {
        "Total Invoice Lines": 3,
        "Total Findings": 0,
        "Potential Duplicate Charges": 0,
        "Credits or Reversals": 0,
        "Zero-Value Adjustments": 0,
        "Gross Potential Exposure": 0,
    }

    output_path = tmp_path / "rate_validation_report.xlsx"

    generate_excel_report(
        audited_invoice=invoice,
        findings=pd.DataFrame(),
        summary=summary,
        output_path=output_path,
        rate_results=rate_results,
    )

    report_summary = pd.read_excel(
        output_path,
        sheet_name="Audit Summary",
    )

    metrics = dict(
        zip(
            report_summary["Metric"],
            report_summary["Value"],
        )
    )

    assert metrics["Missing Invoice Information"] == 2
    assert metrics["Missing Base Freight"] == 2
    assert metrics["Missing Contractual Rates"] == 0
    assert metrics["Potential Rate Overcharges"] == 0
    assert metrics["Gross Potential Rate Exposure"] == 0
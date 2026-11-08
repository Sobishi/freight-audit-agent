"""R6 RED tests for optional surcharge Excel reporting."""

from decimal import Decimal

import pandas as pd
from openpyxl import load_workbook

from reporting.excel_report import generate_excel_report


def _inputs():
    invoice = pd.DataFrame({
        "Invoice Line ID": [1],
        "AWB": ["AWB-1"],
        "Carrier": ["Carrier A"],
        "Total": [115.00],
        "Surcharge Amount": [15.00],
    })

    findings = pd.DataFrame({
        "Classification": [],
    })

    summary = {
        "Invoice Lines": 1,
        "Gross Potential Exposure": 0.0,
    }

    surcharge_results = invoice.copy()
    surcharge_results["Surcharge Status"] = [
        "potential_overcharge"
    ]
    surcharge_results["Surcharge Reason"] = [
        "above_contract"
    ]
    surcharge_results["Expected Surcharge"] = [
        Decimal("10.00")
    ]
    surcharge_results["Potential Surcharge Overcharge"] = [
        Decimal("5.00")
    ]

    return invoice, findings, summary, surcharge_results


def test_surcharge_sheet_is_created_when_results_supplied(tmp_path):
    invoice, findings, summary, surcharge = _inputs()
    output = tmp_path / "audit.xlsx"

    generate_excel_report(
        invoice,
        findings,
        summary,
        str(output),
        surcharge_results=surcharge,
    )

    workbook = load_workbook(output, data_only=True)

    try:
        assert "Surcharge Validation" in workbook.sheetnames
        assert "Audit Summary" in workbook.sheetnames
        assert "Audit Findings" in workbook.sheetnames
        assert "Invoice Data" in workbook.sheetnames

        sheet = workbook["Surcharge Validation"]
        headers = [cell.value for cell in sheet[1]]

        assert "Invoice Line ID" in headers
        assert "Surcharge Status" in headers
        assert "Expected Surcharge" in headers
        assert "Potential Surcharge Overcharge" in headers

        row = dict(zip(
            headers,
            [cell.value for cell in sheet[2]],
        ))

        assert row["Invoice Line ID"] == 1
        assert row["Surcharge Status"] == "potential_overcharge"
        assert row["Expected Surcharge"] == 10
        assert row["Potential Surcharge Overcharge"] == 5
    finally:
        workbook.close()


def test_surcharge_sheet_absent_without_results(tmp_path):
    invoice, findings, summary, _ = _inputs()
    output = tmp_path / "audit.xlsx"

    generate_excel_report(
        invoice,
        findings,
        summary,
        str(output),
    )

    workbook = load_workbook(output, read_only=True)

    try:
        assert "Surcharge Validation" not in workbook.sheetnames
    finally:
        workbook.close()


def test_surcharge_results_do_not_modify_summary(tmp_path):
    invoice, findings, summary, surcharge = _inputs()
    original_summary = summary.copy()

    generate_excel_report(
        invoice,
        findings,
        summary,
        str(tmp_path / "audit.xlsx"),
        surcharge_results=surcharge,
    )

    assert summary == original_summary


def test_surcharge_results_do_not_modify_existing_exposure(tmp_path):
    invoice, findings, summary, surcharge = _inputs()

    combined = pd.DataFrame({
        "Invoice Line ID": [1],
        "AWB": ["AWB-1"],
        "Total": [115.00],
        "Combined Potential Exposure": [3.00],
        "Payment Treatment": ["Review"],
    })

    output = tmp_path / "audit.xlsx"

    generate_excel_report(
        invoice,
        findings,
        summary,
        str(output),
        combined_exposure=combined,
        surcharge_results=surcharge,
    )

    workbook = load_workbook(output, data_only=True)

    try:
        reconciliation = workbook["Exposure Reconciliation"]
        headers = [cell.value for cell in reconciliation[1]]

        exposure_column = headers.index(
            "Combined Potential Exposure"
        ) + 1

        assert reconciliation.cell(
            row=2,
            column=exposure_column,
        ).value == 3.00

        assert "Surcharge Validation" in workbook.sheetnames
    finally:
        workbook.close()

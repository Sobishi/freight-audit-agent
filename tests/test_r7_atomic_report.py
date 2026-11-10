"""R7 acceptance tests for safe Excel report generation."""

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from reporting.excel_report import generate_excel_report


def report_inputs():
    invoice = pd.DataFrame({
        "Invoice Line ID": [1],
        "AWB": ["TEST001"],
        "Carrier": ["Pilot Carrier"],
        "Total": [100.0],
    })

    findings = pd.DataFrame({
        "Classification": [],
    })

    summary = {
        "Invoice Lines": 1,
        "Gross Potential Exposure": 0.0,
    }

    return invoice, findings, summary


def test_failed_report_generation_preserves_existing_file(
    tmp_path,
):
    invoice, findings, summary = report_inputs()

    destination = tmp_path / "existing_report.xlsx"
    original = b"PREVIOUS_REPORT_SENTINEL"
    destination.write_bytes(original)

    with patch(
        "reporting.excel_report.format_excel_worksheet",
        side_effect=RuntimeError(
            "Simulated worksheet formatting failure"
        ),
    ):
        with pytest.raises(
            RuntimeError,
            match="Simulated worksheet formatting failure",
        ):
            generate_excel_report(
                invoice,
                findings,
                summary,
                str(destination),
            )

    assert destination.read_bytes() == original, (
        "Failed report generation overwrote an existing report."
    )

    assert sorted(
        path.name for path in tmp_path.iterdir()
    ) == ["existing_report.xlsx"], (
        "Failed report generation left temporary files behind."
    )


def test_successful_report_is_readable(
    tmp_path,
):
    invoice, findings, summary = report_inputs()

    destination = tmp_path / "audit_report.xlsx"

    returned = generate_excel_report(
        invoice,
        findings,
        summary,
        str(destination),
    )

    assert Path(returned) == destination

    workbook = pd.ExcelFile(destination)

    assert workbook.sheet_names == [
        "Audit Summary",
        "Audit Findings",
        "Invoice Data",
    ]

    exported = pd.read_excel(
        destination,
        sheet_name="Invoice Data",
    )

    assert len(exported) == 1
    assert exported.loc[0, "AWB"] == "TEST001"

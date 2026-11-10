"""R7.4F: Atomic report replacement failure tests."""

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
        "Total": [100.00],
    })

    findings = pd.DataFrame({"Classification": []})

    summary = {
        "Total Invoice Lines": 1,
        "Total Findings": 0,
    }

    return invoice, findings, summary


def generate(path):
    invoice, findings, summary = report_inputs()

    return generate_excel_report(
        audited_invoice=invoice,
        findings=findings,
        summary=summary,
        output_path=path,
    )


def test_failed_replacement_preserves_existing_report(tmp_path):
    output = tmp_path / "audit_report.xlsx"
    original = b"EXISTING_REPORT_SENTINEL"
    output.write_bytes(original)

    with patch(
        "reporting.excel_report.os.replace",
        side_effect=PermissionError("Simulated replacement failure"),
    ) as mocked_replace:

        with pytest.raises(
            PermissionError,
            match="Simulated replacement failure",
        ):
            generate(output)

    mocked_replace.assert_called_once()

    assert output.read_bytes() == original

    assert sorted(tmp_path.iterdir()) == [output]


def test_failed_replacement_does_not_create_final_report(tmp_path):
    output = tmp_path / "audit_report.xlsx"

    with patch(
        "reporting.excel_report.os.replace",
        side_effect=OSError("Simulated filesystem failure"),
    ) as mocked_replace:

        with pytest.raises(
            OSError,
            match="Simulated filesystem failure",
        ):
            generate(output)

    mocked_replace.assert_called_once()

    assert not output.exists()
    assert list(tmp_path.iterdir()) == []

"""R6 integration tests for surcharge evidence in the CLI."""

import subprocess
import sys

import pandas as pd
from openpyxl import load_workbook


def _invoice(tmp_path):
    path = tmp_path / "invoice.csv"

    pd.DataFrame({
        "AWB": ["AWB-101", "AWB-102"],
        "Carrier": ["Carrier A", "Carrier A"],
        "Total": [115.0, 108.0],
        "Base Freight": [100.0, 100.0],
        "Surcharge Amount": [15.0, 8.0],
    }).to_csv(path, index=False)

    return path


def _evidence(tmp_path, *, unknown=False):
    path = tmp_path / "surcharge_evidence.csv"

    pd.DataFrame({
        "Invoice Line ID": [999 if unknown else 1, 2],
        "Applicable": [True, False],
        "Basis": ["fixed", None],
        "Rate": [10.0, None],
    }).to_csv(path, index=False)

    return path


def _run_cli(invoice, output, *extra):
    return subprocess.run(
        [
            sys.executable,
            "main.py",
            str(invoice),
            "--output",
            str(output),
            *map(str, extra),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_creates_surcharge_validation_sheet(tmp_path):
    invoice = _invoice(tmp_path)
    evidence = _evidence(tmp_path)
    output = tmp_path / "audit.xlsx"

    result = _run_cli(
        invoice,
        output,
        "--surcharge-evidence",
        evidence,
    )

    assert result.returncode == 0, result.stderr
    assert output.is_file()

    workbook = load_workbook(output, data_only=True)

    try:
        assert "Surcharge Validation" in workbook.sheetnames

        sheet = workbook["Surcharge Validation"]
        headers = [cell.value for cell in sheet[1]]

        rows = [
            dict(zip(headers, values))
            for values in sheet.iter_rows(
                min_row=2,
                values_only=True,
            )
        ]

        assert len(rows) == 2

        assert rows[0]["Surcharge Status"] == (
            "potential_overcharge"
        )
        assert rows[0]["Potential Surcharge Overcharge"] == 5

        assert rows[1]["Surcharge Status"] == (
            "potential_overcharge"
        )
        assert rows[1]["Potential Surcharge Overcharge"] == 8
    finally:
        workbook.close()


def test_cli_rejects_unknown_surcharge_evidence_id(tmp_path):
    invoice = _invoice(tmp_path)
    evidence = _evidence(tmp_path, unknown=True)
    output = tmp_path / "audit.xlsx"

    result = _run_cli(
        invoice,
        output,
        "--surcharge-evidence",
        evidence,
    )

    assert result.returncode != 0
    assert "unknown" in (
        result.stdout + result.stderr
    ).lower()

    assert not output.exists()


def test_cli_without_surcharge_evidence_remains_compatible(tmp_path):
    invoice = _invoice(tmp_path)
    output = tmp_path / "audit.xlsx"

    result = _run_cli(invoice, output)

    assert result.returncode == 0, result.stderr

    workbook = load_workbook(output, read_only=True)

    try:
        assert "Surcharge Validation" not in workbook.sheetnames
        assert "Audit Summary" in workbook.sheetnames
        assert "Invoice Data" in workbook.sheetnames
    finally:
        workbook.close()


def test_cli_rejects_missing_surcharge_evidence_file(tmp_path):
    invoice = _invoice(tmp_path)
    output = tmp_path / "audit.xlsx"

    result = _run_cli(
        invoice,
        output,
        "--surcharge-evidence",
        tmp_path / "missing.csv",
    )

    assert result.returncode != 0
    assert "surcharge" in (
        result.stdout + result.stderr
    ).lower()
    assert not output.exists()


def test_cli_partial_surcharge_evidence_requires_review(tmp_path):
    invoice = _invoice(tmp_path)
    evidence = tmp_path / "partial_evidence.csv"
    output = tmp_path / "audit.xlsx"

    pd.DataFrame({
        "Invoice Line ID": [1],
        "Applicable": [True],
        "Basis": ["fixed"],
        "Rate": [10.0],
    }).to_csv(evidence, index=False)

    result = _run_cli(
        invoice,
        output,
        "--surcharge-evidence",
        evidence,
    )

    assert result.returncode == 0, result.stderr

    workbook = load_workbook(output, data_only=True)

    try:
        sheet = workbook["Surcharge Validation"]
        headers = [cell.value for cell in sheet[1]]

        rows = [
            dict(zip(headers, values))
            for values in sheet.iter_rows(
                min_row=2,
                values_only=True,
            )
        ]

        assert rows[0]["Surcharge Status"] == (
            "potential_overcharge"
        )

        assert rows[1]["Surcharge Status"] == "review"
        assert rows[1]["Potential Surcharge Overcharge"] is None
    finally:
        workbook.close()


def test_cli_rejects_unsupported_surcharge_format(tmp_path):
    invoice = _invoice(tmp_path)
    evidence = tmp_path / "evidence.json"
    evidence.write_text("{}", encoding="utf-8")
    output = tmp_path / "audit.xlsx"

    result = _run_cli(
        invoice,
        output,
        "--surcharge-evidence",
        evidence,
    )

    assert result.returncode != 0
    assert "unsupported surcharge evidence format" in (
        result.stdout + result.stderr
    ).lower()
    assert not output.exists()


def test_cli_surcharge_validation_preserves_credit_reversals(tmp_path):
    invoice = tmp_path / "credit_invoice.csv"
    evidence = tmp_path / "credit_evidence.csv"
    output = tmp_path / "audit.xlsx"

    pd.DataFrame({
        "AWB": ["AWB-101", "AWB-101"],
        "Carrier": ["Carrier A", "Carrier A"],
        "Invoice Ref": ["INV-001", "INV-001"],
        "Charge Type": ["FREIGHT", "FREIGHT"],
        "Currency": ["USD", "USD"],
        "Base Freight": [100.0, -100.0],
        "Surcharge Amount": [15.0, -15.0],
        "Tax Amount": [0.0, 0.0],
        "Total": [115.0, -115.0],
    }).to_csv(invoice, index=False)

    pd.DataFrame({
        "Invoice Line ID": [1, 2],
        "Applicable": [True, True],
        "Basis": ["fixed", "fixed"],
        "Rate": [10.0, 10.0],
    }).to_csv(evidence, index=False)

    result = _run_cli(
        invoice,
        output,
        "--surcharge-evidence",
        evidence,
    )

    assert result.returncode == 0, result.stderr

    workbook = load_workbook(output, data_only=True)

    try:
        sheet = workbook["Surcharge Validation"]
        headers = [cell.value for cell in sheet[1]]

        rows = [
            dict(zip(headers, values))
            for values in sheet.iter_rows(
                min_row=2,
                values_only=True,
            )
        ]

        assert len(rows) == 2

        for row in rows:
            assert row["Surcharge Status"] == "not_assessed"
            assert row["Surcharge Reason"] == "matched_full_reversal"
            assert row["Potential Surcharge Overcharge"] == 0

    finally:
        workbook.close()

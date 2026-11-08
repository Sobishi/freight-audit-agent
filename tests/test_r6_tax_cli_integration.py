"""R6 TAX-01 end-to-end CLI integration tests."""

import json
import subprocess
import sys

import pandas as pd
import pytest
from openpyxl import load_workbook


def _invoice(tmp_path):
    path = tmp_path / "invoice.csv"

    pd.DataFrame({
        "AWB": ["AWB-101", "AWB-102"],
        "Carrier": ["Carrier A", "Carrier A"],
        "Base Freight": [100.0, 100.0],
        "Tax Amount": [10.0, 0.0],
        "Total": [110.0, 100.0],
    }).to_csv(path, index=False)

    return path


def _evidence(tmp_path, *, unknown=False, partial=False):
    path = tmp_path / "tax_evidence.csv"

    records = [{
        "Invoice Line ID": 999 if unknown else 1,
        "Applicable": "TRUE",
        "Taxable Base": "100",
        "Tax Rate": "0.075",
        "Tax Inclusive": "FALSE",
        "Rounding Increment": "0.01",
    }]

    if not partial:
        records.append({
            "Invoice Line ID": 2,
            "Applicable": "FALSE",
            "Taxable Base": "",
            "Tax Rate": "",
            "Tax Inclusive": "",
            "Rounding Increment": "",
        })

    pd.DataFrame(records).to_csv(path, index=False)

    return path


def _run_cli(invoice, output, *extra):
    return subprocess.run(
        [
            sys.executable,
            "main.py",
            str(invoice),
            "--output",
            str(output),
            "--log-dir",
            str(output.parent / "logs"),
            *map(str, extra),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def _sheet_rows(path, sheet_name):
    workbook = load_workbook(path, data_only=True)

    try:
        sheet = workbook[sheet_name]
        headers = [cell.value for cell in sheet[1]]

        return [
            dict(zip(headers, values))
            for values in sheet.iter_rows(
                min_row=2,
                values_only=True,
            )
        ]
    finally:
        workbook.close()


def test_cli_generates_tax_validation_results(tmp_path):
    invoice = _invoice(tmp_path)
    evidence = _evidence(tmp_path)
    output = tmp_path / "audit.xlsx"

    result = _run_cli(
        invoice,
        output,
        "--tax-evidence",
        evidence,
    )

    assert result.returncode == 0, (
        result.stdout + result.stderr
    )
    assert output.is_file()
    assert "TAX VALIDATION" in result.stdout

    rows = _sheet_rows(output, "Tax Validation")

    assert len(rows) == 2

    assert rows[0]["Tax Status"] == "potential_overcharge"
    assert rows[0]["Expected Tax"] == 7.5
    assert rows[0]["Potential Tax Overcharge"] == 2.5

    assert rows[1]["Tax Status"] == "matched"
    assert rows[1]["Expected Tax"] == 0
    assert rows[1]["Potential Tax Overcharge"] == 0


def test_cli_partial_tax_evidence_requires_review(tmp_path):
    invoice = _invoice(tmp_path)
    evidence = _evidence(tmp_path, partial=True)
    output = tmp_path / "audit.xlsx"

    result = _run_cli(
        invoice,
        output,
        "--tax-evidence",
        evidence,
    )

    assert result.returncode == 0, result.stderr

    rows = _sheet_rows(output, "Tax Validation")

    assert rows[0]["Tax Status"] == "potential_overcharge"
    assert rows[1]["Tax Status"] == "review"
    assert rows[1]["Tax Reason"] == "missing_applicability"
    assert rows[1]["Potential Tax Overcharge"] is None


def test_cli_rejects_unknown_tax_evidence_id(tmp_path):
    invoice = _invoice(tmp_path)
    evidence = _evidence(tmp_path, unknown=True)
    output = tmp_path / "audit.xlsx"

    result = _run_cli(
        invoice,
        output,
        "--tax-evidence",
        evidence,
    )

    assert result.returncode != 0
    assert "unknown" in (
        result.stdout + result.stderr
    ).lower()
    assert not output.exists()


def test_cli_without_tax_evidence_remains_compatible(tmp_path):
    invoice = _invoice(tmp_path)
    output = tmp_path / "audit.xlsx"

    result = _run_cli(invoice, output)

    assert result.returncode == 0, result.stderr

    workbook = load_workbook(output, read_only=True)

    try:
        assert "Tax Validation" not in workbook.sheetnames
        assert "Audit Summary" in workbook.sheetnames
        assert "Invoice Data" in workbook.sheetnames
    finally:
        workbook.close()


def test_cli_rejects_missing_tax_evidence_file(tmp_path):
    invoice = _invoice(tmp_path)
    output = tmp_path / "audit.xlsx"

    result = _run_cli(
        invoice,
        output,
        "--tax-evidence",
        tmp_path / "missing.csv",
    )

    assert result.returncode != 0
    assert "tax evidence" in (
        result.stdout + result.stderr
    ).lower()
    assert not output.exists()


def test_cli_rejects_unsupported_tax_format(tmp_path):
    invoice = _invoice(tmp_path)
    evidence = tmp_path / "tax.json"
    evidence.write_text("{}", encoding="utf-8")
    output = tmp_path / "audit.xlsx"

    result = _run_cli(
        invoice,
        output,
        "--tax-evidence",
        evidence,
    )

    assert result.returncode != 0
    assert "unsupported tax evidence format" in (
        result.stdout + result.stderr
    ).lower()
    assert not output.exists()


def test_cli_rejects_contradictory_tax_evidence(tmp_path):
    invoice = _invoice(tmp_path)
    evidence = _evidence(tmp_path)
    output = tmp_path / "audit.xlsx"

    frame = pd.read_csv(evidence)
    frame.loc[1, "Tax Rate"] = 0.075
    frame.to_csv(evidence, index=False)

    result = _run_cli(
        invoice,
        output,
        "--tax-evidence",
        evidence,
    )

    assert result.returncode != 0
    assert "contradictory" in (
        result.stdout + result.stderr
    ).lower()
    assert not output.exists()


def test_cli_tax_preserves_matched_full_reversals(tmp_path):
    invoice = tmp_path / "credit_invoice.csv"
    evidence = tmp_path / "credit_tax.csv"
    output = tmp_path / "audit.xlsx"

    pd.DataFrame({
        "AWB": ["AWB-101", "AWB-101"],
        "Carrier": ["Carrier A", "Carrier A"],
        "Invoice Ref": ["INV-001", "INV-001"],
        "Charge Type": ["FREIGHT", "FREIGHT"],
        "Currency": ["USD", "USD"],
        "Base Freight": [100.0, -100.0],
        "Surcharge Amount": [0.0, 0.0],
        "Tax Amount": [7.5, -7.5],
        "Total": [107.5, -107.5],
    }).to_csv(invoice, index=False)

    pd.DataFrame({
        "Invoice Line ID": [1, 2],
        "Applicable": ["TRUE", "TRUE"],
        "Taxable Base": ["100", "100"],
        "Tax Rate": ["0.075", "0.075"],
        "Tax Inclusive": ["FALSE", "FALSE"],
        "Rounding Increment": ["0.01", "0.01"],
    }).to_csv(evidence, index=False)

    result = _run_cli(
        invoice,
        output,
        "--tax-evidence",
        evidence,
    )

    assert result.returncode == 0, (
        result.stdout + result.stderr
    )

    rows = _sheet_rows(output, "Tax Validation")
    assert len(rows) == 2

    for row in rows:
        assert row["Tax Status"] == "not_assessed"
        assert row["Tax Reason"] == "matched_full_reversal"
        assert row["Potential Tax Overcharge"] == 0


def test_cli_records_tax_validation_in_run_log(tmp_path):
    invoice = _invoice(tmp_path)
    evidence = _evidence(tmp_path)
    output = tmp_path / "audit.xlsx"

    result = _run_cli(
        invoice,
        output,
        "--tax-evidence",
        evidence,
    )

    assert result.returncode == 0, result.stderr

    logs = list((tmp_path / "logs").glob("*.json"))
    assert logs, "Expected an audit run JSON record."

    records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in logs
    ]

    assert any(
        record.get("settings", {}).get(
            "tax_validation_enabled"
        ) is True
        and record.get("summary", {}).get(
            "tax_status_counts"
        ) == {
            "potential_overcharge": 1,
            "matched": 1,
        }
        for record in records
    )

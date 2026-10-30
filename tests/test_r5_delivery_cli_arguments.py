"""R5 delivery evidence CLI argument validation."""

import subprocess
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*arguments):
    return subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "main.py"),
            *map(str, arguments),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )


def make_invoice(tmp_path):
    path = tmp_path / "invoice.csv"

    pd.DataFrame([
        {
            "AWB": "NBX600",
            "Carrier": "Northbridge Express",
            "Total": 150.0,
        }
    ]).to_csv(path, index=False)

    return path


def test_cli_rejects_missing_delivery_evidence_file(tmp_path):
    invoice_path = make_invoice(tmp_path)
    missing_path = tmp_path / "missing_evidence.xlsx"

    result = run_cli(
        invoice_path,
        "--delivery-evidence",
        missing_path,
    )

    assert result.returncode != 0
    assert "Delivery evidence file not found" in result.stderr


def test_cli_accepts_delivery_evidence_argument(tmp_path):
    invoice_path = make_invoice(tmp_path)
    evidence_path = tmp_path / "evidence.xlsx"

    with pd.ExcelWriter(evidence_path) as writer:
        pd.DataFrame([
            {
                "AWB": "NBX600",
                "Carrier": "Northbridge Express",
                "Status": "Delivered",
                "Delivery Status": "Delivered",
            }
        ]).to_excel(
            writer,
            sheet_name="Carrier Tracking",
            index=False,
        )

    report_path = tmp_path / "delivery_audit.xlsx"

    result = run_cli(
        invoice_path,
        "--delivery-evidence",
        evidence_path,
        "--output",
        report_path,
        "--log-dir",
        tmp_path / "logs",
    )

    assert result.returncode == 0, (
        result.stdout + "\n" + result.stderr
    )

    assert report_path.exists()
    assert "DELIVERY EVIDENCE" in result.stdout


def test_cli_rejects_workbook_without_delivery_sheets(tmp_path):
    invoice_path = make_invoice(tmp_path)
    evidence_path = tmp_path / "unrelated.xlsx"

    with pd.ExcelWriter(evidence_path) as writer:
        pd.DataFrame([
            {"AWB": "NBX600", "Status": "Delivered"}
        ]).to_excel(
            writer,
            sheet_name="Unrelated Data",
            index=False,
        )

    result = run_cli(
        invoice_path,
        "--delivery-evidence",
        evidence_path,
        "--log-dir",
        tmp_path / "logs",
    )

    assert result.returncode != 0
    assert (
        "No recognized delivery evidence worksheets found"
        in result.stderr
    )


def test_cli_rejects_unsupported_delivery_evidence_format(tmp_path):
    invoice_path = make_invoice(tmp_path)
    evidence_path = tmp_path / "evidence.csv"

    pd.DataFrame([
        {"AWB": "NBX600", "Status": "Delivered"}
    ]).to_csv(evidence_path, index=False)

    result = run_cli(
        invoice_path,
        "--delivery-evidence",
        evidence_path,
    )

    assert result.returncode != 0
    assert "Unsupported delivery evidence format" in result.stderr


def test_cli_rejects_corrupt_excel_evidence(tmp_path):
    invoice_path = make_invoice(tmp_path)
    evidence_path = tmp_path / "corrupt.xlsx"

    evidence_path.write_text("This is not an Excel workbook.")

    result = run_cli(
        invoice_path,
        "--delivery-evidence",
        evidence_path,
        "--log-dir",
        tmp_path / "logs",
    )

    assert result.returncode != 0
    assert "Error loading delivery evidence" in result.stderr

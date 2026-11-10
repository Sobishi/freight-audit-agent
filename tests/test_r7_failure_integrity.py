"""R7 failure handling and output integrity acceptance tests."""

import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAIN = PROJECT_ROOT / "main.py"


def run_cli(*arguments):
    return subprocess.run(
        [
            sys.executable,
            str(MAIN),
            *map(str, arguments),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


@pytest.mark.parametrize(
    "filename",
    [
        "missing_invoice.csv",
        "missing_invoice.xlsx",
    ],
)
def test_missing_invoice_fails_without_creating_report(
    tmp_path,
    filename,
):
    missing_invoice = tmp_path / filename
    report = tmp_path / "audit_report.xlsx"

    result = run_cli(
        missing_invoice,
        "--output",
        report,
        "--log-dir",
        tmp_path / "logs",
    )

    assert result.returncode != 0

    assert not report.exists(), (
        "A failed audit must not create an Excel report."
    )

    combined_output = (
        result.stdout + result.stderr
    ).lower()

    assert (
        "not found" in combined_output
        or "no such file" in combined_output
    ), combined_output


def test_missing_invoice_does_not_overwrite_existing_report(
    tmp_path,
):
    missing_invoice = tmp_path / "missing.csv"
    report = tmp_path / "existing_report.xlsx"

    original_content = b"PREVIOUS_VALID_REPORT_SENTINEL"
    report.write_bytes(original_content)

    result = run_cli(
        missing_invoice,
        "--output",
        report,
        "--log-dir",
        tmp_path / "logs",
    )

    assert result.returncode != 0

    assert report.read_bytes() == original_content, (
        "A failed audit changed an existing report."
    )

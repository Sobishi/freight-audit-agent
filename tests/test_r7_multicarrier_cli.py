"""R7 end-to-end acceptance tests for configured carriers."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from openpyxl import load_workbook


CASES = [
    ("corvant", "corvant_invoice.csv"),
    ("northbridge_express", "northbridge_express_invoice.csv"),
    ("swiftline", "swiftline_invoice.csv"),
]


@pytest.fixture(params=CASES, ids=[case[0] for case in CASES])
def pilot_run(request, tmp_path):
    carrier, filename = request.param

    invoice = (
        Path("tests/fixtures/carriers") / filename
    ).resolve()

    output = tmp_path / "audit.xlsx"
    logs = tmp_path / "logs"

    command = [
        sys.executable,
        "main.py",
        str(invoice),
        "--carrier",
        carrier,
        "--output",
        str(output),
        "--log-dir",
        str(logs),
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=60,
    )

    return {
        "carrier": carrier,
        "result": result,
        "output": output,
        "logs": logs,
    }


def test_pilot_cli_succeeds(pilot_run):
    result = pilot_run["result"]

    assert result.returncode == 0, (
        result.stdout + "\n" + result.stderr
    )

    assert pilot_run["output"].is_file()


def test_pilot_excel_preserves_all_decision_lines(pilot_run):
    assert pilot_run["result"].returncode == 0

    workbook = load_workbook(
        pilot_run["output"],
        read_only=True,
        data_only=True,
    )

    try:
        assert "Final Payment Decisions" in workbook.sheetnames

        rows = list(
            workbook["Final Payment Decisions"].values
        )

        assert len(rows) == 4

        headers = list(rows[0])
        records = [
            dict(zip(headers, row))
            for row in rows[1:]
        ]

        assert [
            record["Invoice Line ID"]
            for record in records
        ] == [1, 2, 3]

        assert all(
            record["Decision Completeness"] == "Partial"
            for record in records
        )

    finally:
        workbook.close()


def test_pilot_json_matches_excel_counts(pilot_run):
    assert pilot_run["result"].returncode == 0

    log_files = list(
        pilot_run["logs"].glob("audit_*.json")
    )

    assert len(log_files) == 1

    log = json.loads(
        log_files[0].read_text(encoding="utf-8")
    )

    assert log["status"] == "succeeded"

    summary = log["summary"]

    assert summary["final_payment_treatment_counts"] == {
        "Proceed": 3
    }

    assert summary["final_decision_completeness_counts"] == {
        "Partial": 3
    }


def test_pilot_warns_that_validation_is_incomplete(pilot_run):
    assert pilot_run["result"].returncode == 0

    assert (
        "INCOMPLETE VALIDATION"
        in pilot_run["result"].stdout
    )

"""R6 final payment decisions: end-to-end CLI integration."""

import json
import subprocess
import sys

import pandas as pd
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


def _run_cli(tmp_path, *extra):
    invoice = _invoice(tmp_path)
    output = tmp_path / "audit.xlsx"
    log_dir = tmp_path / "logs"

    result = subprocess.run(
        [
            sys.executable,
            "main.py",
            str(invoice),
            "--output",
            str(output),
            "--log-dir",
            str(log_dir),
            *map(str, extra),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        result.stdout + result.stderr
    )

    return result, output, log_dir


def _decision_rows(output):
    workbook = load_workbook(output, data_only=True)

    try:
        sheet = workbook["Final Payment Decisions"]
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


def _summary(log_dir):
    files = list(log_dir.glob("audit_*.json"))

    assert len(files) == 1

    record = json.loads(
        files[0].read_text(encoding="utf-8")
    )

    assert record["status"] == "succeeded"

    return record["summary"]


def test_cli_creates_decisions_without_rate_card(tmp_path):
    result, output, _ = _run_cli(tmp_path)

    assert output.is_file()

    rows = _decision_rows(output)

    assert len(rows) == 2
    assert [row["Invoice Line ID"] for row in rows] == [1, 2]
    assert all(
        row["Final Payment Treatment"] is not None
        for row in rows
    )


def test_cli_preserves_partial_validation_status(tmp_path):
    _, output, _ = _run_cli(tmp_path)

    rows = _decision_rows(output)

    assert all(
        row["Decision Completeness"] == "Partial"
        for row in rows
    )

    assert all(
        row["Tax Check"] == "Not Run"
        for row in rows
    )


def test_cli_summary_contains_final_treatment_counts(tmp_path):
    _, output, log_dir = _run_cli(tmp_path)

    rows = _decision_rows(output)
    summary = _summary(log_dir)

    expected = pd.Series(
        [row["Final Payment Treatment"] for row in rows]
    ).value_counts().to_dict()

    assert summary["final_payment_treatment_counts"] == expected
    assert sum(
        summary["final_payment_treatment_counts"].values()
    ) == len(rows)


def test_cli_summary_contains_completeness_counts(tmp_path):
    _, output, log_dir = _run_cli(tmp_path)

    rows = _decision_rows(output)
    summary = _summary(log_dir)

    expected = pd.Series(
        [row["Decision Completeness"] for row in rows]
    ).value_counts().to_dict()

    assert summary["final_decision_completeness_counts"] == expected


def test_cli_preserves_legacy_held_lines_semantics(tmp_path):
    _, _, log_dir = _run_cli(tmp_path)

    summary = _summary(log_dir)

    # Legacy exposure reconciliation was not executed.
    assert summary["held_lines"] is None

    # Final decisions have their own independent counts.
    assert "final_payment_treatment_counts" in summary


def test_cli_displays_final_decision_summary(tmp_path):
    result, _, _ = _run_cli(tmp_path)

    assert "FINAL PAYMENT DECISIONS" in result.stdout
    assert "Partial" in result.stdout


def test_cli_warns_partial_decisions_are_not_approval(tmp_path):
    result, _, _ = _run_cli(tmp_path)

    assert "INCOMPLETE VALIDATION" in result.stdout
    assert "NOT PAYMENT APPROVAL" in result.stdout


def test_cli_with_tax_evidence_passes_tax_findings_to_decisions(
    tmp_path,
):
    evidence = tmp_path / "tax_evidence.csv"

    pd.DataFrame({
        "Invoice Line ID": [1, 2],
        "Applicable": ["TRUE", "FALSE"],
        "Taxable Base": ["100", ""],
        "Tax Rate": ["0.075", ""],
        "Tax Inclusive": ["FALSE", ""],
        "Rounding Increment": ["0.01", ""],
    }).to_csv(evidence, index=False)

    _, output, log_dir = _run_cli(
        tmp_path,
        "--tax-evidence",
        evidence,
    )

    rows = _decision_rows(output)

    assert rows[0]["Tax Check"] == "potential_overcharge"
    assert rows[0]["Final Payment Treatment"] == "Hold"
    assert rows[1]["Tax Check"] == "matched"

    summary = _summary(log_dir)
    assert summary["final_payment_treatment_counts"]["Hold"] >= 1

"""R6 final payment decision Excel reporting integration."""

from pathlib import Path

import pandas as pd
import pytest
from openpyxl import load_workbook

from audit_engine.exposure import finalize_payment_decisions
from reporting.excel_report import generate_excel_report


def invoice():
    return pd.DataFrame({
        "Invoice Line ID": [1, 2],
        "AWB": ["AWB001", "AWB002"],
        "Total": [100.0, 200.0],
        "Is Exact Duplicate Charge": [False, False],
        "Needs Charge Review": [False, True],
        "Credit Match Status": ["Not a Credit", "Not a Credit"],
        "Excluded From Exposure": [False, False],
    })


def decisions():
    return finalize_payment_decisions(invoice())


def make_report(tmp_path, *, final_decisions):
    output = tmp_path / "audit.xlsx"

    generate_excel_report(
        invoice(),
        pd.DataFrame(),
        {"Invoice Lines": 2},
        str(output),
        final_payment_decisions=final_decisions,
    )

    return output


def test_report_accepts_final_payment_decisions(tmp_path):
    output = make_report(
        tmp_path,
        final_decisions=decisions(),
    )

    assert output.is_file()


def test_report_contains_final_payment_decisions_sheet(tmp_path):
    output = make_report(
        tmp_path,
        final_decisions=decisions(),
    )

    workbook = load_workbook(output, read_only=True)

    try:
        assert "Final Payment Decisions" in workbook.sheetnames
    finally:
        workbook.close()


def test_final_decision_sheet_preserves_line_ids_and_treatments(tmp_path):
    output = make_report(
        tmp_path,
        final_decisions=decisions(),
    )

    result = pd.read_excel(
        output,
        sheet_name="Final Payment Decisions",
    )

    assert result["Invoice Line ID"].tolist() == [1, 2]
    assert result["Final Payment Treatment"].tolist() == [
        "Proceed",
        "Hold",
    ]


def test_final_decision_sheet_shows_partial_validation(tmp_path):
    output = make_report(
        tmp_path,
        final_decisions=decisions(),
    )

    result = pd.read_excel(
        output,
        sheet_name="Final Payment Decisions",
    )

    assert result["Decision Completeness"].tolist() == [
        "Partial",
        "Partial",
    ]

    assert result["Tax Check"].tolist() == [
        "Not Run",
        "Not Run",
    ]


def test_existing_core_sheets_remain_available(tmp_path):
    output = make_report(
        tmp_path,
        final_decisions=decisions(),
    )

    workbook = load_workbook(output, read_only=True)

    try:
        assert {
            "Audit Summary",
            "Audit Findings",
            "Invoice Data",
        }.issubset(set(workbook.sheetnames))
    finally:
        workbook.close()


def test_report_rejects_mismatched_decision_line_ids(tmp_path):
    invalid = decisions().copy()
    invalid.loc[1, "Invoice Line ID"] = 999

    with pytest.raises(ValueError, match="Invoice Line ID"):
        make_report(
            tmp_path,
            final_decisions=invalid,
        )


def test_report_rejects_duplicate_decision_line_ids(tmp_path):
    invalid = decisions().copy()
    invalid.loc[1, "Invoice Line ID"] = 1

    with pytest.raises(ValueError, match="Invoice Line ID"):
        make_report(
            tmp_path,
            final_decisions=invalid,
        )

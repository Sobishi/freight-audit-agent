"""R5 delivery evidence workbook loading tests."""

import pandas as pd
import pytest

from data.delivery_loader import load_delivery_evidence_workbook


def test_loads_standard_first_row_headers(tmp_path):
    path = tmp_path / "standard.xlsx"

    with pd.ExcelWriter(path) as writer:
        pd.DataFrame([
            {
                "AWB": "NBX001",
                "Carrier": "Northbridge Express",
                "Status": "Delivered",
                "Delivery Status": "Delivered",
            }
        ]).to_excel(
            writer,
            sheet_name="Carrier Tracking",
            index=False,
        )

    result = load_delivery_evidence_workbook(path)

    assert set(result) == {"carrier_tracking"}
    assert len(result["carrier_tracking"]) == 1
    assert result["carrier_tracking"].iloc[0]["AWB"] == "NBX001"


def test_loads_fourth_row_headers(tmp_path):
    path = tmp_path / "fourth_row.xlsx"

    with pd.ExcelWriter(path) as writer:
        pd.DataFrame([
            ["Carrier Tracking Extract", None, None],
            ["Tracking results", None, None],
            [None, None, None],
            ["AWB", "Status", "Carrier"],
            ["NBX002", "Delivered", "Northbridge Express"],
        ]).to_excel(
            writer,
            sheet_name="Carrier Tracking",
            index=False,
            header=False,
        )

    result = load_delivery_evidence_workbook(path)

    tracking = result["carrier_tracking"]

    assert len(tracking) == 1
    assert tracking.iloc[0]["AWB"] == "NBX002"
    assert tracking.iloc[0]["Status"] == "Delivered"


def test_rejects_unrecognizable_headers(tmp_path):
    path = tmp_path / "invalid.xlsx"

    with pd.ExcelWriter(path) as writer:
        pd.DataFrame([
            {"Reference": "NBX003", "Comment": "Delivered"}
        ]).to_excel(
            writer,
            sheet_name="Carrier Tracking",
            index=False,
        )

    with pytest.raises(ValueError, match="Cannot identify delivery evidence headers"):
        load_delivery_evidence_workbook(path)


def test_rejects_duplicate_candidate_header_rows(tmp_path):
    path = tmp_path / "ambiguous.xlsx"

    with pd.ExcelWriter(path) as writer:
        pd.DataFrame([
            ["AWB", "Status"],
            ["NBX004", "Delivered"],
            ["AWB", "Status"],
            ["NBX005", "Delivered"],
        ]).to_excel(
            writer,
            sheet_name="Carrier Tracking",
            index=False,
            header=False,
        )

    with pytest.raises(ValueError, match="Ambiguous delivery evidence headers"):
        load_delivery_evidence_workbook(path)


def test_rejects_workbook_without_supported_sheets(tmp_path):
    path = tmp_path / "unrelated.xlsx"

    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"Value": [1]}).to_excel(
            writer,
            sheet_name="Other",
            index=False,
        )

    with pytest.raises(ValueError, match="No recognized delivery evidence worksheets"):
        load_delivery_evidence_workbook(path)

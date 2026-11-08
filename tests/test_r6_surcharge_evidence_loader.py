"""R6 tests for CSV and Excel surcharge contract evidence loading."""

from decimal import Decimal

import pandas as pd
import pytest

from data.surcharge_evidence_loader import load_surcharge_evidence


COLUMNS = [
    "Invoice Line ID",
    "Applicable",
    "Basis",
    "Rate",
]


def _write_csv(path, rows):
    pd.DataFrame(rows, columns=COLUMNS).to_csv(path, index=False)
    return path


def _write_excel(path, rows):
    pd.DataFrame(rows, columns=COLUMNS).to_excel(
        path, index=False, engine="openpyxl"
    )
    return path


def test_csv_accepts_explicit_true_false_and_blank(tmp_path):
    path = _write_csv(
        tmp_path / "surcharges.csv",
        [
            [101, "TRUE", "fixed", "8.50"],
            [102, "FALSE", None, None],
            [103, None, None, None],
        ],
    )

    result = load_surcharge_evidence(path)

    assert result == {
        101: {
            "applicable": True,
            "basis": "fixed",
            "rate": Decimal("8.50"),
        },
        102: {
            "applicable": False,
            "basis": None,
            "rate": None,
        },
        103: {
            "applicable": None,
            "basis": None,
            "rate": None,
        },
    }


def test_excel_accepts_native_boolean_cells(tmp_path):
    path = _write_excel(
        tmp_path / "surcharges.xlsx",
        [
            [201, True, "per_kg", "2.50"],
            [202, False, None, None],
            [203, None, None, None],
        ],
    )

    result = load_surcharge_evidence(path)

    assert result[201]["applicable"] is True
    assert result[201]["basis"] == "per_kg"
    assert result[201]["rate"] == Decimal("2.50")
    assert result[202]["applicable"] is False
    assert result[203]["applicable"] is None


@pytest.mark.parametrize("value", ["yes", "no", "1", "0", "maybe"])
def test_csv_rejects_unsupported_applicability_text(tmp_path, value):
    path = _write_csv(
        tmp_path / "invalid.csv",
        [[301, value, None, None]],
    )

    with pytest.raises(ValueError, match="applicability"):
        load_surcharge_evidence(path)


@pytest.mark.parametrize("value", [1, 0])
def test_excel_rejects_numeric_applicability(tmp_path, value):
    path = _write_excel(
        tmp_path / "numeric.xlsx",
        [[401, value, None, None]],
    )

    with pytest.raises(ValueError, match="applicability"):
        load_surcharge_evidence(path)


def test_csv_rejects_contradictory_contract_evidence(tmp_path):
    path = _write_csv(
        tmp_path / "contradictory.csv",
        [[501, "FALSE", "fixed", "8.50"]],
    )

    with pytest.raises(ValueError, match="contradictory"):
        load_surcharge_evidence(path)


def test_excel_rejects_duplicate_invoice_line_ids(tmp_path):
    path = _write_excel(
        tmp_path / "duplicates.xlsx",
        [
            [601, True, "fixed", "3.00"],
            [601, True, "fixed", "4.00"],
        ],
    )

    with pytest.raises(ValueError, match="duplicate"):
        load_surcharge_evidence(path)


def test_rejects_unsupported_file_extension(tmp_path):
    path = tmp_path / "evidence.txt"
    path.write_text("Invoice Line ID,Applicable,Basis,Rate\n")

    with pytest.raises(ValueError, match="Unsupported"):
        load_surcharge_evidence(path)


def test_rejects_missing_file(tmp_path):
    path = tmp_path / "missing.csv"

    with pytest.raises(FileNotFoundError):
        load_surcharge_evidence(path)


def test_csv_rejects_missing_required_column(tmp_path):
    path = tmp_path / "incomplete.csv"
    pd.DataFrame({
        "Invoice Line ID": [701],
        "Applicable": ["TRUE"],
        "Basis": ["fixed"],
    }).to_csv(path, index=False)

    with pytest.raises(ValueError, match="required columns"):
        load_surcharge_evidence(path)


def test_csv_preserves_decimal_precision(tmp_path):
    path = _write_csv(
        tmp_path / "precision.csv",
        [[801, "TRUE", "fixed", "0.123456789123456789"]],
    )

    result = load_surcharge_evidence(path)

    assert result[801]["rate"] == Decimal(
        "0.123456789123456789"
    )


@pytest.mark.parametrize(
    "invalid_line_id",
    ["00101", "INV-101", "0", "-1", "1.5", ""],
)
def test_csv_rejects_noncanonical_invoice_line_ids(
    tmp_path,
    invalid_line_id,
):
    path = _write_csv(
        tmp_path / "invalid_line_id.csv",
        [[invalid_line_id, "TRUE", "fixed", "8.50"]],
    )

    with pytest.raises(ValueError, match="Invoice Line ID"):
        load_surcharge_evidence(path)


@pytest.mark.parametrize(
    "invalid_line_id",
    [0, -1, 1.5, "00101", "INV-101", True],
)
def test_excel_rejects_invalid_invoice_line_ids(
    tmp_path,
    invalid_line_id,
):
    path = _write_excel(
        tmp_path / "invalid_line_id.xlsx",
        [[invalid_line_id, True, "fixed", "8.50"]],
    )

    with pytest.raises(ValueError, match="Invoice Line ID"):
        load_surcharge_evidence(path)

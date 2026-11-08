"""R6 TAX-01: CSV and Excel tax evidence loading."""

import csv
from decimal import Decimal

import pandas as pd
import pytest
from openpyxl import Workbook

from data.tax_evidence_loader import load_tax_evidence


COLUMNS = [
    "Invoice Line ID",
    "Applicable",
    "Taxable Base",
    "Tax Rate",
    "Tax Inclusive",
    "Rounding Increment",
]


def _taxable(line_id=101):
    return [line_id, "TRUE", "100", "0.075", "FALSE", "0.01"]


def _exempt(line_id=102):
    return [line_id, "FALSE", "", "", "", ""]


def _unknown(line_id=103):
    return [line_id, "", "", "", "", ""]


def _csv(path, rows, columns=COLUMNS):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(rows)
    return path


def _xlsx(path, rows, columns=COLUMNS):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(columns)
    for row in rows:
        sheet.append(row)
    workbook.save(path)
    workbook.close()
    return path


def test_csv_loads_taxable_exempt_and_unknown_lines(tmp_path):
    path = _csv(
        tmp_path / "tax.csv",
        [_taxable(), _exempt(), _unknown()],
    )

    result = load_tax_evidence(path)

    assert result[101] == {
        "applicable": True,
        "taxable_base": Decimal("100"),
        "tax_rate": Decimal("0.075"),
        "tax_inclusive": False,
        "rounding_increment": Decimal("0.01"),
    }
    assert result[102]["applicable"] is False
    assert result[102]["taxable_base"] is None
    assert result[103]["applicable"] is None


def test_csv_preserves_decimal_precision(tmp_path):
    row = _taxable()
    row[2] = "100.123456789123456789"
    row[3] = "0.075123456789123456789"
    row[5] = "0.00000001"

    result = load_tax_evidence(
        _csv(tmp_path / "precision.csv", [row])
    )

    assert result[101]["taxable_base"] == Decimal(
        "100.123456789123456789"
    )
    assert result[101]["tax_rate"] == Decimal(
        "0.075123456789123456789"
    )
    assert result[101]["rounding_increment"] == Decimal(
        "0.00000001"
    )


def test_excel_accepts_native_boolean_cells(tmp_path):
    result = load_tax_evidence(
        _xlsx(
            tmp_path / "tax.xlsx",
            [
                [201, True, 100, 0.075, False, 0.01],
                [202, False, None, None, None, None],
                [203, None, None, None, None, None],
            ],
        )
    )

    assert result[201]["applicable"] is True
    assert result[201]["tax_inclusive"] is False
    assert result[202]["applicable"] is False
    assert result[203]["applicable"] is None


def test_csv_accepts_case_insensitive_boolean_text(tmp_path):
    row = [301, "true", "100", "0.075", "false", "0.01"]

    result = load_tax_evidence(
        _csv(tmp_path / "case.csv", [row])
    )

    assert result[301]["applicable"] is True
    assert result[301]["tax_inclusive"] is False


@pytest.mark.parametrize(
    "value",
    ["yes", "no", "1", "0", "maybe"],
)
def test_csv_rejects_invalid_applicability(tmp_path, value):
    row = _taxable()
    row[1] = value

    with pytest.raises(ValueError, match="applicability"):
        load_tax_evidence(
            _csv(tmp_path / "invalid.csv", [row])
        )


@pytest.mark.parametrize(
    "value",
    ["yes", "no", "1", "0", ""],
)
def test_csv_rejects_invalid_tax_inclusive(tmp_path, value):
    row = _taxable()
    row[4] = value

    with pytest.raises(ValueError, match="Tax Inclusive"):
        load_tax_evidence(
            _csv(tmp_path / "invalid.csv", [row])
        )


@pytest.mark.parametrize("value", [0, 1])
def test_excel_rejects_numeric_applicability(tmp_path, value):
    row = [401, value, None, None, None, None]

    with pytest.raises(ValueError, match="applicability"):
        load_tax_evidence(
            _xlsx(tmp_path / "numeric.xlsx", [row])
        )


@pytest.mark.parametrize("value", [0, 1])
def test_excel_rejects_numeric_tax_inclusive(tmp_path, value):
    row = [402, True, 100, 0.075, value, 0.01]

    with pytest.raises(ValueError, match="Tax Inclusive"):
        load_tax_evidence(
            _xlsx(tmp_path / "numeric.xlsx", [row])
        )


def test_csv_rejects_contradictory_exemption(tmp_path):
    row = _exempt()
    row[3] = "0.075"

    with pytest.raises(ValueError, match="contradictory"):
        load_tax_evidence(
            _csv(tmp_path / "contradiction.csv", [row])
        )


def test_excel_rejects_duplicate_line_ids(tmp_path):
    with pytest.raises(ValueError, match="Duplicate"):
        load_tax_evidence(
            _xlsx(
                tmp_path / "duplicates.xlsx",
                [
                    [501, True, 100, 0.075, False, 0.01],
                    [501, True, 200, 0.075, False, 0.01],
                ],
            )
        )


@pytest.mark.parametrize(
    "invalid_id",
    ["00101", "INV-101", "0", "-1", "1.5", ""],
)
def test_csv_rejects_invalid_line_ids(tmp_path, invalid_id):
    row = _taxable()
    row[0] = invalid_id

    with pytest.raises(ValueError, match="Invoice Line ID"):
        load_tax_evidence(
            _csv(tmp_path / "invalid_id.csv", [row])
        )


def test_csv_rejects_duplicate_headers(tmp_path):
    columns = COLUMNS.copy()
    columns[3] = "Taxable Base"

    with pytest.raises(ValueError, match="duplicate"):
        load_tax_evidence(
            _csv(tmp_path / "duplicate_headers.csv", [], columns)
        )


def test_csv_rejects_missing_required_column(tmp_path):
    columns = COLUMNS[:-1]

    with pytest.raises(ValueError, match="required columns"):
        load_tax_evidence(
            _csv(tmp_path / "missing_column.csv", [], columns)
        )


def test_csv_rejects_incomplete_row(tmp_path):
    path = tmp_path / "incomplete.csv"
    path.write_text(
        ",".join(COLUMNS) + "\n"
        "101,TRUE,100\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="incomplete"):
        load_tax_evidence(path)


def test_csv_rejects_extra_fields(tmp_path):
    row = _taxable() + ["unexpected"]

    with pytest.raises(ValueError, match="extra fields"):
        load_tax_evidence(
            _csv(tmp_path / "extra.csv", [row])
        )


def test_rejects_unsupported_extension(tmp_path):
    path = tmp_path / "tax.txt"
    path.write_text("unsupported", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported"):
        load_tax_evidence(path)


def test_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_tax_evidence(tmp_path / "missing.csv")


def test_csv_rejects_invalid_tax_rate(tmp_path):
    row = _taxable()
    row[3] = "1.5"

    with pytest.raises(ValueError, match="Tax Rate"):
        load_tax_evidence(
            _csv(tmp_path / "invalid_rate.csv", [row])
        )

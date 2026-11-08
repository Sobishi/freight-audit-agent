"""Load explicit R6 TAX-01 evidence from CSV or Excel."""

import csv
import re
from pathlib import Path

import pandas as pd

from audit_engine.tax_contract_evidence import (
    prepare_tax_contracts,
)


REQUIRED_COLUMNS = (
    "Invoice Line ID",
    "Applicable",
    "Taxable Base",
    "Tax Rate",
    "Tax Inclusive",
    "Rounding Increment",
)

CALCULATION_COLUMNS = (
    "Taxable Base",
    "Tax Rate",
    "Tax Inclusive",
    "Rounding Increment",
)


def _check_columns(columns):
    """Reject duplicate or missing evidence headers."""
    if len(columns) != len(set(columns)):
        raise ValueError(
            "Tax evidence contains duplicate column names."
        )

    missing = set(REQUIRED_COLUMNS) - set(columns)

    if missing:
        raise ValueError(
            "Tax evidence is missing required columns: "
            + ", ".join(sorted(missing))
        )


def _normalise_boolean(value, field, *, allow_blank):
    """Accept genuine booleans or explicit TRUE/FALSE text."""
    if value is None:
        if allow_blank:
            return None
        raise ValueError(f"Missing {field}.")

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        text = value.strip()

        if not text:
            if allow_blank:
                return None
            raise ValueError(f"Missing {field}.")

        if text.upper() == "TRUE":
            return True

        if text.upper() == "FALSE":
            return False

    raise ValueError(
        f"Invalid {field}: {value!r}. "
        "Use TRUE, FALSE or an allowed blank cell."
    )


def _normalise_line_id(value):
    """Preserve identifier integrity across CSV and Excel."""
    if isinstance(value, str):
        if not re.fullmatch(r"[1-9][0-9]*", value):
            raise ValueError(
                f"Invalid Invoice Line ID: {value!r}."
            )
        return int(value)

    return value


def _normalise_record(record):
    """Normalize fields without inferring contractual terms."""
    result = {
        "Invoice Line ID": _normalise_line_id(
            record["Invoice Line ID"]
        ),
        "Applicable": _normalise_boolean(
            record["Applicable"],
            "applicability",
            allow_blank=True,
        ),
    }

    for field in CALCULATION_COLUMNS:
        value = record[field]

        if field == "Tax Inclusive":
            if result["Applicable"] is True:
                result[field] = _normalise_boolean(
                    value,
                    field,
                    allow_blank=False,
                )
            elif value is None or (
                isinstance(value, str)
                and value.strip() == ""
            ):
                result[field] = None
            else:
                # Preserve supplied contradictory evidence so
                # the contract validator can reject it.
                result[field] = _normalise_boolean(
                    value,
                    field,
                    allow_blank=False,
                )
        else:
            if isinstance(value, str) and value.strip() == "":
                result[field] = None
            else:
                result[field] = value

    return result


def _load_csv(path):
    """Read CSV as text to preserve monetary precision."""
    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)

        if reader.fieldnames is None:
            raise ValueError(
                "Tax evidence CSV has no header row."
            )

        _check_columns(reader.fieldnames)

        records = []

        for row in reader:
            if None in row:
                raise ValueError(
                    "Tax evidence CSV contains extra fields."
                )

            if any(value is None for value in row.values()):
                raise ValueError(
                    "Tax evidence CSV contains incomplete rows."
                )

            records.append(_normalise_record(row))

    return pd.DataFrame(
        records,
        columns=REQUIRED_COLUMNS,
    )


def _load_xlsx(path):
    """Read native Excel cell types without pandas inference."""
    from openpyxl import load_workbook

    workbook = load_workbook(
        path,
        read_only=True,
        data_only=True,
    )

    try:
        worksheet = workbook.active
        rows = worksheet.iter_rows(values_only=True)

        header = next(rows, None)

        if header is None:
            raise ValueError(
                "Tax evidence Excel file is empty."
            )

        columns = list(header)
        _check_columns(columns)

        positions = {
            name: columns.index(name)
            for name in REQUIRED_COLUMNS
        }

        records = []

        for values in rows:
            if all(value is None for value in values):
                continue

            record = {
                name: (
                    values[position]
                    if position < len(values)
                    else None
                )
                for name, position in positions.items()
            }

            records.append(_normalise_record(record))

        return pd.DataFrame(
            records,
            columns=REQUIRED_COLUMNS,
        )

    finally:
        workbook.close()


def _load_xls(path):
    """Load legacy XLS through the established pandas path."""
    frame = pd.read_excel(
        path,
        dtype=object,
        keep_default_na=False,
    )

    _check_columns(list(frame.columns))

    records = []

    for _, row in frame.iterrows():
        records.append(
            _normalise_record({
                name: row[name]
                for name in REQUIRED_COLUMNS
            })
        )

    return pd.DataFrame(
        records,
        columns=REQUIRED_COLUMNS,
    )


def load_tax_evidence(path):
    """Load validated tax contracts keyed by Invoice Line ID.

    Tax applicability, taxable base, rate, inclusive treatment
    and rounding must come from explicit evidence.
    """
    path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(
            f"Tax evidence file not found: {path}"
        )

    extension = path.suffix.lower()

    if extension == ".csv":
        evidence = _load_csv(path)
    elif extension == ".xlsx":
        evidence = _load_xlsx(path)
    elif extension == ".xls":
        evidence = _load_xls(path)
    else:
        raise ValueError(
            "Unsupported tax evidence format. "
            "Use CSV or Excel."
        )

    return prepare_tax_contracts(evidence)

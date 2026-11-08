"""Load explicit R6 surcharge contract evidence from CSV or Excel."""

import csv
import re
from pathlib import Path

import pandas as pd

from audit_engine.surcharge_contract_evidence import (
    prepare_surcharge_contracts,
)


REQUIRED_COLUMNS = (
    "Invoice Line ID",
    "Applicable",
    "Basis",
    "Rate",
)


def _normalise_applicability(value):
    """Normalise only explicitly supported applicability representations."""

    if value is None:
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        text = value.strip()

        if text == "":
            return None

        if text.upper() == "TRUE":
            return True

        if text.upper() == "FALSE":
            return False

    raise ValueError(
        f"Invalid surcharge applicability: {value!r}. "
        "Use TRUE, FALSE or a blank cell."
    )


def _check_columns(columns):
    """Reject missing or duplicate evidence column names."""

    if len(columns) != len(set(columns)):
        raise ValueError(
            "Surcharge evidence contains duplicate column names."
        )

    missing = set(REQUIRED_COLUMNS) - set(columns)

    if missing:
        raise ValueError(
            "Surcharge evidence is missing required columns: "
            + ", ".join(sorted(missing))
        )


def _normalise_csv_line_id(value):
    """
    Preserve meaningful identifier formatting.

    Convert only canonical nonnegative integer text to integers.
    Leading-zero and alphanumeric identifiers remain strings.
    """
    if not isinstance(value, str):
        return value

    if re.fullmatch(r"(?:0|[1-9][0-9]*)", value):
        return int(value)

    return value


def _load_csv(path):
    """Read CSV values as text without pandas type inference."""

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)

        if reader.fieldnames is None:
            raise ValueError(
                "Surcharge evidence CSV has no header row."
            )

        _check_columns(reader.fieldnames)

        records = []

        for row in reader:
            if None in row:
                raise ValueError(
                    "Surcharge evidence CSV contains extra fields."
                )

            if any(value is None for value in row.values()):
                raise ValueError(
                    "Surcharge evidence CSV contains incomplete rows."
                )

            records.append({
                "Invoice Line ID": _normalise_csv_line_id(
                    row["Invoice Line ID"]
                ),
                "Applicable": _normalise_applicability(
                    row["Applicable"]
                ),
                "Basis": row["Basis"] or None,
                "Rate": row["Rate"] or None,
            })

    return pd.DataFrame(records, columns=REQUIRED_COLUMNS)


def _load_excel(path):
    """Read Excel cells while preserving boolean versus numeric types."""

    if path.suffix.lower() == ".xlsx":
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
                    "Surcharge evidence Excel file is empty."
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

                record["Applicable"] = _normalise_applicability(
                    record["Applicable"]
                )

                records.append(record)

            return pd.DataFrame(
                records,
                columns=REQUIRED_COLUMNS,
            )

        finally:
            workbook.close()

    # Legacy XLS files are handled through pandas.
    # No numeric applicability value is accepted.
    frame = pd.read_excel(
        path,
        dtype=object,
        keep_default_na=False,
    )

    _check_columns(list(frame.columns))

    records = []

    for _, row in frame.iterrows():
        records.append({
            "Invoice Line ID": row["Invoice Line ID"],
            "Applicable": _normalise_applicability(
                row["Applicable"]
            ),
            "Basis": row["Basis"] or None,
            "Rate": row["Rate"] or None,
        })

    return pd.DataFrame(
        records,
        columns=REQUIRED_COLUMNS,
    )


def load_surcharge_evidence(path):
    """
    Load and validate explicit invoice-line surcharge contract evidence.

    Returns a dictionary keyed by Invoice Line ID.

    Contractual applicability is never inferred from billed amounts.
    """

    path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(
            f"Surcharge evidence file not found: {path}"
        )

    extension = path.suffix.lower()

    if extension == ".csv":
        evidence = _load_csv(path)

    elif extension in {".xlsx", ".xls"}:
        evidence = _load_excel(path)

    else:
        raise ValueError(
            "Unsupported surcharge evidence format. "
            "Use CSV or Excel."
        )

    return prepare_surcharge_contracts(evidence)

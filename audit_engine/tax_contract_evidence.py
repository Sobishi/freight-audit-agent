"""Validate explicit invoice-line tax contract evidence for R6 TAX-01."""

from decimal import Decimal, InvalidOperation

import pandas as pd


REQUIRED_COLUMNS = {
    "Invoice Line ID",
    "Applicable",
    "Taxable Base",
    "Tax Rate",
    "Tax Inclusive",
    "Rounding Increment",
}

CALCULATION_COLUMNS = (
    "Taxable Base",
    "Tax Rate",
    "Tax Inclusive",
    "Rounding Increment",
)


def _missing(value):
    """Recognize missing scalar evidence without coercing valid values."""
    if value is None:
        return True

    if isinstance(value, str):
        return value.strip() == ""

    try:
        result = pd.isna(value)
    except (TypeError, ValueError):
        return False

    return isinstance(result, (bool, type(pd.NA))) and result is True


def _decimal(value, field):
    if isinstance(value, bool) or _missing(value):
        raise ValueError(f"Invalid {field}.")

    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"Invalid {field}.") from None

    if not number.is_finite():
        raise ValueError(f"Invalid {field}.")

    return number


def _line_id(value):
    number = _decimal(value, "Invoice Line ID")

    if number <= 0 or number != number.to_integral_value():
        raise ValueError("Invoice Line ID must be a positive integer.")

    return int(number)


def _boolean(value, field, *, allow_missing=False):
    if _missing(value):
        if allow_missing:
            return None
        raise ValueError(f"Missing {field}.")

    if not isinstance(value, bool):
        raise ValueError(f"Invalid {field}.")

    return value


def prepare_tax_contracts(evidence: pd.DataFrame) -> dict:
    """Return validated tax contracts keyed by Invoice Line ID.

    Taxable lines require complete calculation evidence.
    Exempt or unresolved lines must not contain calculation terms.
    """

    if not isinstance(evidence, pd.DataFrame):
        raise TypeError("Tax evidence must be a pandas DataFrame.")

    if not evidence.columns.is_unique:
        raise ValueError("Tax evidence contains duplicate headers.")

    missing_columns = REQUIRED_COLUMNS - set(evidence.columns)

    if missing_columns:
        raise ValueError(
            "Missing required tax evidence columns: "
            + ", ".join(sorted(missing_columns))
        )

    contracts = {}

    for _, row in evidence.iterrows():
        line_id = _line_id(row["Invoice Line ID"])

        if line_id in contracts:
            raise ValueError(
                f"Duplicate Invoice Line ID: {line_id}."
            )

        applicable = _boolean(
            row["Applicable"],
            "Applicable",
            allow_missing=True,
        )

        if applicable is not True:
            if any(
                not _missing(row[column])
                for column in CALCULATION_COLUMNS
            ):
                raise ValueError(
                    "Tax evidence contains contradictory calculation "
                    f"terms for Invoice Line ID {line_id}."
                )

            contracts[line_id] = {
                "applicable": applicable,
                "taxable_base": None,
                "tax_rate": None,
                "tax_inclusive": None,
                "rounding_increment": None,
            }
            continue

        taxable_base = _decimal(
            row["Taxable Base"],
            "Taxable Base",
        )

        tax_rate = _decimal(
            row["Tax Rate"],
            "Tax Rate",
        )

        tax_inclusive = _boolean(
            row["Tax Inclusive"],
            "Tax Inclusive",
        )

        rounding_increment = _decimal(
            row["Rounding Increment"],
            "Rounding Increment",
        )

        if taxable_base < 0:
            raise ValueError("Taxable Base cannot be negative.")

        if not Decimal("0") <= tax_rate <= Decimal("1"):
            raise ValueError("Tax Rate must be between 0 and 1.")

        if rounding_increment <= 0:
            raise ValueError(
                "Rounding Increment must be positive."
            )

        contracts[line_id] = {
            "applicable": True,
            "taxable_base": taxable_base,
            "tax_rate": tax_rate,
            "tax_inclusive": tax_inclusive,
            "rounding_increment": rounding_increment,
        }

    return contracts

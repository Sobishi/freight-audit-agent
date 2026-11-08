"""Prepare explicit invoice-line surcharge contract evidence for R6."""

from decimal import Decimal, InvalidOperation

import numpy as np
import pandas as pd

from audit_engine.surcharge_validation import SUPPORTED_BASES


REQUIRED_EVIDENCE_COLUMNS = {
    "Invoice Line ID",
    "Applicable",
    "Basis",
    "Rate",
}


def _is_missing(value):
    """Recognise a scalar missing value without interpreting false as missing."""
    try:
        result = pd.isna(value)
        return isinstance(result, (bool, np.bool_)) and bool(result)
    except (TypeError, ValueError):
        return False


def _parse_applicability(value):
    """Accept genuine booleans or missing evidence, never numeric substitutes."""
    if _is_missing(value):
        return None

    if isinstance(value, (bool, np.bool_)):
        return bool(value)

    raise ValueError(
        f"Invalid surcharge applicability: {value!r}. "
        "Expected True, False or missing."
    )


def _parse_rate(value):
    """Return a finite nonnegative Decimal contractual rate."""
    if _is_missing(value):
        raise ValueError("Applicable surcharge is missing a rate.")

    if isinstance(value, (bool, np.bool_)):
        raise ValueError("Surcharge rate must be numeric.")

    try:
        rate = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(
            f"Invalid surcharge rate: {value!r}."
        ) from None

    if not rate.is_finite() or rate < 0:
        raise ValueError(
            f"Invalid surcharge rate: {value!r}."
        )

    return rate


def prepare_surcharge_contracts(evidence: pd.DataFrame) -> dict:
    """
    Prepare explicit contractual surcharge terms keyed by Invoice Line ID.

    Required columns:
        Invoice Line ID
        Applicable
        Basis
        Rate

    True applicability requires a supported basis and valid rate.

    False or unknown applicability does not create contractual entitlement.
    The caller must provide verified evidence; applicability is not inferred
    from the invoice's billed surcharge amount.

    This function does not select contracts by carrier, date or service.
    """

    if not isinstance(evidence, pd.DataFrame):
        raise TypeError(
            "Surcharge contract evidence must be a pandas DataFrame."
        )

    if not evidence.columns.is_unique:
        raise ValueError(
            "Surcharge evidence contains duplicate column names."
        )

    missing_columns = (
        REQUIRED_EVIDENCE_COLUMNS - set(evidence.columns)
    )

    if missing_columns:
        raise ValueError(
            "Surcharge evidence is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    line_ids = evidence["Invoice Line ID"]

    if line_ids.isna().any():
        raise ValueError(
            "Surcharge evidence contains missing Invoice Line ID values."
        )

    for line_id in line_ids:
        if (
            isinstance(line_id, (bool, np.bool_))
            or not isinstance(line_id, (int, np.integer))
            or line_id <= 0
        ):
            raise ValueError(
                "Invalid Invoice Line ID in surcharge evidence: "
                f"{line_id!r}. Expected a positive integer."
            )

    if line_ids.duplicated().any():
        raise ValueError(
            "Surcharge evidence contains duplicate Invoice Line ID values."
        )

    contracts = {}

    for _, row in evidence.iterrows():
        line_id = row["Invoice Line ID"]
        applicable = _parse_applicability(row["Applicable"])

        if applicable is True:
            basis = row["Basis"]

            if (
                not isinstance(basis, str)
                or basis not in SUPPORTED_BASES
            ):
                raise ValueError(
                    f"Invalid surcharge basis for Invoice Line ID "
                    f"{line_id!r}: {basis!r}."
                )

            rate = _parse_rate(row["Rate"])

        else:
            # Non-applicable or unknown terms must not contain
            # contradictory contractual pricing evidence.
            supplied_basis = row["Basis"]
            supplied_rate = row["Rate"]

            if (
                not _is_missing(supplied_basis)
                or not _is_missing(supplied_rate)
            ):
                raise ValueError(
                    "Surcharge evidence contains contradictory "
                    f"contract terms for Invoice Line ID {line_id!r}: "
                    "basis and rate must be blank when applicability "
                    "is False or unknown."
                )

            basis = None
            rate = None

        contracts[line_id] = {
            "applicable": applicable,
            "basis": basis,
            "rate": rate,
        }

    return contracts

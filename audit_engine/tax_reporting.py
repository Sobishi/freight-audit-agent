"""Conservative invoice-line tax reporting for R6 TAX-01."""

from decimal import Decimal, InvalidOperation

import numpy as np
import pandas as pd

from audit_engine.tax_validation import validate_tax_charge


REQUIRED_INVOICE_COLUMNS = {
    "Invoice Line ID",
    "Tax Amount",
}

RESULT_COLUMNS = [
    "Tax Status",
    "Tax Reason",
    "Expected Tax",
    "Potential Tax Overcharge",
]

MATCHED_REVERSAL_STATUSES = {
    "Fully Reversed",
    "Matched Full Reversal",
}

UNRESOLVED_CREDIT_STATUSES = {
    "Unmatched Credit",
    "Ambiguous Credit",
    "Missing Match Information",
}

VALID_CREDIT_STATUSES = (
    MATCHED_REVERSAL_STATUSES
    | UNRESOLVED_CREDIT_STATUSES
    | {"Not a Credit"}
)


def _is_negative(value):
    """Identify finite negative values without coercing invalid inputs."""
    if isinstance(value, bool):
        return False

    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return False

    return amount.is_finite() and amount < 0


def _result(status, reason=None, expected=None, exposure=None):
    return {
        "status": status,
        "reason": reason,
        "expected_tax": expected,
        "potential_overcharge": exposure,
    }


def generate_tax_validation_results(
    invoice: pd.DataFrame,
    tax_contracts: dict,
    *,
    tolerance="0.01",
) -> pd.DataFrame:
    """Validate invoice tax using explicit invoice-line contract terms.

    Missing or inconsistent evidence produces review with unknown
    exposure. Matched full reversals are excluded from assessment.

    This function does not align evidence IDs, load evidence files,
    reconcile exposures or make final payment decisions.
    """
    if not isinstance(invoice, pd.DataFrame):
        raise TypeError("Invoice must be a pandas DataFrame.")

    if not isinstance(tax_contracts, dict):
        raise TypeError("Tax contracts must be a dictionary.")

    if not invoice.columns.is_unique:
        raise ValueError("Invoice contains duplicate column names.")

    missing = REQUIRED_INVOICE_COLUMNS - set(invoice.columns)

    if missing:
        raise ValueError(
            "Invoice missing required tax columns: "
            + ", ".join(sorted(missing))
        )

    existing = set(RESULT_COLUMNS) & set(invoice.columns)

    if existing:
        raise ValueError(
            "Invoice already contains tax result columns: "
            + ", ".join(sorted(existing))
        )

    line_ids = invoice["Invoice Line ID"]

    if line_ids.isna().any() or line_ids.duplicated().any():
        raise ValueError(
            "Invoice Line ID values must be non-null and unique."
        )

    credit_columns = {
        "Credit Match Status",
        "Excluded From Exposure",
    }

    present = credit_columns & set(invoice.columns)

    if present and present != credit_columns:
        raise ValueError(
            "Incomplete credit metadata: Credit Match Status and "
            "Excluded From Exposure must be supplied together."
        )

    has_credit_metadata = present == credit_columns

    records = []

    for _, line in invoice.iterrows():
        line_id = line["Invoice Line ID"]

        contract = tax_contracts.get(line_id)

        if contract is None:
            contract = {}

        if not isinstance(contract, dict):
            raise ValueError(
                f"Invalid tax contract for Invoice Line ID {line_id!r}."
            )

        credit_status = (
            line["Credit Match Status"]
            if has_credit_metadata
            else None
        )

        excluded = (
            line["Excluded From Exposure"]
            if has_credit_metadata
            else None
        )

        if has_credit_metadata and (
            not isinstance(excluded, (bool, np.bool_))
            or not isinstance(credit_status, str)
            or credit_status not in VALID_CREDIT_STATUSES
        ):
            result = _result(
                "review",
                reason="invalid_credit_metadata",
            )

        elif has_credit_metadata and (
            (
                credit_status in MATCHED_REVERSAL_STATUSES
                and not excluded
            )
            or (
                credit_status not in MATCHED_REVERSAL_STATUSES
                and excluded
            )
        ):
            result = _result(
                "review",
                reason="inconsistent_credit_metadata",
            )

        elif (
            has_credit_metadata
            and credit_status in MATCHED_REVERSAL_STATUSES
        ):
            result = _result(
                "not_assessed",
                reason="matched_full_reversal",
                exposure=Decimal("0"),
            )

        elif (
            has_credit_metadata
            and credit_status in UNRESOLVED_CREDIT_STATUSES
        ):
            result = _result(
                "review",
                reason="unresolved_credit",
            )

        elif _is_negative(line["Tax Amount"]):
            result = _result(
                "review",
                reason="negative_tax_adjustment",
            )

        else:
            result = validate_tax_charge(
                billed_tax=line["Tax Amount"],
                applicable=contract.get("applicable"),
                taxable_base=contract.get("taxable_base"),
                tax_rate=contract.get("tax_rate"),
                tax_inclusive=contract.get("tax_inclusive"),
                rounding_increment=contract.get(
                    "rounding_increment"
                ),
                tolerance=tolerance,
            )

        records.append({
            "Tax Status": result["status"],
            "Tax Reason": result["reason"],
            "Expected Tax": result["expected_tax"],
            "Potential Tax Overcharge": result[
                "potential_overcharge"
            ],
        })

    results = pd.DataFrame(
        records,
        index=invoice.index,
        columns=RESULT_COLUMNS,
    )

    return pd.concat(
        [
            invoice[["Invoice Line ID"]].copy(),
            results,
        ],
        axis=1,
    )

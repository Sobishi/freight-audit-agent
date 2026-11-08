"""Invoice-line surcharge validation reporting for R6."""

from decimal import Decimal, InvalidOperation

import numpy as np
import pandas as pd

from audit_engine.surcharge_validation import validate_surcharge_charge


REQUIRED_INVOICE_COLUMNS = {
    "Invoice Line ID",
    "Surcharge Amount",
}


def _is_negative(value):
    """Identify a finite negative surcharge without coercing invalid values."""
    if isinstance(value, bool):
        return False

    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return False

    return amount.is_finite() and amount < 0


def generate_surcharge_validation_results(
    invoice: pd.DataFrame,
    surcharge_contracts: dict,
    *,
    tolerance="0.01",
) -> pd.DataFrame:
    """
    Validate billed surcharges against explicit invoice-line contract terms.

    surcharge_contracts is keyed by Invoice Line ID. Each entry contains:
        applicable: True, False or None
        basis: fixed, per_kg or percent_of_freight
        rate: contractual surcharge rate

    Contract applicability is never inferred from billed amounts.
    Missing contract evidence results in review, not zero exposure.

    This function does not reconcile duplicate billing or credit matching.
    """

    if not isinstance(invoice, pd.DataFrame):
        raise TypeError("Invoice must be a pandas DataFrame.")

    if not isinstance(surcharge_contracts, dict):
        raise TypeError("Surcharge contracts must be a dictionary.")

    if not invoice.columns.is_unique:
        raise ValueError(
            "Invoice contains duplicate column names."
        )

    generated_columns = {
        "Surcharge Status",
        "Surcharge Reason",
        "Expected Surcharge",
        "Potential Surcharge Overcharge",
    }

    existing_results = generated_columns & set(invoice.columns)

    if existing_results:
        raise ValueError(
            "Invoice already contains surcharge result columns: "
            + ", ".join(sorted(existing_results))
        )

    missing_columns = REQUIRED_INVOICE_COLUMNS - set(invoice.columns)

    if missing_columns:
        raise ValueError(
            "Invoice is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    credit_metadata_columns = {
        "Credit Match Status",
        "Excluded From Exposure",
    }

    present_credit_metadata = (
        credit_metadata_columns & set(invoice.columns)
    )

    if present_credit_metadata and (
        present_credit_metadata != credit_metadata_columns
    ):
        raise ValueError(
            "Incomplete credit metadata: Credit Match Status and "
            "Excluded From Exposure must be supplied together."
        )

    line_ids = invoice["Invoice Line ID"]

    if line_ids.isna().any():
        raise ValueError("Invoice Line ID contains missing values.")

    if line_ids.duplicated().any():
        raise ValueError("Invoice Line ID contains duplicate values.")

    records = []

    for _, line in invoice.iterrows():
        line_id = line["Invoice Line ID"]
        contract = surcharge_contracts.get(line_id)

        if contract is None:
            contract = {}

        if not isinstance(contract, dict):
            raise ValueError(
                f"Invalid surcharge contract for Invoice Line ID {line_id!r}."
            )

        credit_status = line.get("Credit Match Status")
        excluded = line.get("Excluded From Exposure")

        matched_statuses = {
            "Fully Reversed",
            "Matched Full Reversal",
        }
        unresolved_statuses = {
            "Unmatched Credit",
            "Ambiguous Credit",
            "Missing Match Information",
        }

        has_credit_metadata = (
            "Credit Match Status" in invoice.columns
            and "Excluded From Exposure" in invoice.columns
        )

        valid_credit_statuses = (
            matched_statuses
            | unresolved_statuses
            | {"Not a Credit"}
        )

        valid_exclusion = isinstance(
            excluded, (bool, np.bool_)
        )

        valid_credit_status = (
            isinstance(credit_status, str)
            and credit_status in valid_credit_statuses
        )

        if has_credit_metadata and (
            not valid_exclusion or not valid_credit_status
        ):
            result = {
                "status": "review",
                "reason": "invalid_credit_metadata",
                "expected_surcharge": None,
                "potential_overcharge": None,
            }

        elif has_credit_metadata and (
            (credit_status in matched_statuses and not bool(excluded))
            or (bool(excluded) and credit_status not in matched_statuses)
        ):
            result = {
                "status": "review",
                "reason": "inconsistent_credit_metadata",
                "expected_surcharge": None,
                "potential_overcharge": None,
            }

        elif (
            has_credit_metadata
            and credit_status in matched_statuses
            and bool(excluded)
        ):
            result = {
                "status": "not_assessed",
                "reason": "matched_full_reversal",
                "expected_surcharge": None,
                "potential_overcharge": Decimal("0"),
            }

        elif (
            has_credit_metadata
            and credit_status in unresolved_statuses
        ):
            result = {
                "status": "review",
                "reason": "unresolved_credit",
                "expected_surcharge": None,
                "potential_overcharge": None,
            }

        elif (
            has_credit_metadata
            and credit_status == "Not a Credit"
            and _is_negative(line.get("Surcharge Amount"))
        ):
            result = {
                "status": "review",
                "reason": "negative_surcharge_adjustment",
                "expected_surcharge": None,
                "potential_overcharge": None,
            }

        else:
            result = validate_surcharge_charge(
                billed_amount=line["Surcharge Amount"],
                applicable=contract.get("applicable"),
                basis=contract.get("basis"),
                rate=contract.get("rate"),
                chargeable_weight=line.get("Chargeable Weight (kg)"),
                base_freight=line.get("Base Freight"),
                tolerance=tolerance,
            )

        records.append(
            {
                "Surcharge Status": result["status"],
                "Surcharge Reason": result["reason"],
                "Expected Surcharge": result["expected_surcharge"],
                "Potential Surcharge Overcharge": result[
                    "potential_overcharge"
                ],
            }
        )

    result_frame = pd.DataFrame(
        records,
        index=invoice.index,
        columns=[
            "Surcharge Status",
            "Surcharge Reason",
            "Expected Surcharge",
            "Potential Surcharge Overcharge",
        ],
    )

    return pd.concat(
        [
            invoice.copy(deep=True),
            result_frame,
        ],
        axis=1,
    )

"""Batch contract pricing results for standardized invoice lines."""

import pandas as pd

from audit_engine.shipment_pricing import price_shipment


RESULT_COLUMNS = [
    "Invoice Line ID",
    "AWB",
    "Carrier ID",
    "Pricing Status",
    "Pricing Review Reason",
    "Expected Chargeable Weight (kg)",
    "Expected Base Freight",
    "Invoiced Base Freight",
    "Potential Contract Overcharge",
    "Rate Difference",
    "Currency",
]


def _validate_line_ids(frame, label):
    """Require complete, unique invoice line identifiers."""

    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{label} must be a pandas DataFrame.")

    if "Invoice Line ID" not in frame.columns:
        raise ValueError(
            f"{label} requires an Invoice Line ID column."
        )

    ids = frame["Invoice Line ID"]

    if ids.isna().any():
        raise ValueError(
            f"{label} contains missing Invoice Line ID values."
        )

    if (
        ids.astype("string").str.strip().eq("").any()
    ):
        raise ValueError(
            f"{label} contains blank Invoice Line ID values."
        )

    if ids.duplicated().any():
        raise ValueError(
            f"{label} Invoice Line ID values must be unique."
        )


def generate_contract_pricing_results(
    invoice,
    weight_results,
    contract_rates,
    *,
    tolerance=0.01,
):
    """
    Generate one contract pricing result per invoice line.

    Weight evidence is joined by Invoice Line ID, never by row
    position. Missing evidence requires review.

    This function does not modify existing audit exposure.
    """

    _validate_line_ids(invoice, "Invoice")
    _validate_line_ids(weight_results, "Weight results")

    if not isinstance(contract_rates, pd.DataFrame):
        raise TypeError(
            "Contract rates must be a pandas DataFrame."
        )

    required_invoice_columns = {
        "Carrier ID",
        "Service Type",
        "Billed Zone",
        "Ship Date",
        "Currency",
        "Base Freight",
    }

    missing_invoice_columns = (
        required_invoice_columns - set(invoice.columns)
    )

    if missing_invoice_columns:
        raise ValueError(
            "Invoice is missing required columns: "
            + ", ".join(sorted(missing_invoice_columns))
        )

    required_weight_columns = {
        "Weight Status",
        "Weight Calculation Eligible",
        "Expected Chargeable Weight (kg)",
    }

    missing_weight_columns = (
        required_weight_columns - set(weight_results.columns)
    )

    if missing_weight_columns:
        raise ValueError(
            "Weight results are missing required columns: "
            + ", ".join(sorted(missing_weight_columns))
        )

    weights_by_id = {
        row["Invoice Line ID"]: row.to_dict()
        for _, row in weight_results.iterrows()
    }

    records = []

    for _, invoice_row in invoice.iterrows():
        shipment = invoice_row.to_dict()
        line_id = shipment["Invoice Line ID"]

        evidence = weights_by_id.get(line_id)

        if evidence is None:
            records.append({
                "Invoice Line ID": line_id,
                "AWB": shipment.get("AWB"),
                "Carrier ID": shipment.get("Carrier ID"),
                "Pricing Status": "review",
                "Pricing Review Reason": "weight_evidence_missing",
                "Expected Chargeable Weight (kg)": None,
                "Expected Base Freight": None,
                "Invoiced Base Freight": None,
                "Potential Contract Overcharge": None,
                "Rate Difference": None,
                "Currency": shipment.get("Currency"),
            })
            continue

        identity_mismatch = None

        for field, mismatch_reason, evidence_missing_reason, invoice_missing_reason in (
            (
                "Carrier ID",
                "weight_evidence_carrier_mismatch",
                "weight_evidence_carrier_missing",
                "invoice_carrier_missing",
            ),
            (
                "AWB",
                "weight_evidence_awb_mismatch",
                "weight_evidence_awb_missing",
                "invoice_awb_missing",
            ),
        ):
            if field not in evidence:
                continue

            invoice_value = shipment.get(field)
            evidence_value = evidence.get(field)

            invoice_missing = (
                pd.isna(invoice_value)
                or not str(invoice_value).strip()
            )

            evidence_missing = (
                pd.isna(evidence_value)
                or not str(evidence_value).strip()
            )

            if evidence_missing:
                identity_mismatch = evidence_missing_reason
                break

            if invoice_missing:
                identity_mismatch = invoice_missing_reason
                break

            invoice_text = str(invoice_value).strip()
            evidence_text = str(evidence_value).strip()

            if invoice_text != evidence_text:
                identity_mismatch = mismatch_reason
                break

        if identity_mismatch is not None:
            records.append({
                "Invoice Line ID": line_id,
                "AWB": shipment.get("AWB"),
                "Carrier ID": shipment.get("Carrier ID"),
                "Pricing Status": "review",
                "Pricing Review Reason": identity_mismatch,
                "Expected Chargeable Weight (kg)": None,
                "Expected Base Freight": None,
                "Invoiced Base Freight": None,
                "Potential Contract Overcharge": None,
                "Rate Difference": None,
                "Currency": shipment.get("Currency"),
            })
            continue

        shipment["Zone"] = shipment.get("Billed Zone")

        result = price_shipment(
            shipment,
            evidence,
            contract_rates,
            tolerance=tolerance,
        )

        records.append({
            "Invoice Line ID": line_id,
            "AWB": shipment.get("AWB"),
            "Carrier ID": shipment.get("Carrier ID"),
            "Pricing Status": result["status"],
            "Pricing Review Reason": result["reason"],
            "Expected Chargeable Weight (kg)": (
                evidence.get("Expected Chargeable Weight (kg)")
            ),
            "Expected Base Freight": result.get(
                "expected_base_freight"
            ),
            "Invoiced Base Freight": result.get(
                "invoiced_base_freight"
            ),
            "Potential Contract Overcharge": result.get(
                "potential_overcharge"
            ),
            "Rate Difference": result.get("rate_difference"),
            "Currency": result.get(
                "currency",
                shipment.get("Currency"),
            ),
        })

    return pd.DataFrame(
        records,
        columns=RESULT_COLUMNS,
    )

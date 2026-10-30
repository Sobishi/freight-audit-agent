"""Generate invoice-level delivery evidence reconciliation results."""

import pandas as pd

from audit_engine.delivery_evidence import normalize_delivery_evidence
from audit_engine.delivery_reconciliation import reconcile_delivery_evidence


RESULT_COLUMNS = [
    "Invoice Line ID",
    "AWB",
    "Delivery Status",
    "Matched Evidence Count",
    "Evidence Sources",
    "Has Signature Name",
    "Review Reason",
]


def _normalize_source(frame, source):
    """Normalize evidence records without changing the input DataFrame."""
    if frame is None:
        return []

    if not isinstance(frame, pd.DataFrame):
        raise TypeError(
            f"{source} must be a pandas DataFrame or None."
        )

    return [
        normalize_delivery_evidence(
            record,
            source=source,
        )
        for record in frame.to_dict(orient="records")
    ]


def generate_delivery_evidence_results(
    invoice,
    *,
    internal_tracker=None,
    carrier_tracking=None,
    alt_pod=None,
):
    """Produce one delivery evidence assessment per invoice line.

    Repeated invoice AWBs remain separate invoice lines.
    Missing evidence does not establish nondelivery or monetary exposure.
    """
    if not isinstance(invoice, pd.DataFrame):
        raise TypeError("Invoice must be a pandas DataFrame.")

    required_columns = {"Invoice Line ID", "AWB"}

    missing_columns = required_columns.difference(invoice.columns)

    if missing_columns:
        raise ValueError(
            f"Invoice missing required columns: {sorted(missing_columns)}"
        )

    line_ids = invoice["Invoice Line ID"]

    missing_ids = line_ids.map(
        lambda value: (
            pd.isna(value)
            or (
                isinstance(value, str)
                and not value.strip()
            )
        )
    )

    if missing_ids.any():
        raise ValueError("Invoice contains missing Invoice Line ID.")

    if line_ids.duplicated().any():
        raise ValueError("Invoice contains duplicate Invoice Line ID.")

    evidence_records = []

    evidence_records.extend(
        _normalize_source(internal_tracker, "internal_tracker")
    )

    evidence_records.extend(
        _normalize_source(carrier_tracking, "carrier_tracking")
    )

    evidence_records.extend(
        _normalize_source(alt_pod, "alt_pod")
    )

    evidence_by_awb = {}

    for record in evidence_records:
        awb = record.get("awb")

        if not isinstance(awb, str) or not awb.strip():
            continue

        evidence_by_awb.setdefault(awb.strip(), []).append(record)

    results = []

    for _, shipment in invoice.iterrows():
        shipment_awb = shipment["AWB"]

        if isinstance(shipment_awb, str):
            matching_records = evidence_by_awb.get(
                shipment_awb.strip(),
                [],
            )
        else:
            matching_records = []

        invoice_carrier = shipment.get("Carrier")

        def carrier_key(value):
            if not isinstance(value, str):
                return None
            cleaned = value.strip().casefold()
            return cleaned or None

        invoice_carrier_key = carrier_key(invoice_carrier)

        verified_records = []
        carrier_review_reasons = set()
        unverified_carrier_records = []

        for record in matching_records:
            evidence_carrier_key = carrier_key(record.get("carrier"))

            if (
                invoice_carrier_key is None
                and evidence_carrier_key is None
            ):
                verified_records.append(record)

            elif (
                invoice_carrier_key is not None
                and invoice_carrier_key == evidence_carrier_key
            ):
                verified_records.append(record)

            elif invoice_carrier_key is None:
                carrier_review_reasons.add("missing_invoice_carrier")

            elif evidence_carrier_key is None:
                carrier_review_reasons.add("missing_evidence_carrier")
                unverified_carrier_records.append(record)

            else:
                carrier_review_reasons.add("carrier_mismatch")

        assessment = reconcile_delivery_evidence(
            shipment_awb,
            verified_records,
        )

        review_reasons = set(carrier_review_reasons)

        verified_statuses = {
            record["delivery_status"]
            for record in verified_records
        }

        unverified_statuses = {
            record["delivery_status"]
            for record in unverified_carrier_records
        }

        if (
            "not_delivered" in verified_statuses
            and "delivered" in unverified_statuses
        ):
            review_reasons.add(
                "unverified_delivery_status_conflict"
            )

        if carrier_review_reasons:
            assessment["delivery_status"] = "review"

        elif assessment["delivery_status"] == "review":
            review_reasons.add("delivery_evidence_review")

        results.append({
            "Invoice Line ID": shipment["Invoice Line ID"],
            "AWB": shipment["AWB"],
            "Delivery Status": assessment["delivery_status"],
            "Matched Evidence Count": assessment["matched_evidence_count"],
            "Evidence Sources": "; ".join(assessment["sources"]),
            "Has Signature Name": assessment["has_signature_name"],
            "Review Reason": "; ".join(sorted(review_reasons)),
        })

    return pd.DataFrame(results, columns=RESULT_COLUMNS)

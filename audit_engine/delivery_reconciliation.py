"""Conservative reconciliation of normalized delivery evidence."""

from collections.abc import Mapping


KNOWN_STATUSES = frozenset({
    "delivered",
    "not_delivered",
    "unknown",
})


def _clean_awb(value):
    """Normalize AWB identity without allowing partial matches."""
    if not isinstance(value, str):
        return None

    value = value.strip()
    return value if value else None


def reconcile_delivery_evidence(awb, evidence_records):
    """Assess delivery evidence for one shipment AWB.

    This function evaluates reported delivery observations.
    It does not authenticate POD documents or establish monetary exposure.
    """
    shipment_awb = _clean_awb(awb)

    if shipment_awb is None:
        return {
            "delivery_status": "review",
            "matched_evidence_count": 0,
            "sources": [],
            "has_signature_name": False,
        }

    matched = [
        record
        for record in evidence_records
        if (
            isinstance(record, Mapping)
            and _clean_awb(record.get("awb")) == shipment_awb
        )
    ]

    if not matched:
        return {
            "delivery_status": "missing_evidence",
            "matched_evidence_count": 0,
            "sources": [],
            "has_signature_name": False,
        }

    statuses = {
        record.get("delivery_status")
        for record in matched
        if isinstance(record.get("delivery_status"), str)
    }

    if (
        "delivered" in statuses
        and "not_delivered" in statuses
    ):
        delivery_status = "conflicting_evidence"

    elif not statuses or not statuses.issubset(KNOWN_STATUSES):
        delivery_status = "review"

    elif "unknown" in statuses:
        delivery_status = "review"

    elif statuses == {"delivered"}:
        delivery_status = "confirmed"

    elif statuses == {"not_delivered"}:
        delivery_status = "not_confirmed"

    else:
        delivery_status = "review"

    if delivery_status == "confirmed":
        dates = {
            record.get("delivery_date")
            for record in matched
            if isinstance(record.get("delivery_date"), str)
            and record["delivery_date"].strip()
        }

        signatories = {
            record["signed_by"].strip().casefold()
            for record in matched
            if isinstance(record.get("signed_by"), str)
            and record["signed_by"].strip()
        }

        if len(dates) > 1 or len(signatories) > 1:
            delivery_status = "review"

        if any(
            record.get("delivery_status") not in KNOWN_STATUSES
            for record in matched
        ):
            delivery_status = "review"

    sources = sorted({
        record["source"]
        for record in matched
        if isinstance(record.get("source"), str)
        and record["source"].strip()
    })

    has_signature_name = any(
        isinstance(record.get("signed_by"), str)
        and bool(record["signed_by"].strip())
        for record in matched
    )

    return {
        "delivery_status": delivery_status,
        "matched_evidence_count": len(matched),
        "sources": sources,
        "has_signature_name": has_signature_name,
    }

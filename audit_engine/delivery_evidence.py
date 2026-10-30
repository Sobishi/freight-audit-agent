"""Normalize delivery evidence from supported shipment data sources."""

from datetime import date, datetime
from collections.abc import Mapping

import pandas as pd


SUPPORTED_SOURCES = frozenset({
    "carrier_tracking",
    "internal_tracker",
    "alt_pod",
})

DELIVERED_STATUSES = frozenset({
    "delivered",
})

NOT_DELIVERED_STATUSES = frozenset({
    "in transit",
    "in-transit",
    "out for delivery",
    "pending",
    "exception",
    "failed delivery",
    "delivery attempted",
    "returned",
    "return to sender",
})


def _clean_text(value):
    """Return trimmed text or None for missing values."""
    if value is None:
        return None

    if not isinstance(value, (str, int, float, date, datetime)):
        return None

    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        return None

    text = str(value).strip()

    if not text or text.lower() in {"nan", "nat", "none"}:
        return None

    return text


def _normalize_date(value):
    """Return an ISO date or None when the date cannot be interpreted."""
    if isinstance(value, (datetime, date)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()

    text = _clean_text(value)

    if text is None:
        return None

    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def _normalize_status(record, source):
    """Classify explicit status evidence without inferring delivery."""
    fields = {
        "carrier_tracking": ("Delivery Status", "Status"),
        "internal_tracker": ("Status",),
        "alt_pod": ("Status", "Last Scan Text"),
    }[source]

    statuses = [
        _clean_text(record.get(field))
        for field in fields
    ]

    statuses = [
        status.lower()
        for status in statuses
        if status is not None
    ]

    if not statuses:
        return "unknown"

    if all(status in DELIVERED_STATUSES for status in statuses):
        return "delivered"

    if all(status in NOT_DELIVERED_STATUSES for status in statuses):
        return "not_delivered"

    return "unknown"


def normalize_delivery_evidence(record, *, source):
    """Normalize one evidence record while preserving its source.

    A recorded signatory name is not verification of a signed POD document.
    """
    if source not in SUPPORTED_SOURCES:
        raise ValueError(
            f"Unsupported delivery evidence source: {source}"
        )

    if not isinstance(record, Mapping):
        raise TypeError("Delivery evidence record must be a mapping.")

    date_field = (
        "Last Scan Date"
        if source == "alt_pod"
        else "Delivery Date"
    )

    signature_field = (
        "POD Signed By"
        if source == "internal_tracker"
        else "Signed By"
    )

    signed_by = _clean_text(record.get(signature_field))

    return {
        "awb": _clean_text(record.get("AWB")),
        "carrier": _clean_text(record.get("Carrier")),
        "source": source,
        "delivery_status": _normalize_status(record, source),
        "delivery_date": _normalize_date(record.get(date_field)),
        "signed_by": signed_by,
        "has_signature_name": signed_by is not None,
    }

"""R5 shipment delivery evidence reconciliation tests."""

from audit_engine.delivery_reconciliation import reconcile_delivery_evidence


def evidence(awb, source, status, signed_by=None):
    return {
        "awb": awb,
        "source": source,
        "delivery_status": status,
        "delivery_date": "2026-09-23",
        "signed_by": signed_by,
        "has_signature_name": signed_by is not None,
    }


def test_confirmed_delivery_with_carrier_evidence():
    records = [
        evidence(
            "NBX001",
            "carrier_tracking",
            "delivered",
            signed_by="Ivy Lane",
        )
    ]

    result = reconcile_delivery_evidence("NBX001", records)

    assert result["delivery_status"] == "confirmed"
    assert result["matched_evidence_count"] == 1
    assert result["sources"] == ["carrier_tracking"]
    assert result["has_signature_name"] is True


def test_missing_evidence_is_not_nondelivery():
    result = reconcile_delivery_evidence("NBX002", [])

    assert result["delivery_status"] == "missing_evidence"
    assert result["matched_evidence_count"] == 0
    assert result["has_signature_name"] is False


def test_other_awb_evidence_is_ignored():
    records = [
        evidence("NBX999", "carrier_tracking", "delivered")
    ]

    result = reconcile_delivery_evidence("NBX003", records)

    assert result["delivery_status"] == "missing_evidence"
    assert result["matched_evidence_count"] == 0


def test_conflicting_delivery_observations_require_review():
    records = [
        evidence("NBX004", "carrier_tracking", "delivered"),
        evidence("NBX004", "alt_pod", "not_delivered"),
    ]

    result = reconcile_delivery_evidence("NBX004", records)

    assert result["delivery_status"] == "conflicting_evidence"
    assert result["matched_evidence_count"] == 2


def test_in_transit_evidence_does_not_confirm_delivery():
    records = [
        evidence("NBX005", "carrier_tracking", "not_delivered")
    ]

    result = reconcile_delivery_evidence("NBX005", records)

    assert result["delivery_status"] == "not_confirmed"


def test_unknown_evidence_requires_review():
    records = [
        evidence("NBX006", "carrier_tracking", "unknown")
    ]

    result = reconcile_delivery_evidence("NBX006", records)

    assert result["delivery_status"] == "review"


def test_duplicate_identical_evidence_does_not_create_extra_confirmation():
    record = evidence(
        "NBX007",
        "carrier_tracking",
        "delivered",
    )

    result = reconcile_delivery_evidence(
        "NBX007",
        [record, dict(record)],
    )

    assert result["delivery_status"] == "confirmed"
    assert result["matched_evidence_count"] == 2
    assert result["sources"] == ["carrier_tracking"]


def test_missing_invoice_awb_cannot_match_evidence():
    records = [
        evidence(None, "carrier_tracking", "delivered")
    ]

    result = reconcile_delivery_evidence(None, records)

    assert result["delivery_status"] == "review"
    assert result["matched_evidence_count"] == 0


def test_conflicting_delivery_dates_require_review():
    first = evidence(
        "NBX008",
        "carrier_tracking",
        "delivered",
        signed_by="Ivy Lane",
    )

    second = evidence(
        "NBX008",
        "alt_pod",
        "delivered",
        signed_by="Ivy Lane",
    )
    second["delivery_date"] = "2026-09-24"

    result = reconcile_delivery_evidence(
        "NBX008",
        [first, second],
    )

    assert result["delivery_status"] == "review"


def test_conflicting_signatories_require_review():
    first = evidence(
        "NBX009",
        "carrier_tracking",
        "delivered",
        signed_by="Ivy Lane",
    )

    second = evidence(
        "NBX009",
        "internal_tracker",
        "delivered",
        signed_by="Jonah Quinn",
    )

    result = reconcile_delivery_evidence(
        "NBX009",
        [first, second],
    )

    assert result["delivery_status"] == "review"


def test_missing_status_cannot_strengthen_confirmation():
    first = evidence(
        "NBX010",
        "carrier_tracking",
        "delivered",
    )

    second = evidence(
        "NBX010",
        "internal_tracker",
        None,
    )

    result = reconcile_delivery_evidence(
        "NBX010",
        [first, second],
    )

    assert result["delivery_status"] == "review"


def test_identical_duplicate_records_do_not_create_conflict():
    record = evidence(
        "NBX011",
        "carrier_tracking",
        "delivered",
        signed_by="Ivy Lane",
    )

    result = reconcile_delivery_evidence(
        "NBX011",
        [record, dict(record)],
    )

    assert result["delivery_status"] == "confirmed"
    assert result["matched_evidence_count"] == 2


def test_unrelated_awb_conflict_does_not_affect_shipment():
    records = [
        evidence("NBX012", "carrier_tracking", "delivered"),
        evidence("NBX999", "alt_pod", "not_delivered"),
    ]

    result = reconcile_delivery_evidence(
        "NBX012",
        records,
    )

    assert result["delivery_status"] == "confirmed"
    assert result["matched_evidence_count"] == 1

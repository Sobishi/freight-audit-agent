"""R5 delivery evidence normalization tests."""

from audit_engine.delivery_evidence import normalize_delivery_evidence


def test_normalizes_carrier_tracking_delivery():
    record = {
        "AWB": " NBX9074924207 ",
        "Status": "Delivered",
        "Delivery Status": "Delivered",
        "Delivery Date": "2026-09-23",
        "Signed By": "Ivy Lane",
    }

    result = normalize_delivery_evidence(
        record,
        source="carrier_tracking",
    )

    assert result["awb"] == "NBX9074924207"
    assert result["source"] == "carrier_tracking"
    assert result["delivery_status"] == "delivered"
    assert result["delivery_date"] == "2026-09-23"
    assert result["signed_by"] == "Ivy Lane"
    assert result["has_signature_name"] is True


def test_normalizes_alternative_pod_fields():
    record = {
        "AWB": "NBX8855282876",
        "Status": "Delivered",
        "Last Scan Date": "2026-09-04",
        "Last Scan Text": "Delivered",
        "Signed By": "Marcus Fenwick",
    }

    result = normalize_delivery_evidence(
        record,
        source="alt_pod",
    )

    assert result["source"] == "alt_pod"
    assert result["delivery_status"] == "delivered"
    assert result["delivery_date"] == "2026-09-04"
    assert result["signed_by"] == "Marcus Fenwick"


def test_missing_signature_is_not_treated_as_signed_pod():
    record = {
        "AWB": "NBX001",
        "Status": "Delivered",
        "Delivery Status": "Delivered",
        "Delivery Date": "2026-09-23",
        "Signed By": None,
    }

    result = normalize_delivery_evidence(
        record,
        source="carrier_tracking",
    )

    assert result["delivery_status"] == "delivered"
    assert result["has_signature_name"] is False


def test_normalizes_internal_tracker_fields():
    record = {
        "AWB": "NBX002",
        "Status": "Delivered",
        "Delivery Date": "2026-09-23",
        "POD Signed By": "Ivy Lane",
    }

    result = normalize_delivery_evidence(
        record,
        source="internal_tracker",
    )

    assert result["source"] == "internal_tracker"
    assert result["delivery_status"] == "delivered"
    assert result["signed_by"] == "Ivy Lane"


def test_unknown_delivery_status_requires_review():
    record = {
        "AWB": "NBX003",
        "Status": "Investigation Pending",
        "Delivery Date": None,
        "Signed By": None,
    }

    result = normalize_delivery_evidence(
        record,
        source="carrier_tracking",
    )

    assert result["delivery_status"] == "unknown"


def test_rejects_unsupported_evidence_source():
    record = {
        "AWB": "NBX004",
        "Status": "Delivered",
    }

    try:
        normalize_delivery_evidence(
            record,
            source="unknown_source",
        )
    except ValueError as error:
        assert "Unsupported delivery evidence source" in str(error)
    else:
        raise AssertionError(
            "Unsupported evidence source was accepted."
        )


def test_conflicting_carrier_statuses_are_unknown():
    record = {
        "AWB": "NBX005",
        "Status": "Delivered",
        "Delivery Status": "In Transit",
        "Delivery Date": "2026-09-23",
        "Signed By": "Ivy Lane",
    }

    result = normalize_delivery_evidence(
        record,
        source="carrier_tracking",
    )

    assert result["delivery_status"] == "unknown"


def test_missing_awb_does_not_create_matchable_identity():
    record = {
        "AWB": "   ",
        "Status": "Delivered",
        "Delivery Date": "2026-09-23",
        "Signed By": "Ivy Lane",
    }

    result = normalize_delivery_evidence(
        record,
        source="internal_tracker",
    )

    assert result["awb"] is None


def test_invalid_delivery_date_is_not_preserved_as_valid():
    record = {
        "AWB": "NBX006",
        "Status": "Delivered",
        "Delivery Date": "2026-02-30",
        "Signed By": "Ivy Lane",
    }

    result = normalize_delivery_evidence(
        record,
        source="carrier_tracking",
    )

    assert result["delivery_date"] is None


def test_missing_delivery_status_is_unknown():
    record = {
        "AWB": "NBX007",
        "Status": None,
        "Delivery Status": None,
        "Delivery Date": "2026-09-23",
        "Signed By": "Ivy Lane",
    }

    result = normalize_delivery_evidence(
        record,
        source="carrier_tracking",
    )

    assert result["delivery_status"] == "unknown"


def test_alt_pod_scan_text_cannot_override_conflicting_status():
    record = {
        "AWB": "NBX008",
        "Status": "In Transit",
        "Last Scan Text": "Delivered",
        "Last Scan Date": "2026-09-23",
        "Signed By": "Ivy Lane",
    }

    result = normalize_delivery_evidence(
        record,
        source="alt_pod",
    )

    assert result["delivery_status"] == "unknown"


def test_normalization_preserves_carrier_identity():
    record = {
        "AWB": "NBX100",
        "Carrier": " Northbridge Express ",
        "Status": "Delivered",
        "Delivery Status": "Delivered",
    }

    result = normalize_delivery_evidence(
        record,
        source="carrier_tracking",
    )

    assert result["carrier"] == "Northbridge Express"


def test_normalization_preserves_missing_carrier():
    record = {
        "AWB": "NBX101",
        "Status": "Delivered",
    }

    result = normalize_delivery_evidence(
        record,
        source="alt_pod",
    )

    assert result["carrier"] is None

"""R5 batch delivery evidence reconciliation tests."""

import pandas as pd

from audit_engine.delivery_reporting import generate_delivery_evidence_results


def test_batch_preserves_duplicate_invoice_awbs():
    invoice = pd.DataFrame([
        {"Invoice Line ID": 1, "AWB": "NBX001"},
        {"Invoice Line ID": 2, "AWB": "NBX001"},
        {"Invoice Line ID": 3, "AWB": "NBX002"},
    ])

    carrier_tracking = pd.DataFrame([
        {
            "AWB": "NBX001",
            "Status": "Delivered",
            "Delivery Status": "Delivered",
            "Delivery Date": "2026-09-23",
            "Signed By": "Ivy Lane",
        }
    ])

    result = generate_delivery_evidence_results(
        invoice,
        carrier_tracking=carrier_tracking,
    )

    assert len(result) == 3
    assert result["Invoice Line ID"].tolist() == [1, 2, 3]
    assert result["Delivery Status"].tolist() == [
        "confirmed",
        "confirmed",
        "missing_evidence",
    ]


def test_batch_combines_three_evidence_sources():
    invoice = pd.DataFrame([
        {"Invoice Line ID": 1, "AWB": "NBX003"},
    ])

    internal_tracker = pd.DataFrame([
        {
            "AWB": "NBX003",
            "Status": "Delivered",
            "Delivery Date": "2026-09-23",
            "POD Signed By": "Ivy Lane",
        }
    ])

    carrier_tracking = pd.DataFrame([
        {
            "AWB": "NBX003",
            "Status": "Delivered",
            "Delivery Status": "Delivered",
            "Delivery Date": "2026-09-23",
            "Signed By": "Ivy Lane",
        }
    ])

    alt_pod = pd.DataFrame([
        {
            "AWB": "NBX003",
            "Status": "Delivered",
            "Last Scan Text": "Delivered",
            "Last Scan Date": "2026-09-23",
            "Signed By": "Ivy Lane",
        }
    ])

    result = generate_delivery_evidence_results(
        invoice,
        internal_tracker=internal_tracker,
        carrier_tracking=carrier_tracking,
        alt_pod=alt_pod,
    )

    assert result.loc[0, "Delivery Status"] == "confirmed"
    assert result.loc[0, "Matched Evidence Count"] == 3
    assert result.loc[0, "Evidence Sources"] == (
        "alt_pod; carrier_tracking; internal_tracker"
    )


def test_batch_detects_conflicting_sources():
    invoice = pd.DataFrame([
        {"Invoice Line ID": 1, "AWB": "NBX004"},
    ])

    carrier_tracking = pd.DataFrame([
        {
            "AWB": "NBX004",
            "Status": "Delivered",
            "Delivery Status": "Delivered",
        }
    ])

    alt_pod = pd.DataFrame([
        {
            "AWB": "NBX004",
            "Status": "In Transit",
            "Last Scan Text": "In Transit",
        }
    ])

    result = generate_delivery_evidence_results(
        invoice,
        carrier_tracking=carrier_tracking,
        alt_pod=alt_pod,
    )

    assert result.loc[0, "Delivery Status"] == "conflicting_evidence"


def test_batch_missing_awb_requires_review():
    invoice = pd.DataFrame([
        {"Invoice Line ID": 1, "AWB": None},
    ])

    result = generate_delivery_evidence_results(invoice)

    assert result.loc[0, "Delivery Status"] == "review"
    assert result.loc[0, "Matched Evidence Count"] == 0


def test_batch_without_evidence_sources_is_safe():
    invoice = pd.DataFrame([
        {"Invoice Line ID": 1, "AWB": "NBX005"},
    ])

    result = generate_delivery_evidence_results(invoice)

    assert result.loc[0, "Delivery Status"] == "missing_evidence"
    assert result.loc[0, "Matched Evidence Count"] == 0


def test_batch_does_not_mutate_source_dataframes():
    invoice = pd.DataFrame([
        {"Invoice Line ID": 1, "AWB": "NBX006"},
    ])

    carrier_tracking = pd.DataFrame([
        {
            "AWB": "NBX006",
            "Status": "Delivered",
            "Delivery Status": "Delivered",
        }
    ])

    original_invoice = invoice.copy(deep=True)
    original_tracking = carrier_tracking.copy(deep=True)

    generate_delivery_evidence_results(
        invoice,
        carrier_tracking=carrier_tracking,
    )

    pd.testing.assert_frame_equal(invoice, original_invoice)
    pd.testing.assert_frame_equal(carrier_tracking, original_tracking)


def test_batch_rejects_duplicate_invoice_line_ids():
    invoice = pd.DataFrame([
        {"Invoice Line ID": 1, "AWB": "NBX001"},
        {"Invoice Line ID": 1, "AWB": "NBX002"},
    ])

    try:
        generate_delivery_evidence_results(invoice)
    except ValueError as error:
        assert "duplicate Invoice Line ID" in str(error)
    else:
        raise AssertionError("Duplicate invoice line IDs were accepted.")


def test_batch_rejects_missing_invoice_line_id():
    invoice = pd.DataFrame([
        {"Invoice Line ID": None, "AWB": "NBX001"},
    ])

    try:
        generate_delivery_evidence_results(invoice)
    except ValueError as error:
        assert "missing Invoice Line ID" in str(error)
    else:
        raise AssertionError("Missing invoice line ID was accepted.")


def test_batch_rejects_blank_invoice_line_id():
    invoice = pd.DataFrame([
        {"Invoice Line ID": "   ", "AWB": "NBX001"},
    ])

    try:
        generate_delivery_evidence_results(invoice)
    except ValueError as error:
        assert "missing Invoice Line ID" in str(error)
    else:
        raise AssertionError("Blank invoice line ID was accepted.")


def test_batch_accepts_empty_invoice_with_required_columns():
    invoice = pd.DataFrame(
        columns=["Invoice Line ID", "AWB"]
    )

    result = generate_delivery_evidence_results(invoice)

    assert result.empty
    assert result.columns.tolist() == [
        "Invoice Line ID",
        "AWB",
        "Delivery Status",
        "Matched Evidence Count",
        "Evidence Sources",
        "Has Signature Name",
        "Review Reason",
    ]


def test_batch_ignores_evidence_with_missing_awb():
    invoice = pd.DataFrame([
        {"Invoice Line ID": 1, "AWB": "NBX020"},
    ])

    carrier_tracking = pd.DataFrame([
        {
            "AWB": None,
            "Status": "Delivered",
            "Delivery Status": "Delivered",
        }
    ])

    result = generate_delivery_evidence_results(
        invoice,
        carrier_tracking=carrier_tracking,
    )

    assert result.loc[0, "Delivery Status"] == "missing_evidence"
    assert result.loc[0, "Matched Evidence Count"] == 0


def test_batch_matches_awb_after_whitespace_normalization():
    invoice = pd.DataFrame([
        {"Invoice Line ID": 1, "AWB": " NBX021 "},
    ])

    carrier_tracking = pd.DataFrame([
        {
            "AWB": "NBX021",
            "Status": "Delivered",
            "Delivery Status": "Delivered",
        }
    ])

    result = generate_delivery_evidence_results(
        invoice,
        carrier_tracking=carrier_tracking,
    )

    assert result.loc[0, "Delivery Status"] == "confirmed"
    assert result.loc[0, "Matched Evidence Count"] == 1


def test_batch_preserves_duplicate_evidence_count_without_extra_sources():
    invoice = pd.DataFrame([
        {"Invoice Line ID": 1, "AWB": "NBX022"},
    ])

    carrier_tracking = pd.DataFrame([
        {
            "AWB": "NBX022",
            "Status": "Delivered",
            "Delivery Status": "Delivered",
        },
        {
            "AWB": "NBX022",
            "Status": "Delivered",
            "Delivery Status": "Delivered",
        },
    ])

    result = generate_delivery_evidence_results(
        invoice,
        carrier_tracking=carrier_tracking,
    )

    assert result.loc[0, "Delivery Status"] == "confirmed"
    assert result.loc[0, "Matched Evidence Count"] == 2
    assert result.loc[0, "Evidence Sources"] == "carrier_tracking"


def test_batch_excludes_evidence_from_different_carrier():
    invoice = pd.DataFrame([
        {
            "Invoice Line ID": 1,
            "AWB": "SHARED001",
            "Carrier": "Northbridge Express",
        }
    ])

    carrier_tracking = pd.DataFrame([
        {
            "AWB": "SHARED001",
            "Carrier": "Other Carrier",
            "Status": "Delivered",
            "Delivery Status": "Delivered",
        }
    ])

    result = generate_delivery_evidence_results(
        invoice,
        carrier_tracking=carrier_tracking,
    )

    assert result.loc[0, "Delivery Status"] == "review"
    assert result.loc[0, "Matched Evidence Count"] == 0


def test_batch_matches_same_carrier_case_insensitively():
    invoice = pd.DataFrame([
        {
            "Invoice Line ID": 1,
            "AWB": "NBX102",
            "Carrier": "Northbridge Express",
        }
    ])

    carrier_tracking = pd.DataFrame([
        {
            "AWB": "NBX102",
            "Carrier": " northbridge express ",
            "Status": "Delivered",
            "Delivery Status": "Delivered",
        }
    ])

    result = generate_delivery_evidence_results(
        invoice,
        carrier_tracking=carrier_tracking,
    )

    assert result.loc[0, "Delivery Status"] == "confirmed"
    assert result.loc[0, "Matched Evidence Count"] == 1


def test_batch_missing_evidence_carrier_requires_review():
    invoice = pd.DataFrame([
        {
            "Invoice Line ID": 1,
            "AWB": "NBX103",
            "Carrier": "Northbridge Express",
        }
    ])

    alt_pod = pd.DataFrame([
        {
            "AWB": "NBX103",
            "Status": "Delivered",
            "Last Scan Text": "Delivered",
        }
    ])

    result = generate_delivery_evidence_results(
        invoice,
        alt_pod=alt_pod,
    )

    assert result.loc[0, "Delivery Status"] == "review"
    assert result.loc[0, "Matched Evidence Count"] == 0


def test_batch_reviews_mixed_matching_and_mismatched_carriers():
    invoice = pd.DataFrame([
        {
            "Invoice Line ID": 1,
            "AWB": "SHARED200",
            "Carrier": "Northbridge Express",
        }
    ])

    carrier_tracking = pd.DataFrame([
        {
            "AWB": "SHARED200",
            "Carrier": "Northbridge Express",
            "Status": "Delivered",
            "Delivery Status": "Delivered",
        },
        {
            "AWB": "SHARED200",
            "Carrier": "Other Carrier",
            "Status": "Delivered",
            "Delivery Status": "Delivered",
        },
    ])

    result = generate_delivery_evidence_results(
        invoice,
        carrier_tracking=carrier_tracking,
    )

    assert result.loc[0, "Delivery Status"] == "review"
    assert result.loc[0, "Matched Evidence Count"] == 1
    assert result.loc[0, "Evidence Sources"] == "carrier_tracking"


def test_batch_reviews_known_evidence_carrier_when_invoice_carrier_missing():
    invoice = pd.DataFrame([
        {
            "Invoice Line ID": 1,
            "AWB": "NBX201",
            "Carrier": None,
        }
    ])

    carrier_tracking = pd.DataFrame([
        {
            "AWB": "NBX201",
            "Carrier": "Northbridge Express",
            "Status": "Delivered",
            "Delivery Status": "Delivered",
        }
    ])

    result = generate_delivery_evidence_results(
        invoice,
        carrier_tracking=carrier_tracking,
    )

    assert result.loc[0, "Delivery Status"] == "review"
    assert result.loc[0, "Matched Evidence Count"] == 0


def test_batch_reviews_matching_and_unidentified_carrier_evidence():
    invoice = pd.DataFrame([
        {
            "Invoice Line ID": 1,
            "AWB": "NBX202",
            "Carrier": "Northbridge Express",
        }
    ])

    carrier_tracking = pd.DataFrame([
        {
            "AWB": "NBX202",
            "Carrier": "Northbridge Express",
            "Status": "Delivered",
            "Delivery Status": "Delivered",
        }
    ])

    alt_pod = pd.DataFrame([
        {
            "AWB": "NBX202",
            "Status": "Delivered",
            "Last Scan Text": "Delivered",
        }
    ])

    result = generate_delivery_evidence_results(
        invoice,
        carrier_tracking=carrier_tracking,
        alt_pod=alt_pod,
    )

    assert result.loc[0, "Delivery Status"] == "review"
    assert result.loc[0, "Matched Evidence Count"] == 1
    assert result.loc[0, "Evidence Sources"] == "carrier_tracking"


def test_batch_reviews_mixed_matching_and_mismatched_carriers():
    invoice = pd.DataFrame([
        {
            "Invoice Line ID": 1,
            "AWB": "SHARED200",
            "Carrier": "Northbridge Express",
        }
    ])

    carrier_tracking = pd.DataFrame([
        {
            "AWB": "SHARED200",
            "Carrier": "Northbridge Express",
            "Status": "Delivered",
            "Delivery Status": "Delivered",
        },
        {
            "AWB": "SHARED200",
            "Carrier": "Other Carrier",
            "Status": "Delivered",
            "Delivery Status": "Delivered",
        },
    ])

    result = generate_delivery_evidence_results(
        invoice,
        carrier_tracking=carrier_tracking,
    )

    assert result.loc[0, "Delivery Status"] == "review"
    assert result.loc[0, "Matched Evidence Count"] == 1
    assert result.loc[0, "Evidence Sources"] == "carrier_tracking"


def test_batch_reviews_known_evidence_carrier_when_invoice_carrier_missing():
    invoice = pd.DataFrame([
        {
            "Invoice Line ID": 1,
            "AWB": "NBX201",
            "Carrier": None,
        }
    ])

    carrier_tracking = pd.DataFrame([
        {
            "AWB": "NBX201",
            "Carrier": "Northbridge Express",
            "Status": "Delivered",
            "Delivery Status": "Delivered",
        }
    ])

    result = generate_delivery_evidence_results(
        invoice,
        carrier_tracking=carrier_tracking,
    )

    assert result.loc[0, "Delivery Status"] == "review"
    assert result.loc[0, "Matched Evidence Count"] == 0


def test_batch_reviews_matching_and_unidentified_carrier_evidence():
    invoice = pd.DataFrame([
        {
            "Invoice Line ID": 1,
            "AWB": "NBX202",
            "Carrier": "Northbridge Express",
        }
    ])

    carrier_tracking = pd.DataFrame([
        {
            "AWB": "NBX202",
            "Carrier": "Northbridge Express",
            "Status": "Delivered",
            "Delivery Status": "Delivered",
        }
    ])

    alt_pod = pd.DataFrame([
        {
            "AWB": "NBX202",
            "Status": "Delivered",
            "Last Scan Text": "Delivered",
        }
    ])

    result = generate_delivery_evidence_results(
        invoice,
        carrier_tracking=carrier_tracking,
        alt_pod=alt_pod,
    )

    assert result.loc[0, "Delivery Status"] == "review"
    assert result.loc[0, "Matched Evidence Count"] == 1
    assert result.loc[0, "Evidence Sources"] == "carrier_tracking"


def test_batch_reports_carrier_mismatch_reason():
    invoice = pd.DataFrame([
        {
            "Invoice Line ID": 1,
            "AWB": "NBX300",
            "Carrier": "Northbridge Express",
        }
    ])

    carrier_tracking = pd.DataFrame([
        {
            "AWB": "NBX300",
            "Carrier": "Other Carrier",
            "Status": "Delivered",
            "Delivery Status": "Delivered",
        }
    ])

    result = generate_delivery_evidence_results(
        invoice,
        carrier_tracking=carrier_tracking,
    )

    assert result.loc[0, "Delivery Status"] == "review"
    assert result.loc[0, "Review Reason"] == "carrier_mismatch"


def test_batch_reports_missing_evidence_carrier_reason():
    invoice = pd.DataFrame([
        {
            "Invoice Line ID": 1,
            "AWB": "NBX301",
            "Carrier": "Northbridge Express",
        }
    ])

    alt_pod = pd.DataFrame([
        {
            "AWB": "NBX301",
            "Status": "Delivered",
            "Last Scan Text": "Delivered",
        }
    ])

    result = generate_delivery_evidence_results(
        invoice,
        alt_pod=alt_pod,
    )

    assert result.loc[0, "Delivery Status"] == "review"
    assert result.loc[0, "Review Reason"] == "missing_evidence_carrier"


def test_batch_confirmed_delivery_has_no_review_reason():
    invoice = pd.DataFrame([
        {
            "Invoice Line ID": 1,
            "AWB": "NBX302",
            "Carrier": "Northbridge Express",
        }
    ])

    carrier_tracking = pd.DataFrame([
        {
            "AWB": "NBX302",
            "Carrier": "Northbridge Express",
            "Status": "Delivered",
            "Delivery Status": "Delivered",
        }
    ])

    result = generate_delivery_evidence_results(
        invoice,
        carrier_tracking=carrier_tracking,
    )

    assert result.loc[0, "Delivery Status"] == "confirmed"
    assert result.loc[0, "Review Reason"] == ""


def test_batch_reports_multiple_carrier_review_reasons():
    invoice = pd.DataFrame([
        {
            "Invoice Line ID": 1,
            "AWB": "NBX400",
            "Carrier": "Northbridge Express",
        }
    ])

    carrier_tracking = pd.DataFrame([
        {
            "AWB": "NBX400",
            "Carrier": "Other Carrier",
            "Status": "Delivered",
            "Delivery Status": "Delivered",
        }
    ])

    alt_pod = pd.DataFrame([
        {
            "AWB": "NBX400",
            "Status": "Delivered",
            "Last Scan Text": "Delivered",
        }
    ])

    result = generate_delivery_evidence_results(
        invoice,
        carrier_tracking=carrier_tracking,
        alt_pod=alt_pod,
    )

    assert result.loc[0, "Delivery Status"] == "review"
    assert result.loc[0, "Matched Evidence Count"] == 0
    assert result.loc[0, "Review Reason"] == (
        "carrier_mismatch; missing_evidence_carrier"
    )


def test_batch_reports_missing_invoice_carrier_reason():
    invoice = pd.DataFrame([
        {
            "Invoice Line ID": 1,
            "AWB": "NBX401",
            "Carrier": None,
        }
    ])

    carrier_tracking = pd.DataFrame([
        {
            "AWB": "NBX401",
            "Carrier": "Northbridge Express",
            "Status": "Delivered",
            "Delivery Status": "Delivered",
        }
    ])

    result = generate_delivery_evidence_results(
        invoice,
        carrier_tracking=carrier_tracking,
    )

    assert result.loc[0, "Delivery Status"] == "review"
    assert result.loc[0, "Matched Evidence Count"] == 0
    assert result.loc[0, "Review Reason"] == "missing_invoice_carrier"


def test_batch_reports_general_evidence_review_reason():
    invoice = pd.DataFrame([
        {
            "Invoice Line ID": 1,
            "AWB": "NBX402",
            "Carrier": "Northbridge Express",
        }
    ])

    carrier_tracking = pd.DataFrame([
        {
            "AWB": "NBX402",
            "Carrier": "Northbridge Express",
            "Status": "Unknown",
            "Delivery Status": "Unknown",
        }
    ])

    result = generate_delivery_evidence_results(
        invoice,
        carrier_tracking=carrier_tracking,
    )

    assert result.loc[0, "Delivery Status"] == "review"
    assert result.loc[0, "Matched Evidence Count"] == 1
    assert result.loc[0, "Review Reason"] == "delivery_evidence_review"


def test_unverified_alt_pod_conflict_is_explicitly_reported():
    import pandas as pd
    from audit_engine.delivery_reporting import (
        generate_delivery_evidence_results,
    )

    invoice = pd.DataFrame([
        {
            "Invoice Line ID": 1,
            "AWB": "NBX-CONFLICT",
            "Carrier": "Northbridge Express",
            "Total": 100.0,
        }
    ])

    internal_tracker = pd.DataFrame([
        {
            "AWB": "NBX-CONFLICT",
            "Carrier": "Northbridge Express",
            "Status": "Pending POD",
        }
    ])

    carrier_tracking = pd.DataFrame([
        {
            "AWB": "NBX-CONFLICT",
            "Carrier": "Northbridge Express",
            "Status": "Exception",
            "Delivery Status": "Exception",
        }
    ])

    alt_pod = pd.DataFrame([
        {
            "AWB": "NBX-CONFLICT",
            "Status": "Delivered",
            "Last Scan Text": "Delivered",
            "Signed By": "Reception",
        }
    ])

    results = generate_delivery_evidence_results(
        invoice,
        internal_tracker=internal_tracker,
        carrier_tracking=carrier_tracking,
        alt_pod=alt_pod,
    )

    record = results.iloc[0]

    assert record["Delivery Status"] == "review"
    assert "missing_evidence_carrier" in record["Review Reason"]
    assert (
        "unverified_delivery_status_conflict"
        in record["Review Reason"]
    )

    assert record["Matched Evidence Count"] == 2
    assert record["Has Signature Name"] == False


def test_unknown_verified_status_does_not_create_supplementary_conflict():
    invoice = pd.DataFrame([
        {
            "Invoice Line ID": 1,
            "AWB": "NBX-UNKNOWN",
            "Carrier": "Northbridge Express",
        }
    ])

    carrier_tracking = pd.DataFrame([
        {
            "AWB": "NBX-UNKNOWN",
            "Carrier": "Northbridge Express",
            "Status": "Awaiting verification",
            "Delivery Status": "Awaiting verification",
        }
    ])

    alt_pod = pd.DataFrame([
        {
            "AWB": "NBX-UNKNOWN",
            "Status": "Delivered",
            "Last Scan Text": "Delivered",
        }
    ])

    result = generate_delivery_evidence_results(
        invoice,
        carrier_tracking=carrier_tracking,
        alt_pod=alt_pod,
    )

    record = result.iloc[0]

    assert record["Delivery Status"] == "review"
    assert "missing_evidence_carrier" in record["Review Reason"]
    assert (
        "unverified_delivery_status_conflict"
        not in record["Review Reason"]
    )


def test_verified_delivery_and_unverified_pending_status_do_not_conflict():
    invoice = pd.DataFrame([
        {
            "Invoice Line ID": 1,
            "AWB": "NBX-DELIVERED",
            "Carrier": "Northbridge Express",
        }
    ])

    carrier_tracking = pd.DataFrame([
        {
            "AWB": "NBX-DELIVERED",
            "Carrier": "Northbridge Express",
            "Status": "Delivered",
            "Delivery Status": "Delivered",
        }
    ])

    alt_pod = pd.DataFrame([
        {
            "AWB": "NBX-DELIVERED",
            "Status": "Pending",
            "Last Scan Text": "Pending",
        }
    ])

    result = generate_delivery_evidence_results(
        invoice,
        carrier_tracking=carrier_tracking,
        alt_pod=alt_pod,
    )

    record = result.iloc[0]

    assert record["Delivery Status"] == "review"
    assert record["Matched Evidence Count"] == 1
    assert "missing_evidence_carrier" in record["Review Reason"]
    assert (
        "unverified_delivery_status_conflict"
        not in record["Review Reason"]
    )


def test_different_carrier_delivery_claim_does_not_create_supplementary_conflict():
    invoice = pd.DataFrame([
        {
            "Invoice Line ID": 1,
            "AWB": "SHARED-CONFLICT",
            "Carrier": "Northbridge Express",
        }
    ])

    carrier_tracking = pd.DataFrame([
        {
            "AWB": "SHARED-CONFLICT",
            "Carrier": "Northbridge Express",
            "Status": "Exception",
            "Delivery Status": "Exception",
        }
    ])

    alt_pod = pd.DataFrame([
        {
            "AWB": "SHARED-CONFLICT",
            "Carrier": "Other Carrier",
            "Status": "Delivered",
            "Last Scan Text": "Delivered",
        }
    ])

    result = generate_delivery_evidence_results(
        invoice,
        carrier_tracking=carrier_tracking,
        alt_pod=alt_pod,
    )

    record = result.iloc[0]

    assert record["Delivery Status"] == "review"
    assert record["Matched Evidence Count"] == 1
    assert "carrier_mismatch" in record["Review Reason"]
    assert (
        "unverified_delivery_status_conflict"
        not in record["Review Reason"]
    )

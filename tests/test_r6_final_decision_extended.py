"""R6 final decision integration and financial safeguards."""

from decimal import Decimal

import pandas as pd
import pytest

from audit_engine.exposure import finalize_payment_decisions


def invoice(
    ids=(1,),
    totals=(100,),
    credit_statuses=None,
    exclusions=None,
):
    count = len(ids)
    return pd.DataFrame({
        "Invoice Line ID": list(ids),
        "Total": list(totals),
        "Is Exact Duplicate Charge": [False] * count,
        "Needs Charge Review": [False] * count,
        "Credit Match Status": (
            credit_statuses
            if credit_statuses is not None
            else ["Not a Credit"] * count
        ),
        "Excluded From Exposure": (
            exclusions
            if exclusions is not None
            else [False] * count
        ),
    })


def weight(ids, statuses):
    return pd.DataFrame({
        "Invoice Line ID": ids,
        "Weight Status": statuses,
        "Weight Comparison Status": [None] * len(ids),
    })


def pricing(ids, statuses, exposures):
    return pd.DataFrame({
        "Invoice Line ID": ids,
        "Pricing Status": statuses,
        "Potential Contract Overcharge": exposures,
    })


def delivery(ids, statuses):
    return pd.DataFrame({
        "Invoice Line ID": ids,
        "Delivery Status": statuses,
    })


def test_weight_review_requires_hold():
    result = finalize_payment_decisions(
        invoice(),
        weight_results=weight([1], ["review"]),
    )

    assert result.loc[0, "Final Payment Treatment"] == "Hold"
    assert result.loc[0, "Weight Check"] == "review"


def test_delivery_review_requires_hold():
    result = finalize_payment_decisions(
        invoice(),
        delivery_evidence_results=delivery([1], ["review"]),
    )

    assert result.loc[0, "Final Payment Treatment"] == "Hold"
    assert result.loc[0, "Delivery Check"] == "review"


def test_contract_pricing_overcharge_requires_hold():
    result = finalize_payment_decisions(
        invoice(),
        contract_pricing_results=pricing(
            [1],
            ["potential_overcharge"],
            [Decimal("15.00")],
        ),
    )

    assert result.loc[0, "Final Payment Treatment"] == "Hold"
    assert result.loc[0, "Contract Pricing Check"] == (
        "potential_overcharge"
    )


def test_unknown_contract_pricing_exposure_requires_hold():
    result = finalize_payment_decisions(
        invoice(),
        contract_pricing_results=pricing(
            [1], ["review"], [None]
        ),
    )

    assert result.loc[0, "Final Payment Treatment"] == "Hold"
    assert result.loc[0, "Contract Pricing Exposure Status"] == (
        "Unknown"
    )


def test_weight_and_delivery_align_by_invoice_line_id():
    result = finalize_payment_decisions(
        invoice(ids=(1, 2), totals=(100, 200)),
        weight_results=weight(
            [2, 1], ["review", "review"]
        ),
        delivery_evidence_results=delivery(
            [2, 1], ["review", "confirmed"]
        ),
    )

    by_id = result.set_index("Invoice Line ID")

    assert by_id.loc[1, "Delivery Check"] == "confirmed"
    assert by_id.loc[2, "Delivery Check"] == "review"


def test_rejects_mismatched_delivery_line_ids():
    with pytest.raises(ValueError, match="Invoice Line ID"):
        finalize_payment_decisions(
            invoice(),
            delivery_evidence_results=delivery(
                [999], ["delivered"]
            ),
        )


def test_rejects_duplicate_weight_line_ids():
    with pytest.raises(ValueError, match="Invoice Line ID"):
        finalize_payment_decisions(
            invoice(),
            weight_results=weight(
                [1, 1], ["review", "review"]
            ),
        )


def test_inconsistent_credit_metadata_cannot_authorize_reversal():
    result = finalize_payment_decisions(
        invoice(
            credit_statuses=["Fully Reversed"],
            exclusions=[False],
        ),
    )

    assert result.loc[0, "Final Payment Treatment"] == "Hold"


def test_unrecognized_credit_status_requires_hold():
    result = finalize_payment_decisions(
        invoice(
            credit_statuses=["Unknown Credit State"],
            exclusions=[False],
        ),
    )

    assert result.loc[0, "Final Payment Treatment"] == "Hold"


def test_nonfinite_total_cannot_proceed():
    result = finalize_payment_decisions(
        invoice(totals=(float("nan"),)),
    )

    assert result.loc[0, "Final Payment Treatment"] == "Hold"


def test_zero_value_line_preserves_no_payment_treatment():
    result = finalize_payment_decisions(
        invoice(totals=(0,)),
    )

    assert result.loc[0, "Final Payment Treatment"] == (
        "No Payment - Zero"
    )


def test_matched_reversal_overrides_delivery_review():
    result = finalize_payment_decisions(
        invoice(
            credit_statuses=["Fully Reversed"],
            exclusions=[True],
        ),
        delivery_evidence_results=delivery([1], ["review"]),
    )

    assert result.loc[0, "Final Payment Treatment"] == (
        "No Payment - Reversed"
    )


def test_missing_modules_remain_explicitly_not_run():
    result = finalize_payment_decisions(invoice())

    assert result.loc[0, "Weight Check"] == "Not Run"
    assert result.loc[0, "Delivery Check"] == "Not Run"
    assert result.loc[0, "Contract Pricing Check"] == "Not Run"
    assert result.loc[0, "Decision Completeness"] == "Partial"

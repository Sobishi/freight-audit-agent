"""R6 final payment decision contract: RED tests."""

from decimal import Decimal

import pandas as pd
import pytest

from audit_engine.exposure import finalize_payment_decisions


def invoice(
    ids=(1,),
    totals=(100.0,),
    credit_statuses=None,
    excluded=None,
):
    n = len(ids)

    if credit_statuses is None:
        credit_statuses = ["Not a Credit"] * n

    if excluded is None:
        excluded = [False] * n

    return pd.DataFrame({
        "Invoice Line ID": list(ids),
        "Total": list(totals),
        "Credit Match Status": credit_statuses,
        "Excluded From Exposure": excluded,
        "Is Exact Duplicate Charge": [False] * n,
        "Needs Charge Review": [False] * n,
    })


def tax_results(ids, statuses, exposures):
    return pd.DataFrame({
        "Invoice Line ID": ids,
        "Tax Status": statuses,
        "Potential Tax Overcharge": exposures,
    })


def surcharge_results(ids, statuses, exposures):
    return pd.DataFrame({
        "Invoice Line ID": ids,
        "Surcharge Status": statuses,
        "Potential Surcharge Overcharge": exposures,
    })


def test_clean_supplied_validations_can_proceed():
    result = finalize_payment_decisions(
        invoice(),
        tax_results=tax_results([1], ["matched"], [Decimal("0")]),
        surcharge_results=surcharge_results(
            [1], ["matched"], [Decimal("0")]
        ),
    )

    assert result.loc[0, "Final Payment Treatment"] == "Proceed"
    assert result.loc[0, "Tax Check"] == "matched"
    assert result.loc[0, "Surcharge Check"] == "matched"


def test_missing_optional_checks_are_not_reported_as_passed():
    result = finalize_payment_decisions(invoice())

    assert result.loc[0, "Tax Check"] == "Not Run"
    assert result.loc[0, "Surcharge Check"] == "Not Run"
    assert result.loc[0, "Decision Completeness"] == "Partial"


def test_tax_overcharge_requires_hold():
    result = finalize_payment_decisions(
        invoice(),
        tax_results=tax_results(
            [1], ["potential_overcharge"], [Decimal("2.50")]
        ),
    )

    assert result.loc[0, "Final Payment Treatment"] == "Hold"


def test_missing_tax_evidence_requires_hold_not_zero_exposure():
    result = finalize_payment_decisions(
        invoice(),
        tax_results=tax_results([1], ["review"], [None]),
    )

    assert result.loc[0, "Final Payment Treatment"] == "Hold"
    assert result.loc[0, "Tax Exposure Status"] == "Unknown"


def test_surcharge_results_align_by_invoice_line_id():
    result = finalize_payment_decisions(
        invoice(ids=(1, 2), totals=(100.0, 200.0)),
        surcharge_results=surcharge_results(
            [2, 1],
            ["potential_overcharge", "matched"],
            [Decimal("12.00"), Decimal("0")],
        ),
    )

    by_id = result.set_index("Invoice Line ID")

    assert by_id.loc[1, "Final Payment Treatment"] == "Proceed"
    assert by_id.loc[2, "Final Payment Treatment"] == "Hold"


def test_matched_reversal_takes_precedence_over_tax_review():
    result = finalize_payment_decisions(
        invoice(
            ids=(1,),
            totals=(107.50,),
            credit_statuses=["Fully Reversed"],
            excluded=[True],
        ),
        tax_results=tax_results([1], ["review"], [None]),
    )

    assert (
        result.loc[0, "Final Payment Treatment"]
        == "No Payment - Reversed"
    )


def test_unmatched_credit_requires_review():
    result = finalize_payment_decisions(
        invoice(
            ids=(1,),
            totals=(-107.50,),
            credit_statuses=["Unmatched Credit"],
            excluded=[False],
        ),
    )

    assert result.loc[0, "Final Payment Treatment"] == "Review Credit"


def test_rate_overcharge_overrides_preliminary_proceed():
    preliminary = pd.DataFrame({
        "Invoice Line ID": [1],
        "Payment Treatment": ["Proceed"],
        "Rate Exposure": [Decimal("20")],
        "Rate Exposure Status": ["Quantified"],
        "Combined Potential Exposure": [Decimal("20")],
    })

    result = finalize_payment_decisions(
        invoice(),
        combined_exposure=preliminary,
    )

    assert result.loc[0, "Final Payment Treatment"] == "Hold"


def test_rejects_mismatched_tax_line_ids():
    with pytest.raises(ValueError, match="Invoice Line ID"):
        finalize_payment_decisions(
            invoice(),
            tax_results=tax_results([999], ["matched"], [0]),
        )


def test_rejects_duplicate_surcharge_line_ids():
    with pytest.raises(ValueError, match="Invoice Line ID"):
        finalize_payment_decisions(
            invoice(),
            surcharge_results=surcharge_results(
                [1, 1],
                ["matched", "matched"],
                [0, 0],
            ),
        )

"""R7 controlled tax, surcharge and payment reconciliation."""

from decimal import Decimal

import pandas as pd

from audit_engine.exposure import finalize_payment_decisions


IDS = [1, 2, 3]


def frame(**columns):
    return pd.DataFrame({
        "Invoice Line ID": IDS,
        **columns,
    })


def test_complete_validation_reconciles_payment_decisions():
    invoice = frame(
        **{
            "Total": [100, 107.50, 112],
            "Credit Match Status": ["Not a Credit"] * 3,
            "Excluded From Exposure": [False] * 3,
            "Is Exact Duplicate Charge": [False] * 3,
            "Needs Charge Review": [False] * 3,
        }
    )

    combined = frame(
        **{
            "Payment Treatment": ["Proceed"] * 3,
            "Rate Exposure": [0] * 3,
            "Rate Exposure Status": ["Quantified"] * 3,
            "Combined Potential Exposure": [0] * 3,
        }
    )

    tax = frame(
        **{
            "Tax Status": [
                "matched",
                "potential_overcharge",
                "matched",
            ],
            "Potential Tax Overcharge": [
                Decimal("0"),
                Decimal("7.50"),
                Decimal("0"),
            ],
        }
    )

    surcharge = frame(
        **{
            "Surcharge Status": [
                "matched",
                "matched",
                "potential_overcharge",
            ],
            "Potential Surcharge Overcharge": [
                Decimal("0"),
                Decimal("0"),
                Decimal("12.00"),
            ],
        }
    )

    weight = frame(
        **{
            "Weight Status": ["calculated"] * 3,
            "Weight Comparison Status": ["match"] * 3,
        }
    )

    pricing = frame(
        **{
            "Pricing Status": ["matched"] * 3,
            "Potential Contract Overcharge": [0] * 3,
        }
    )

    delivery = frame(
        **{
            "Delivery Status": ["confirmed"] * 3,
        }
    )

    result = finalize_payment_decisions(
        invoice,
        combined_exposure=combined,
        tax_results=tax,
        surcharge_results=surcharge,
        weight_results=weight,
        contract_pricing_results=pricing,
        delivery_evidence_results=delivery,
    )

    by_id = result.set_index("Invoice Line ID")

    assert by_id.loc[
        1, "Final Payment Treatment"
    ] == "Proceed"

    assert by_id.loc[
        2, "Final Payment Treatment"
    ] == "Hold"

    assert by_id.loc[
        3, "Final Payment Treatment"
    ] == "Hold"

    assert result["Decision Completeness"].eq(
        "Complete"
    ).all()

    tax_exposure = sum([
        Decimal("0"),
        Decimal("7.50"),
        Decimal("0"),
    ])

    surcharge_exposure = sum([
        Decimal("0"),
        Decimal("0"),
        Decimal("12.00"),
    ])

    assert (
        tax_exposure + surcharge_exposure
    ) == Decimal("19.50")


def test_missing_weight_comparison_blocks_payment():
    invoice = frame(
        **{
            "Total": [100, 100, 100],
            "Credit Match Status": ["Not a Credit"] * 3,
            "Excluded From Exposure": [False] * 3,
        }
    )

    weight = frame(
        **{
            "Weight Status": ["calculated"] * 3,
            "Weight Comparison Status": [None] * 3,
        }
    )

    result = finalize_payment_decisions(
        invoice,
        weight_results=weight,
    )

    assert result["Final Payment Treatment"].eq(
        "Hold"
    ).all()

    assert result["Decision Reason"].str.contains(
        "weight_comparison_not_performed",
        regex=False,
    ).all()


def test_tax_and_surcharge_exposure_statuses_are_quantified():
    invoice = frame(
        **{
            "Total": [100, 107.50, 112],
        }
    )

    tax = frame(
        **{
            "Tax Status": [
                "matched",
                "potential_overcharge",
                "matched",
            ],
            "Potential Tax Overcharge": [
                Decimal("0"),
                Decimal("7.50"),
                Decimal("0"),
            ],
        }
    )

    surcharge = frame(
        **{
            "Surcharge Status": [
                "matched",
                "matched",
                "potential_overcharge",
            ],
            "Potential Surcharge Overcharge": [
                Decimal("0"),
                Decimal("0"),
                Decimal("12.00"),
            ],
        }
    )

    result = finalize_payment_decisions(
        invoice,
        tax_results=tax,
        surcharge_results=surcharge,
    )

    assert result["Tax Exposure Status"].eq(
        "Quantified"
    ).all()

    assert result["Surcharge Exposure Status"].eq(
        "Quantified"
    ).all()

    by_id = result.set_index("Invoice Line ID")

    assert "tax_positive_exposure" in by_id.loc[
        2, "Decision Reason"
    ]

    assert "surcharge_positive_exposure" in by_id.loc[
        3, "Decision Reason"
    ]


def test_missing_tax_evidence_is_not_treated_as_zero():
    invoice = frame(
        **{
            "Total": [100, 100, 100],
        }
    )

    tax = frame(
        **{
            "Tax Status": [
                "matched",
                "review",
                "matched",
            ],
            "Potential Tax Overcharge": [
                Decimal("0"),
                None,
                Decimal("0"),
            ],
        }
    )

    result = finalize_payment_decisions(
        invoice,
        tax_results=tax,
    )

    by_id = result.set_index("Invoice Line ID")

    assert by_id.loc[
        2, "Final Payment Treatment"
    ] == "Hold"

    assert by_id.loc[
        2, "Tax Exposure Status"
    ] == "Unknown"

    assert "tax_unknown_exposure" in by_id.loc[
        2, "Decision Reason"
    ]

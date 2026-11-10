"""R7 controlled financial reconciliation acceptance tests."""

from decimal import Decimal

import pandas as pd

from audit_engine.audit import (
    detect_duplicates,
    detect_exact_duplicate_charges,
)
from audit_engine.rate_validation import validate_freight_rates
from audit_engine.exposure import (
    calculate_combined_exposure,
    finalize_payment_decisions,
)


def pilot_invoice():
    return pd.DataFrame({
        "Invoice Line ID": [1, 2, 3, 4, 5],
        "AWB": ["A100", "A200", "A300", "A400", "A400"],
        "Carrier": ["Pilot Carrier"] * 5,
        "Service Type": ["Standard"] * 5,
        "Invoice Ref": [
            "INV001",
            "INV001",
            "INV001",
            "INV001",
            "INV002",
        ],
        "Base Freight": [100, 130, 80, 100, 100],
        "Total": [100, 130, 80, 100, 100],
    })


def pilot_rates():
    return pd.DataFrame({
        "Carrier": ["Pilot Carrier"],
        "Service Type": ["Standard"],
        "Agreed Rate": [100],
    })


def run_reconciliation():
    invoice = pilot_invoice()

    audited = detect_duplicates(invoice)
    audited = detect_exact_duplicate_charges(audited)

    rates = validate_freight_rates(
        audited,
        pilot_rates(),
    )

    exposure = calculate_combined_exposure(
        audited,
        rates,
    )

    decisions = finalize_payment_decisions(
        audited,
        combined_exposure=exposure,
    )

    return audited, rates, exposure, decisions


def amounts(values):
    return [
        Decimal(str(value)).quantize(Decimal("0.01"))
        for value in values
    ]


def test_rate_differences_match_independent_expectations():
    _, rates, _, _ = run_reconciliation()

    assert amounts(rates["Rate Difference"]) == amounts(
        [0, 30, -20, 0, 0]
    )

    assert amounts(
        rates["Potential Rate Overcharge"]
    ) == amounts([0, 30, 0, 0, 0])


def test_exact_duplicate_is_identified_once():
    audited, _, _, _ = run_reconciliation()

    assert audited["Is Exact Duplicate Charge"].tolist() == [
        False, False, False, False, True
    ]


def test_duplicate_and_rate_exposure_are_reconciled():
    _, _, exposure, _ = run_reconciliation()

    assert amounts(exposure["Duplicate Exposure"]) == amounts(
        [0, 0, 0, 0, 100]
    )

    assert amounts(exposure["Rate Exposure"]) == amounts(
        [0, 30, 0, 0, 0]
    )

    assert amounts(
        exposure["Combined Potential Exposure"]
    ) == amounts([0, 30, 0, 0, 100])

    assert sum(
        amounts(exposure["Combined Potential Exposure"])
    ) == Decimal("130.00")


def test_final_decision_holds_the_rate_overcharge():
    _, _, _, decisions = run_reconciliation()

    by_id = decisions.set_index("Invoice Line ID")

    assert by_id.loc[
        2, "Final Payment Treatment"
    ] == "Hold"


def test_final_decisions_preserve_all_invoice_lines():
    _, _, _, decisions = run_reconciliation()

    assert decisions["Invoice Line ID"].tolist() == [
        1, 2, 3, 4, 5
    ]

    assert decisions["Decision Completeness"].eq(
        "Partial"
    ).all()

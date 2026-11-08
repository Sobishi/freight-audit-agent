from decimal import Decimal

import pytest

from audit_engine.surcharge_validation import validate_surcharge_charge


@pytest.mark.parametrize(
    "billed,expected_status,expected_exposure",
    [
        ("10.00", "matched", Decimal("0")),
        ("12.50", "potential_overcharge", Decimal("2.50")),
        ("8.00", "below_contract", Decimal("0")),
    ],
)
def test_compares_billed_surcharge_with_contract(
    billed, expected_status, expected_exposure
):
    result = validate_surcharge_charge(
        billed_amount=billed,
        applicable=True,
        basis="per_kg",
        rate="2.50",
        chargeable_weight="4",
        tolerance="0.01",
    )

    assert result["status"] == expected_status
    assert result["expected_surcharge"] == Decimal("10.00")
    assert result["potential_overcharge"] == expected_exposure


def test_unknown_applicability_requires_review():
    result = validate_surcharge_charge(
        billed_amount="15.00",
        applicable=None,
        basis="fixed",
        rate="10.00",
    )

    assert result["status"] == "review"
    assert result["potential_overcharge"] is None


def test_missing_contract_rate_requires_review():
    result = validate_surcharge_charge(
        billed_amount="15.00",
        applicable=True,
        basis="fixed",
        rate=None,
    )

    assert result["status"] == "review"
    assert result["potential_overcharge"] is None


def test_explicitly_prohibited_surcharge_is_flagged():
    result = validate_surcharge_charge(
        billed_amount="15.00",
        applicable=False,
        basis=None,
        rate=None,
    )

    assert result["status"] == "potential_overcharge"
    assert result["expected_surcharge"] == Decimal("0")
    assert result["potential_overcharge"] == Decimal("15.00")


def test_reversed_charge_is_not_assessed():
    result = validate_surcharge_charge(
        billed_amount="-15.00",
        applicable=True,
        basis="fixed",
        rate="15.00",
    )

    assert result["status"] == "not_assessed"
    assert result["potential_overcharge"] == Decimal("0")


def test_invalid_billed_amount_requires_review():
    result = validate_surcharge_charge(
        billed_amount="unknown",
        applicable=True,
        basis="fixed",
        rate="10.00",
    )

    assert result["status"] == "review"
    assert result["potential_overcharge"] is None


def test_tolerance_is_respected():
    result = validate_surcharge_charge(
        billed_amount="10.005",
        applicable=True,
        basis="fixed",
        rate="10.00",
        tolerance="0.01",
    )

    assert result["status"] == "matched"
    assert result["potential_overcharge"] == Decimal("0")


def test_missing_applicability_does_not_assume_zero():
    result = validate_surcharge_charge(
        billed_amount="25.00",
        applicable=None,
        basis=None,
        rate=None,
    )

    assert result["status"] == "review"
    assert result["expected_surcharge"] is None
    assert result["potential_overcharge"] is None


@pytest.mark.parametrize(
    "tolerance",
    [-0.01, "invalid", None, float("nan")],
)
def test_invalid_tolerance_requires_review(tolerance):
    result = validate_surcharge_charge(
        billed_amount="15.00",
        applicable=True,
        basis="fixed",
        rate="10.00",
        tolerance=tolerance,
    )

    assert result["status"] == "review"
    assert result["reason"] == "invalid_tolerance"
    assert result["potential_overcharge"] is None


@pytest.mark.parametrize(
    "applicable",
    ["yes", 1, 0, [], {}],
)
def test_invalid_applicability_requires_review(applicable):
    result = validate_surcharge_charge(
        billed_amount="15.00",
        applicable=applicable,
        basis="fixed",
        rate="10.00",
    )

    assert result["status"] == "review"
    assert result["reason"] == "invalid_applicability"


def test_zero_billed_surcharge_with_unknown_contract_requires_review():
    result = validate_surcharge_charge(
        billed_amount="0",
        applicable=None,
        basis=None,
        rate=None,
    )

    assert result["status"] == "review"
    assert result["potential_overcharge"] is None


def test_prohibited_zero_surcharge_is_matched():
    result = validate_surcharge_charge(
        billed_amount="0",
        applicable=False,
        basis=None,
        rate=None,
    )

    assert result["status"] == "matched"
    assert result["expected_surcharge"] == Decimal("0")
    assert result["potential_overcharge"] == Decimal("0")


def test_missing_billed_amount_requires_review():
    result = validate_surcharge_charge(
        billed_amount=None,
        applicable=True,
        basis="fixed",
        rate="10",
    )

    assert result["status"] == "review"
    assert result["reason"] == "invalid_billed_amount"
    assert result["potential_overcharge"] is None


def test_credit_precedence_does_not_claim_a_verified_reversal():
    result = validate_surcharge_charge(
        billed_amount="-10",
        applicable=None,
        basis=None,
        rate=None,
    )

    assert result["status"] == "not_assessed"
    assert result["reason"] == "credit_or_reversal"
    assert result["potential_overcharge"] == Decimal("0")


def test_surcharge_overcharge_is_not_rounded_prematurely():
    result = validate_surcharge_charge(
        billed_amount="10.125",
        applicable=True,
        basis="fixed",
        rate="10.00",
        tolerance="0.01",
    )

    assert result["status"] == "potential_overcharge"
    assert result["potential_overcharge"] == Decimal("0.125")

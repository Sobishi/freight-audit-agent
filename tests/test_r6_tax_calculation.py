"""R6 TAX-01: explicit-evidence tax calculation tests."""

from decimal import Decimal

import pytest

from audit_engine.tax_validation import (
    calculate_expected_tax,
    validate_tax_charge,
)


def test_exclusive_tax_calculation():
    result = calculate_expected_tax(
        taxable_base="100",
        tax_rate="0.075",
        tax_inclusive=False,
        rounding_increment="0.01",
    )

    assert result["status"] == "calculated"
    assert result["expected_tax"] == Decimal("7.50")


def test_inclusive_tax_calculation():
    result = calculate_expected_tax(
        taxable_base="107.50",
        tax_rate="0.075",
        tax_inclusive=True,
        rounding_increment="0.01",
    )

    assert result["status"] == "calculated"
    assert result["expected_tax"] == Decimal("7.50")


def test_tax_rounding_half_up():
    result = calculate_expected_tax(
        taxable_base="115",
        tax_rate="0.075",
        tax_inclusive=False,
        rounding_increment="0.01",
    )

    assert result["expected_tax"] == Decimal("8.63")


def test_tax_potential_overcharge():
    result = validate_tax_charge(
        billed_tax="9.00",
        applicable=True,
        taxable_base="100",
        tax_rate="0.075",
        tax_inclusive=False,
        rounding_increment="0.01",
    )

    assert result["status"] == "potential_overcharge"
    assert result["expected_tax"] == Decimal("7.50")
    assert result["potential_overcharge"] == Decimal("1.50")


def test_tax_exemption():
    result = validate_tax_charge(
        billed_tax="5.00",
        applicable=False,
        taxable_base=None,
        tax_rate=None,
        tax_inclusive=None,
        rounding_increment="0.01",
    )

    assert result["status"] == "potential_overcharge"
    assert result["expected_tax"] == Decimal("0")
    assert result["potential_overcharge"] == Decimal("5.00")


def test_missing_applicability_requires_review():
    result = validate_tax_charge(
        billed_tax="7.50",
        applicable=None,
        taxable_base="100",
        tax_rate="0.075",
        tax_inclusive=False,
        rounding_increment="0.01",
    )

    assert result["status"] == "review"
    assert result["potential_overcharge"] is None


@pytest.mark.parametrize(
    "missing_field",
    ["taxable_base", "tax_rate", "tax_inclusive",
     "rounding_increment"],
)
def test_missing_required_tax_evidence(missing_field):
    inputs = {
        "billed_tax": "7.50",
        "applicable": True,
        "taxable_base": "100",
        "tax_rate": "0.075",
        "tax_inclusive": False,
        "rounding_increment": "0.01",
    }

    inputs[missing_field] = None

    result = validate_tax_charge(**inputs)

    assert result["status"] == "review"
    assert result["potential_overcharge"] is None


@pytest.mark.parametrize(
    "invalid_rate",
    ["-0.01", "1.01", "nan", True],
)
def test_invalid_tax_rate_requires_review(invalid_rate):
    result = validate_tax_charge(
        billed_tax="7.50",
        applicable=True,
        taxable_base="100",
        tax_rate=invalid_rate,
        tax_inclusive=False,
        rounding_increment="0.01",
    )

    assert result["status"] == "review"
    assert result["potential_overcharge"] is None


def test_tax_below_expected():
    result = validate_tax_charge(
        billed_tax="6.00",
        applicable=True,
        taxable_base="100",
        tax_rate="0.075",
        tax_inclusive=False,
        rounding_increment="0.01",
    )

    assert result["status"] == "below_contract"
    assert result["potential_overcharge"] == Decimal("0")


def test_tax_match_within_tolerance():
    result = validate_tax_charge(
        billed_tax="7.51",
        applicable=True,
        taxable_base="100",
        tax_rate="0.075",
        tax_inclusive=False,
        rounding_increment="0.01",
        tolerance="0.01",
    )

    assert result["status"] == "matched"
    assert result["potential_overcharge"] == Decimal("0")


def test_invalid_billed_tax_requires_review():
    result = validate_tax_charge(
        billed_tax="invalid",
        applicable=True,
        taxable_base="100",
        tax_rate="0.075",
        tax_inclusive=False,
        rounding_increment="0.01",
    )

    assert result["status"] == "review"
    assert result["potential_overcharge"] is None


@pytest.mark.parametrize(
    "invalid_base",
    ["-100", "nan", "Infinity", "invalid", True],
)
def test_invalid_taxable_base_requires_review(invalid_base):
    result = calculate_expected_tax(
        taxable_base=invalid_base,
        tax_rate="0.075",
        tax_inclusive=False,
        rounding_increment="0.01",
    )

    assert result["status"] == "review"
    assert result["expected_tax"] is None


@pytest.mark.parametrize(
    "invalid_increment",
    ["0", "-0.01", "nan", "Infinity", True],
)
def test_invalid_rounding_increment_requires_review(invalid_increment):
    result = calculate_expected_tax(
        taxable_base="100",
        tax_rate="0.075",
        tax_inclusive=False,
        rounding_increment=invalid_increment,
    )

    assert result["status"] == "review"
    assert result["expected_tax"] is None


@pytest.mark.parametrize(
    "invalid_inclusive",
    [None, "false", 0, 1],
)
def test_invalid_tax_inclusive_requires_review(invalid_inclusive):
    result = calculate_expected_tax(
        taxable_base="100",
        tax_rate="0.075",
        tax_inclusive=invalid_inclusive,
        rounding_increment="0.01",
    )

    assert result["status"] == "review"
    assert result["expected_tax"] is None


def test_rounding_uses_supplied_increment():
    result = calculate_expected_tax(
        taxable_base="101",
        tax_rate="0.075",
        tax_inclusive=False,
        rounding_increment="0.05",
    )

    assert result["status"] == "calculated"
    assert result["expected_tax"] == Decimal("7.60")


def test_exact_tolerance_boundary_is_matched():
    result = validate_tax_charge(
        billed_tax="7.51",
        applicable=True,
        taxable_base="100",
        tax_rate="0.075",
        tax_inclusive=False,
        rounding_increment="0.01",
        tolerance="0.01",
    )

    assert result["status"] == "matched"
    assert result["potential_overcharge"] == Decimal("0")


def test_amount_above_tolerance_is_overcharge():
    result = validate_tax_charge(
        billed_tax="7.52",
        applicable=True,
        taxable_base="100",
        tax_rate="0.075",
        tax_inclusive=False,
        rounding_increment="0.01",
        tolerance="0.01",
    )

    assert result["status"] == "potential_overcharge"
    assert result["potential_overcharge"] == Decimal("0.02")


@pytest.mark.parametrize(
    "invalid_tolerance",
    ["-0.01", "nan", "Infinity", True],
)
def test_invalid_tolerance_requires_review(invalid_tolerance):
    result = validate_tax_charge(
        billed_tax="7.50",
        applicable=True,
        taxable_base="100",
        tax_rate="0.075",
        tax_inclusive=False,
        rounding_increment="0.01",
        tolerance=invalid_tolerance,
    )

    assert result["status"] == "review"
    assert result["potential_overcharge"] is None


def test_zero_tax_on_explicit_exemption_is_matched():
    result = validate_tax_charge(
        billed_tax="0",
        applicable=False,
        taxable_base=None,
        tax_rate=None,
        tax_inclusive=None,
        rounding_increment=None,
    )

    assert result["status"] == "matched"
    assert result["expected_tax"] == Decimal("0")
    assert result["potential_overcharge"] == Decimal("0")


def test_negative_billed_tax_requires_review():
    result = validate_tax_charge(
        billed_tax="-7.50",
        applicable=True,
        taxable_base="100",
        tax_rate="0.075",
        tax_inclusive=False,
        rounding_increment="0.01",
    )

    assert result["status"] == "review"
    assert result["potential_overcharge"] is None

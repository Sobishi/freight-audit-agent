import pytest

from audit_engine.surcharge_validation import calculate_expected_surcharge


@pytest.mark.parametrize(
    "basis,rate,weight,freight,expected",
    [
        ("fixed", 12.50, None, None, 12.50),
        ("per_kg", 2.50, 4.0, None, 10.00),
        ("percent_of_freight", 0.15, None, 100.00, 15.00),
    ],
)
def test_calculates_supported_surcharge_bases(
    basis, rate, weight, freight, expected
):
    result = calculate_expected_surcharge(
        basis=basis,
        rate=rate,
        chargeable_weight=weight,
        base_freight=freight,
    )

    assert result["status"] == "calculated"
    assert result["expected_surcharge"] == pytest.approx(expected)
    assert result["reason"] is None


@pytest.mark.parametrize(
    "basis,rate,weight,freight,reason",
    [
        ("fixed", None, None, None, "missing_rate"),
        ("per_kg", 2.50, None, None, "invalid_weight"),
        ("percent_of_freight", 0.15, None, None, "invalid_base_freight"),
        ("unknown", 10.00, None, None, "unsupported_basis"),
        ("fixed", -5.00, None, None, "invalid_rate"),
        ("fixed", float("nan"), None, None, "invalid_rate"),
    ],
)
def test_unverifiable_surcharges_require_review(
    basis, rate, weight, freight, reason
):
    result = calculate_expected_surcharge(
        basis=basis,
        rate=rate,
        chargeable_weight=weight,
        base_freight=freight,
    )

    assert result["status"] == "review"
    assert result["expected_surcharge"] is None
    assert result["reason"] == reason


def test_zero_surcharge_rate_is_valid():
    result = calculate_expected_surcharge(
        basis="fixed",
        rate=0,
    )

    assert result["status"] == "calculated"
    assert result["expected_surcharge"] == 0


@pytest.mark.parametrize(
    "rate",
    [0, 1],
)
def test_percentage_rate_boundaries(rate):
    result = calculate_expected_surcharge(
        basis="percent_of_freight",
        rate=rate,
        base_freight=100,
    )

    assert result["status"] == "calculated"
    assert result["expected_surcharge"] == pytest.approx(rate * 100)


def test_percentage_above_one_requires_review():
    result = calculate_expected_surcharge(
        basis="percent_of_freight",
        rate=1.01,
        base_freight=100,
    )

    assert result["status"] == "review"
    assert result["reason"] == "invalid_rate"


@pytest.mark.parametrize(
    "basis,rate,weight,freight",
    [
        ("fixed", True, None, None),
        ("per_kg", 2, True, None),
        ("percent_of_freight", 0.1, None, True),
        ("per_kg", 2, -5, None),
        ("percent_of_freight", 0.1, None, -100),
    ],
)
def test_invalid_numeric_inputs_require_review(
    basis, rate, weight, freight
):
    result = calculate_expected_surcharge(
        basis=basis,
        rate=rate,
        chargeable_weight=weight,
        base_freight=freight,
    )

    assert result["status"] == "review"
    assert result["expected_surcharge"] is None


def test_overflow_requires_review():
    result = calculate_expected_surcharge(
        basis="per_kg",
        rate=1e308,
        chargeable_weight=1e308,
    )

    assert result["status"] == "review"
    assert result["reason"] == "invalid_calculation"


def test_decimal_surcharge_is_precise():
    result = calculate_expected_surcharge(
        basis="per_kg",
        rate="0.10",
        chargeable_weight="3",
    )

    assert result["status"] == "calculated"
    assert str(result["expected_surcharge"]) == "0.30"

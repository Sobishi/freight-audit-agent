from pathlib import Path

from data.carrier_profile import load_profile
from audit_engine.weight_validation import calculate_dimensional_weight


def test_dimensional_weight_uses_carrier_divisor():
    profile = load_profile(
        Path("config/carriers/northbridge_express.yaml")
    )

    result = calculate_dimensional_weight(
        length=50,
        width=40,
        height=30,
        divisor=profile.dim_divisor,
    )

    assert result == 12.0


import math
import pytest


def test_dimensional_weight_uses_different_carrier_divisors():
    profile = load_profile(
        Path("config/carriers/swiftline.yaml")
    )

    result = calculate_dimensional_weight(
        length=50,
        width=40,
        height=30,
        divisor=profile.dim_divisor,
    )

    assert result == 10.0


@pytest.mark.parametrize(
    "field,value",
    [
        ("length", 0),
        ("width", -5),
        ("height", None),
        ("length", float("nan")),
        ("width", float("inf")),
        ("height", True),
        ("divisor", 0),
        ("divisor", -5000),
        ("divisor", "5000"),
    ],
)
def test_dimensional_weight_rejects_invalid_inputs(field, value):
    measurements = {
        "length": 50,
        "width": 40,
        "height": 30,
        "divisor": 5000,
    }

    measurements[field] = value

    with pytest.raises(ValueError, match=field):
        calculate_dimensional_weight(**measurements)


from audit_engine.weight_validation import round_billable_weight


@pytest.mark.parametrize(
    "carrier_file,raw_weight,expected",
    [
        ("northbridge_express.yaml", 9.6, 10.0),
        ("northbridge_express.yaml", 10.0, 10.0),
        ("northbridge_express.yaml", 10.1, 11.0),
        ("corvant.yaml", 19.6, 20.0),
        ("corvant.yaml", 20.0, 20.0),
        ("corvant.yaml", 20.1, 21.0),
        ("swiftline.yaml", 8.2, 9.0),
    ],
)
def test_carrier_specific_weight_rounding(
    carrier_file, raw_weight, expected
):
    profile = load_profile(
        Path("config/carriers") / carrier_file
    )

    result = round_billable_weight(
        raw_weight,
        profile.rounding,
    )

    assert result == expected


@pytest.mark.parametrize(
    "invalid_weight",
    [None, -1, float("nan"), float("inf"), True, "10"],
)
def test_weight_rounding_rejects_invalid_weight(invalid_weight):
    profile = load_profile(
        Path("config/carriers/northbridge_express.yaml")
    )

    with pytest.raises(ValueError):
        round_billable_weight(
            invalid_weight,
            profile.rounding,
        )


from audit_engine.weight_validation import calculate_chargeable_weight


def test_chargeable_weight_uses_dimensional_weight_when_higher():
    profile = load_profile(
        Path("config/carriers/northbridge_express.yaml")
    )

    result = calculate_chargeable_weight(
        actual_weight=8.4,
        length=50,
        width=40,
        height=30,
        profile=profile,
    )

    assert result["actual_weight"] == 8.4
    assert result["dimensional_weight"] == 12.0
    assert result["weight_basis"] == "dimensional"
    assert result["chargeable_weight"] == 12.0


def test_chargeable_weight_uses_actual_weight_when_higher():
    profile = load_profile(
        Path("config/carriers/northbridge_express.yaml")
    )

    result = calculate_chargeable_weight(
        actual_weight=12.3,
        length=20,
        width=20,
        height=20,
        profile=profile,
    )

    assert result["dimensional_weight"] == 1.6
    assert result["weight_basis"] == "actual"
    assert result["chargeable_weight"] == 13.0


def test_chargeable_weight_applies_carrier_specific_rounding():
    profile = load_profile(
        Path("config/carriers/swiftline.yaml")
    )

    result = calculate_chargeable_weight(
        actual_weight=8.2,
        length=20,
        width=20,
        height=20,
        profile=profile,
    )

    assert result["weight_basis"] == "actual"
    assert result["chargeable_weight"] == 9.0


def test_chargeable_weight_rejects_missing_actual_weight():
    profile = load_profile(
        Path("config/carriers/northbridge_express.yaml")
    )

    with pytest.raises(ValueError, match="actual_weight"):
        calculate_chargeable_weight(
            actual_weight=None,
            length=50,
            width=40,
            height=30,
            profile=profile,
        )


from audit_engine.weight_validation import compare_billed_weight


@pytest.mark.parametrize(
    "expected,billed,tolerance,status,difference",
    [
        (12.0, 12.0, 0.01, "match", 0.0),
        (12.0, 15.0, 0.01, "billed_weight_high", 3.0),
        (12.0, 10.0, 0.01, "billed_weight_low", -2.0),
        (12.0, 12.005, 0.01, "match", 0.005),
        (12.0, 12.02, 0.01, "billed_weight_high", 0.02),
    ],
)
def test_compare_billed_weight(
    expected, billed, tolerance, status, difference
):
    result = compare_billed_weight(
        expected_weight=expected,
        billed_weight=billed,
        tolerance=tolerance,
    )

    assert result["status"] == status
    assert result["difference"] == pytest.approx(difference)
    assert result["expected_weight"] == expected
    assert result["billed_weight"] == billed


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_weight", None),
        ("expected_weight", 0),
        ("billed_weight", None),
        ("billed_weight", -1),
        ("tolerance", -0.01),
        ("tolerance", float("nan")),
    ],
)
def test_compare_billed_weight_rejects_invalid_inputs(field, value):
    values = {
        "expected_weight": 12.0,
        "billed_weight": 12.0,
        "tolerance": 0.01,
    }

    values[field] = value

    with pytest.raises(ValueError, match=field):
        compare_billed_weight(**values)


from audit_engine.weight_validation import (
    convert_weight_to_kg,
    convert_dimension_to_cm,
)


@pytest.mark.parametrize(
    "value,unit,expected",
    [
        (10, "kg", 10.0),
        (10, "lb", 4.5359237),
        (1, "lb", 0.45359237),
    ],
)
def test_weight_unit_conversion(value, unit, expected):
    result = convert_weight_to_kg(value, unit)
    assert result == pytest.approx(expected)


@pytest.mark.parametrize(
    "value,unit,expected",
    [
        (50, "cm", 50.0),
        (10, "in", 25.4),
        (1, "in", 2.54),
    ],
)
def test_dimension_unit_conversion(value, unit, expected):
    result = convert_dimension_to_cm(value, unit)
    assert result == pytest.approx(expected)


@pytest.mark.parametrize(
    "value,unit",
    [
        (None, "kg"),
        (0, "kg"),
        (-2, "lb"),
        (float("nan"), "kg"),
        (10, "stone"),
        (10, None),
    ],
)
def test_weight_conversion_rejects_invalid_inputs(value, unit):
    with pytest.raises(ValueError):
        convert_weight_to_kg(value, unit)


@pytest.mark.parametrize(
    "value,unit",
    [
        (None, "cm"),
        (0, "cm"),
        (-2, "in"),
        (float("inf"), "cm"),
        (10, "metres"),
        (10, None),
    ],
)
def test_dimension_conversion_rejects_invalid_inputs(value, unit):
    with pytest.raises(ValueError):
        convert_dimension_to_cm(value, unit)

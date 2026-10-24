import pytest

from data.carrier_profile import CarrierProfile, RoundingRule
from audit_engine.weight_validation import (
    calculate_mapped_package_weight,
)


def profile():
    return CarrierProfile(
        carrier_id="demo_carrier",
        carrier_name="Demo Carrier",
        currency="USD",
        pricing_method="weight_band",
        unit_system="metric",
        dim_divisor=5000,
        rounding=RoundingRule(
            step_low=0.5,
            threshold=10,
            step_high=1,
        ),
    )


def row(**overrides):
    values = {
        "Carrier ID": "demo_carrier",
        "Actual Weight": 5.0,
        "Length": 40.0,
        "Width": 30.0,
        "Height": 20.0,
        "Weight Unit": "kg",
        "Dimension Unit": "cm",
        "Pieces": 1.0,
        "Billed Weight": 5.0,
    }
    values.update(overrides)
    return values


def test_metric_package_calculates_dimensional_weight():
    result = calculate_mapped_package_weight(
        row(),
        profile=profile(),
        package_count_verified=True,
    )

    assert result["status"] == "calculated"
    assert result["calculation"]["dimensional_weight"] == pytest.approx(4.8)
    assert result["calculation"]["weight_basis"] == "actual"
    assert result["calculation"]["chargeable_weight"] == 5.0


def test_dimensional_weight_can_exceed_actual_weight():
    result = calculate_mapped_package_weight(
        row(**{"Actual Weight": 2.0}),
        profile=profile(),
        package_count_verified=True,
    )

    assert result["calculation"]["weight_basis"] == "dimensional"
    assert result["calculation"]["chargeable_weight"] == 5.0


def test_imperial_measurements_are_converted():
    result = calculate_mapped_package_weight(
        row(**{
            "Actual Weight": 10.0,
            "Length": 12.0,
            "Width": 10.0,
            "Height": 8.0,
            "Weight Unit": "lb",
            "Dimension Unit": "in",
            "Billed Weight": 10.0,
        }),
        profile=profile(),
        package_count_verified=True,
    )

    assert result["status"] == "calculated"
    assert result["converted_measurements"]["actual_weight_kg"] == pytest.approx(
        4.5359237
    )
    assert result["converted_measurements"]["length_cm"] == pytest.approx(30.48)
    assert result["calculation"]["chargeable_weight"] > 0


def test_missing_height_blocks_calculation():
    result = calculate_mapped_package_weight(
        row(**{"Height": None}),
        profile=profile(),
        package_count_verified=True,
    )

    assert result["status"] == "incomplete_dimensions"
    assert result["calculation"] is None


def test_multiple_packages_block_calculation():
    result = calculate_mapped_package_weight(
        row(**{"Pieces": 2}),
        profile=profile(),
        package_count_verified=True,
    )

    assert result["status"] == "package_structure_review"
    assert result["calculation"] is None


def test_unverified_package_count_blocks_calculation():
    result = calculate_mapped_package_weight(
        row(),
        profile=profile(),
        package_count_verified=False,
    )

    assert result["status"] == "package_structure_review"
    assert result["calculation"] is None


def test_missing_billed_weight_does_not_block_calculation():
    result = calculate_mapped_package_weight(
        row(**{"Billed Weight": None}),
        profile=profile(),
        package_count_verified=True,
    )

    assert result["status"] == "calculated"
    assert result["weight_comparison"] is None


def test_weight_comparison_requires_explicit_tolerance():
    result = calculate_mapped_package_weight(
        row(**{"Billed Weight": 6.0, "Billed Weight Unit": "kg"}),
        profile=profile(),
        package_count_verified=True,
        weight_tolerance=0.1,
    )

    assert result["weight_comparison"]["status"] == "billed_weight_high"
    assert result["weight_comparison"]["difference"] == pytest.approx(1.0)


def test_without_tolerance_comparison_is_not_performed():
    result = calculate_mapped_package_weight(
        row(**{"Billed Weight": 6.0}),
        profile=profile(),
        package_count_verified=True,
    )

    assert result["status"] == "calculated"
    assert result["weight_comparison"] is None


def test_billed_weight_uses_declared_weight_unit():
    result = calculate_mapped_package_weight(
        row(**{
            "Actual Weight": 10.0,
            "Weight Unit": "lb",
            "Billed Weight": 11.0,
        "Billed Weight Unit": "lb",
        }),
        profile=profile(),
        package_count_verified=True,
        weight_tolerance=0.1,
    )

    assert result["weight_comparison"] is not None
    assert result["weight_comparison"]["billed_weight"] == pytest.approx(
        11 * 0.45359237
    )


def test_carrier_mismatch_is_rejected():
    with pytest.raises(ValueError, match="carrier"):
        calculate_mapped_package_weight(
            row(**{"Carrier ID": "different_carrier"}),
            profile=profile(),
            package_count_verified=True,
        )

import pandas as pd
import pytest

from data.carrier_profile import CarrierProfile, RoundingRule
from data.mapping import parse_mapping, standardize_invoice
from audit_engine.weight_validation import calculate_mapped_package_weight


def profile(**changes):
    values = dict(
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
    values.update(changes)
    return CarrierProfile(**values)


def row(**changes):
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
    values.update(changes)
    return values


@pytest.mark.parametrize(
    "billed",
    [0, -1, float("inf"), "invalid"],
)
def test_invalid_billed_weight_requires_review(billed):
    result = calculate_mapped_package_weight(
        row(**{"Billed Weight": billed, "Billed Weight Unit": "kg"}),
        profile=profile(),
        package_count_verified=True,
        weight_tolerance=0.1,
    )

    assert result["status"] == "calculation_review"
    assert result["review_reason"] == "invalid_billed_weight"
    assert result["weight_comparison"] is None
    assert result["calculation"] is not None


def test_different_billed_weight_unit_requires_review():
    result = calculate_mapped_package_weight(
        row(**{"Billed Weight Unit": "lb"}),
        profile=profile(),
        package_count_verified=True,
        weight_tolerance=0.1,
    )

    assert result["status"] == "calculation_review"
    assert result["review_reason"] == "weight_unit_mismatch"
    assert result["weight_comparison"] is None


def test_explicit_matching_billed_unit_allows_comparison():
    result = calculate_mapped_package_weight(
        row(**{
            "Billed Weight": 6.0,
            "Billed Weight Unit": "kg",
        }),
        profile=profile(),
        package_count_verified=True,
        weight_tolerance=0.1,
    )

    assert result["status"] == "calculated"
    assert result["weight_comparison"]["status"] == "billed_weight_high"


def test_unsupported_profile_requires_review():
    result = calculate_mapped_package_weight(
        row(),
        profile=profile(unit_system="imperial"),
        package_count_verified=True,
    )

    assert result["status"] == "calculation_review"
    assert result["review_reason"] == "unsupported_profile"
    assert result["calculation"] is None


def test_standardized_invoice_row_calculates():
    mapping = parse_mapping({
        "carrier_id": "demo_carrier",
        "carrier_name": "Demo Carrier",
        "columns": {
            "Waybill": "AWB",
            "Amount": "Total",
            "ActualKg": "Actual Weight",
            "LengthCm": "Length",
            "WidthCm": "Width",
            "HeightCm": "Height",
            "Unit": "Weight Unit",
            "DimensionUnit": "Dimension Unit",
            "Packages": "Pieces",
            "BilledKg": "Billed Weight",
            "BilledUnit": "Billed Weight Unit",
        },
    })

    raw = pd.DataFrame([{
        "Waybill": "PKG001",
        "Amount": "120",
        "ActualKg": "5",
        "LengthCm": "40",
        "WidthCm": "30",
        "HeightCm": "20",
        "Unit": "kg",
        "DimensionUnit": "cm",
        "Packages": "1",
        "BilledKg": "6",
        "BilledUnit": "kg",
    }])

    standardized = standardize_invoice(raw, mapping)

    result = calculate_mapped_package_weight(
        standardized.iloc[0],
        profile=profile(),
        package_count_verified=True,
        weight_tolerance=0.1,
    )

    assert result["status"] == "calculated"
    assert result["calculation"]["chargeable_weight"] == 5.0
    assert result["weight_comparison"]["status"] == "billed_weight_high"


def test_missing_billed_weight_unit_requires_review():
    result = calculate_mapped_package_weight(
        row(),
        profile=profile(),
        package_count_verified=True,
        weight_tolerance=0.1,
    )

    assert result["status"] == "calculation_review"
    assert result["review_reason"] == "missing_billed_weight_unit"
    assert result["weight_comparison"] is None
    assert result["calculation"] is not None


def test_null_billed_weight_unit_requires_review():
    result = calculate_mapped_package_weight(
        row(**{"Billed Weight Unit": pd.NA}),
        profile=profile(),
        package_count_verified=True,
        weight_tolerance=0.1,
    )

    assert result["status"] == "calculation_review"
    assert result["review_reason"] == "missing_billed_weight_unit"
    assert result["weight_comparison"] is None
    assert result["calculation"] is not None


def test_missing_billed_unit_without_tolerance_retains_calculation():
    result = calculate_mapped_package_weight(
        row(),
        profile=profile(),
        package_count_verified=True,
    )

    assert result["status"] == "calculated"
    assert result["review_reason"] is None
    assert result["weight_comparison"] is None
    assert result["calculation"] is not None


def test_missing_billed_weight_does_not_require_billed_unit():
    result = calculate_mapped_package_weight(
        row(**{"Billed Weight": None}),
        profile=profile(),
        package_count_verified=True,
        weight_tolerance=0.1,
    )

    assert result["status"] == "calculated"
    assert result["review_reason"] is None
    assert result["weight_comparison"] is None
    assert result["calculation"] is not None


@pytest.mark.parametrize("billed_unit", ["", " ", "   "])
def test_blank_billed_weight_unit_requires_missing_evidence_review(billed_unit):
    result = calculate_mapped_package_weight(
        row(**{"Billed Weight Unit": billed_unit}),
        profile=profile(),
        package_count_verified=True,
        weight_tolerance=0.1,
    )

    assert result["status"] == "calculation_review"
    assert result["review_reason"] == "missing_billed_weight_unit"
    assert result["weight_comparison"] is None
    assert result["calculation"] is not None

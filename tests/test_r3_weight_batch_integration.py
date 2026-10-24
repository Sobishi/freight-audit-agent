import pandas as pd

from data.carrier_profile import CarrierProfile, RoundingRule
from audit_engine.weight_reporting import generate_weight_validation_results


def test_weight_results_preserve_invoice_line_identity_and_review_reason():
    profile = CarrierProfile(
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

    invoice = pd.DataFrame([
        {
            "Invoice Line ID": "line-001",
            "Carrier ID": "demo_carrier",
            "AWB": "AWB001",
            "Actual Weight": 5.0,
            "Length": 40.0,
            "Width": 30.0,
            "Height": 20.0,
            "Weight Unit": "kg",
            "Dimension Unit": "cm",
            "Pieces": 1,
            "Billed Weight": 7.0,
            "Billed Weight Unit": pd.NA,
            "Total": 120.0,
        }
    ])

    results = generate_weight_validation_results(
        invoice,
        profile=profile,
        package_count_verified=True,
        weight_tolerance=0.1,
    )

    assert len(results) == 1
    assert results["Invoice Line ID"].tolist() == ["line-001"]

    result = results.iloc[0]

    assert result["Weight Status"] == "calculation_review"
    assert result["Weight Review Reason"] == "missing_billed_weight_unit"
    assert result["Expected Chargeable Weight (kg)"] == 5.0
    assert result["Billed Weight"] == 7.0

    assert "Potential Exposure" not in results.columns
    assert "Combined Potential Exposure" not in results.columns


def test_weight_results_reject_duplicate_invoice_line_ids():
    import pytest

    invoice = pd.DataFrame({
        "Invoice Line ID": ["line-001", "line-001"],
    })

    with pytest.raises(ValueError, match="must be unique"):
        generate_weight_validation_results(
            invoice,
            profile=None,
            package_count_verified=True,
        )


def test_weight_results_reject_missing_invoice_line_ids():
    import pytest

    invoice = pd.DataFrame({
        "Invoice Line ID": ["line-001", pd.NA],
    })

    with pytest.raises(ValueError, match="cannot contain missing"):
        generate_weight_validation_results(
            invoice,
            profile=None,
            package_count_verified=True,
        )


def test_weight_results_reject_implicit_package_verification():
    import pytest

    invoice = pd.DataFrame({
        "Invoice Line ID": ["line-001"],
    })

    with pytest.raises(ValueError, match="explicitly True or False"):
        generate_weight_validation_results(
            invoice,
            profile=None,
            package_count_verified=None,
        )


def test_multiple_packages_require_review():
    from data.carrier_profile import CarrierProfile, RoundingRule

    profile = CarrierProfile(
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

    invoice = pd.DataFrame([{
        "Invoice Line ID": "line-002",
        "Carrier ID": "demo_carrier",
        "AWB": "AWB002",
        "Actual Weight": 5.0,
        "Length": 40.0,
        "Width": 30.0,
        "Height": 20.0,
        "Weight Unit": "kg",
        "Dimension Unit": "cm",
        "Pieces": 2,
        "Billed Weight": 7.0,
        "Billed Weight Unit": "kg",
    }])

    results = generate_weight_validation_results(
        invoice,
        profile=profile,
        package_count_verified=True,
        weight_tolerance=0.1,
    )

    assert len(results) == 1
    assert results.iloc[0]["Weight Status"] == "package_structure_review"
    assert results.iloc[0]["Weight Calculation Eligible"] == False
    assert pd.isna(
        results.iloc[0]["Expected Chargeable Weight (kg)"]
    )


def test_carrier_mismatch_is_rejected():
    import pytest
    from data.carrier_profile import CarrierProfile, RoundingRule

    profile = CarrierProfile(
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

    invoice = pd.DataFrame([{
        "Invoice Line ID": "line-003",
        "Carrier ID": "different_carrier",
        "Actual Weight": 5.0,
        "Length": 40.0,
        "Width": 30.0,
        "Height": 20.0,
        "Weight Unit": "kg",
        "Dimension Unit": "cm",
        "Pieces": 1,
    }])

    with pytest.raises(
        ValueError,
        match="Invoice carrier does not match carrier profile",
    ):
        generate_weight_validation_results(
            invoice,
            profile=profile,
            package_count_verified=True,
        )


def test_weight_results_preserve_measurement_and_calculation_evidence():
    profile = CarrierProfile(
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

    invoice = pd.DataFrame([{
        "Invoice Line ID": "line-004",
        "Carrier ID": "demo_carrier",
        "AWB": "AWB004",
        "Actual Weight": 3.0,
        "Length": 40.0,
        "Width": 30.0,
        "Height": 20.0,
        "Weight Unit": "kg",
        "Dimension Unit": "cm",
        "Pieces": 1,
        "Billed Weight": 6.0,
        "Billed Weight Unit": "kg",
    }])

    results = generate_weight_validation_results(
        invoice,
        profile=profile,
        package_count_verified=True,
        weight_tolerance=0.1,
    )

    result = results.iloc[0]

    assert result["Actual Weight"] == 3.0
    assert result["Length"] == 40.0
    assert result["Width"] == 30.0
    assert result["Height"] == 20.0
    assert result["Weight Unit"] == "kg"
    assert result["Dimension Unit"] == "cm"
    assert result["Pieces"] == 1

    assert result["Actual Weight (kg)"] == 3.0
    assert result["Length (cm)"] == 40.0
    assert result["Width (cm)"] == 30.0
    assert result["Height (cm)"] == 20.0

    assert result["Dimensional Weight (kg)"] == 4.8
    assert result["Expected Chargeable Weight (kg)"] == 5.0
    assert result["Weight Comparison Status"] == "billed_weight_high"

    assert "Potential Exposure" not in results.columns
    assert "Combined Potential Exposure" not in results.columns


def test_weight_results_preserve_calculation_rules_and_comparison_evidence():
    profile = CarrierProfile(
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
        tolerance=0.01,
    )

    invoice = pd.DataFrame([{
        "Invoice Line ID": "line-005",
        "Carrier ID": "demo_carrier",
        "AWB": "AWB005",
        "Actual Weight": 3.0,
        "Length": 40.0,
        "Width": 30.0,
        "Height": 20.0,
        "Weight Unit": "kg",
        "Dimension Unit": "cm",
        "Pieces": 1,
        "Billed Weight": 6.0,
        "Billed Weight Unit": "kg",
    }])

    results = generate_weight_validation_results(
        invoice,
        profile=profile,
        package_count_verified=True,
        weight_tolerance=0.1,
    )

    result = results.iloc[0]

    assert result["Dimensional Divisor"] == 5000
    assert result["Rounding Step Low (kg)"] == 0.5
    assert result["Rounding Threshold (kg)"] == 10
    assert result["Rounding Step High (kg)"] == 1

    assert result["Weight Basis"] == "dimensional"
    assert result["Unrounded Chargeable Weight (kg)"] == 4.8
    assert result["Expected Chargeable Weight (kg)"] == 5.0

    assert result["Billed Weight (kg)"] == 6.0
    assert result["Weight Difference (kg)"] == 1.0
    assert result["Weight Tolerance (kg)"] == 0.1
    assert result["Weight Comparison Status"] == "billed_weight_high"

    assert "Potential Exposure" not in results.columns
    assert "Combined Potential Exposure" not in results.columns

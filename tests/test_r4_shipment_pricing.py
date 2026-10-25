import pandas as pd

from audit_engine.shipment_pricing import price_shipment


def contract_rates():
    return pd.DataFrame([
        {
            "Carrier ID": "swiftline",
            "Service Type": "Express",
            "Zone": "A",
            "Min Weight (kg)": 0,
            "Max Weight (kg)": 5,
            "Valid From": "2026-01-01",
            "Valid To": "2026-12-31",
            "Currency": "USD",
            "Agreed Base Freight": 100.0,
        }
    ])


def shipment():
    return {
        "Invoice Line ID": "INV-001",
        "Carrier ID": "swiftline",
        "Service Type": "Express",
        "Zone": "A",
        "Ship Date": "2026-05-15",
        "Currency": "USD",
        "Base Freight": 120.0,
    }


def weight_evidence():
    return {
        "Weight Status": "calculated",
        "Weight Calculation Eligible": True,
        "Expected Chargeable Weight (kg)": 4.0,
    }


def test_valid_evidence_produces_expected_base_freight():
    result = price_shipment(
        shipment(),
        weight_evidence(),
        contract_rates(),
        tolerance=0.01,
    )

    assert result["status"] == "potential_overcharge"
    assert result["expected_base_freight"] == 100.0
    assert result["invoiced_base_freight"] == 120.0
    assert result["potential_overcharge"] == 20.0


def test_incomplete_weight_evidence_requires_review():
    evidence = weight_evidence()
    evidence["Weight Status"] = "calculation_review"
    evidence["Weight Calculation Eligible"] = False
    evidence["Expected Chargeable Weight (kg)"] = None

    result = price_shipment(
        shipment(),
        evidence,
        contract_rates(),
        tolerance=0.01,
    )

    assert result["status"] == "review"
    assert result["reason"] == "weight_evidence_incomplete"
    assert result["expected_base_freight"] is None
    assert result["potential_overcharge"] is None


def test_missing_contract_rate_requires_review():
    data = shipment()
    data["Zone"] = "Z"

    result = price_shipment(
        data,
        weight_evidence(),
        contract_rates(),
        tolerance=0.01,
    )

    assert result["status"] == "review"
    assert result["reason"] == "rate_not_found"
    assert result["potential_overcharge"] is None


def test_matching_base_freight_has_no_overcharge():
    data = shipment()
    data["Base Freight"] = 100.0

    result = price_shipment(
        data,
        weight_evidence(),
        contract_rates(),
        tolerance=0.01,
    )

    assert result["status"] == "matched"
    assert result["expected_base_freight"] == 100.0
    assert result["potential_overcharge"] == 0.0


def test_overcharge_within_tolerance_is_matched():
    data = shipment()
    data["Base Freight"] = 100.01

    result = price_shipment(
        data,
        weight_evidence(),
        contract_rates(),
        tolerance=0.01,
    )

    assert result["status"] == "matched"
    assert result["potential_overcharge"] == 0.0


def test_overcharge_above_tolerance_is_flagged():
    data = shipment()
    data["Base Freight"] = 100.02

    result = price_shipment(
        data,
        weight_evidence(),
        contract_rates(),
        tolerance=0.01,
    )

    assert result["status"] == "potential_overcharge"
    assert result["potential_overcharge"] == 0.02


def test_undercharge_is_not_recoverable_overcharge():
    data = shipment()
    data["Base Freight"] = 90.0

    result = price_shipment(
        data,
        weight_evidence(),
        contract_rates(),
        tolerance=0.01,
    )

    assert result["status"] == "below_contract_rate"
    assert result["potential_overcharge"] == 0.0


def test_missing_invoiced_base_freight_requires_review():
    data = shipment()
    data["Base Freight"] = None

    result = price_shipment(
        data,
        weight_evidence(),
        contract_rates(),
        tolerance=0.01,
    )

    assert result["status"] == "review"
    assert result["reason"] == "invalid_invoiced_base_freight"
    assert result["potential_overcharge"] is None


def test_invalid_weight_evidence_cannot_generate_overcharge():
    evidence = weight_evidence()
    evidence["Expected Chargeable Weight (kg)"] = float("nan")

    result = price_shipment(
        shipment(),
        evidence,
        contract_rates(),
        tolerance=0.01,
    )

    assert result["status"] == "review"
    assert result["reason"] == "weight_evidence_incomplete"
    assert result["potential_overcharge"] is None


def test_negative_monetary_tolerance_is_rejected():
    import pytest

    with pytest.raises(ValueError, match="tolerance"):
        price_shipment(
            shipment(),
            weight_evidence(),
            contract_rates(),
            tolerance=-0.01,
        )


def test_nonfinite_monetary_tolerance_is_rejected():
    import pytest

    with pytest.raises(ValueError, match="tolerance"):
        price_shipment(
            shipment(),
            weight_evidence(),
            contract_rates(),
            tolerance=float("inf"),
        )

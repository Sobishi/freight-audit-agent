"""Shipment-level contract pricing for R4."""

import math
from decimal import Decimal

from audit_engine.contract_pricing import select_contract_rate


def _valid_amount(value, *, allow_zero=False):
    if isinstance(value, bool):
        return False

    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return False

    if not math.isfinite(number):
        return False

    return number >= 0 if allow_zero else number > 0


def _review(reason):
    return {
        "status": "review",
        "reason": reason,
        "expected_base_freight": None,
        "invoiced_base_freight": None,
        "potential_overcharge": None,
    }


def price_shipment(
    shipment,
    weight_evidence,
    contract_rates,
    *,
    tolerance=0.01,
):
    """
    Compare invoiced Base Freight with a selected contract rate.

    Only validated R3 weight evidence can support a contract
    pricing calculation.

    Weight discrepancies alone do not establish financial exposure.
    """

    if not _valid_amount(tolerance, allow_zero=True):
        raise ValueError(
            "Monetary tolerance must be finite and nonnegative."
        )

    if not isinstance(shipment, dict):
        raise TypeError("Shipment must be a dictionary.")

    if not isinstance(weight_evidence, dict):
        raise TypeError("Weight evidence must be a dictionary.")

    if (
        weight_evidence.get("Weight Status") != "calculated"
        or weight_evidence.get("Weight Calculation Eligible") is not True
    ):
        return _review("weight_evidence_incomplete")

    expected_weight = weight_evidence.get(
        "Expected Chargeable Weight (kg)"
    )

    if not _valid_amount(expected_weight):
        return _review("weight_evidence_incomplete")

    pricing_shipment = shipment.copy()
    pricing_shipment["Chargeable Weight (kg)"] = float(
        expected_weight
    )

    selection = select_contract_rate(
        pricing_shipment,
        contract_rates,
    )

    if selection["status"] != "matched":
        return _review(selection["reason"])

    expected_freight = selection["expected_base_freight"]

    invoiced_freight = shipment.get("Base Freight")

    if not _valid_amount(invoiced_freight, allow_zero=True):
        return _review("invalid_invoiced_base_freight")

    expected = Decimal(str(expected_freight))
    invoiced = Decimal(str(invoiced_freight))
    allowed_difference = Decimal(str(tolerance))

    difference = invoiced - expected

    if difference > allowed_difference:
        status = "potential_overcharge"
        potential_overcharge = float(difference)
    elif difference < -allowed_difference:
        status = "below_contract_rate"
        potential_overcharge = 0.0
    else:
        status = "matched"
        potential_overcharge = 0.0

    return {
        "status": status,
        "reason": None,
        "expected_base_freight": float(expected),
        "invoiced_base_freight": float(invoiced),
        "potential_overcharge": potential_overcharge,
        "rate_difference": float(difference),
        "currency": selection["currency"],
        "expected_chargeable_weight_kg": float(expected_weight),
        "invoice_line_id": shipment.get("Invoice Line ID"),
    }

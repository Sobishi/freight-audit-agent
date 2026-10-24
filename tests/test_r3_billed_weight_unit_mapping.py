import pandas as pd
import pytest

from data.mapping import parse_mapping, standardize_invoice


def mapping():
    return parse_mapping({
        "carrier_id": "demo_carrier",
        "carrier_name": "Demo Carrier",
        "columns": {
            "Waybill": "AWB",
            "Amount": "Total",
            "ActualKg": "Actual Weight",
            "BilledKg": "Billed Weight",
            "ActualUnit": "Weight Unit",
            "BilledUnit": "Billed Weight Unit",
        },
    })


def test_billed_weight_unit_survives_standardization():
    raw = pd.DataFrame([{
        "Waybill": "PKG001",
        "Amount": "120",
        "ActualKg": "5",
        "BilledKg": "11",
        "ActualUnit": "kg",
        "BilledUnit": "lb",
    }])

    result = standardize_invoice(raw, mapping())

    assert result.loc[0, "Weight Unit"] == "kg"
    assert result.loc[0, "Billed Weight Unit"] == "lb"


def test_billed_weight_unit_is_normalized():
    raw = pd.DataFrame([{
        "Waybill": "PKG001",
        "Amount": "120",
        "ActualKg": "5",
        "BilledKg": "6",
        "ActualUnit": "kg",
        "BilledUnit": " KG ",
    }])

    result = standardize_invoice(raw, mapping())

    assert result.loc[0, "Billed Weight Unit"] == "kg"


def test_invalid_billed_weight_unit_is_rejected():
    raw = pd.DataFrame([{
        "Waybill": "PKG001",
        "Amount": "120",
        "ActualKg": "5",
        "BilledKg": "6",
        "ActualUnit": "kg",
        "BilledUnit": "stone",
    }])

    with pytest.raises(ValueError, match="Billed Weight Unit has invalid value"):
        standardize_invoice(raw, mapping())

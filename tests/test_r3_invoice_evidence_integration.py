import pandas as pd
import pytest

from data.mapping import parse_mapping, standardize_invoice
from audit_engine.weight_validation import (
    assess_mapped_package_weight_evidence,
)


def carrier_mapping():
    return parse_mapping({
        "carrier_id": "demo_carrier",
        "carrier_name": "Demo Carrier",
        "columns": {
            "Waybill": "AWB",
            "Amount": "Total",
            "ActualKg": "Actual Weight",
            "ParcelLength": "Length",
            "ParcelWidth": "Width",
            "ParcelHeight": "Height",
            "WeightUOM": "Weight Unit",
            "DimensionUOM": "Dimension Unit",
            "Packages": "Pieces",
        },
    })


def raw_invoice(**overrides):
    values = {
        "Waybill": "PKG001",
        "Amount": "120.00",
        "ActualKg": "5.0",
        "ParcelLength": "40",
        "ParcelWidth": "30",
        "ParcelHeight": "20",
        "WeightUOM": "kg",
        "DimensionUOM": "cm",
        "Packages": "1",
    }
    values.update(overrides)

    return pd.DataFrame([values])


def assess_invoice(raw, *, verified=True):
    standardized = standardize_invoice(raw, carrier_mapping())

    return (
        standardized,
        assess_mapped_package_weight_evidence(
            standardized.iloc[0],
            package_count_verified=verified,
        ),
    )


def test_complete_invoice_is_ready():
    standardized, result = assess_invoice(raw_invoice())

    assert standardized.loc[0, "Carrier ID"] == "demo_carrier"
    assert standardized.loc[0, "Actual Weight"] == 5.0
    assert standardized.loc[0, "Height"] == 20.0

    assert result["status"] == "ready"
    assert result["eligible"] is True


@pytest.mark.parametrize(
    "field,expected",
    [
        ("ActualKg", "missing_actual_weight"),
        ("ParcelLength", "incomplete_dimensions"),
        ("ParcelWidth", "incomplete_dimensions"),
        ("ParcelHeight", "incomplete_dimensions"),
    ],
)
def test_blank_invoice_measurements_remain_missing(field, expected):
    standardized, result = assess_invoice(
        raw_invoice(**{field: None})
    )

    assert pd.isna(
        standardized.loc[0, {
            "ActualKg": "Actual Weight",
            "ParcelLength": "Length",
            "ParcelWidth": "Width",
            "ParcelHeight": "Height",
        }[field]]
    )

    assert result["status"] == expected
    assert result["eligible"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("ActualKg", "0"),
        ("ParcelLength", "-4"),
        ("ParcelWidth", "0"),
    ],
)
def test_invalid_invoice_measurements_are_not_ready(field, value):
    _, result = assess_invoice(
        raw_invoice(**{field: value})
    )

    assert result["status"] == "invalid_measurement"


def test_multiple_packages_require_review():
    _, result = assess_invoice(
        raw_invoice(Packages="2")
    )

    assert result["status"] == "package_structure_review"


def test_unverified_package_count_requires_review():
    _, result = assess_invoice(
        raw_invoice(),
        verified=False,
    )

    assert result["status"] == "package_structure_review"


def test_missing_package_count_is_invalid():
    _, result = assess_invoice(
        raw_invoice(Packages=None)
    )

    assert result["status"] == "invalid_package_count"


def test_original_measurements_are_preserved_as_evidence():
    _, result = assess_invoice(raw_invoice())

    evidence = result["evidence"]

    assert evidence["actual_weight"] == 5.0
    assert evidence["length"] == 40.0
    assert evidence["width"] == 30.0
    assert evidence["height"] == 20.0
    assert evidence["weight_unit"] == "kg"
    assert evidence["dimension_unit"] == "cm"
    assert evidence["package_count"] == 1.0

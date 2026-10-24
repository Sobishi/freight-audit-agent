import pandas as pd
import pytest

from data.mapping import parse_mapping, standardize_invoice


def measurement_mapping():
    return parse_mapping({
        "carrier_id": "demo_carrier",
        "carrier_name": "Demo Carrier",
        "columns": {
            "Waybill": "AWB",
            "Amount": "Total",
            "Scale Weight": "Actual Weight",
            "Parcel Length": "Length",
            "Parcel Width": "Width",
            "Parcel Height": "Height",
            "Size Unit": "Dimension Unit",
            "Package Count": "Pieces",
        },
    })


def test_measurements_map_to_standard_fields():
    raw = pd.DataFrame({
        "Waybill": ["AWB001"],
        "Amount": [100.0],
        "Scale Weight": [8.4],
        "Parcel Length": [50],
        "Parcel Width": [40],
        "Parcel Height": [30],
        "Size Unit": ["cm"],
        "Package Count": [1],
    })

    result = standardize_invoice(raw, measurement_mapping())

    assert result.loc[0, "Actual Weight"] == 8.4
    assert result.loc[0, "Length"] == 50
    assert result.loc[0, "Width"] == 40
    assert result.loc[0, "Height"] == 30
    assert result.loc[0, "Dimension Unit"] == "cm"
    assert result.loc[0, "Pieces"] == 1


def test_missing_measurements_remain_missing_not_zero():
    raw = pd.DataFrame({
        "Waybill": ["AWB001"],
        "Amount": [100.0],
        "Scale Weight": [None],
        "Parcel Length": [None],
        "Parcel Width": [40],
        "Parcel Height": [30],
        "Size Unit": ["cm"],
        "Package Count": [1],
    })

    result = standardize_invoice(raw, measurement_mapping())

    assert pd.isna(result.loc[0, "Actual Weight"])
    assert pd.isna(result.loc[0, "Length"])
    assert result.loc[0, "Width"] == 40


def test_unsupported_dimension_unit_is_rejected():
    raw = pd.DataFrame({
        "Waybill": ["AWB001"],
        "Amount": [100.0],
        "Scale Weight": [8.4],
        "Parcel Length": [50],
        "Parcel Width": [40],
        "Parcel Height": [30],
        "Size Unit": ["metres"],
        "Package Count": [1],
    })

    with pytest.raises(ValueError, match="Dimension Unit"):
        standardize_invoice(raw, measurement_mapping())


def test_older_invoice_without_measurements_still_works():
    mapping = parse_mapping({
        "carrier_id": "legacy_carrier",
        "carrier_name": "Legacy Carrier",
        "columns": {
            "Waybill": "AWB",
            "Amount": "Total",
        },
    })

    raw = pd.DataFrame({
        "Waybill": ["AWB001"],
        "Amount": [100.0],
    })

    result = standardize_invoice(raw, mapping)

    assert result.loc[0, "AWB"] == "AWB001"
    assert result.loc[0, "Total"] == 100.0
    assert "Actual Weight" not in result.columns
    assert "Dimension Unit" not in result.columns


@pytest.mark.parametrize(
    "raw_unit,expected",
    [
        ("cm", "cm"),
        (" CM ", "cm"),
        ("IN", "in"),
        (" in ", "in"),
    ],
)
def test_dimension_units_are_normalized(raw_unit, expected):
    mapping = parse_mapping({
        "carrier_id": "demo_carrier",
        "carrier_name": "Demo Carrier",
        "columns": {
            "Waybill": "AWB",
            "Amount": "Total",
            "Size Unit": "Dimension Unit",
        },
    })

    raw = pd.DataFrame({
        "Waybill": ["AWB001"],
        "Amount": [100.0],
        "Size Unit": [raw_unit],
    })

    result = standardize_invoice(raw, mapping)

    assert result.loc[0, "Dimension Unit"] == expected


@pytest.mark.parametrize("unit", ["cm", "in", " CM ", "IN"])
def test_valid_dimension_unit_default(unit):
    mapping = parse_mapping({
        "carrier_id": "demo_carrier",
        "carrier_name": "Demo Carrier",
        "columns": {
            "Waybill": "AWB",
            "Amount": "Total",
        },
        "defaults": {
            "Dimension Unit": unit,
        },
    })

    raw = pd.DataFrame({
        "Waybill": ["AWB001"],
        "Amount": [100.0],
    })

    result = standardize_invoice(raw, mapping)

    assert result.loc[0, "Dimension Unit"] == unit.strip().lower()


@pytest.mark.parametrize("unit", ["metres", "feet", "mm"])
def test_invalid_dimension_unit_default_is_rejected(unit):
    with pytest.raises(ValueError, match="Dimension Unit"):
        parse_mapping({
            "carrier_id": "demo_carrier",
            "carrier_name": "Demo Carrier",
            "columns": {
                "Waybill": "AWB",
                "Amount": "Total",
            },
            "defaults": {
                "Dimension Unit": unit,
            },
        })


def test_incomplete_dimensions_are_not_filled_with_zero():
    mapping = measurement_mapping()

    raw = pd.DataFrame({
        "Waybill": ["AWB001"],
        "Amount": [100.0],
        "Scale Weight": [5.0],
        "Parcel Length": [50],
        "Parcel Width": [None],
        "Parcel Height": [30],
        "Size Unit": ["cm"],
        "Package Count": [1],
    })

    result = standardize_invoice(raw, mapping)

    assert result.loc[0, "Length"] == 50
    assert pd.isna(result.loc[0, "Width"])
    assert result.loc[0, "Height"] == 30
    assert result.loc[0, "Actual Weight"] == 5.0

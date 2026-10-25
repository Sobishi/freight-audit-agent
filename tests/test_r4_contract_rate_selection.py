import pandas as pd
import pytest

from audit_engine.contract_pricing import select_contract_rate


@pytest.fixture
def contract_rates():
    return pd.DataFrame([
        {
            "Carrier ID": "swiftline",
            "Service Type": "Express",
            "Zone": "A",
            "Min Weight (kg)": 0,
            "Max Weight (kg)": 5,
            "Valid From": "2026-01-01",
            "Valid To": "2026-06-30",
            "Currency": "USD",
            "Agreed Base Freight": 100.0,
        },
        {
            "Carrier ID": "swiftline",
            "Service Type": "Express",
            "Zone": "A",
            "Min Weight (kg)": 5,
            "Max Weight (kg)": 10,
            "Valid From": "2026-01-01",
            "Valid To": "2026-06-30",
            "Currency": "USD",
            "Agreed Base Freight": 150.0,
        },
        {
            "Carrier ID": "swiftline",
            "Service Type": "Express",
            "Zone": "A",
            "Min Weight (kg)": 0,
            "Max Weight (kg)": 5,
            "Valid From": "2026-07-01",
            "Valid To": "2026-12-31",
            "Currency": "USD",
            "Agreed Base Freight": 120.0,
        },
    ])


def shipment(**overrides):
    data = {
        "Carrier ID": "swiftline",
        "Service Type": "Express",
        "Zone": "A",
        "Chargeable Weight (kg)": 4.0,
        "Ship Date": "2026-05-15",
        "Currency": "USD",
    }
    data.update(overrides)
    return data


def test_selects_matching_zone_weight_band_and_contract_date(contract_rates):
    result = select_contract_rate(
        shipment(),
        contract_rates,
    )

    assert result["status"] == "matched"
    assert result["expected_base_freight"] == 100.0
    assert result["currency"] == "USD"


def test_weight_band_upper_boundary_is_inclusive(contract_rates):
    result = select_contract_rate(
        shipment(**{"Chargeable Weight (kg)": 5.0}),
        contract_rates,
    )

    assert result["status"] == "matched"
    assert result["expected_base_freight"] == 100.0


def test_weight_above_boundary_selects_next_band(contract_rates):
    result = select_contract_rate(
        shipment(**{"Chargeable Weight (kg)": 5.01}),
        contract_rates,
    )

    assert result["status"] == "matched"
    assert result["expected_base_freight"] == 150.0


def test_selects_contract_version_by_ship_date(contract_rates):
    result = select_contract_rate(
        shipment(**{"Ship Date": "2026-08-15"}),
        contract_rates,
    )

    assert result["status"] == "matched"
    assert result["expected_base_freight"] == 120.0


def test_missing_zone_requires_review(contract_rates):
    result = select_contract_rate(
        shipment(Zone=None),
        contract_rates,
    )

    assert result["status"] == "review"
    assert result["reason"] == "missing_zone"
    assert result["expected_base_freight"] is None


def test_missing_contract_rate_requires_review(contract_rates):
    result = select_contract_rate(
        shipment(Zone="Z"),
        contract_rates,
    )

    assert result["status"] == "review"
    assert result["reason"] == "rate_not_found"
    assert result["expected_base_freight"] is None


def test_overlapping_applicable_rates_are_rejected(contract_rates):
    duplicate = contract_rates.iloc[[0]].copy()
    duplicate["Agreed Base Freight"] = 110.0

    overlapping = pd.concat(
        [contract_rates, duplicate],
        ignore_index=True,
    )

    result = select_contract_rate(
        shipment(),
        overlapping,
    )

    assert result["status"] == "review"
    assert result["reason"] == "ambiguous_contract_rate"
    assert result["expected_base_freight"] is None


def test_currency_mismatch_requires_review(contract_rates):
    result = select_contract_rate(
        shipment(Currency="NGN"),
        contract_rates,
    )

    assert result["status"] == "review"
    assert result["reason"] == "currency_mismatch"
    assert result["expected_base_freight"] is None


def test_invalid_contract_weight_band_requires_review(contract_rates):
    invalid = contract_rates.copy()
    invalid.loc[0, "Max Weight (kg)"] = -5

    result = select_contract_rate(
        shipment(),
        invalid,
    )

    assert result["status"] == "review"
    assert result["reason"] == "invalid_contract_data"
    assert result["expected_base_freight"] is None


def test_invalid_contract_date_requires_review(contract_rates):
    invalid = contract_rates.copy()
    invalid.loc[0, "Valid From"] = "not-a-date"

    result = select_contract_rate(
        shipment(),
        invalid,
    )

    assert result["status"] == "review"
    assert result["reason"] == "invalid_contract_data"
    assert result["expected_base_freight"] is None


def test_invalid_agreed_rate_requires_review(contract_rates):
    invalid = contract_rates.copy()
    invalid.loc[0, "Agreed Base Freight"] = -100

    result = select_contract_rate(
        shipment(),
        invalid,
    )

    assert result["status"] == "review"
    assert result["reason"] == "invalid_contract_data"
    assert result["expected_base_freight"] is None


def test_invalid_unrelated_carrier_does_not_block_valid_match(contract_rates):
    unrelated = contract_rates.iloc[[0]].copy()
    unrelated["Carrier ID"] = "another_carrier"
    unrelated["Max Weight (kg)"] = -5

    rates = pd.concat(
        [contract_rates, unrelated],
        ignore_index=True,
    )

    result = select_contract_rate(
        shipment(),
        rates,
    )

    assert result["status"] == "matched"
    assert result["expected_base_freight"] == 100.0


def test_nonfinite_shipment_weight_requires_review(contract_rates):
    result = select_contract_rate(
        shipment(**{"Chargeable Weight (kg)": float("inf")}),
        contract_rates,
    )

    assert result["status"] == "review"
    assert result["reason"] == "invalid_chargeable_weight"
    assert result["expected_base_freight"] is None


def test_overlapping_contract_dates_are_ambiguous(contract_rates):
    overlapping = contract_rates.iloc[[0]].copy()

    overlapping["Valid From"] = "2026-04-01"
    overlapping["Valid To"] = "2026-09-30"
    overlapping["Agreed Base Freight"] = 115.0

    rates = pd.concat(
        [contract_rates, overlapping],
        ignore_index=True,
    )

    result = select_contract_rate(
        shipment(),
        rates,
    )

    assert result["status"] == "review"
    assert result["reason"] == "ambiguous_contract_rate"
    assert result["expected_base_freight"] is None


def test_contract_valid_from_boundary_is_inclusive(contract_rates):
    result = select_contract_rate(
        shipment(**{"Ship Date": "2026-01-01"}),
        contract_rates,
    )

    assert result["status"] == "matched"
    assert result["expected_base_freight"] == 100.0


def test_contract_valid_to_boundary_is_inclusive(contract_rates):
    result = select_contract_rate(
        shipment(**{"Ship Date": "2026-06-30"}),
        contract_rates,
    )

    assert result["status"] == "matched"
    assert result["expected_base_freight"] == 100.0


def test_missing_shipment_date_requires_review(contract_rates):
    result = select_contract_rate(
        shipment(**{"Ship Date": None}),
        contract_rates,
    )

    assert result["status"] == "review"
    assert result["reason"] == "missing_or_invalid_ship_date"
    assert result["expected_base_freight"] is None


def test_ambiguous_shipment_date_requires_review(contract_rates):
    result = select_contract_rate(
        shipment(**{"Ship Date": "05/06/2026"}),
        contract_rates,
    )

    assert result["status"] == "review"
    assert result["reason"] == "missing_or_invalid_ship_date"
    assert result["expected_base_freight"] is None


def test_ambiguous_contract_date_requires_review(contract_rates):
    invalid = contract_rates.copy()
    invalid.loc[0, "Valid From"] = "01/02/2026"

    result = select_contract_rate(
        shipment(),
        invalid,
    )

    assert result["status"] == "review"
    assert result["reason"] == "invalid_contract_data"
    assert result["expected_base_freight"] is None


def test_missing_contract_currency_requires_review(contract_rates):
    invalid = contract_rates.copy()
    invalid.loc[0, "Currency"] = None

    result = select_contract_rate(
        shipment(),
        invalid,
    )

    assert result["status"] == "review"
    assert result["reason"] == "invalid_contract_data"
    assert result["expected_base_freight"] is None


@pytest.mark.parametrize(
    "field, value, expected_reason",
    [
        ("Carrier ID", None, "missing_carrier"),
        ("Carrier ID", "   ", "missing_carrier"),
        ("Service Type", None, "missing_service"),
        ("Service Type", "   ", "missing_service"),
        ("Zone", None, "missing_zone"),
        ("Zone", "   ", "missing_zone"),
        ("Currency", None, "missing_currency"),
        ("Currency", "   ", "missing_currency"),
    ],
)
def test_missing_shipment_identifiers_require_review(
    contract_rates,
    field,
    value,
    expected_reason,
):
    result = select_contract_rate(
        shipment(**{field: value}),
        contract_rates,
    )

    assert result["status"] == "review"
    assert result["reason"] == expected_reason
    assert result["expected_base_freight"] is None


@pytest.mark.parametrize(
    "weight",
    [
        None,
        0,
        -1,
        float("nan"),
        float("-inf"),
        "not-a-weight",
        True,
    ],
)
def test_invalid_shipment_weights_require_review(
    contract_rates,
    weight,
):
    result = select_contract_rate(
        shipment(**{"Chargeable Weight (kg)": weight}),
        contract_rates,
    )

    assert result["status"] == "review"
    assert result["reason"] == "invalid_chargeable_weight"
    assert result["expected_base_freight"] is None


def test_valid_date_object_is_supported(contract_rates):
    from datetime import date

    result = select_contract_rate(
        shipment(**{"Ship Date": date(2026, 5, 15)}),
        contract_rates,
    )

    assert result["status"] == "matched"
    assert result["expected_base_freight"] == 100.0


def test_valid_pandas_timestamp_is_supported(contract_rates):
    result = select_contract_rate(
        shipment(**{"Ship Date": pd.Timestamp("2026-05-15")}),
        contract_rates,
    )

    assert result["status"] == "matched"
    assert result["expected_base_freight"] == 100.0

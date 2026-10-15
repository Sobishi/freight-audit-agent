import datetime

import pytest

from data.carrier_profile import load_profile, parse_profile


def _data(**changes):
    data = {
        "carrier_id": "demo_carrier",
        "carrier_name": "Demo Carrier",
        "currency": "USD",
        "pricing_method": "parcel_zone_weight",
        "unit_system": "metric",
        "dim_divisor": 5000,
        "rounding": {"step_low": 0.5, "threshold": 10, "step_high": 1},
    }
    data.update(changes)
    return data


def test_valid_profile_with_defaults():
    profile = parse_profile(_data())

    assert profile.carrier_id == "demo_carrier"
    assert profile.currency == "USD"
    assert profile.dim_divisor == 5000
    assert profile.rounding.step_low == 0.5
    assert profile.rounding.threshold == 10
    assert profile.rounding.step_high == 1
    assert profile.tolerance == 0.01
    assert profile.tax_rate == 0
    assert profile.tax_inclusive is False
    assert profile.max_band is None
    assert profile.surcharge_basis is None
    assert profile.valid_from is None


@pytest.mark.parametrize("key", [
    "carrier_id", "carrier_name", "currency", "pricing_method",
    "unit_system", "dim_divisor", "rounding",
])
def test_required_keys_are_enforced(key):
    data = _data()
    del data[key]

    with pytest.raises(ValueError, match=key):
        parse_profile(data)


def test_unknown_keys_are_rejected_to_catch_typos():
    with pytest.raises(ValueError, match="dim_divsor"):
        parse_profile(_data(dim_divsor=6000))


@pytest.mark.parametrize("field, value", [
    ("dim_divisor", 0),
    ("dim_divisor", -5000),
    ("dim_divisor", "5000"),
    ("dim_divisor", True),
    ("tolerance", -0.01),
    ("tax_rate", 1.5),
    ("tax_rate", -0.1),
    ("max_band", 0),
    ("currency", "usd"),
    ("currency", "US"),
    ("pricing_method", "air_freight"),
    ("unit_system", "martian"),
    ("surcharge_basis", "per_banana"),
    ("tax_inclusive", "yes"),
    ("carrier_id", "Bad Id"),
])
def test_invalid_values_are_rejected(field, value):
    with pytest.raises(ValueError, match=field):
        parse_profile(_data(**{field: value}))


@pytest.mark.parametrize("rounding", [
    {"step_low": 0, "threshold": 10, "step_high": 1},
    {"step_low": 0.5, "threshold": 0, "step_high": 1},
    {"step_low": 0.5, "threshold": 10, "step_high": -1},
    {"step_low": 0.5, "threshold": 10},
    {"step_low": 0.5, "threshold": 10, "step_high": 1, "extra": 1},
    "0.5",
])
def test_invalid_rounding_is_rejected(rounding):
    with pytest.raises(ValueError, match="rounding"):
        parse_profile(_data(rounding=rounding))


def test_validity_dates_accept_dates_and_iso_text():
    profile = parse_profile(_data(
        valid_from=datetime.date(2026, 1, 1),
        valid_to="2026-12-31",
    ))

    assert profile.valid_from == datetime.date(2026, 1, 1)
    assert profile.valid_to == datetime.date(2026, 12, 31)


def test_valid_to_cannot_be_before_valid_from():
    with pytest.raises(ValueError, match="valid_to"):
        parse_profile(_data(valid_from="2026-12-31", valid_to="2026-01-01"))


def test_invalid_date_text_is_rejected():
    with pytest.raises(ValueError, match="valid_from"):
        parse_profile(_data(valid_from="soon"))


def test_optional_fields_are_read():
    profile = parse_profile(_data(
        tolerance=0.05, max_band=30, excess_band_code="EXCESS_KG",
        tax_rate=0.075, tax_inclusive=True, surcharge_basis="per_kg",
    ))

    assert profile.tolerance == 0.05
    assert profile.max_band == 30
    assert profile.excess_band_code == "EXCESS_KG"
    assert profile.tax_rate == 0.075
    assert profile.tax_inclusive is True
    assert profile.surcharge_basis == "per_kg"


def test_load_profile_reads_a_yaml_file(tmp_path):
    path = tmp_path / "demo.yaml"
    path.write_text(
        "carrier_id: demo\ncarrier_name: Demo\ncurrency: USD\n"
        "pricing_method: parcel_zone_weight\nunit_system: metric\n"
        "dim_divisor: 5000\nrounding: {step_low: 1, threshold: 10, step_high: 1}\n"
        "valid_from: 2026-01-01\n"
    )

    profile = load_profile(path)

    assert profile.carrier_id == "demo"
    assert profile.valid_from == datetime.date(2026, 1, 1)


def test_load_profile_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_profile(tmp_path / "nope.yaml")


@pytest.mark.parametrize("text", ["", "- a\n- b\n", "just text", "a: [unclosed"])
def test_load_profile_rejects_files_that_are_not_a_mapping(tmp_path, text):
    path = tmp_path / "bad.yaml"
    path.write_text(text)

    with pytest.raises(ValueError, match="bad.yaml"):
        load_profile(path)

from pathlib import Path

import pandas as pd
import pytest

from audit_engine.rate_validation import validate_freight_rates
from data.carrier_config import DEFAULT_CONFIG_DIR, list_carriers, load_carrier_config
from data.loader import load_invoice_with_mapping

FIXTURES = Path(__file__).parent / "fixtures" / "carriers"
PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEMO_CARRIERS = ["corvant", "northbridge_express", "swiftline"]


# ---------------------------------------------------------------
# Exit test for Phase R1: three carriers, three layouts, no
# carrier specific code.
# ---------------------------------------------------------------

def test_demo_carriers_are_listed():
    assert list_carriers() == DEMO_CARRIERS


def _load_demo(carrier_id):
    config = load_carrier_config(carrier_id)
    invoice = load_invoice_with_mapping(
        FIXTURES / f"{carrier_id}_invoice.csv",
        config.mapping,
    )
    return config, invoice


@pytest.mark.parametrize("carrier_id", DEMO_CARRIERS)
def test_each_demo_carrier_loads_into_the_same_standard_format(carrier_id):
    config, invoice = _load_demo(carrier_id)

    for column in [
        "Invoice Line ID", "Carrier ID", "Carrier", "AWB", "Invoice Ref",
        "Ship Date", "Service Type", "Base Freight", "Surcharge Amount",
        "Tax Amount", "Total", "Currency", "Weight Unit", "Billed Weight",
    ]:
        assert column in invoice.columns, column

    assert len(invoice) == 3
    assert invoice["Invoice Line ID"].tolist() == [1, 2, 3]
    assert invoice["AWB"].is_unique
    assert invoice["Carrier ID"].eq(carrier_id).all()
    assert invoice["Carrier"].eq(config.profile.carrier_name).all()
    assert invoice["Currency"].eq("USD").all()
    assert invoice["Weight Unit"].eq("kg").all()


@pytest.mark.parametrize("carrier_id", DEMO_CARRIERS)
def test_mapped_amounts_add_up_on_every_line(carrier_id):
    """If a column were mapped to the wrong field, this would fail."""

    _, invoice = _load_demo(carrier_id)

    parts = invoice["Base Freight"] + invoice["Surcharge Amount"] + invoice["Tax Amount"]

    assert (parts - invoice["Total"]).abs().max() < 0.011


@pytest.mark.parametrize("carrier_id", DEMO_CARRIERS)
def test_ship_dates_are_all_in_september_2026(carrier_id):
    _, invoice = _load_demo(carrier_id)

    assert invoice["Ship Date"].notna().all()
    assert invoice["Ship Date"].dt.year.eq(2026).all()
    assert invoice["Ship Date"].dt.month.eq(9).all()


def test_swiftline_reads_day_first_dates_and_thousands_separators():
    _, invoice = _load_demo("swiftline")

    assert invoice.loc[0, "Ship Date"] == pd.Timestamp("2026-09-01")
    assert invoice.loc[0, "Base Freight"] == 1250.0
    assert invoice.loc[0, "Total"] == 1505.0


def test_corvant_header_is_found_below_the_title_rows():
    _, invoice = _load_demo("corvant")

    assert invoice.loc[0, "AWB"] == "CVF9000000001"
    assert invoice["Pieces"].tolist() == [1, 2, 1]


@pytest.mark.parametrize("carrier_id", DEMO_CARRIERS)
def test_standard_invoices_run_through_the_existing_rate_check(carrier_id):
    config, invoice = _load_demo(carrier_id)

    # The current rate check matches on carrier and service only, so the
    # agreed rate is the highest freight charge for that service. Zone and
    # weight band pricing arrives in a later phase.
    rate_card = (
        invoice.groupby(["Carrier", "Service Type"], as_index=False)["Base Freight"]
        .max()
        .rename(columns={"Base Freight": "Agreed Rate"})
    )

    result = validate_freight_rates(
        invoice,
        rate_card,
        tolerance=config.profile.tolerance,
    )

    assert result["Rate Status"].isin(["Rate Matched", "Below Agreed Rate"]).all()
    assert result["Potential Rate Overcharge"].eq(0).all()
    assert result["Rate Basis"].eq("Base Freight").all()


def test_a_new_carrier_needs_only_config_files_and_no_code(tmp_path):
    (tmp_path / "carriers").mkdir()
    (tmp_path / "mappings").mkdir()

    (tmp_path / "carriers" / "acme_air.yaml").write_text(
        "carrier_id: acme_air\ncarrier_name: Acme Air\ncurrency: GBP\n"
        "pricing_method: parcel_zone_weight\nunit_system: metric\n"
        "dim_divisor: 4000\n"
        "rounding: {step_low: 1, threshold: 5, step_high: 2}\n"
    )
    (tmp_path / "mappings" / "acme_air_invoice.yaml").write_text(
        "carrier_id: acme_air\ncarrier_name: Acme Air\n"
        "columns:\n  Consignment: AWB\n  Freight: Base Freight\n  Net: Total\n"
    )
    invoice_file = tmp_path / "acme.csv"
    invoice_file.write_text("Consignment,Freight,Net\nAC1,10.00,12.00\n")

    config = load_carrier_config("acme_air", tmp_path)
    invoice = load_invoice_with_mapping(invoice_file, config.mapping)

    assert list_carriers(tmp_path) == ["acme_air"]
    assert invoice.loc[0, "Carrier"] == "Acme Air"
    assert invoice.loc[0, "Currency"] == "GBP"
    assert invoice.loc[0, "Total"] == 12.0


def test_engine_code_contains_no_carrier_names():
    """Carrier rules must live in config files, never in code."""

    names = ("northbridge", "swiftline", "corvant")
    offenders = []

    code_files = [PROJECT_ROOT / "main.py"]
    for folder in ("data", "audit_engine", "reporting"):
        code_files += sorted((PROJECT_ROOT / folder).glob("*.py"))

    for path in code_files:
        text = path.read_text().lower()
        offenders += [f"{path.name}: {name}" for name in names if name in text]

    assert offenders == []


# ---------------------------------------------------------------
# Loading and consistency rules
# ---------------------------------------------------------------

def _write_pair(root, profile_id="demo", mapping_id="demo", extra_mapping="", currency="USD"):
    (root / "carriers").mkdir(exist_ok=True)
    (root / "mappings").mkdir(exist_ok=True)

    (root / "carriers" / "demo.yaml").write_text(
        f"carrier_id: {profile_id}\ncarrier_name: Demo\ncurrency: {currency}\n"
        "pricing_method: parcel_zone_weight\nunit_system: metric\n"
        "dim_divisor: 5000\n"
        "rounding: {step_low: 1, threshold: 10, step_high: 1}\n"
    )
    (root / "mappings" / "demo_invoice.yaml").write_text(
        f"carrier_id: {mapping_id}\ncarrier_name: Demo\n"
        "columns:\n  W: AWB\n  T: Total\n" + extra_mapping
    )


def test_profile_and_mapping_must_name_the_same_carrier(tmp_path):
    _write_pair(tmp_path, profile_id="demo", mapping_id="other")

    with pytest.raises(ValueError, match="other"):
        load_carrier_config("demo", tmp_path)


def test_file_must_match_the_requested_carrier(tmp_path):
    _write_pair(tmp_path, profile_id="different", mapping_id="different")

    with pytest.raises(ValueError, match="different"):
        load_carrier_config("demo", tmp_path)


@pytest.mark.parametrize("bad_id", ["../etc", "Demo", "a b", "", "a/b"])
def test_carrier_id_cannot_escape_the_config_folder(tmp_path, bad_id):
    with pytest.raises(ValueError, match="carrier"):
        load_carrier_config(bad_id, tmp_path)


def test_unknown_carrier_lists_the_available_ones(tmp_path):
    _write_pair(tmp_path)

    with pytest.raises(FileNotFoundError, match="demo"):
        load_carrier_config("missing_carrier", tmp_path)


def test_missing_mapping_file_is_reported(tmp_path):
    _write_pair(tmp_path)
    (tmp_path / "mappings" / "demo_invoice.yaml").unlink()

    with pytest.raises(FileNotFoundError, match="demo_invoice.yaml"):
        load_carrier_config("demo", tmp_path)


def test_currency_and_weight_unit_come_from_the_profile_when_not_in_the_mapping(tmp_path):
    _write_pair(tmp_path, currency="EUR")

    mapping = load_carrier_config("demo", tmp_path).mapping

    assert mapping.defaults["Currency"] == "EUR"
    assert mapping.defaults["Weight Unit"] == "kg"


def test_mapping_currency_must_agree_with_the_profile(tmp_path):
    _write_pair(tmp_path, currency="EUR", extra_mapping="defaults:\n  Currency: USD\n")

    with pytest.raises(ValueError, match="Currency"):
        load_carrier_config("demo", tmp_path)


def test_default_config_folder_is_inside_the_project():
    assert DEFAULT_CONFIG_DIR == PROJECT_ROOT / "config"


def test_list_carriers_on_an_empty_or_missing_folder(tmp_path):
    assert list_carriers(tmp_path) == []
    assert list_carriers(tmp_path / "nope") == []

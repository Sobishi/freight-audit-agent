import pandas as pd
import pytest

from data.mapping import parse_mapping, standardize_invoice


def _data(**changes):
    data = {
        "carrier_id": "demo_carrier",
        "carrier_name": "Demo Carrier",
        "columns": {
            "Waybill": "AWB",
            "Amount": "Total",
        },
    }
    data.update(changes)
    return data


def _mapping(**changes):
    return parse_mapping(_data(**changes))


def _raw(**columns):
    return pd.DataFrame(columns)


# ---------------------------------------------------------------
# Parsing and validating a mapping
# ---------------------------------------------------------------

def test_valid_mapping_gets_sensible_defaults():
    mapping = _mapping()

    assert mapping.carrier_id == "demo_carrier"
    assert mapping.carrier_name == "Demo Carrier"
    assert mapping.header_row == 0
    assert mapping.sheet is None
    assert mapping.date_format is None
    assert mapping.decimal == "."
    assert mapping.thousands == ","
    assert mapping.columns == {"Waybill": "AWB", "Amount": "Total"}


@pytest.mark.parametrize("bad_id", ["", "Demo Carrier!", "../x", "UPPER", None])
def test_mapping_rejects_invalid_carrier_id(bad_id):
    with pytest.raises(ValueError, match="carrier_id"):
        _mapping(carrier_id=bad_id)


def test_mapping_requires_carrier_name():
    data = _data()
    del data["carrier_name"]

    with pytest.raises(ValueError, match="carrier_name"):
        parse_mapping(data)


@pytest.mark.parametrize("bad_columns", [None, {}, ["AWB"], "AWB"])
def test_mapping_requires_columns(bad_columns):
    with pytest.raises(ValueError, match="columns"):
        _mapping(columns=bad_columns)


def test_mapping_rejects_unknown_standard_field():
    with pytest.raises(ValueError, match="Not A Field"):
        _mapping(columns={"Waybill": "AWB", "Amount": "Total", "X": "Not A Field"})


def test_mapping_rejects_generated_fields():
    with pytest.raises(ValueError, match="Carrier ID"):
        _mapping(columns={"Waybill": "AWB", "Amount": "Total", "X": "Carrier ID"})


def test_mapping_rejects_two_columns_for_one_field():
    with pytest.raises(ValueError, match="Total"):
        _mapping(columns={"Waybill": "AWB", "Amount": "Total", "Gross": "Total"})


def test_mapping_rejects_source_names_that_clean_to_the_same_name():
    with pytest.raises(ValueError, match="same"):
        _mapping(columns={"Waybill": "AWB", "waybill_": "Alt AWB", "Amount": "Total"})


@pytest.mark.parametrize("missing", ["AWB", "Total"])
def test_mapping_requires_awb_and_total(missing):
    columns = {"Waybill": "AWB", "Amount": "Total"}
    columns = {k: v for k, v in columns.items() if v != missing}
    columns["Other"] = "Service Type"

    with pytest.raises(ValueError, match=missing):
        _mapping(columns=columns)


def test_mapping_rejects_unknown_top_level_keys():
    with pytest.raises(ValueError, match="colums"):
        parse_mapping(_data(colums={"x": "AWB"}))


def test_defaults_must_use_standard_fields():
    with pytest.raises(ValueError, match="Nope"):
        _mapping(defaults={"Nope": "x"})


def test_default_cannot_duplicate_a_mapped_field():
    with pytest.raises(ValueError, match="Total"):
        _mapping(defaults={"Total": 5})


def test_text_default_must_be_text_not_a_yaml_boolean():
    # YAML turns an unquoted NO (Norway) into false.
    with pytest.raises(ValueError, match="quotes"):
        _mapping(defaults={"Origin Country": False})


def test_number_default_must_be_numeric():
    with pytest.raises(ValueError, match="Pieces"):
        _mapping(defaults={"Pieces": "many"})


@pytest.mark.parametrize("header_row", [-1, "0", 1.5, True])
def test_header_row_must_be_a_non_negative_integer(header_row):
    with pytest.raises(ValueError, match="header_row"):
        _mapping(header_row=header_row)


def test_number_format_characters_must_differ_and_be_single():
    with pytest.raises(ValueError, match="decimal"):
        _mapping(decimal=",", thousands=",")

    with pytest.raises(ValueError, match="decimal"):
        _mapping(decimal="..")


# ---------------------------------------------------------------
# Converting a raw invoice to the standard format
# ---------------------------------------------------------------

def test_standardize_renames_and_adds_generated_columns():
    raw = _raw(Waybill=["A1", "A2"], Amount=["10", "20.5"])

    result = standardize_invoice(raw, _mapping())

    assert list(result.columns[:2]) == ["Invoice Line ID", "Carrier ID"]
    assert result["Invoice Line ID"].tolist() == [1, 2]
    assert result["Carrier ID"].tolist() == ["demo_carrier"] * 2
    assert result["Carrier"].tolist() == ["Demo Carrier"] * 2
    assert result["AWB"].tolist() == ["A1", "A2"]
    assert result["Total"].tolist() == [10.0, 20.5]


def test_standardize_does_not_modify_the_input():
    raw = _raw(Waybill=[" A1 "], Amount=["1,000.00"])
    before = raw.copy()

    standardize_invoice(raw, _mapping())

    pd.testing.assert_frame_equal(raw, before)


def test_standardize_trims_text_and_turns_blanks_into_missing():
    raw = _raw(
        Waybill=["  A1  ", "A2"],
        Amount=["1", "2"],
        Svc=["  Express ", "   "],
    )
    mapping = _mapping(columns={"Waybill": "AWB", "Amount": "Total", "Svc": "Service Type"})

    result = standardize_invoice(raw, mapping)

    assert result["AWB"].tolist() == ["A1", "A2"]
    assert result.loc[0, "Service Type"] == "Express"
    assert pd.isna(result.loc[1, "Service Type"])


def test_standardize_reads_thousands_separators():
    raw = _raw(Waybill=["A1"], Amount=["1,250.00"])

    result = standardize_invoice(raw, _mapping())

    assert result.loc[0, "Total"] == 1250.0


def test_standardize_reads_european_number_format():
    raw = _raw(Waybill=["A1"], Amount=["1.250,50"])

    result = standardize_invoice(raw, _mapping(decimal=",", thousands="."))

    assert result.loc[0, "Total"] == 1250.5


def test_numeric_input_is_not_reinterpreted_by_the_number_format():
    raw = _raw(Waybill=["A1"], Amount=[1500.0])

    result = standardize_invoice(raw, _mapping(decimal=",", thousands="."))

    assert result.loc[0, "Total"] == 1500.0


def test_negative_amounts_are_kept_as_credits():
    raw = _raw(Waybill=["A1"], Amount=["-45.00"])

    result = standardize_invoice(raw, _mapping())

    assert result.loc[0, "Total"] == -45.0


def _date_mapping(**changes):
    return _mapping(
        columns={"Waybill": "AWB", "Amount": "Total", "Sent": "Ship Date"},
        **changes,
    )


def test_dates_use_the_mapping_date_format():
    raw = _raw(Waybill=["A1", "A2"], Amount=["1", "2"], Sent=["01/09/2026", "15/09/2026"])

    result = standardize_invoice(raw, _date_mapping(date_format="%d/%m/%Y"))

    assert result["Ship Date"].tolist() == [
        pd.Timestamp("2026-09-01"),
        pd.Timestamp("2026-09-15"),
    ]


def test_iso_dates_work_without_a_format():
    raw = _raw(Waybill=["A1"], Amount=["1"], Sent=["2026-09-01"])

    result = standardize_invoice(raw, _date_mapping())

    assert result.loc[0, "Ship Date"] == pd.Timestamp("2026-09-01")


def test_excel_style_iso_timestamps_work_even_when_a_format_is_set():
    raw = _raw(Waybill=["A1"], Amount=["1"], Sent=["2026-09-01 00:00:00"])

    result = standardize_invoice(raw, _date_mapping(date_format="%d/%m/%Y"))

    assert result.loc[0, "Ship Date"] == pd.Timestamp("2026-09-01")


def test_invalid_dates_are_rejected_with_the_column_name():
    raw = _raw(Waybill=["A1"], Amount=["1"], Sent=["not a date"])

    with pytest.raises(ValueError, match="Sent"):
        standardize_invoice(raw, _date_mapping())


def test_blank_dates_stay_missing():
    raw = _raw(Waybill=["A1"], Amount=["1"], Sent=[""])

    result = standardize_invoice(raw, _date_mapping())

    assert pd.isna(result.loc[0, "Ship Date"])


def test_completely_blank_rows_are_dropped():
    raw = _raw(Waybill=["A1", None, "A2"], Amount=["1", None, "2"])

    result = standardize_invoice(raw, _mapping())

    assert result["AWB"].tolist() == ["A1", "A2"]
    assert result["Invoice Line ID"].tolist() == [1, 2]


def test_missing_mapped_column_is_reported_by_name():
    raw = _raw(Waybill=["A1"])

    with pytest.raises(ValueError, match="Amount"):
        standardize_invoice(raw, _mapping())


def test_column_matching_ignores_case_and_punctuation():
    raw = _raw(**{"WAYBILL ": ["A1"], "amount_": ["5"]})

    result = standardize_invoice(raw, _mapping())

    assert result.loc[0, "AWB"] == "A1"
    assert result.loc[0, "Total"] == 5.0


def test_two_file_columns_matching_one_mapped_name_is_rejected():
    raw = _raw(**{"Amount": ["1"], "amount_": ["2"], "Waybill": ["A1"]})

    with pytest.raises(ValueError, match="Amount"):
        standardize_invoice(raw, _mapping())


def test_blank_awb_is_rejected():
    raw = _raw(Waybill=["A1", "  "], Amount=["1", "2"])

    with pytest.raises(ValueError, match="AWB"):
        standardize_invoice(raw, _mapping())


def test_non_numeric_total_is_rejected_with_the_column_name():
    raw = _raw(Waybill=["A1"], Amount=["abc"])

    with pytest.raises(ValueError, match="Amount"):
        standardize_invoice(raw, _mapping())


def test_blank_total_is_rejected():
    raw = _raw(Waybill=["A1"], Amount=[""])

    with pytest.raises(ValueError, match="Amount"):
        standardize_invoice(raw, _mapping())


def test_blank_optional_amount_stays_missing_not_zero():
    raw = _raw(Waybill=["A1"], Amount=["10"], Base=[""])
    mapping = _mapping(columns={"Waybill": "AWB", "Amount": "Total", "Base": "Base Freight"})

    result = standardize_invoice(raw, mapping)

    assert pd.isna(result.loc[0, "Base Freight"])


def test_currency_is_uppercased_and_validated():
    mapping = _mapping(columns={"Waybill": "AWB", "Amount": "Total", "Cur": "Currency"})

    result = standardize_invoice(_raw(Waybill=["A1"], Amount=["1"], Cur=["usd"]), mapping)
    assert result.loc[0, "Currency"] == "USD"

    with pytest.raises(ValueError, match="Currency"):
        standardize_invoice(_raw(Waybill=["A1"], Amount=["1"], Cur=["US"]), mapping)


def test_weight_unit_is_lowercased_and_validated():
    mapping = _mapping(columns={"Waybill": "AWB", "Amount": "Total", "U": "Weight Unit"})

    result = standardize_invoice(_raw(Waybill=["A1"], Amount=["1"], U=["KG"]), mapping)
    assert result.loc[0, "Weight Unit"] == "kg"

    with pytest.raises(ValueError, match="Weight Unit"):
        standardize_invoice(_raw(Waybill=["A1"], Amount=["1"], U=["stone"]), mapping)


def test_defaults_fill_fields_the_file_does_not_have():
    mapping = _mapping(defaults={"Currency": "usd", "Weight Unit": "kg", "Pieces": 1})

    result = standardize_invoice(_raw(Waybill=["A1"], Amount=["1"]), mapping)

    assert result.loc[0, "Currency"] == "USD"
    assert result.loc[0, "Weight Unit"] == "kg"
    assert result.loc[0, "Pieces"] == 1


def test_mapped_carrier_column_blanks_fall_back_to_the_carrier_name():
    mapping = _mapping(columns={"Waybill": "AWB", "Amount": "Total", "Who": "Carrier"})
    raw = _raw(Waybill=["A1", "A2"], Amount=["1", "2"], Who=["Other Name", ""])

    result = standardize_invoice(raw, mapping)

    assert result["Carrier"].tolist() == ["Other Name", "Demo Carrier"]


def test_unmapped_columns_are_dropped_unless_requested():
    raw = _raw(Waybill=["A1"], Amount=["1"], Notes=["keep me?"])

    dropped = standardize_invoice(raw, _mapping())
    kept = standardize_invoice(raw, _mapping(), keep_unmapped=True)

    assert "Notes" not in dropped.columns
    assert kept.loc[0, "Notes"] == "keep me?"


def test_fields_appear_in_standard_order_after_generated_columns():
    mapping = _mapping(columns={
        "Amount": "Total",
        "Base": "Base Freight",
        "Waybill": "AWB",
    })
    raw = _raw(Waybill=["A1"], Amount=["3"], Base=["2"])

    result = standardize_invoice(raw, mapping)

    assert list(result.columns) == [
        "Invoice Line ID", "Carrier ID", "AWB", "Carrier", "Base Freight", "Total",
    ]


def test_date_error_names_the_expected_format_when_one_is_set():
    raw = _raw(Waybill=["A1"], Amount=["1"], Sent=["13/13/2026"])

    with pytest.raises(ValueError, match="%d/%m/%Y"):
        standardize_invoice(raw, _date_mapping(date_format="%d/%m/%Y"))


def test_date_error_suggests_date_format_when_none_is_set():
    raw = _raw(Waybill=["A1"], Amount=["1"], Sent=["01/09/2026"])

    with pytest.raises(ValueError, match="date_format"):
        standardize_invoice(raw, _date_mapping())


def test_invoice_with_no_data_rows_is_rejected():
    raw = _raw(Waybill=[None, None], Amount=[None, None])

    with pytest.raises(ValueError, match="no data rows"):
        standardize_invoice(raw, _mapping())

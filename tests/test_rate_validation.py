import pandas as pd
import pytest

from audit_engine.rate_validation import validate_freight_rates


def test_rate_validation_calculations():

    invoice = pd.DataFrame({
        "AWB": ["ABC123", "XYZ456", "DEF789"],
        "Carrier": ["DHL", "FedEx", "DHL"],
        "Service Type": ["Express", "Standard", "Express"],
        "Total": [18000, 20000, 12000],
    })

    rate_card = pd.DataFrame({
        "Carrier": ["DHL", "FedEx"],
        "Service Type": ["Express", "Standard"],
        "Agreed Rate": [15000, 20000],
    })

    result = validate_freight_rates(invoice, rate_card)

    assert result["Rate Difference"].tolist() == [
        3000, 0, -3000
    ]

    assert result["Potential Rate Overcharge"].tolist() == [
        3000, 0, 0
    ]

    assert result["Rate Status"].tolist() == [
        "Potential Overcharge",
        "Rate Matched",
        "Below Agreed Rate",
    ]


def test_missing_contractual_rate():

    invoice = pd.DataFrame({
        "AWB": ["ABC123"],
        "Carrier": ["UPS"],
        "Service Type": ["Express"],
        "Total": [18000],
    })

    rate_card = pd.DataFrame({
        "Carrier": ["DHL"],
        "Service Type": ["Express"],
        "Agreed Rate": [15000],
    })

    result = validate_freight_rates(invoice, rate_card)

    assert result.iloc[0]["Rate Status"] == "Rate Not Found"

    assert pd.isna(result.iloc[0]["Agreed Rate"])
    assert pd.isna(result.iloc[0]["Potential Rate Overcharge"])


def test_duplicate_rate_card_entries():

    invoice = pd.DataFrame({
        "AWB": ["ABC123"],
        "Carrier": ["DHL"],
        "Service Type": ["Express"],
        "Total": [18000],
    })

    rate_card = pd.DataFrame({
        "Carrier": ["DHL", "DHL"],
        "Service Type": ["Express", "Express"],
        "Agreed Rate": [15000, 16000],
    })

    with pytest.raises(
        ValueError,
        match="duplicate carrier/service combinations",
    ):
        validate_freight_rates(invoice, rate_card)

def test_rate_validation_uses_base_freight_amount():
    invoice = pd.DataFrame({
        "AWB": ["ABC123"],
        "Carrier": ["DHL"],
        "Service Type": ["Express"],
        "Base Freight": [12000],
        "Fuel Surcharge": [2000],
        "Handling Fee": [1000],
        "Total": [15000],
    })

    rate_card = pd.DataFrame({
        "Carrier": ["DHL"],
        "Service Type": ["Express"],
        "Agreed Rate": [12000],
    })

    result = validate_freight_rates(invoice, rate_card)

    assert result.loc[0, "Total"] == 15000
    assert result.loc[0, "Rate Difference"] == 0
    assert result.loc[0, "Potential Rate Overcharge"] == 0
    assert result.loc[0, "Rate Status"] == "Rate Matched"

def test_rate_validation_flags_missing_base_freight():
    invoice = pd.DataFrame({
        "AWB": ["ABC123", "XYZ456"],
        "Carrier": ["DHL", "DHL"],
        "Service Type": ["Express", "Express"],
        "Base Freight": [12000, None],
        "Total": [15000, 18000],
    })

    rate_card = pd.DataFrame({
        "Carrier": ["DHL"],
        "Service Type": ["Express"],
        "Agreed Rate": [12000],
    })

    result = validate_freight_rates(invoice, rate_card)

    # First shipment has a valid base freight amount.
    assert result.loc[0, "Rate Status"] == "Rate Matched"
    assert result.loc[0, "Potential Rate Overcharge"] == 0

    # Second shipment requires investigation.
    assert result.loc[1, "Rate Status"] == "Missing Base Freight"

    assert pd.isna(
        result.loc[1, "Rate Difference"]
    )

    assert pd.isna(
        result.loc[1, "Potential Rate Overcharge"]
    )

@pytest.mark.parametrize(
    "invalid_rate",
    [0, -5000, None, "invalid"],
)
def test_rate_validation_rejects_invalid_contractual_rates(
    invalid_rate,
):
    invoice = pd.DataFrame({
        "AWB": ["ABC123"],
        "Carrier": ["DHL"],
        "Service Type": ["Express"],
        "Total": [15000],
    })

    rate_card = pd.DataFrame({
        "Carrier": ["DHL"],
        "Service Type": ["Express"],
        "Agreed Rate": [invalid_rate],
    })

    with pytest.raises(
        ValueError,
        match="Agreed Rate must contain positive numeric values",
    ):
        validate_freight_rates(
            invoice,
            rate_card,
        )

def test_rate_validation_flags_missing_invoice_information():
    invoice = pd.DataFrame({
        "AWB": ["ABC123", "XYZ456", "DEF789", "GHI012"],
        "Carrier": ["DHL", None, "FedEx", "  "],
        "Service Type": ["Express", "Express", None, "Standard"],
        "Total": [15000, 18000, 22000, 12000],
    })

    rate_card = pd.DataFrame({
        "Carrier": ["DHL", "FedEx"],
        "Service Type": ["Express", "Standard"],
        "Agreed Rate": [12000, 18000],
    })

    result = validate_freight_rates(invoice, rate_card)

    assert result.loc[0, "Rate Status"] == "Potential Overcharge"

    for index in [1, 2, 3]:
        assert (
            result.loc[index, "Rate Status"]
            == "Missing Invoice Information"
        )

        assert pd.isna(
            result.loc[index, "Potential Rate Overcharge"]
        )
def test_rate_validation_tracks_overlapping_missing_information():
    invoice = pd.DataFrame({
        "AWB": ["ABC123", "XYZ456"],
        "Carrier": [None, "DHL"],
        "Service Type": ["Express", "Express"],
        "Base Freight": [None, 12000],
        "Total": [15000, 15000],
    })

    rate_card = pd.DataFrame({
        "Carrier": ["DHL"],
        "Service Type": ["Express"],
        "Agreed Rate": [12000],
    })

    result = validate_freight_rates(invoice, rate_card)

    assert result.loc[0, "Rate Status"] == "Missing Invoice Information"

    assert result.loc[0, "Has Missing Invoice Information"]
    assert result.loc[0, "Has Missing Base Freight"]

    assert pd.isna(result.loc[0, "Potential Rate Overcharge"])

    assert not result.loc[1, "Has Missing Invoice Information"]
    assert not result.loc[1, "Has Missing Base Freight"]

    assert result.loc[1, "Rate Status"] == "Rate Matched"



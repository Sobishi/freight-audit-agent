import pandas as pd
import pytest

from data.schema import (
    normalize_columns,
    validate_required_columns,
)


def test_normalizes_alternative_column_names():
    """Recognize common freight invoice naming conventions."""

    invoice = pd.DataFrame({
        "Tracking Number": ["ABC123"],
        "Courier": ["DHL"],
        "Invoice Amount": [15000],
        "Invoice Number": ["INV001"],
    })

    result = normalize_columns(invoice)

    assert "AWB" in result.columns
    assert "Carrier" in result.columns
    assert "Total" in result.columns
    assert "Invoice Ref" in result.columns

    assert result.loc[0, "AWB"] == "ABC123"
    assert result.loc[0, "Total"] == 15000


def test_preserves_unrecognized_columns():
    """Do not discard customer-specific information."""

    invoice = pd.DataFrame({
        "Tracking Number": ["ABC123"],
        "Customer Department": ["Operations"],
    })

    result = normalize_columns(invoice)

    assert "AWB" in result.columns
    assert "Customer Department" in result.columns


def test_rejects_ambiguous_column_mapping():
    """Do not silently select between equivalent columns."""

    invoice = pd.DataFrame({
        "AWB": ["ABC123"],
        "Tracking Number": ["XYZ456"],
    })

    with pytest.raises(ValueError, match="Ambiguous column mapping"):
        normalize_columns(invoice)


def test_identifies_missing_required_columns():
    """Report missing information required for an audit."""

    invoice = pd.DataFrame({
        "Courier": ["DHL"],
        "Invoice Amount": [15000],
    })

    normalized = normalize_columns(invoice)

    with pytest.raises(ValueError, match="Missing required columns"):
        validate_required_columns(
            normalized,
            ["AWB"],
        )


def test_preserves_original_dataframe():
    """Normalization must not modify the uploaded data."""

    invoice = pd.DataFrame({
        "Tracking Number": ["ABC123"],
    })

    normalize_columns(invoice)

    assert "Tracking Number" in invoice.columns
    assert "AWB" not in invoice.columns

def test_rejects_invalid_invoice_amounts():
    """
    Invoice amounts must be numeric when
    the Total column is provided.
    """

    import pandas as pd
    import pytest

    from data.schema import validate_invoice_data

    invoice = pd.DataFrame({
        "AWB": [
            "ABC123",
            "XYZ456",
            "DEF789",
        ],
        "Total": [
            15000,
            "Not Available",
            22000,
        ],
    })

    with pytest.raises(
        ValueError,
        match="invalid invoice amount",
    ):
        validate_invoice_data(invoice)
def test_normalizes_invoice_amounts():
    """
    Invoice amounts should be converted to numeric values
    without modifying the original DataFrame.
    """

    import pandas as pd

    from data.schema import normalize_invoice_data

    invoice = pd.DataFrame({
        "AWB": ["ABC123", "XYZ456", "DEF789"],
        "Total": ["15000", "22000.50", "-5000"],
    })

    normalized = normalize_invoice_data(invoice)

    # Verify that amounts are numeric.
    assert pd.api.types.is_numeric_dtype(normalized["Total"])

    # Verify that values are preserved.
    assert normalized["Total"].tolist() == [
        15000.0,
        22000.5,
        -5000.0,
    ]

    # Verify that shipment identifiers remain unchanged.
    assert normalized["AWB"].tolist() == [
        "ABC123",
        "XYZ456",
        "DEF789",
    ]

    # Verify that the original DataFrame was not modified.
    assert invoice["Total"].tolist() == [
        "15000",
        "22000.50",
        "-5000",
    ]
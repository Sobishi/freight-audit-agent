"""R7 financial input integrity acceptance tests."""

import math

import pandas as pd
import pytest

from data.loader import load_invoice, load_invoice_with_mapping
from data.carrier_config import load_carrier_config


@pytest.mark.parametrize(
    "amount",
    ["ABC", "", "inf", "-inf", "Infinity"],
)
def test_standard_loader_rejects_invalid_totals(
    tmp_path,
    amount,
):
    invoice_file = tmp_path / "invoice.csv"

    pd.DataFrame({
        "AWB": ["TEST001"],
        "Total": [amount],
    }).to_csv(invoice_file, index=False)

    with pytest.raises(ValueError):
        load_invoice(
            invoice_file,
            header_row=0,
        )


@pytest.mark.parametrize(
    "amount",
    ["ABC", "", "inf", "-inf", "Infinity"],
)
def test_carrier_loader_rejects_invalid_totals(
    tmp_path,
    amount,
):
    carrier = load_carrier_config("swiftline")

    invoice_file = tmp_path / "invoice.csv"

    # Reuse the existing pilot invoice structure to
    # preserve its carrier-specific mapping requirements.
    original = pd.read_csv(
        "tests/fixtures/carriers/swiftline_invoice.csv",
        dtype=str,
        keep_default_na=False,
    )

    # Locate the raw column mapped to Total.
    mapping = carrier.mapping
    total_sources = [
        source
        for source, target in mapping.columns.items()
        if target == "Total"
    ]

    assert len(total_sources) == 1

    total_column = total_sources[0]

    original.loc[0, total_column] = amount
    original.to_csv(invoice_file, index=False)

    with pytest.raises(ValueError):
        load_invoice_with_mapping(
            invoice_file,
            mapping,
        )


@pytest.mark.parametrize(
    "amount",
    ["100.00", "-25.50", "0"],
)
def test_standard_loader_preserves_valid_totals(
    tmp_path,
    amount,
):
    invoice_file = tmp_path / "valid_invoice.csv"

    pd.DataFrame({
        "AWB": ["TEST001"],
        "Total": [amount],
    }).to_csv(invoice_file, index=False)

    loaded = load_invoice(
        invoice_file,
        header_row=0,
    )

    actual = float(loaded.loc[0, "Total"])

    assert math.isfinite(actual)
    assert actual == float(amount)

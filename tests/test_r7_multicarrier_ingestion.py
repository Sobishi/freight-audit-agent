"""R7 pilot acceptance tests for configured carrier ingestion."""

from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from data.carrier_config import load_carrier_config
from data.loader import load_invoice_with_mapping


FIXTURES = Path("tests/fixtures/carriers")

CASES = [
    (
        "corvant",
        "corvant_invoice.csv",
        ["CVF9000000001", "CVF9000000002", "CVF9000000003"],
        ("99.60", "15.94", "11.56", "127.10"),
    ),
    (
        "northbridge_express",
        "northbridge_express_invoice.csv",
        ["NBX1000000001", "NBX1000000002", "NBX1000000003"],
        ("95.50", "15.28", "11.08", "121.86"),
    ),
    (
        "swiftline",
        "swiftline_invoice.csv",
        ["SFL7000000001", "SFL7000000002", "SFL7000000003"],
        ("1524.00", "182.88", "128.02", "1834.90"),
    ),
]


def load_pilot_invoice(carrier_id, filename):
    config = load_carrier_config(carrier_id)
    return load_invoice_with_mapping(
        FIXTURES / filename,
        config.mapping,
    )


def money_sum(series):
    return sum(
        (Decimal(str(value)) for value in series),
        Decimal("0"),
    ).quantize(Decimal("0.01"))


@pytest.mark.parametrize(
    "carrier_id,filename,expected_awbs,expected_totals",
    CASES,
)
def test_carrier_preserves_all_shipment_lines(
    carrier_id, filename, expected_awbs, expected_totals
):
    invoice = load_pilot_invoice(carrier_id, filename)

    assert len(invoice) == 3
    assert invoice["AWB"].tolist() == expected_awbs
    assert invoice["Invoice Line ID"].tolist() == [1, 2, 3]
    assert invoice["AWB"].is_unique
    assert invoice["Carrier ID"].eq(carrier_id).all()


@pytest.mark.parametrize(
    "carrier_id,filename,expected_awbs,expected_totals",
    CASES,
)
def test_carrier_preserves_financial_totals(
    carrier_id, filename, expected_awbs, expected_totals
):
    invoice = load_pilot_invoice(carrier_id, filename)

    columns = [
        "Base Freight",
        "Surcharge Amount",
        "Tax Amount",
        "Total",
    ]

    for column, expected in zip(columns, expected_totals):
        assert money_sum(invoice[column]) == Decimal(expected)


@pytest.mark.parametrize(
    "carrier_id,filename,expected_awbs,expected_totals",
    CASES,
)
def test_carrier_preserves_line_level_charge_reconciliation(
    carrier_id, filename, expected_awbs, expected_totals
):
    invoice = load_pilot_invoice(carrier_id, filename)

    for _, row in invoice.iterrows():
        components = sum(
            (
                Decimal(str(row[column]))
                for column in (
                    "Base Freight",
                    "Surcharge Amount",
                    "Tax Amount",
                )
            ),
            Decimal("0"),
        )

        total = Decimal(str(row["Total"]))

        assert components.quantize(
            Decimal("0.01")
        ) == total.quantize(Decimal("0.01"))


def test_corvant_metadata_rows_are_not_invoice_lines():
    invoice = load_pilot_invoice(
        "corvant", "corvant_invoice.csv"
    )

    assert len(invoice) == 3
    assert invoice["Invoice Ref"].eq("CVF-2609").all()


def test_swiftline_thousands_separator_is_preserved():
    invoice = load_pilot_invoice(
        "swiftline", "swiftline_invoice.csv"
    )

    assert Decimal(
        str(invoice.loc[0, "Base Freight"])
    ) == Decimal("1250.00")

    assert Decimal(
        str(invoice.loc[0, "Total"])
    ) == Decimal("1505.00")


def test_swiftline_day_first_date_is_preserved():
    invoice = load_pilot_invoice(
        "swiftline", "swiftline_invoice.csv"
    )

    assert pd.Timestamp(
        invoice.loc[0, "Ship Date"]
    ).date().isoformat() == "2026-09-01"

    assert pd.Timestamp(
        invoice.loc[1, "Ship Date"]
    ).date().isoformat() == "2026-09-03"

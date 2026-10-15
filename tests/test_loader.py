import pandas as pd
import pytest
from data.loader import load_invoice

def test_rejects_ambiguous_invoice_worksheets(tmp_path):
    """
    The loader must reject workbooks containing
    multiple equally plausible invoice worksheets.
    """

    workbook_path = tmp_path / "ambiguous_invoices.xlsx"

    invoice_data = pd.DataFrame({
        "Tracking Number": ["ABC123", "XYZ456"],
        "Courier": ["DHL", "FedEx"],
        "Invoice Number": ["INV001", "INV002"],
        "Invoice Amount": [15000, 22000],
    })

    with pd.ExcelWriter(workbook_path) as writer:
        invoice_data.to_excel(
            writer,
            sheet_name="October Invoices",
            index=False,
        )

        invoice_data.to_excel(
            writer,
            sheet_name="November Invoices",
            index=False,
        )

    with pytest.raises(
        ValueError,
        match="Multiple possible invoice worksheets",
    ):
        load_invoice(workbook_path)

def test_loads_and_normalizes_customer_csv():
    """
    Customer CSV files should be loaded and normalized
    without manually specifying column mappings.
    """

    invoice = load_invoice(
        "tests/fixtures/customer_invoice.csv"
    )

    assert isinstance(invoice, pd.DataFrame)

    assert len(invoice) == 3

    assert invoice.columns.tolist() == [
        "Invoice Line ID",
        "AWB",
        "Carrier",
        "Invoice Ref",
        "Total",
        "Service Type",
    ]

    assert invoice["Invoice Line ID"].tolist() == [1, 2, 3]
    assert invoice["Invoice Line ID"].is_unique

    assert invoice["AWB"].tolist() == [
        "ABC123",
        "XYZ456",
        "ABC123",
    ]


def test_automatically_loads_excel_invoice(tmp_path):
    """
    Verify automatic worksheet and header detection
    using a generated Excel workbook.
    """

    workbook_path = tmp_path / "customer_freight.xlsx"

    invoice_data = pd.DataFrame({
        "Tracking Number": ["AWB001", "AWB002", "AWB003"],
        "Courier": ["DHL", "FedEx", "DHL"],
        "Invoice Number": ["INV001", "INV002", "INV003"],
        "Invoice Amount": [15000, 22000, 18000],
    })

    summary_data = pd.DataFrame({
        "Description": ["Total Freight Spend"],
        "Amount": [55000],
    })

    with pd.ExcelWriter(workbook_path) as writer:

        summary_data.to_excel(
            writer,
            sheet_name="Summary",
            index=False,
        )

        invoice_data.to_excel(
            writer,
            sheet_name="October Billing",
            index=False,
            startrow=3,
        )

    invoice = load_invoice(workbook_path)

    assert isinstance(invoice, pd.DataFrame)

    assert len(invoice) == 3

    assert invoice["AWB"].tolist() == [
        "AWB001",
        "AWB002",
        "AWB003",
    ]

    assert invoice["Carrier"].tolist() == [
        "DHL",
        "FedEx",
        "DHL",
    ]

    assert invoice["Total"].tolist() == [
        15000,
        22000,
        18000,
    ]
def test_rejects_invoice_without_awb(tmp_path):
    """
    The loader must reject invoices without
    a recognizable shipment identifier.
    """

    csv_path = tmp_path / "missing_awb.csv"

    invoice_data = pd.DataFrame({
        "Courier": ["DHL", "FedEx"],
        "Invoice Number": ["INV001", "INV002"],
        "Invoice Amount": [15000, 22000],
    })

    invoice_data.to_csv(csv_path, index=False)

    with pytest.raises(
        ValueError,
        match="Unable to identify an invoice header row",
    ):
        load_invoice(csv_path)

def test_allows_manual_worksheet_selection(tmp_path):
    """
    Users should be able to select a worksheet
    when automatic detection is ambiguous.
    """

    workbook_path = tmp_path / "multiple_invoices.xlsx"

    october_data = pd.DataFrame({
        "Tracking Number": ["OCT001", "OCT002"],
        "Courier": ["DHL", "FedEx"],
        "Invoice Amount": [15000, 22000],
    })

    november_data = pd.DataFrame({
        "Tracking Number": ["NOV001", "NOV002"],
        "Courier": ["DHL", "FedEx"],
        "Invoice Amount": [18000, 25000],
    })

    with pd.ExcelWriter(workbook_path) as writer:
        october_data.to_excel(
            writer,
            sheet_name="October Invoices",
            index=False,
        )

        november_data.to_excel(
            writer,
            sheet_name="November Invoices",
            index=False,
        )

    invoice = load_invoice(
        workbook_path,
        sheet_name="November Invoices",
    )

    assert len(invoice) == 2

    assert invoice["AWB"].tolist() == [
        "NOV001",
        "NOV002",
    ]

    assert invoice["Total"].tolist() == [
        18000,
        25000,
    ]

def test_rejects_conflicting_column_mappings(tmp_path):
    """
    The loader must reject invoices containing
    multiple columns that map to the same field.
    """

    csv_path = tmp_path / "conflicting_columns.csv"

    invoice_data = pd.DataFrame({
        "AWB": ["ABC123", "XYZ456"],
        "Tracking Number": ["ABC123", "XYZ456"],
        "Courier": ["DHL", "FedEx"],
        "Invoice Amount": [15000, 22000],
    })

    invoice_data.to_csv(csv_path, index=False)

    with pytest.raises(
        ValueError,
        match="Ambiguous column mapping",
    ):
        load_invoice(csv_path)

def test_rejects_ambiguous_header_even_with_valid_candidate(tmp_path):
    """
    The loader should not silently ignore a plausible
    ambiguous header when another valid header exists.
    """

    workbook_path = tmp_path / "conflicting_headers.xlsx"

    rows = [
        ["AWB", "Tracking Number", "Courier", "Invoice Amount"],
        ["AWB", "Carrier", "Total", None],
        ["ABC123", "DHL", 15000, None],
    ]

    with pd.ExcelWriter(workbook_path) as writer:
        pd.DataFrame(rows).to_excel(
            writer,
            sheet_name="Billing",
            index=False,
            header=False,
        )

    with pytest.raises(
        ValueError,
        match="Ambiguous column mapping",
    ):
        load_invoice(
            workbook_path,
            sheet_name="Billing",
        )

def test_allows_manual_header_selection(tmp_path):
    """
    Users should be able to specify the header row
    instead of relying on automatic detection.
    """

    workbook_path = tmp_path / "manual_header.xlsx"

    invoice_data = pd.DataFrame({
        "Tracking Number": ["ABC123", "XYZ456"],
        "Courier": ["DHL", "FedEx"],
        "Invoice Amount": [15000, 22000],
    })

    with pd.ExcelWriter(workbook_path) as writer:
        invoice_data.to_excel(
            writer,
            sheet_name="Customer Billing",
            index=False,
            startrow=5,
        )

    invoice = load_invoice(
        workbook_path,
        sheet_name="Customer Billing",
        header_row=5,
    )

    assert len(invoice) == 2

    assert invoice["AWB"].tolist() == [
        "ABC123",
        "XYZ456",
    ]

    assert invoice["Total"].tolist() == [
        15000,
        22000,
    ]

def test_loader_rejects_missing_awb_values(tmp_path):
    """
    The loader must reject invoices containing
    missing or blank shipment identifiers.
    """

    csv_path = tmp_path / "missing_awb_values.csv"

    invoice_data = pd.DataFrame({
        "Tracking Number": [
            "ABC123",
            None,
            "  ",
            "XYZ456",
        ],
        "Courier": [
            "DHL",
            "FedEx",
            "DHL",
            "FedEx",
        ],
        "Invoice Amount": [
            15000,
            22000,
            18000,
            25000,
        ],
    })

    invoice_data.to_csv(csv_path, index=False)

    with pytest.raises(
        ValueError,
        match=r"Invoice contains 2 record\(s\) with missing AWB values",
    ):
        load_invoice(csv_path)

def test_loader_returns_numeric_invoice_amounts(tmp_path):
    """
    The loader should return numeric invoice amounts
    even when the source CSV stores them as text.
    """

    csv_path = tmp_path / "numeric_amounts.csv"

    invoice_data = pd.DataFrame({
        "Tracking Number": ["ABC123", "XYZ456", "DEF789"],
        "Courier": ["DHL", "FedEx", "DHL"],
        "Invoice Amount": ["15000", "22000.50", "-5000"],
    })

    invoice_data.to_csv(csv_path, index=False)

    invoice = load_invoice(csv_path)

    # Confirm that the amount column is numeric.
    assert pd.api.types.is_numeric_dtype(invoice["Total"])

    # Confirm that the values are correct.
    assert invoice["Total"].tolist() == [
        15000.0,
        22000.5,
        -5000.0,
    ]

    # Confirm that shipment identifiers are preserved.
    assert invoice["AWB"].tolist() == [
        "ABC123",
        "XYZ456",
        "DEF789",
    ]

def test_loader_preserves_awb_formats(tmp_path):
    """
    Shipment identifiers must be preserved as text,
    regardless of their original format.
    """

    csv_path = tmp_path / "awb_formats.csv"

    csv_path.write_text(
        "Tracking Number,Courier,Invoice Amount\n"
        "0012345678,DHL,15000\n"
        "1234567890,FedEx,22000\n"
        "DHL12345678,DHL,18000\n"
        "1Z999AA10123456784,UPS,25000\n"
        "ABC-123-XYZ,FedEx,12000\n"
        "AB 123456,DHL,16000\n"
    )

    invoice = load_invoice(csv_path)

    assert invoice["AWB"].tolist() == [
        "0012345678",
        "1234567890",
        "DHL12345678",
        "1Z999AA10123456784",
        "ABC-123-XYZ",
        "AB 123456",
    ]

def test_loader_preserves_numeric_awb_leading_zeros(tmp_path):
    """
    Numeric-looking shipment identifiers must retain
    their leading zeros when loaded from CSV.
    """

    csv_path = tmp_path / "numeric_awbs.csv"

    csv_path.write_text(
        "Tracking Number,Courier,Invoice Amount\n"
        "0012345678,DHL,15000\n"
        "0009876543,FedEx,22000\n"
        "1234567890,DHL,18000\n"
    )

    invoice = load_invoice(csv_path)

    assert invoice["AWB"].tolist() == [
        "0012345678",
        "0009876543",
        "1234567890",
    ]

def test_loader_preserves_excel_awb_formats(tmp_path):
    """
    Excel shipment identifiers must be returned as text,
    preserving leading zeros where they exist in the source.
    """

    workbook_path = tmp_path / "excel_awb_formats.xlsx"

    invoice_data = pd.DataFrame({
        "Tracking Number": [
            "0012345678",
            1234567890,
            "DHL12345678",
            "1Z999AA10123456784",
        ],
        "Courier": [
            "DHL",
            "FedEx",
            "DHL",
            "UPS",
        ],
        "Invoice Amount": [
            15000,
            22000,
            18000,
            25000,
        ],
    })

    invoice_data.to_excel(
        workbook_path,
        sheet_name="Billing",
        index=False,
    )

    invoice = load_invoice(
        workbook_path,
        sheet_name="Billing",
    )

    assert invoice["AWB"].tolist() == [
        "0012345678",
        "1234567890",
        "DHL12345678",
        "1Z999AA10123456784",
    ]

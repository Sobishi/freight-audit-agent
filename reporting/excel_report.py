from pathlib import Path
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
import pandas as pd


def generate_excel_report(
    audited_invoice: pd.DataFrame,
    findings: pd.DataFrame,
    summary: dict,
    output_path: str,
combined_exposure: pd.DataFrame | None = None,
    rate_results: pd.DataFrame | None = None,
    weight_results: pd.DataFrame | None = None,
    contract_pricing_results: pd.DataFrame | None = None,
) -> Path:
    """
    Generate an Excel freight audit report.

    The report contains:
    - Audit Summary
    - Audit Findings
    - Invoice Data
    - Rate Validation (when a rate card is provided)
    """

    output_file = Path(output_path)

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Preserve the original audit summary.
    report_summary = summary.copy()

    # Add rate validation metrics when rate results are available.
    if rate_results is not None:
        report_summary["Potential Rate Overcharges"] = int(
            (rate_results["Rate Status"] == "Potential Overcharge").sum()
        )

        report_summary["Missing Contractual Rates"] = int(
            (rate_results["Rate Status"] == "Rate Not Found").sum()
        )

        # Count missing invoice information, including overlapping exceptions.
        if "Has Missing Invoice Information" in rate_results.columns:
            missing_invoice_count = int(
                rate_results["Has Missing Invoice Information"].sum()
            )
        else:
            missing_invoice_count = int(
                (
                        rate_results["Rate Status"]
                        == "Missing Invoice Information"
                ).sum()
            )

        report_summary["Missing Invoice Information"] = missing_invoice_count

        # Count missing base freight, including overlapping exceptions.
        if "Has Missing Base Freight" in rate_results.columns:
            missing_base_freight_count = int(
                rate_results["Has Missing Base Freight"].sum()
            )
        else:
            missing_base_freight_count = int(
                (
                        rate_results["Rate Status"]
                        == "Missing Base Freight"
                ).sum()
            )

        report_summary["Missing Base Freight"] = missing_base_freight_count

        report_summary["Gross Potential Rate Exposure"] = float(
            rate_results["Potential Rate Overcharge"].sum()
        )
        # Include overlap-adjusted financial exposure when available.
        if combined_exposure is not None:
            report_summary["Combined Potential Exposure"] = float(
                combined_exposure["Combined Potential Exposure"].sum()
            )


    summary_df = pd.DataFrame(
        list(report_summary.items()),
        columns=["Metric", "Value"],
    )

    with pd.ExcelWriter(
        output_file,
        engine="openpyxl",
    ) as writer:

        summary_df.to_excel(
            writer,
            sheet_name="Audit Summary",
            index=False,
        )

        findings.to_excel(
            writer,
            sheet_name="Audit Findings",
            index=False,
        )

        audited_invoice.to_excel(
            writer,
            sheet_name="Invoice Data",
            index=False,
        )

        # Weight evidence is review information, not financial exposure.
        if weight_results is not None:
            weight_results.to_excel(
                writer,
                sheet_name="Weight Validation",
                index=False,
            )
        # R4 contract pricing is reported separately from combined exposure.
        if contract_pricing_results is not None:
            contract_pricing_results.to_excel(
                writer,
                sheet_name="Contract Pricing",
                index=False,
            )

        # Add a detailed reconciliation worksheet when available.
        if combined_exposure is not None:
            reconciliation_columns = [
                "Invoice Line ID",
                "AWB",
                "Invoice Ref",
                "Carrier",
                "Total",
                "Is Exact Duplicate Charge",
                "Duplicate Exposure",
                "Rate Exposure",
                "Combined Potential Exposure",
                'Charge Type',
                'Currency',
                'Duplicate Match Basis',
                'Duplicate Exposure Status',
                'Credit Match Status',
                'Matched Line ID',
                'Excluded From Exposure',
                "Rate Exposure Status",
                "Payment Treatment",
            ]

            available_columns = [
                column
                for column in reconciliation_columns
                if column in combined_exposure.columns
            ]

            combined_exposure[available_columns].to_excel(
                writer,
                sheet_name="Exposure Reconciliation",
                index=False,
            )

        # Include rate validation only when results are available.
        if rate_results is not None:
            rate_columns = [
                "AWB",
                "Carrier",
                "Invoice Ref",
                "Service Type",
                "Total",
                "Rate Validation Amount",
                "Agreed Rate",
                "Rate Difference",
                "Potential Rate Overcharge",
                "Rate Status",
                "Rate Basis",
                'Charge Type',
                'Currency',
                'Credit Match Status',
                'Matched Line ID',
                'Excluded From Exposure',
                "Rule IDs",
                "Rule Versions",
                "Rule Descriptions",
                "Has Missing Invoice Information",
                "Has Missing Base Freight",
            ]
            available_columns = [
                column
                for column in rate_columns
                if column in rate_results.columns
            ]

            rate_results[available_columns].to_excel(
                writer,
                sheet_name="Rate Validation",
                index=False,
            )

        # Format every worksheet once.
        for worksheet in writer.book.worksheets:
            format_excel_worksheet(worksheet)

        # Highlight duplicate audit findings.
        highlight_audit_findings(
            writer.book["Audit Findings"]
        )

        # Add the audit disclaimer once.
        add_audit_disclaimer(
            writer.book["Audit Summary"]
        )

    return output_file

def format_excel_worksheet(worksheet):
    """
    Apply professional formatting to an audit worksheet.
    """

    header_fill = PatternFill(
        start_color="17365D",
        end_color="17365D",
        fill_type="solid",
    )

    header_font = Font(
        color="FFFFFF",
        bold=True,
    )

    # Format column headers
    for cell in worksheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
        )

    worksheet.row_dimensions[1].height = 25

    # Automatically adjust column widths
    for column in worksheet.columns:
        column_letter = get_column_letter(column[0].column)

        max_length = max(
            len(str(cell.value))
            if cell.value is not None
            else 0
            for cell in column
        )

        worksheet.column_dimensions[column_letter].width = min(
            max_length + 4,
            45,
        )

    # Freeze the header row
    worksheet.freeze_panes = "A2"

    # Enable filters
    worksheet.auto_filter.ref = worksheet.dimensions

    # Format financial columns
    financial_headers = {
        "Total",
        "Billed Amount",
        "Potential Exposure",
        "Agreed Rate",
        "Rate Difference",
        "Rate Validation Amount",
        "Potential Rate Overcharge",
    }

    for column in worksheet.iter_cols():
        header = column[0].value

        if header in financial_headers:
            for cell in column[1:]:
                if isinstance(cell.value, (int, float)):
                    cell.number_format = "#,##0.00;[Red](#,##0.00)"

def highlight_audit_findings(worksheet):
    """
    Highlight audit findings based on their classification.
    """

    classification_colors = {
        "Potential Duplicate Charge": "FCE4D6",
        "Credit or Reversal": "E2F0D9",
        "Zero-Value Adjustment": "FFF2CC",
    }

    headers = {
        cell.value: cell.column
        for cell in worksheet[1]
    }

    classification_column = headers.get("Classification")

    if classification_column is None:
        return

    for row in range(2, worksheet.max_row + 1):

        classification = worksheet.cell(
            row=row,
            column=classification_column,
        ).value

        color = classification_colors.get(classification)

        if color:
            worksheet.cell(
                row=row,
                column=classification_column,
            ).fill = PatternFill(
                start_color=color,
                end_color=color,
                fill_type="solid",
            )
def add_audit_disclaimer(worksheet):
    """
    Add an explanatory note to the audit summary.
    """

    disclaimer_row = worksheet.max_row + 3

    worksheet.cell(
        row=disclaimer_row,
        column=1,
        value="AUDIT DISCLAIMER",
    )

    worksheet.cell(
        row=disclaimer_row + 1,
        column=1,
        value=(
            "Potential exposure represents flagged billing amounts "
            "requiring investigation. It does not represent confirmed "
            "overcharges or recoverable amounts."
        ),
    )

    worksheet.merge_cells(
        start_row=disclaimer_row + 1,
        start_column=1,
        end_row=disclaimer_row + 1,
        end_column=4,
    )

    disclaimer_cell = worksheet.cell(
        row=disclaimer_row + 1,
        column=1,
    )

    disclaimer_cell.alignment = Alignment(
        wrap_text=True,
        vertical="top",
    )

    worksheet.row_dimensions[disclaimer_row + 1].height = 45
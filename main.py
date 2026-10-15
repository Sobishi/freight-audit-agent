import pandas as pd
import argparse
from audit_engine.exposure import calculate_combined_exposure
from reporting.excel_report import generate_excel_report
from data.loader import load_invoice
from audit_engine.rate_validation import validate_freight_rates
from audit_engine.audit import (
    detect_duplicates,
    detect_exact_duplicate_charges,
    generate_duplicate_findings,
    generate_audit_summary,
)

def main():
    parser = argparse.ArgumentParser(
        description="Freight Audit Agent"
    )

    parser.add_argument(
        "--output",
        default=None,
        help="Path to save the Excel audit report (optional)",
    )

    parser.add_argument(
        "invoice_file",
        help="Path to the customer invoice (CSV or Excel)",
    )
    parser.add_argument(
        "--sheet",
        default=None,
        help="Excel worksheet name (optional)"
    )

    parser.add_argument(
        "--header-row",
        type=int,
        default=None,
        help="Header row position, starting from 0 (optional)"
    )
    parser.add_argument(
        "--rates",
        help="Path to a CSV or Excel file containing agreed carrier rates.",
    )

    args = parser.parse_args()

    print("\nFREIGHT AUDIT AGENT")
    print("-------------------")

    invoice = load_invoice(
        file_path=args.invoice_file,
        sheet_name=args.sheet,
        header_row=args.header_row,
    )
    rate_results = None
    # Load and validate carrier rates when a rate card is provided.
    if args.rates:
        if args.rates.lower().endswith(".csv"):
            rate_card = pd.read_csv(args.rates)
        elif args.rates.lower().endswith((".xlsx", ".xls")):
            rate_card = pd.read_excel(args.rates)
        else:
            raise ValueError(
                "Unsupported rate card format. Use CSV or Excel."
            )

        rate_results = validate_freight_rates(invoice, rate_card)

        print("\nFREIGHT RATE VALIDATION")
        print("-----------------------")

        print(
            rate_results[
                [
                    "AWB",
                    "Carrier",
                    "Total",
                    "Agreed Rate",
                    "Rate Difference",
                    "Potential Rate Overcharge",
                    "Rate Status",
                ]
            ].to_string(index=False)
        )

        print(
            "\nTotal Potential Rate Overcharge: "
            f"{rate_results['Potential Rate Overcharge'].sum():,.2f}"
        )

    audited_invoice = detect_duplicates(invoice)

    audited_invoice = detect_exact_duplicate_charges(
        audited_invoice
    )

    findings = generate_duplicate_findings(audited_invoice)
    summary = generate_audit_summary(audited_invoice, findings)
    # Reconcile duplicate and rate exposures when a rate card is provided.
    combined_exposure = None

    if rate_results is not None:
        combined_exposure = calculate_combined_exposure(
            audited_invoice,
            rate_results,
        )

        combined_total = float(
            combined_exposure["Combined Potential Exposure"].sum()
        )

        print("\nFINANCIAL EXPOSURE RECONCILIATION")
        print("---------------------------------")
        print(
            f"Combined Potential Exposure: {combined_total:,.2f}"
        )
    if args.output:
        report_path = generate_excel_report(
    audited_invoice,
    findings,
    summary,
    args.output,
    combined_exposure=combined_exposure,
    rate_results=rate_results,
)

        print(f"\nExcel audit report saved to: {report_path}")
    duplicate_lines = audited_invoice[
        audited_invoice["Is Duplicate"]
    ]
    print("\nFREIGHT AUDIT SUMMARY")
    print("---------------------")

    for metric, value in summary.items():
        print(f"{metric}: {value:,.2f}" if metric == "Gross Potential Exposure"
              else f"{metric}: {value}")

    print("\nSTRUCTURED AUDIT FINDINGS")
    print("-------------------------")

    if findings.empty:
        print("No potential duplicate billing detected.")

    else:
        print(findings.to_string(index=False))


if __name__ == "__main__":
    main()
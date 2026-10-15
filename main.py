import pandas as pd
import argparse
from audit_engine.exposure import calculate_combined_exposure
from reporting.excel_report import generate_excel_report
from data.carrier_config import DEFAULT_CONFIG_DIR, load_carrier_config
from data.loader import load_invoice, load_invoice_with_mapping
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

    parser.add_argument(
        "--carrier",
        default=None,
        help=(
            "Carrier id. Loads that carrier's profile and invoice mapping "
            "from the config folder, instead of guessing column names."
        ),
    )

    parser.add_argument(
        "--config-dir",
        default=str(DEFAULT_CONFIG_DIR),
        help="Folder holding carriers/ and mappings/ (default: config).",
    )

    parser.add_argument(
        "--allow-total-fallback",
        action="store_true",
        help=(
            "Compare rates against Total when the invoice has no "
            "Base Freight column. Total may include surcharges and tax, "
            "so overcharges can be overstated."
        ),
    )

    args = parser.parse_args()

    print("\nFREIGHT AUDIT AGENT")
    print("-------------------")

    profile = None

    if args.carrier:
        try:
            carrier_config = load_carrier_config(
                args.carrier,
                args.config_dir,
            )

            profile = carrier_config.profile

            invoice = load_invoice_with_mapping(
                args.invoice_file,
                carrier_config.mapping,
                sheet_name=args.sheet,
                header_row=args.header_row,
            )
        except (FileNotFoundError, ValueError) as error:
            raise SystemExit(f"Error: {error}")

        print(
            f"Carrier profile: {profile.carrier_name} "
            f"({profile.carrier_id})"
        )

    else:
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

        try:
            rate_results = validate_freight_rates(
                invoice,
                rate_card,
                tolerance=profile.tolerance if profile else 0.01,
                require_base_freight=not args.allow_total_fallback,
            )
        except ValueError as error:
            if "Base Freight" in str(error):
                raise SystemExit(
                    "Error: the invoice has no Base Freight column, so "
                    "rates cannot be checked reliably. Add a freight "
                    "column, or run again with --allow-total-fallback to "
                    "compare against Total."
                )
            raise

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

        held = combined_exposure[
            combined_exposure["Payment Treatment"] == "Hold"
        ]

        if len(held):
            print(
                f"Lines on hold, exposure unknown: {len(held)} "
                f"(billed value {held['Total'].sum():,.2f})"
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
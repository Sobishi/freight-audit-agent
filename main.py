import pandas as pd
import argparse
import re
from pathlib import Path
from audit_engine.run_log import AuditRun
from audit_engine.rules import DUPLICATE_RULE_IDS, RATE_RULE_IDS
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

    parser.add_argument(
        "--log-dir", default="logs",
        help="Folder for local audit run records (default: logs).",
    )
    args = parser.parse_args()
    with AuditRun(args.log_dir, settings={
        "carrier_id": args.carrier,
        "sheet": args.sheet,
        "header_row": args.header_row,
        "allow_total_fallback": args.allow_total_fallback,
    }) as run:
        run.stage = "input_snapshot"
        run.add_input("invoice", args.invoice_file)
        if args.rates:
            run.add_input("rate_card", args.rates)
        if args.carrier:
            # Do not form a path from an invalid carrier id.
            if re.fullmatch(r"[a-z0-9_]+", args.carrier):
                root = Path(args.config_dir)
                run.add_input("carrier_profile", root / "carriers" / f"{args.carrier}.yaml")
                run.add_input("invoice_mapping", root / "mappings" / f"{args.carrier}_invoice.yaml")
        _execute_audit(args, run)
    print(f"Audit run log: {run.path}")


def _execute_audit(args, run):

    print("\nFREIGHT AUDIT AGENT")
    print("-------------------")

    run.stage = "invoice_loading"
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

    run.data["settings"]["effective_tolerance"] = profile.tolerance if profile else 0.01
    run.data["settings"]["profile_currency"] = profile.currency if profile else None
    rate_results = None
    # Load and validate carrier rates when a rate card is provided.
    if args.rates:
        run.stage = "rate_card_loading"
        if args.rates.lower().endswith(".csv"):
            rate_card = pd.read_csv(args.rates)
        elif args.rates.lower().endswith((".xlsx", ".xls")):
            rate_card = pd.read_excel(args.rates)
        else:
            raise ValueError(
                "Unsupported rate card format. Use CSV or Excel."
            )

        run.stage = "rate_validation"
        run.begin_rules(*RATE_RULE_IDS)
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

        run.complete_rules(*RATE_RULE_IDS)
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

    run.stage = "duplicate_checks"
    run.begin_rules(*DUPLICATE_RULE_IDS)
    audited_invoice = detect_duplicates(invoice)

    audited_invoice = detect_exact_duplicate_charges(
        audited_invoice
    )

    findings = generate_duplicate_findings(audited_invoice)
    if "Charge Type" not in invoice:
        print("Duplicate matching basis: legacy; Charge Type is unavailable. Review potential duplicates before claiming.")
    summary = generate_audit_summary(audited_invoice, findings)
    run.complete_rules(*DUPLICATE_RULE_IDS)
    # Reconcile duplicate and rate exposures when a rate card is provided.
    combined_exposure = None

    if rate_results is not None:
        run.stage = "exposure_calculation"
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
    run.set_summary({
        "invoice_lines": int(len(invoice)),
        "duplicate_findings": int(len(findings)),
        "charge_type_available": "Charge Type" in invoice,
        "credit_status_counts": ({str(k): int(v) for k, v in audited_invoice["Credit Match Status"].value_counts().items()}
                                 if "Credit Match Status" in audited_invoice else {}),
        "charge_review_lines": int(audited_invoice["Needs Charge Review"].sum()),
        "rate_status_counts": ({str(k): int(v) for k, v in rate_results["Rate Status"].value_counts().items()}
                               if rate_results is not None else {}),
        "held_lines": (int(combined_exposure["Payment Treatment"].eq("Hold").sum())
                       if combined_exposure is not None else None),
    })
    summary["Audit Run ID"] = run.run_id
    if args.output:
        run.stage = "report_generation"
        report_path = generate_excel_report(
            audited_invoice,
            findings,
            summary,
            args.output,
            combined_exposure=combined_exposure,
            rate_results=rate_results,
        )

        run.add_output("excel_report", report_path)
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
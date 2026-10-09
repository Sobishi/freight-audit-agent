from data.loader import load_workbook
from audit_engine.audit import detect_duplicates


def main():
    print("FREIGHT AUDIT AGENT")
    print("-------------------")

    data = load_workbook()

    invoice = data["Invoice"]

    # Run duplicate detection.
    audited_invoice = detect_duplicates(invoice)

    print("\nDUPLICATE BILLING ANALYSIS")
    print("--------------------------")

    duplicate_lines = audited_invoice[
        audited_invoice["Is Duplicate"]
    ]

    print(f"Total invoice lines: {len(audited_invoice)}")
    print(f"Duplicate billing lines: {len(duplicate_lines)}")

    print("\nFIRST TEN DUPLICATE LINES")
    print("-------------------------")

    columns = [
        "Carrier",
        "Invoice Ref",
        "AWB",
        "Occurrence",
        "Total",
    ]

    print(duplicate_lines[columns].head(10).to_string(index=False))

    # Compare our occurrence calculations against Excel.
    workbook_audit = data["Audit"]

    occurrence_matches = (
        audited_invoice["Occurrence"].reset_index(drop=True)
        == workbook_audit["Occurrence"].reset_index(drop=True)
    )

    print("\nEXCEL OCCURRENCE VALIDATION")
    print("---------------------------")

    print(f"Matching lines: {occurrence_matches.sum()}")
    print(f"Total lines: {len(occurrence_matches)}")

    if occurrence_matches.all():
        print("PASS: Python occurrence counts match Excel.")
    else:
        print("FAIL: Some occurrence counts differ from Excel.")


if __name__ == "__main__":
    main()
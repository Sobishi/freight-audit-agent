import pandas as pd


def detect_duplicates(invoice: pd.DataFrame) -> pd.DataFrame:
    """
    Identify repeated AWBs in invoice row order.

    The first occurrence is treated as the original billing.
    Subsequent occurrences are flagged as duplicates.

    This reproduces the workbook's COUNTIF logic.
    """

    result = invoice.copy()

    # Match Excel's TRIM behaviour for AWB values.
    result["AWB"] = (
        result["AWB"]
        .astype("string")
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
    )

    # Count occurrences in their original row order.
    result["Occurrence"] = (
        result.groupby("AWB", dropna=False).cumcount() + 1
    )

    # Flag every occurrence after the first.
    result["Is Duplicate"] = result["Occurrence"] > 1

    return result


def generate_duplicate_findings(
    audited_invoice: pd.DataFrame,
) -> pd.DataFrame:
    """
    Generate structured findings for repeated AWBs.

    Potential exposure represents the billed amount
    associated with a flagged line, not a confirmed loss.
    """

    duplicates = audited_invoice[
        audited_invoice["Is Duplicate"]
    ].copy()

    findings = pd.DataFrame(index=duplicates.index)

    findings["Finding Type"] = "Potential Duplicate Billing"
    findings["AWB"] = duplicates["AWB"]

    findings["Carrier"] = (
        duplicates["Carrier"]
        if "Carrier" in duplicates.columns
        else pd.NA
    )

    findings["Invoice Ref"] = (
        duplicates["Invoice Ref"]
        if "Invoice Ref" in duplicates.columns
        else pd.NA
    )

    findings["Occurrence"] = duplicates["Occurrence"]
    findings["Exact Charge Match"] = (
        duplicates["Is Exact Duplicate Charge"]
        if "Is Exact Duplicate Charge" in duplicates.columns
        else False
    )

    findings["Billed Amount"] = (
        duplicates["Total"]
        if "Total" in duplicates.columns
        else pd.NA
    )

    findings["Potential Exposure"] = (
        findings["Billed Amount"]
        .clip(lower=0)
    )

    findings["Classification"] = "Amount Unavailable"

    amounts = findings["Billed Amount"]

    findings.loc[
        amounts > 0,
        "Classification"
    ] = "Potential Duplicate Charge"

    findings.loc[
        amounts < 0,
        "Classification"
    ] = "Credit or Reversal"

    findings.loc[
        amounts == 0,
        "Classification"
    ] = "Zero-Value Adjustment"
    # Assign investigation priority based on available evidence.
    findings["Priority"] = "Review"

    findings.loc[
        findings["Classification"] == "Zero-Value Adjustment",
        "Priority",
    ] = "Low"

    findings.loc[
        findings["Classification"] == "Potential Duplicate Charge",
        "Priority",
    ] = "Medium"

    findings.loc[
        (findings["Classification"] == "Potential Duplicate Charge")
        & (findings["Exact Charge Match"] == True),
        "Priority",
    ] = "High"

    findings["Status"] = "Requires Review"

    return findings.reset_index(drop=True)


def generate_audit_summary(
    audited_invoice: pd.DataFrame,
    findings: pd.DataFrame,
) -> dict:
    """
    Summarize duplicate billing findings and financial exposure.

    Gross potential exposure is not a confirmed overcharge.
    """

    classifications = findings["Classification"]

    summary = {
        "Total Invoice Lines": int(len(audited_invoice)),

        "Total Findings": int(len(findings)),

        "Potential Duplicate Charges": int(
            (classifications == "Potential Duplicate Charge").sum()
        ),

        "Credits or Reversals": int(
            (classifications == "Credit or Reversal").sum()
        ),

        "Zero-Value Adjustments": int(
            (classifications == "Zero-Value Adjustment").sum()
        ),

        "Gross Potential Exposure": float(
            findings["Potential Exposure"].sum()
        ),
    }

    return summary


def detect_exact_duplicate_charges(
    invoice: pd.DataFrame,
) -> pd.DataFrame:
    """
    Identify repeated positive charges with matching
    AWB, carrier and billed amount.

    These are potential duplicates requiring review,
    not confirmed billing errors.
    """

    result = invoice.copy()

    result["AWB"] = (
        result["AWB"]
        .astype("string")
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
    )

    if "Carrier" in result.columns:
        result["Carrier"] = (
            result["Carrier"]
            .astype("string")
            .str.strip()
            .str.upper()
        )
    else:
        result["Carrier"] = pd.NA

    if "Total" not in result.columns:
        result["Is Exact Duplicate Charge"] = False
        return result

    amounts = pd.to_numeric(result["Total"], errors="coerce")

    # Compare normalized numeric amounts without changing
    # the original invoice values.
    comparison_data = pd.DataFrame({
        "AWB": result["AWB"],
        "Carrier": result["Carrier"],
        "Amount": amounts,
    })

    repeated = comparison_data.duplicated(
        subset=["AWB", "Carrier", "Amount"],
        keep="first",
    )

    result["Is Exact Duplicate Charge"] = (
        repeated & (amounts > 0)
    )

    return result
import warnings

import pandas as pd


def validate_freight_rates(
    invoice: pd.DataFrame,
    rate_card: pd.DataFrame,
    tolerance: float = 0.01,
    require_base_freight: bool = True,
) -> pd.DataFrame:
    """
    Compare invoiced freight amounts against agreed rates.

    This initial version assumes rates are determined
    by carrier and service type.

    tolerance
        Largest absolute difference, in invoice currency, that is still
        treated as a match. This absorbs rounding differences.
        The default is 0.01.

    require_base_freight
        When True (the default), an invoice without a Base Freight column
        is rejected instead of being compared on Total. Total normally
        includes surcharges and tax, so it can create false overcharges.
        Pass False to compare on Total. A warning is then raised and the
        Rate Basis column shows "Total".

    The "Rate Basis" column shows which invoice amount was compared.
    """

    if tolerance < 0:
        raise ValueError("Tolerance cannot be negative.")

    required_invoice_columns = {
        "AWB",
        "Carrier",
        "Service Type",
        "Total",
    }

    required_rate_columns = {
        "Carrier",
        "Service Type",
        "Agreed Rate",
    }

    if not required_invoice_columns.issubset(invoice.columns):
        raise ValueError("Invoice is missing required rate validation columns.")

    if not required_rate_columns.issubset(rate_card.columns):
        raise ValueError("Rate card is missing required columns.")

    invoice_data = invoice.copy()
    rates = rate_card.copy()

    for df in (invoice_data, rates):
        df["Carrier"] = df["Carrier"].astype("string").str.strip().str.upper()
        df["Service Type"] = df["Service Type"].astype("string").str.strip().str.upper()

    # Reject ambiguous rate cards rather than choosing a rate arbitrarily.
    if rates.duplicated(subset=["Carrier", "Service Type"]).any():
        raise ValueError("Rate card contains duplicate carrier/service combinations.")

    invoice_data["Total"] = pd.to_numeric(
        invoice_data["Total"],
        errors="raise",
    )
    # Use Base Freight for rate validation when available.
    # Otherwise, retain the existing Total-based calculation.
    if require_base_freight and "Base Freight" not in invoice_data.columns:
        raise ValueError(
            "Invoice has no Base Freight column. "
            "Rate validation on Total is not allowed."
        )

    if "Base Freight" in invoice_data.columns:
        invoice_data["Base Freight"] = pd.to_numeric(
            invoice_data["Base Freight"],
            errors="raise",
        )

        invoice_data["Rate Validation Amount"] = (
            invoice_data["Base Freight"]
        )
        invoice_data["Rate Basis"] = "Base Freight"
    else:
        warnings.warn(
            "Invoice has no Base Freight column. Rates are compared "
            "against Total, which may include surcharges and tax and "
            "can overstate overcharges.",
            UserWarning,
            stacklevel=2,
        )

        invoice_data["Rate Validation Amount"] = (
            invoice_data["Total"]
        )
        invoice_data["Rate Basis"] = "Total"
    # Convert contractual rates to numeric values.
    rates["Agreed Rate"] = pd.to_numeric(
        rates["Agreed Rate"],
        errors="coerce",
    )

    # Reject missing, zero, negative, or nonnumeric rates.
    invalid_rates = (
            rates["Agreed Rate"].isna()
            | (rates["Agreed Rate"] <= 0)
    )

    if invalid_rates.any():
        raise ValueError(
            "Agreed Rate must contain positive numeric values."
        )

    result = invoice_data.merge(
        rates,
        on=["Carrier", "Service Type"],
        how="left",
        validate="many_to_one",
    )

    result["Rate Difference"] = (
            result["Rate Validation Amount"] - result["Agreed Rate"]
    )

    # Differences within the tolerance are treated as matches.
    # Round first so floating point noise cannot tip a result.
    rounded_difference = result["Rate Difference"].round(2)

    over_tolerance = rounded_difference > tolerance
    under_tolerance = rounded_difference < -tolerance

    result["Potential Rate Overcharge"] = (
        result["Rate Difference"]
        .where(over_tolerance, 0)
        .where(result["Rate Difference"].notna())
    )

    # Classify rate validation results.
    result["Rate Status"] = "Rate Not Found"

    # A rate is matched only when both amounts are available.
    valid_comparison = (
            result["Agreed Rate"].notna()
            & result["Rate Validation Amount"].notna()
    )

    result.loc[
        valid_comparison,
        "Rate Status"
    ] = "Rate Matched"

    result.loc[
        valid_comparison & over_tolerance,
        "Rate Status"
    ] = "Potential Overcharge"

    result.loc[
        valid_comparison & under_tolerance,
        "Rate Status"
    ] = "Below Agreed Rate"

    # Flag missing base freight amounts for investigation.
    if "Base Freight" in invoice_data.columns:
        result.loc[
            result["Rate Validation Amount"].isna(),
            "Rate Status"
        ] = "Missing Base Freight"
    # Identify invoices with missing carrier or service information.
    missing_invoice_information = (
            result["Carrier"].isna()
            | result["Carrier"].eq("").fillna(False)
            | result["Service Type"].isna()
            | result["Service Type"].eq("").fillna(False)
    )
    # Track missing invoice information independently.
    result["Has Missing Invoice Information"] = (
        missing_invoice_information.fillna(False).astype(bool)
    )

    # Track missing base freight independently.
    if "Base Freight" in invoice_data.columns:
        result["Has Missing Base Freight"] = (
            result["Base Freight"].isna()
        )
    else:
        result["Has Missing Base Freight"] = False

    result.loc[
        missing_invoice_information,
        "Rate Status"
    ] = "Missing Invoice Information"

    # Incomplete invoice information cannot support rate validation.
    result.loc[
        missing_invoice_information,
        [
            "Rate Difference",
            "Potential Rate Overcharge",
        ]
    ] = float("nan")
    return result

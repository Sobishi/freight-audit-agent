import pandas as pd


def calculate_combined_exposure(
    audited_invoice: pd.DataFrame,
    rate_results: pd.DataFrame,
) -> pd.DataFrame:
    """
    Calculate preliminary combined exposure per invoice line.

    For each line, use the larger of:
    - Potential duplicate billing exposure
    - Potential contractual rate overcharge

    This prevents simple double-counting when both
    audit rules flag the same invoice line.
    """

    if len(audited_invoice) != len(rate_results):
        raise ValueError(
            "Invoice and rate validation results must have "
            "the same number of rows."
        )

    required_columns = {
        "Total",
        "Is Exact Duplicate Charge",
    }

    if not required_columns.issubset(audited_invoice.columns):
        raise ValueError(
            "Audited invoice is missing required exposure columns."
        )

    if "Potential Rate Overcharge" not in rate_results.columns:
        raise ValueError(
            "Rate results are missing Potential Rate Overcharge."
        )

    result = audited_invoice.copy().reset_index(drop=True)
    rates = rate_results.reset_index(drop=True)

    # Verify that rate results correspond to the correct invoice lines.
    # Match rate validation results using unique invoice-line IDs.
    id_column = "Invoice Line ID"

    if id_column not in result.columns or id_column not in rates.columns:
        raise ValueError(
            "Both datasets must contain Invoice Line ID."
        )

    if result[id_column].isna().any() or rates[id_column].isna().any():
        raise ValueError(
            "Invoice Line ID cannot contain missing values."
        )

    if result[id_column].duplicated().any() or rates[id_column].duplicated().any():
        raise ValueError(
            "Invoice Line ID must be unique within each dataset."
        )

    # Confirm both datasets contain exactly the same invoice lines.
    if set(result[id_column]) != set(rates[id_column]):
        raise ValueError(
            "Invoice Line IDs do not match between datasets."
        )

    # Reorder rate results to match the audited invoice.
    rates = (
        rates.set_index(id_column)
        .loc[result[id_column]]
        .reset_index()
    )

    result["Duplicate Exposure"] = (
        pd.to_numeric(result["Total"], errors="coerce")
        .clip(lower=0)
        .where(result["Is Exact Duplicate Charge"], 0)
    )

    result["Rate Exposure"] = (
        pd.to_numeric(
            rates["Potential Rate Overcharge"],
            errors="coerce",
        )
        .fillna(0)
        .clip(lower=0)
    )

    result["Combined Potential Exposure"] = result[
        ["Duplicate Exposure", "Rate Exposure"]
    ].max(axis=1)

    return result
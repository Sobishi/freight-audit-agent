import re

import pandas as pd


# Standard internal names and their recognized alternatives.
COLUMN_ALIASES = {
    "AWB": {
        "awb",
        "awb number",
        "tracking number",
        "tracking no",
        "waybill number",
        "waybill no",
        "consignment number",
        "consignment no",
        "shipment id",
        "shipment number",
    },
    "Carrier": {
        "carrier",
        "courier",
        "logistics provider",
        "shipping provider",
        "transport provider",
    },
    "Invoice Ref": {
        "invoice ref",
        "invoice reference",
        "invoice number",
        "invoice no",
        "invoice id",
    },
    "Total": {
        "total",
        "total amount",
        "invoice amount",
        "freight charge",
        "billed amount",
    },
}


def clean_column_name(name):
    """
    Standardize a column name for comparison.

    Examples:
        'Tracking_Number' -> 'tracking number'
        ' Invoice-No. '  -> 'invoice no'
    """

    name = str(name).strip().lower()

    # Replace punctuation and underscores with spaces.
    name = re.sub(r"[^a-z0-9]+", " ", name)

    # Remove repeated spaces.
    name = re.sub(r"\s+", " ", name).strip()

    return name


def normalize_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    """
    Convert recognized column names to the agent's
    standard internal naming convention.

    Unrecognized columns are preserved.
    """

    result = dataframe.copy()

    rename_map = {}
    matched_fields = {}

    for column in result.columns:
        cleaned_name = clean_column_name(column)

        for standard_name, aliases in COLUMN_ALIASES.items():
            if cleaned_name in aliases:

                if standard_name in matched_fields:
                    previous_column = matched_fields[standard_name]

                    raise ValueError(
                        f"Ambiguous column mapping: "
                        f"'{previous_column}' and '{column}' "
                        f"both map to '{standard_name}'."
                    )

                rename_map[column] = standard_name
                matched_fields[standard_name] = column

                break

    result = result.rename(columns=rename_map)

    return result


def validate_required_columns(
    dataframe: pd.DataFrame,
    required_columns: list,
):
    """
    Check that the normalized data contains
    the fields required for a specific audit.
    """

    missing_columns = [
        column
        for column in required_columns
        if column not in dataframe.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Missing required columns: {missing_columns}"
        )
def identify_columns(column_names):
    """
    Identify recognized freight invoice fields
    without modifying the original column names.

    Returns a dictionary mapping standard field names
    to their corresponding source column names.
    """

    matches = {}

    for column in column_names:
        cleaned_name = clean_column_name(column)

        for standard_name, aliases in COLUMN_ALIASES.items():
            if cleaned_name in aliases:

                if standard_name in matches:
                    raise ValueError(
                        f"Ambiguous mapping for '{standard_name}': "
                        f"'{matches[standard_name]}' and '{column}'."
                    )

                matches[standard_name] = column
                break

    return matches
def validate_invoice_data(dataframe: pd.DataFrame):
    """
    Validate essential invoice data quality.

    Raises an error when shipment identifiers
    are missing or blank.
    """

    validate_required_columns(dataframe, ["AWB"])

    awb_values = dataframe["AWB"]

    missing_awb = (
        awb_values.isna()
        | awb_values.astype(str).str.strip().eq("")
    )

    if missing_awb.any():
        invalid_count = int(missing_awb.sum())

        raise ValueError(
            f"Invoice contains {invalid_count} "
            f"record(s) with missing AWB values."
        )
    # Validate invoice amounts when the Total column exists.
    if "Total" in dataframe.columns:

        amounts = dataframe["Total"]

        # Convert values to numbers without modifying the original data.
        numeric_amounts = pd.to_numeric(
            amounts,
            errors="coerce",
        )

        # Identify missing or nonnumeric amounts.
        invalid_amounts = numeric_amounts.isna()

        if invalid_amounts.any():
            invalid_count = int(invalid_amounts.sum())

            raise ValueError(
                f"Invoice contains {invalid_count} "
                f"record(s) with invalid invoice amount values."
            )

def normalize_invoice_data(dataframe: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize invoice values into consistent data types.

    Assumes the invoice has already passed validation.
    """

    normalized = dataframe.copy()

    if "Total" in normalized.columns:
        normalized["Total"] = pd.to_numeric(
            normalized["Total"],
            errors="raise",
        )

    return normalized
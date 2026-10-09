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
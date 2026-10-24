"""Report-ready weight evidence, separate from financial exposure."""

import pandas as pd

from audit_engine.weight_validation import calculate_mapped_package_weight


def generate_weight_validation_results(
    invoice: pd.DataFrame,
    *,
    profile,
    package_count_verified,
    weight_tolerance=None,
) -> pd.DataFrame:
    """Calculate traceable weight evidence for standardized invoice lines."""

    if not isinstance(invoice, pd.DataFrame):
        raise TypeError("Expected an invoice DataFrame.")

    if "Invoice Line ID" not in invoice.columns:
        raise ValueError("Invoice Line ID is required for weight validation.")

    line_ids = invoice["Invoice Line ID"]

    if line_ids.isna().any():
        raise ValueError("Invoice Line ID cannot contain missing values.")

    if line_ids.duplicated().any():
        raise ValueError("Invoice Line ID must be unique.")

    if not isinstance(package_count_verified, bool):
        raise ValueError(
            "package_count_verified must be explicitly True or False."
        )

    records = []

    for _, row in invoice.iterrows():
        result = calculate_mapped_package_weight(
            row,
            profile=profile,
            package_count_verified=package_count_verified,
            weight_tolerance=weight_tolerance,
        )

        calculation = result["calculation"] or {}
        comparison = result["weight_comparison"] or {}
        converted = result["converted_measurements"] or {}

        records.append({
            "Invoice Line ID": row["Invoice Line ID"],
            "AWB": row.get("AWB"),
            "Carrier ID": row.get("Carrier ID", profile.carrier_id),
            "Weight Status": result["status"],
            "Weight Review Reason": result["review_reason"],
            "Weight Calculation Eligible": result["eligible"],
            "Expected Chargeable Weight (kg)": calculation.get(
                "chargeable_weight"
            ),
            "Billed Weight": row.get("Billed Weight"),
            "Billed Weight Unit": row.get("Billed Weight Unit"),
            "Weight Comparison Status": comparison.get("status"),
            "Actual Weight": row.get("Actual Weight"),
            "Length": row.get("Length"),
            "Width": row.get("Width"),
            "Height": row.get("Height"),
            "Weight Unit": row.get("Weight Unit"),
            "Dimension Unit": row.get("Dimension Unit"),
            "Pieces": row.get("Pieces"),
            "Actual Weight (kg)": converted.get("actual_weight_kg"),
            "Length (cm)": converted.get("length_cm"),
            "Width (cm)": converted.get("width_cm"),
            "Height (cm)": converted.get("height_cm"),
            "Dimensional Weight (kg)": calculation.get("dimensional_weight"),
            "Dimensional Divisor": (
                profile.dim_divisor if calculation else None
            ),
            "Rounding Step Low (kg)": (
                profile.rounding.step_low if calculation else None
            ),
            "Rounding Threshold (kg)": (
                profile.rounding.threshold if calculation else None
            ),
            "Rounding Step High (kg)": (
                profile.rounding.step_high if calculation else None
            ),
            "Weight Basis": calculation.get("weight_basis"),
            "Unrounded Chargeable Weight (kg)": calculation.get(
                "unrounded_weight"
            ),
            "Billed Weight (kg)": comparison.get("billed_weight"),
            "Weight Difference (kg)": comparison.get("difference"),
            "Weight Tolerance (kg)": comparison.get("tolerance"),
        })

    return pd.DataFrame(
        records,
        columns=[
            "Invoice Line ID",
            "AWB",
            "Carrier ID",
            "Weight Status",
            "Weight Review Reason",
            "Weight Calculation Eligible",
            "Expected Chargeable Weight (kg)",
            "Billed Weight",
            "Billed Weight Unit",
            "Weight Comparison Status",
            "Actual Weight",
            "Length",
            "Width",
            "Height",
            "Weight Unit",
            "Dimension Unit",
            "Pieces",
            "Actual Weight (kg)",
            "Length (cm)",
            "Width (cm)",
            "Height (cm)",
            "Dimensional Weight (kg)",
            "Dimensional Divisor",
            "Rounding Step Low (kg)",
            "Rounding Threshold (kg)",
            "Rounding Step High (kg)",
            "Weight Basis",
            "Unrounded Chargeable Weight (kg)",
            "Billed Weight (kg)",
            "Weight Difference (kg)",
            "Weight Tolerance (kg)",
        ],
    )

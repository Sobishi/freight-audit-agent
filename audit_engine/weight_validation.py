"""
Weight and measurement validation for the freight audit engine.

R3 implementation.
"""


def calculate_dimensional_weight(*, length, width, height, divisor):
    """
    Calculate dimensional weight using consistent measurement units.

    For metric carrier profiles:
        dimensions are in centimetres
        divisor is in cubic centimetres per kilogram

    Rounding is intentionally excluded from this function.
    Carrier-specific rounding will be implemented separately.
    """

    measurements = {
        "length": length,
        "width": width,
        "height": height,
        "divisor": divisor,
    }

    for name, value in measurements.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
        ):
            raise ValueError(
                f"{name} must be a positive number."
            )

        import math

        if not math.isfinite(value) or value <= 0:
            raise ValueError(
                f"{name} must be a finite positive number."
            )

    return (length * width * height) / divisor


def round_billable_weight(weight, rounding):
    """
    Round a positive weight upwards using carrier profile rules.

    At or below threshold: round upwards in step_low increments.
    Above threshold: round upwards from threshold in step_high increments.

    This implements the illustrative carrier profile convention.
    """
    from decimal import Decimal, ROUND_CEILING

    def positive_decimal(value, name):
        if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
            raise ValueError(f"{name} must be a positive number.")

        number = Decimal(str(value))

        if not number.is_finite() or number <= 0:
            raise ValueError(f"{name} must be a finite positive number.")

        return number

    raw = positive_decimal(weight, "weight")

    try:
        low = positive_decimal(rounding.step_low, "step_low")
        threshold = positive_decimal(rounding.threshold, "threshold")
        high = positive_decimal(rounding.step_high, "step_high")
    except AttributeError as exc:
        raise ValueError("Invalid carrier rounding configuration.") from exc

    if raw <= threshold:
        rounded = (
            (raw / low).to_integral_value(rounding=ROUND_CEILING) * low
        )
    else:
        excess = raw - threshold
        rounded = threshold + (
            (excess / high).to_integral_value(rounding=ROUND_CEILING) * high
        )

    return float(rounded)


def calculate_chargeable_weight(
    *,
    actual_weight,
    length,
    width,
    height,
    profile,
):
    """
    Calculate expected chargeable weight for one metric parcel.

    Assumptions:
        - Actual weight is in kilograms.
        - Dimensions are in centimetres.
        - The carrier profile uses metric units.
        - Actual and dimensional weights are compared before rounding.

    Returns calculation evidence for audit traceability.
    """
    import math

    if getattr(profile, "unit_system", None) != "metric":
        raise ValueError(
            "Only metric carrier profiles are currently supported."
        )

    if (
        isinstance(actual_weight, bool)
        or not isinstance(actual_weight, (int, float))
        or not math.isfinite(actual_weight)
        or actual_weight <= 0
    ):
        raise ValueError(
            "actual_weight must be a finite positive number."
        )

    dimensional_weight = calculate_dimensional_weight(
        length=length,
        width=width,
        height=height,
        divisor=profile.dim_divisor,
    )

    if actual_weight >= dimensional_weight:
        weight_basis = "actual"
        unrounded_weight = actual_weight
    else:
        weight_basis = "dimensional"
        unrounded_weight = dimensional_weight

    chargeable_weight = round_billable_weight(
        unrounded_weight,
        profile.rounding,
    )

    return {
        "actual_weight": actual_weight,
        "dimensional_weight": dimensional_weight,
        "weight_basis": weight_basis,
        "unrounded_weight": unrounded_weight,
        "chargeable_weight": chargeable_weight,
    }


def compare_billed_weight(*, expected_weight, billed_weight, tolerance):
    """
    Compare expected and carrier-billed weights.

    All values must use the same weight unit.
    Tolerance is an absolute weight difference, not a percentage.

    A discrepancy is a weight audit finding, not a confirmed
    monetary overcharge.
    """
    from decimal import Decimal

    def validated_number(value, name, *, allow_zero=False):
        if isinstance(value, bool) or not isinstance(
            value, (int, float, Decimal)
        ):
            raise ValueError(f"{name} must be a valid number.")

        number = Decimal(str(value))

        if not number.is_finite():
            raise ValueError(f"{name} must be finite.")

        if number < 0 or (number == 0 and not allow_zero):
            raise ValueError(
                f"{name} must be "
                f"{'non-negative' if allow_zero else 'positive'}."
            )

        return number

    expected = validated_number(expected_weight, "expected_weight")
    billed = validated_number(billed_weight, "billed_weight")
    allowed = validated_number(
        tolerance, "tolerance", allow_zero=True
    )

    difference = billed - expected

    if abs(difference) <= allowed:
        status = "match"
    elif difference > 0:
        status = "billed_weight_high"
    else:
        status = "billed_weight_low"

    return {
        "expected_weight": float(expected),
        "billed_weight": float(billed),
        "difference": float(difference),
        "tolerance": float(allowed),
        "status": status,
    }


def _convert_positive_measurement(value, unit, factors, measurement_name):
    """
    Convert a positive measurement using an explicit unit factor.

    Returns the converted value as a float. Callers must retain
    the original measurement and unit separately for audit evidence.
    """
    from decimal import Decimal, InvalidOperation

    if isinstance(value, bool) or not isinstance(
        value, (int, float, Decimal)
    ):
        raise ValueError(
            f"{measurement_name} must be a positive number."
        )

    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(
            f"{measurement_name} must be a valid number."
        ) from exc

    if not number.is_finite() or number <= 0:
        raise ValueError(
            f"{measurement_name} must be a finite positive number."
        )

    if not isinstance(unit, str) or unit.strip().lower() not in factors:
        raise ValueError(
            f"Unsupported {measurement_name} unit: {unit!r}. "
            f"Supported units: {', '.join(factors)}."
        )

    normalized_unit = unit.strip().lower()
    return float(number * Decimal(factors[normalized_unit]))


def convert_weight_to_kg(value, unit):
    """
    Convert a positive weight to kilograms.

    Supported units:
        kg: kilograms
        lb: pounds
    """
    return _convert_positive_measurement(
        value,
        unit,
        {
            "kg": "1",
            "lb": "0.45359237",
        },
        "weight",
    )


def convert_dimension_to_cm(value, unit):
    """
    Convert a positive dimension to centimetres.

    Supported units:
        cm: centimetres
        in: inches
    """
    return _convert_positive_measurement(
        value,
        unit,
        {
            "cm": "1",
            "in": "2.54",
        },
        "dimension",
    )


def assess_package_weight_evidence(
    *,
    actual_weight,
    length,
    width,
    height,
    weight_unit,
    dimension_unit,
    package_count,
    package_count_verified,
):
    """
    Assess whether an invoice line has sufficient evidence for
    single-package chargeable weight calculation.

    Does not calculate weight or establish financial liability.

    Returns:
        status: assessment outcome
        eligible: whether calculation can proceed
        evidence: original measurements and package information
    """
    import math
    from decimal import Decimal

    evidence = {
        "actual_weight": actual_weight,
        "length": length,
        "width": width,
        "height": height,
        "weight_unit": weight_unit,
        "dimension_unit": dimension_unit,
        "package_count": package_count,
        "package_count_verified": package_count_verified,
    }

    def outcome(status):
        return {
            "status": status,
            "eligible": status == "ready",
            "evidence": evidence.copy(),
        }

    def is_missing(value):
        if value is None:
            return True

        import pandas as pd
        return value is pd.NA

    def is_positive_measurement(value):
        if isinstance(value, bool) or not isinstance(
            value, (int, float, Decimal)
        ):
            return False

        try:
            number = Decimal(str(value))
        except Exception:
            return False

        return number.is_finite() and number > 0

    # Package structure must be known and reliable.
    if (
        isinstance(package_count, bool)
        or not isinstance(package_count, (int, float, Decimal))
        or not math.isfinite(float(package_count))
        or package_count <= 0
        or package_count != int(package_count)
    ):
        return outcome("invalid_package_count")

    if package_count != 1 or package_count_verified is not True:
        return outcome("package_structure_review")

    # Actual weight is mandatory for a complete comparison.
    if is_missing(actual_weight):
        return outcome("missing_actual_weight")

    # Dimensions must be complete.
    if any(is_missing(value) for value in (length, width, height)):
        return outcome("incomplete_dimensions")

    # Measurement values must be positive and finite.
    if not all(
        is_positive_measurement(value)
        for value in (actual_weight, length, width, height)
    ):
        return outcome("invalid_measurement")

    # Both measurement units must be explicitly available.
    if (
        not isinstance(weight_unit, str)
        or not weight_unit.strip()
        or not isinstance(dimension_unit, str)
        or not dimension_unit.strip()
    ):
        return outcome("missing_unit")

    # Reject unsupported units rather than assuming conversions.
    if weight_unit.strip().lower() not in ("kg", "lb"):
        return outcome("invalid_measurement")

    if dimension_unit.strip().lower() not in ("cm", "in"):
        return outcome("invalid_measurement")

    return outcome("ready")


def assess_mapped_package_weight_evidence(
    row,
    *,
    package_count_verified,
):
    """
    Assess package evidence from a standardized invoice row.

    Pandas missing markers in optional measurement fields represent
    unavailable evidence. Non-missing invalid measurements remain
    subject to strict validation.

    This function does not calculate charges or financial liability.
    """
    import pandas as pd

    if not isinstance(row, pd.Series):
        raise TypeError("Expected a standardized invoice row as a pandas Series.")

    def measurement(name):
        value = row.get(name)
        if value is None or pd.isna(value):
            return None
        return value

    return assess_package_weight_evidence(
        actual_weight=measurement("Actual Weight"),
        length=measurement("Length"),
        width=measurement("Width"),
        height=measurement("Height"),
        weight_unit=measurement("Weight Unit"),
        dimension_unit=measurement("Dimension Unit"),
        package_count=measurement("Pieces"),
        package_count_verified=package_count_verified,
    )


def calculate_mapped_package_weight(
    row,
    *,
    profile,
    package_count_verified,
    weight_tolerance=None,
):
    """
    Calculate chargeable weight from a standardized invoice row.

    Unsupported calculations and invalid billed-weight comparisons
    receive explicit review outcomes. No financial liability is
    established by this function.

    Billed-weight comparisons require an explicitly declared billed
    weight unit. Missing unit evidence requires review.
    """
    import pandas as pd

    if isinstance(row, pd.Series):
        source = row
    elif isinstance(row, dict):
        source = pd.Series(row)
    else:
        raise TypeError("Expected a standardized invoice row.")

    carrier_id = source.get("Carrier ID")

    if carrier_id is not None and not pd.isna(carrier_id):
        if carrier_id != profile.carrier_id:
            raise ValueError(
                "Invoice carrier does not match carrier profile."
            )

    assessment = assess_mapped_package_weight_evidence(
        source,
        package_count_verified=package_count_verified,
    )

    result = {
        "status": assessment["status"],
        "eligible": assessment["eligible"],
        "review_reason": None,
        "source_evidence": assessment["evidence"],
        "converted_measurements": None,
        "calculation": None,
        "weight_comparison": None,
    }

    if not assessment["eligible"]:
        return result

    if getattr(profile, "unit_system", None) != "metric":
        result["status"] = "calculation_review"
        result["eligible"] = False
        result["review_reason"] = "unsupported_profile"
        return result

    evidence = assessment["evidence"]

    converted = {
        "actual_weight_kg": convert_weight_to_kg(
            evidence["actual_weight"],
            evidence["weight_unit"],
        ),
        "length_cm": convert_dimension_to_cm(
            evidence["length"],
            evidence["dimension_unit"],
        ),
        "width_cm": convert_dimension_to_cm(
            evidence["width"],
            evidence["dimension_unit"],
        ),
        "height_cm": convert_dimension_to_cm(
            evidence["height"],
            evidence["dimension_unit"],
        ),
    }

    calculation = calculate_chargeable_weight(
        actual_weight=converted["actual_weight_kg"],
        length=converted["length_cm"],
        width=converted["width_cm"],
        height=converted["height_cm"],
        profile=profile,
    )

    result.update({
        "status": "calculated",
        "converted_measurements": converted,
        "calculation": calculation,
    })

    billed_weight = source.get("Billed Weight")

    if billed_weight is None or pd.isna(billed_weight):
        return result

    if weight_tolerance is None:
        return result

    billed_unit = source.get("Billed Weight Unit")

    if (
        billed_unit is None
        or (
            isinstance(billed_unit, str)
            and not billed_unit.strip()
        )
        or (
            not isinstance(billed_unit, (str, list, tuple, dict))
            and pd.isna(billed_unit)
        )
    ):
        result["status"] = "calculation_review"
        result["review_reason"] = "missing_billed_weight_unit"
        return result

    if (
        not isinstance(billed_unit, str)
        or billed_unit.strip().lower()
        != evidence["weight_unit"].strip().lower()
    ):
        result["status"] = "calculation_review"
        result["review_reason"] = "weight_unit_mismatch"
        return result

    try:
        billed_kg = convert_weight_to_kg(
            billed_weight,
            evidence["weight_unit"],
        )
    except (ValueError, TypeError, OverflowError):
        result["status"] = "calculation_review"
        result["review_reason"] = "invalid_billed_weight"
        return result

    result["weight_comparison"] = compare_billed_weight(
        expected_weight=calculation["chargeable_weight"],
        billed_weight=billed_kg,
        tolerance=weight_tolerance,
    )

    return result

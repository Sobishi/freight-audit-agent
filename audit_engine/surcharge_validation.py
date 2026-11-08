"""Conservative contractual surcharge calculations for R6."""

from decimal import Decimal, InvalidOperation, localcontext


SUPPORTED_BASES = (
    "fixed",
    "per_kg",
    "percent_of_freight",
)


def _number(value):
    """Return a finite Decimal, excluding booleans."""
    if isinstance(value, bool):
        return None

    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None

    return number if number.is_finite() else None


def _review(reason):
    return {
        "status": "review",
        "reason": reason,
        "expected_surcharge": None,
    }


def calculate_expected_surcharge(
    *,
    basis,
    rate,
    chargeable_weight=None,
    base_freight=None,
):
    """
    Calculate an expected surcharge from explicit contractual inputs.

    Supported bases:
    - fixed: agreed fixed amount
    - per_kg: agreed rate multiplied by chargeable weight
    - percent_of_freight: agreed fraction of contractual base freight

    This function does not establish surcharge applicability,
    calculate overcharges, or make payment decisions.

    Successful calculations return Decimal values without
    premature currency rounding.
    """

    if basis not in SUPPORTED_BASES:
        return _review("unsupported_basis")

    if rate is None:
        return _review("missing_rate")

    numeric_rate = _number(rate)

    if numeric_rate is None or numeric_rate < 0:
        return _review("invalid_rate")

    if basis == "fixed":
        expected = numeric_rate

    elif basis == "per_kg":
        weight = _number(chargeable_weight)

        if weight is None or weight <= 0:
            return _review("invalid_weight")

        try:
            with localcontext() as context:
                context.prec = 28
                expected = numeric_rate * weight
        except (InvalidOperation, OverflowError):
            return _review("invalid_calculation")

    else:
        freight = _number(base_freight)

        if freight is None or freight < 0:
            return _review("invalid_base_freight")

        if numeric_rate > 1:
            return _review("invalid_rate")

        try:
            with localcontext() as context:
                context.prec = 28
                expected = numeric_rate * freight
        except (InvalidOperation, OverflowError):
            return _review("invalid_calculation")

    # Reject extreme computational results without treating this
    # safeguard as a contractual or currency-specific amount limit.
    if not expected.is_finite() or abs(expected) > Decimal("1E+100"):
        return _review("invalid_calculation")

    return {
        "status": "calculated",
        "reason": None,
        "expected_surcharge": expected,
    }


def _validation_result(status, expected=None, exposure=None, reason=None):
    """Return a consistent surcharge validation result."""
    return {
        "status": status,
        "expected_surcharge": expected,
        "potential_overcharge": exposure,
        "reason": reason,
    }


def validate_surcharge_charge(
    *,
    billed_amount,
    applicable,
    basis,
    rate,
    chargeable_weight=None,
    base_freight=None,
    tolerance="0.01",
):
    """
    Compare one billed surcharge with an explicit contractual rule.

    applicable:
        True  - surcharge is contractually permitted.
        False - surcharge is explicitly prohibited.
        None  - contractual applicability is unknown.

    A review outcome carries unknown exposure (None), not zero.
    Negative billed amounts are not assessed as surcharge overcharges.
    """

    billed = _number(billed_amount)

    if billed is None:
        return _validation_result(
            "review", reason="invalid_billed_amount"
        )

    if billed < 0:
        return _validation_result(
            "not_assessed",
            exposure=Decimal("0"),
            reason="credit_or_reversal",
        )

    allowed_tolerance = _number(tolerance)

    if allowed_tolerance is None or allowed_tolerance < 0:
        return _validation_result(
            "review", reason="invalid_tolerance"
        )

    if not isinstance(applicable, bool) and applicable is not None:
        return _validation_result(
            "review", reason="invalid_applicability"
        )

    if applicable is None:
        return _validation_result(
            "review", reason="unknown_applicability"
        )

    if applicable is False:
        expected = Decimal("0")
    else:
        calculation = calculate_expected_surcharge(
            basis=basis,
            rate=rate,
            chargeable_weight=chargeable_weight,
            base_freight=base_freight,
        )

        if calculation["status"] != "calculated":
            return _validation_result(
                "review",
                reason=calculation["reason"],
            )

        expected = calculation["expected_surcharge"]

    difference = billed - expected

    if abs(difference) <= allowed_tolerance:
        return _validation_result(
            "matched",
            expected=expected,
            exposure=Decimal("0"),
        )

    if difference > allowed_tolerance:
        return _validation_result(
            "potential_overcharge",
            expected=expected,
            exposure=difference,
        )

    return _validation_result(
        "below_contract",
        expected=expected,
        exposure=Decimal("0"),
    )

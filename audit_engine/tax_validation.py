"""Conservative, evidence-driven tax calculations for R6 TAX-01.

The taxable base, applicability, rate, treatment and rounding
must be supported by explicit evidence. This module does not
infer tax treatment from invoice totals or carrier defaults.
"""

from decimal import (
    Decimal,
    InvalidOperation,
    ROUND_HALF_UP,
    localcontext,
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
        "expected_tax": None,
    }


def _validation_result(
    status,
    *,
    expected=None,
    exposure=None,
    reason=None,
):
    return {
        "status": status,
        "reason": reason,
        "expected_tax": expected,
        "potential_overcharge": exposure,
    }


def calculate_expected_tax(
    *,
    taxable_base,
    tax_rate,
    tax_inclusive,
    rounding_increment,
):
    """Calculate tax only from explicit contractual inputs.

    For exclusive treatment, taxable_base is the pre-tax amount.

    For inclusive treatment, taxable_base is the amount already
    including tax.

    ROUND_HALF_UP is a provisional monetary rounding convention.
    """
    base = _number(taxable_base)
    rate = _number(tax_rate)
    increment = _number(rounding_increment)

    if base is None or base < 0:
        return _review("invalid_taxable_base")

    if rate is None or not Decimal("0") <= rate <= Decimal("1"):
        return _review("invalid_tax_rate")

    if not isinstance(tax_inclusive, bool):
        return _review("invalid_tax_inclusive")

    if increment is None or increment <= 0:
        return _review("invalid_rounding_increment")

    try:
        with localcontext() as context:
            context.prec = 50

            if tax_inclusive:
                expected = base * rate / (Decimal("1") + rate)
            else:
                expected = base * rate

            units = (
                expected / increment
            ).to_integral_value(rounding=ROUND_HALF_UP)

            expected = units * increment

    except (
        InvalidOperation,
        OverflowError,
        ZeroDivisionError,
    ):
        return _review("invalid_calculation")

    if (
        not expected.is_finite()
        or abs(expected) > Decimal("1E+100")
    ):
        return _review("invalid_calculation")

    return {
        "status": "calculated",
        "reason": None,
        "expected_tax": expected,
    }


def validate_tax_charge(
    *,
    billed_tax,
    applicable,
    taxable_base,
    tax_rate,
    tax_inclusive,
    rounding_increment,
    tolerance="0.01",
):
    """Compare billed tax with an explicitly supported tax amount.

    Review results carry unknown exposure, not zero exposure.
    This function does not resolve credits or payment decisions.
    """
    billed = _number(billed_tax)

    if billed is None or billed < 0:
        return _validation_result(
            "review",
            reason="invalid_billed_tax",
        )

    allowed_tolerance = _number(tolerance)

    if allowed_tolerance is None or allowed_tolerance < 0:
        return _validation_result(
            "review",
            reason="invalid_tolerance",
        )

    if not isinstance(applicable, bool) and applicable is not None:
        return _validation_result(
            "review",
            reason="invalid_applicability",
        )

    if applicable is None:
        return _validation_result(
            "review",
            reason="missing_applicability",
        )

    if applicable is False:
        expected = Decimal("0")
    else:
        calculation = calculate_expected_tax(
            taxable_base=taxable_base,
            tax_rate=tax_rate,
            tax_inclusive=tax_inclusive,
            rounding_increment=rounding_increment,
        )

        if calculation["status"] != "calculated":
            return _validation_result(
                "review",
                reason=calculation["reason"],
            )

        expected = calculation["expected_tax"]

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

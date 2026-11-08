"""R6 TAX-01: invoice-level tax reporting contract."""

from decimal import Decimal

import pandas as pd
import pytest

from audit_engine.tax_reporting import (
    generate_tax_validation_results,
)


def _invoice():
    return pd.DataFrame({
        "Invoice Line ID": [1, 2, 3],
        "AWB": ["AWB-101", "AWB-102", "AWB-103"],
        "Tax Amount": [9.00, 7.50, 0.00],
        "Credit Match Status": [
            "Not a Credit",
            "Not a Credit",
            "Not a Credit",
        ],
        "Excluded From Exposure": [
            False, False, False,
        ],
    })


def _contract(
    applicable=True,
    taxable_base="100",
    tax_rate="0.075",
    tax_inclusive=False,
    rounding_increment="0.01",
):
    return {
        "applicable": applicable,
        "taxable_base": taxable_base,
        "tax_rate": tax_rate,
        "tax_inclusive": tax_inclusive,
        "rounding_increment": rounding_increment,
    }


def test_invoice_tax_results_preserve_line_identity():
    invoice = _invoice()

    contracts = {
        1: _contract(),
        2: _contract(),
        3: _contract(applicable=False),
    }

    result = generate_tax_validation_results(
        invoice, contracts,
    )

    assert result["Invoice Line ID"].tolist() == [1, 2, 3]
    assert result.index.equals(invoice.index)
    assert len(result) == 3

    assert result["Tax Status"].tolist() == [
        "potential_overcharge",
        "matched",
        "matched",
    ]

    assert result.loc[
        0, "Potential Tax Overcharge"
    ] == Decimal("1.50")


def test_missing_contract_evidence_requires_review():
    result = generate_tax_validation_results(
        _invoice(),
        {1: _contract()},
    )

    assert result.loc[1, "Tax Status"] == "review"
    assert result.loc[
        1, "Potential Tax Overcharge"
    ] is None


def test_explicit_exemption_detects_billed_tax():
    invoice = _invoice()

    result = generate_tax_validation_results(
        invoice,
        {1: _contract(applicable=False)},
    )

    assert result.loc[0, "Tax Status"] == (
        "potential_overcharge"
    )

    assert result.loc[
        0, "Expected Tax"
    ] == Decimal("0")

    assert result.loc[
        0, "Potential Tax Overcharge"
    ] == Decimal("9.00")


def test_matched_full_reversal_is_not_assessed():
    invoice = _invoice().iloc[:2].copy()

    invoice["Tax Amount"] = [7.50, -7.50]
    invoice["Credit Match Status"] = [
        "Fully Reversed",
        "Matched Full Reversal",
    ]
    invoice["Excluded From Exposure"] = [True, True]

    result = generate_tax_validation_results(
        invoice,
        {
            1: _contract(),
            2: _contract(),
        },
    )

    assert result["Tax Status"].tolist() == [
        "not_assessed",
        "not_assessed",
    ]

    assert result["Tax Reason"].tolist() == [
        "matched_full_reversal",
        "matched_full_reversal",
    ]

    assert result[
        "Potential Tax Overcharge"
    ].tolist() == [
        Decimal("0"),
        Decimal("0"),
    ]


@pytest.mark.parametrize(
    "credit_status",
    [
        "Unmatched Credit",
        "Ambiguous Credit",
        "Missing Match Information",
    ],
)
def test_unresolved_credit_requires_review(credit_status):
    invoice = _invoice().iloc[:1].copy()

    invoice["Tax Amount"] = [-7.50]
    invoice["Credit Match Status"] = [credit_status]

    result = generate_tax_validation_results(
        invoice,
        {1: _contract()},
    )

    assert result.loc[0, "Tax Status"] == "review"
    assert result.loc[0, "Tax Reason"] == (
        "unresolved_credit"
    )
    assert result.loc[
        0, "Potential Tax Overcharge"
    ] is None


def test_negative_tax_adjustment_requires_review():
    invoice = _invoice().iloc[:1].copy()

    invoice["Tax Amount"] = [-2.00]

    result = generate_tax_validation_results(
        invoice,
        {1: _contract()},
    )

    assert result.loc[0, "Tax Status"] == "review"
    assert result.loc[0, "Tax Reason"] == (
        "negative_tax_adjustment"
    )


def test_missing_tax_amount_requires_review():
    invoice = _invoice().iloc[:1].copy()
    invoice["Tax Amount"] = [None]

    result = generate_tax_validation_results(
        invoice,
        {1: _contract()},
    )

    assert result.loc[0, "Tax Status"] == "review"
    assert result.loc[
        0, "Potential Tax Overcharge"
    ] is None


def test_duplicate_invoice_line_ids_rejected():
    invoice = _invoice()
    invoice.loc[1, "Invoice Line ID"] = 1

    with pytest.raises(ValueError):
        generate_tax_validation_results(
            invoice,
            {1: _contract()},
        )


def test_incomplete_credit_metadata_rejected():
    invoice = _invoice().drop(
        columns=["Excluded From Exposure"]
    )

    with pytest.raises(ValueError):
        generate_tax_validation_results(
            invoice,
            {1: _contract()},
        )


def test_inconsistent_reversal_metadata_requires_review():
    invoice = _invoice().iloc[:1].copy()

    invoice["Credit Match Status"] = [
        "Fully Reversed"
    ]
    invoice["Excluded From Exposure"] = [False]

    result = generate_tax_validation_results(
        invoice,
        {1: _contract()},
    )

    assert result.loc[0, "Tax Status"] == "review"
    assert result.loc[0, "Tax Reason"] == (
        "inconsistent_credit_metadata"
    )
    assert result.loc[
        0, "Potential Tax Overcharge"
    ] is None


def test_invalid_contract_object_rejected():
    with pytest.raises(ValueError):
        generate_tax_validation_results(
            _invoice(),
            {1: "not a contract"},
        )


def test_existing_tax_result_columns_rejected():
    invoice = _invoice()
    invoice["Tax Status"] = "matched"

    with pytest.raises(ValueError):
        generate_tax_validation_results(
            invoice,
            {1: _contract()},
        )


@pytest.mark.parametrize(
    "unknown_status",
    [
        "Unknown Credit",
        "Pending Reconciliation",
        "",
    ],
)
def test_unknown_credit_status_requires_review(unknown_status):
    invoice = _invoice().iloc[:1].copy()

    invoice["Credit Match Status"] = [unknown_status]
    invoice["Excluded From Exposure"] = [False]

    result = generate_tax_validation_results(
        invoice,
        {1: _contract()},
    )

    assert result.loc[0, "Tax Status"] == "review"
    assert result.loc[0, "Tax Reason"] == (
        "invalid_credit_metadata"
    )
    assert result.loc[
        0, "Potential Tax Overcharge"
    ] is None


@pytest.mark.parametrize(
    "invalid_exclusion",
    [None, 0, 1, "False", "True"],
)
def test_invalid_exposure_exclusion_requires_review(
    invalid_exclusion,
):
    invoice = _invoice().iloc[:1].copy()

    invoice["Excluded From Exposure"] = [
        invalid_exclusion
    ]

    result = generate_tax_validation_results(
        invoice,
        {1: _contract()},
    )

    assert result.loc[0, "Tax Status"] == "review"
    assert result.loc[0, "Tax Reason"] == (
        "invalid_credit_metadata"
    )
    assert result.loc[
        0, "Potential Tax Overcharge"
    ] is None

"""R6 TAX-01: explicit tax contract evidence validation."""

from decimal import Decimal

import pandas as pd
import pytest

from audit_engine.tax_contract_evidence import prepare_tax_contracts


COLUMNS = [
    "Invoice Line ID",
    "Applicable",
    "Taxable Base",
    "Tax Rate",
    "Tax Inclusive",
    "Rounding Increment",
]


def _row(**changes):
    row = {
        "Invoice Line ID": 1,
        "Applicable": True,
        "Taxable Base": "100",
        "Tax Rate": "0.075",
        "Tax Inclusive": False,
        "Rounding Increment": "0.01",
    }
    row.update(changes)
    return row


def _evidence(*rows):
    return pd.DataFrame(list(rows), columns=COLUMNS)


def test_valid_tax_contract():
    contracts = prepare_tax_contracts(
        _evidence(_row())
    )

    assert set(contracts) == {1}
    assert contracts[1] == {
        "applicable": True,
        "taxable_base": Decimal("100"),
        "tax_rate": Decimal("0.075"),
        "tax_inclusive": False,
        "rounding_increment": Decimal("0.01"),
    }


def test_explicit_exemption():
    contracts = prepare_tax_contracts(
        _evidence(_row(
            Applicable=False,
            **{
                "Taxable Base": None,
                "Tax Rate": None,
                "Tax Inclusive": None,
                "Rounding Increment": None,
            },
        ))
    )

    assert contracts[1]["applicable"] is False
    assert contracts[1]["taxable_base"] is None


def test_unknown_applicability():
    contracts = prepare_tax_contracts(
        _evidence(_row(
            Applicable=None,
            **{
                "Taxable Base": None,
                "Tax Rate": None,
                "Tax Inclusive": None,
                "Rounding Increment": None,
            },
        ))
    )

    assert contracts[1]["applicable"] is None


@pytest.mark.parametrize(
    "invalid_id",
    [0, -1, 1.5, True, None],
)
def test_invalid_invoice_line_id_rejected(invalid_id):
    with pytest.raises(ValueError):
        prepare_tax_contracts(
            _evidence(_row(**{
                "Invoice Line ID": invalid_id
            }))
        )


def test_duplicate_invoice_line_ids_rejected():
    with pytest.raises(ValueError):
        prepare_tax_contracts(
            _evidence(_row(), _row())
        )


@pytest.mark.parametrize(
    "field",
    [
        "Taxable Base",
        "Tax Rate",
        "Tax Inclusive",
        "Rounding Increment",
    ],
)
def test_taxable_line_requires_complete_evidence(field):
    with pytest.raises(ValueError):
        prepare_tax_contracts(
            _evidence(_row(**{field: None}))
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("Taxable Base", "-100"),
        ("Taxable Base", "nan"),
        ("Tax Rate", "-0.01"),
        ("Tax Rate", "1.01"),
        ("Tax Rate", True),
        ("Tax Inclusive", "false"),
        ("Rounding Increment", "0"),
        ("Rounding Increment", "-0.01"),
    ],
)
def test_invalid_calculation_evidence_rejected(field, value):
    with pytest.raises(ValueError):
        prepare_tax_contracts(
            _evidence(_row(**{field: value}))
        )


@pytest.mark.parametrize(
    "applicable",
    [False, None],
)
def test_non_taxable_or_unknown_line_rejects_calculation_terms(
    applicable,
):
    with pytest.raises(ValueError, match="contradictory"):
        prepare_tax_contracts(
            _evidence(_row(Applicable=applicable))
        )


def test_duplicate_headers_rejected():
    evidence = _evidence(_row())
    evidence.columns = [
        "Invoice Line ID",
        "Applicable",
        "Tax Rate",
        "Tax Rate",
        "Tax Inclusive",
        "Rounding Increment",
    ]

    with pytest.raises(ValueError):
        prepare_tax_contracts(evidence)


def test_missing_required_column_rejected():
    evidence = _evidence(_row()).drop(
        columns=["Tax Inclusive"]
    )

    with pytest.raises(ValueError):
        prepare_tax_contracts(evidence)


def test_non_dataframe_rejected():
    with pytest.raises(TypeError):
        prepare_tax_contracts([_row()])

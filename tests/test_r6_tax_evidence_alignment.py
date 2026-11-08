"""R6 TAX-01: align tax evidence with invoice line identities."""

from copy import deepcopy
from decimal import Decimal

import pandas as pd
import pytest

from audit_engine.tax_evidence_alignment import (
    align_tax_evidence,
)


def _invoice(ids=(1, 2, 3)):
    return pd.DataFrame({
        "Invoice Line ID": list(ids),
        "Tax Amount": ["7.50"] * len(ids),
    })


def _contracts():
    return {
        1: {
            "applicable": True,
            "taxable_base": Decimal("100"),
            "tax_rate": Decimal("0.075"),
            "tax_inclusive": False,
            "rounding_increment": Decimal("0.01"),
        },
        2: {
            "applicable": False,
            "taxable_base": None,
            "tax_rate": None,
            "tax_inclusive": None,
            "rounding_increment": None,
        },
    }


def test_accepts_partial_evidence():
    result = align_tax_evidence(
        _invoice(),
        _contracts(),
    )

    assert result == _contracts()
    assert 3 not in result


def test_accepts_complete_evidence():
    contracts = _contracts()

    contracts[3] = {
        "applicable": None,
        "taxable_base": None,
        "tax_rate": None,
        "tax_inclusive": None,
        "rounding_increment": None,
    }

    assert align_tax_evidence(
        _invoice(),
        contracts,
    ) == contracts


def test_rejects_unknown_invoice_line():
    contracts = _contracts()
    contracts[999] = deepcopy(contracts[1])

    with pytest.raises(ValueError, match="unknown"):
        align_tax_evidence(
            _invoice(),
            contracts,
        )


def test_rejects_duplicate_invoice_ids():
    with pytest.raises(ValueError, match="duplicate"):
        align_tax_evidence(
            _invoice((1, 1, 3)),
            _contracts(),
        )


def test_rejects_missing_invoice_ids():
    with pytest.raises(ValueError, match="missing"):
        align_tax_evidence(
            _invoice((1, None, 3)),
            _contracts(),
        )


@pytest.mark.parametrize(
    "invalid_id",
    [0, -1, 1.5, "1", True],
)
def test_rejects_invalid_invoice_ids(invalid_id):
    with pytest.raises(ValueError, match="Invoice Line ID"):
        align_tax_evidence(
            _invoice((invalid_id, 2, 3)),
            {},
        )


@pytest.mark.parametrize(
    "invalid_id",
    [0, -1, 1.5, "1", True],
)
def test_rejects_invalid_evidence_ids(invalid_id):
    contracts = {invalid_id: deepcopy(_contracts()[1])}

    with pytest.raises(ValueError, match="Invoice Line ID"):
        align_tax_evidence(
            _invoice(),
            contracts,
        )


def test_rejects_missing_invoice_id_column():
    invoice = _invoice().drop(
        columns=["Invoice Line ID"]
    )

    with pytest.raises(ValueError, match="Invoice Line ID"):
        align_tax_evidence(
            invoice,
            _contracts(),
        )


def test_rejects_duplicate_invoice_columns():
    invoice = _invoice()
    invoice.insert(
        1,
        "Duplicate",
        [1, 2, 3],
    )

    invoice.columns = [
        "Invoice Line ID",
        "Invoice Line ID",
        "Tax Amount",
    ]

    with pytest.raises(ValueError, match="duplicate"):
        align_tax_evidence(
            invoice,
            _contracts(),
        )


def test_rejects_non_dataframe_invoice():
    with pytest.raises(TypeError, match="DataFrame"):
        align_tax_evidence([], _contracts())


def test_rejects_non_dictionary_contracts():
    with pytest.raises(TypeError, match="dictionary"):
        align_tax_evidence(_invoice(), [])


def test_does_not_mutate_inputs():
    invoice = _invoice()
    contracts = _contracts()

    original_invoice = invoice.copy(deep=True)
    original_contracts = deepcopy(contracts)

    result = align_tax_evidence(
        invoice,
        contracts,
    )

    pd.testing.assert_frame_equal(
        invoice,
        original_invoice,
    )

    assert contracts == original_contracts
    assert result == contracts

    result[1]["tax_rate"] = Decimal("0.20")

    assert contracts[1]["tax_rate"] == Decimal("0.075")


def test_empty_evidence_is_allowed():
    assert align_tax_evidence(
        _invoice(),
        {},
    ) == {}


def test_empty_invoice_accepts_empty_evidence():
    assert align_tax_evidence(
        _invoice(()),
        {},
    ) == {}


def test_empty_invoice_rejects_supplied_evidence():
    with pytest.raises(ValueError, match="unknown"):
        align_tax_evidence(
            _invoice(()),
            _contracts(),
        )

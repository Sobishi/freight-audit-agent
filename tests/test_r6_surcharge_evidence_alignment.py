"""R6 tests for aligning surcharge contract evidence with an invoice."""

from copy import deepcopy
from decimal import Decimal

import pandas as pd
import pytest

from audit_engine.surcharge_evidence_alignment import (
    align_surcharge_evidence,
)


def _invoice(ids=(1, 2, 3)):
    return pd.DataFrame({
        "Invoice Line ID": list(ids),
        "Surcharge Amount": ["8.50"] * len(ids),
    })


def _contracts():
    return {
        1: {
            "applicable": True,
            "basis": "fixed",
            "rate": Decimal("8.50"),
        },
        2: {
            "applicable": False,
            "basis": None,
            "rate": None,
        },
    }


def test_accepts_partial_evidence():
    result = align_surcharge_evidence(
        _invoice(),
        _contracts(),
    )

    assert result == _contracts()
    assert 3 not in result


def test_accepts_complete_evidence():
    contracts = _contracts()
    contracts[3] = {
        "applicable": None,
        "basis": None,
        "rate": None,
    }

    assert align_surcharge_evidence(
        _invoice(), contracts
    ) == contracts


def test_rejects_evidence_for_unknown_invoice_line():
    contracts = _contracts()
    contracts[999] = {
        "applicable": True,
        "basis": "fixed",
        "rate": Decimal("10.00"),
    }

    with pytest.raises(ValueError, match="unknown"):
        align_surcharge_evidence(_invoice(), contracts)


def test_rejects_duplicate_invoice_ids():
    with pytest.raises(ValueError, match="duplicate"):
        align_surcharge_evidence(
            _invoice((1, 1, 3)),
            _contracts(),
        )


def test_rejects_missing_invoice_ids():
    with pytest.raises(ValueError, match="missing"):
        align_surcharge_evidence(
            _invoice((1, None, 3)),
            _contracts(),
        )


@pytest.mark.parametrize(
    "invalid_id",
    [0, -1, 1.5, "1", True],
)
def test_rejects_invalid_invoice_ids(invalid_id):
    with pytest.raises(ValueError, match="Invoice Line ID"):
        align_surcharge_evidence(
            _invoice((invalid_id, 2, 3)),
            {},
        )


def test_rejects_missing_invoice_id_column():
    invoice = _invoice().drop(
        columns=["Invoice Line ID"]
    )

    with pytest.raises(ValueError, match="Invoice Line ID"):
        align_surcharge_evidence(invoice, _contracts())


def test_rejects_non_dataframe_invoice():
    with pytest.raises(TypeError, match="DataFrame"):
        align_surcharge_evidence([], _contracts())


def test_rejects_non_dictionary_contracts():
    with pytest.raises(TypeError, match="dictionary"):
        align_surcharge_evidence(_invoice(), [])


def test_does_not_mutate_inputs():
    invoice = _invoice()
    contracts = _contracts()

    original_invoice = invoice.copy(deep=True)
    original_contracts = deepcopy(contracts)

    align_surcharge_evidence(invoice, contracts)

    pd.testing.assert_frame_equal(
        invoice, original_invoice
    )
    assert contracts == original_contracts


def test_empty_evidence_is_allowed():
    assert align_surcharge_evidence(
        _invoice(), {}
    ) == {}


def test_empty_invoice_accepts_empty_evidence():
    assert align_surcharge_evidence(
        _invoice(()), {}
    ) == {}


def test_empty_invoice_rejects_supplied_evidence():
    with pytest.raises(ValueError, match="unknown"):
        align_surcharge_evidence(
            _invoice(()),
            _contracts(),
        )

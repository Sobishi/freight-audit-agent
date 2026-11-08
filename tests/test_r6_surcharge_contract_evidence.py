"""R6 tests for preparing explicit surcharge contract evidence."""

from decimal import Decimal

import pandas as pd
import pytest

from audit_engine.surcharge_contract_evidence import (
    prepare_surcharge_contracts,
)


def _evidence():
    return pd.DataFrame({
        "Invoice Line ID": [101, 102, 103],
        "Applicable": [True, False, None],
        "Basis": ["fixed", None, None],
        "Rate": ["8.50", None, None],
    })


def test_prepares_explicit_invoice_line_contracts():
    result = prepare_surcharge_contracts(_evidence())

    assert result == {
        101: {
            "applicable": True,
            "basis": "fixed",
            "rate": Decimal("8.50"),
        },
        102: {
            "applicable": False,
            "basis": None,
            "rate": None,
        },
        103: {
            "applicable": None,
            "basis": None,
            "rate": None,
        },
    }


def test_does_not_mutate_contract_evidence():
    evidence = _evidence()
    original = evidence.copy(deep=True)

    prepare_surcharge_contracts(evidence)

    pd.testing.assert_frame_equal(evidence, original)


def test_duplicate_invoice_line_ids_are_rejected():
    evidence = _evidence()
    evidence.loc[1, "Invoice Line ID"] = 101

    with pytest.raises(ValueError, match="duplicate"):
        prepare_surcharge_contracts(evidence)


def test_missing_invoice_line_id_is_rejected():
    evidence = _evidence()
    evidence.loc[0, "Invoice Line ID"] = None

    with pytest.raises(ValueError, match="missing"):
        prepare_surcharge_contracts(evidence)


@pytest.mark.parametrize(
    "invalid_applicability",
    [1, 0, "yes", "no", "maybe", 2],
)
def test_invalid_applicability_is_rejected(invalid_applicability):
    evidence = _evidence()
    evidence["Applicable"] = evidence["Applicable"].astype(object)
    evidence.at[0, "Applicable"] = invalid_applicability

    with pytest.raises(ValueError, match="applicability"):
        prepare_surcharge_contracts(evidence)


def test_applicable_surcharge_requires_basis():
    evidence = _evidence()
    evidence.at[0, "Basis"] = None

    with pytest.raises(ValueError, match="basis"):
        prepare_surcharge_contracts(evidence)


def test_applicable_surcharge_requires_rate():
    evidence = _evidence()
    evidence.at[0, "Rate"] = None

    with pytest.raises(ValueError, match="rate"):
        prepare_surcharge_contracts(evidence)


def test_missing_required_evidence_column_is_rejected():
    evidence = _evidence().drop(columns=["Applicable"])

    with pytest.raises(ValueError, match="required columns"):
        prepare_surcharge_contracts(evidence)


def test_duplicate_evidence_column_names_are_rejected():
    evidence = _evidence()
    evidence.columns = [
        "Invoice Line ID",
        "Applicable",
        "Applicable",
        "Rate",
    ]

    with pytest.raises(ValueError, match="duplicate column"):
        prepare_surcharge_contracts(evidence)


def test_unknown_applicability_does_not_create_contractual_entitlement():
    evidence = pd.DataFrame({
        "Invoice Line ID": [501],
        "Applicable": [None],
        "Basis": [None],
        "Rate": [None],
    })

    result = prepare_surcharge_contracts(evidence)

    assert result[501]["applicable"] is None
    assert result[501]["rate"] is None


@pytest.mark.parametrize(
    "applicable,basis,rate",
    [
        (False, "fixed", None),
        (False, None, "8.50"),
        (False, "fixed", "8.50"),
        (None, "per_kg", None),
        (None, None, "2.50"),
        (None, "per_kg", "2.50"),
    ],
)
def test_non_applicable_or_unknown_contract_rejects_terms(
    applicable, basis, rate
):
    evidence = pd.DataFrame({
        "Invoice Line ID": [601],
        "Applicable": [applicable],
        "Basis": [basis],
        "Rate": [rate],
    })

    with pytest.raises(ValueError, match="contradictory"):
        prepare_surcharge_contracts(evidence)


@pytest.mark.parametrize(
    "invalid_rate",
    [
        "-1.00",
        "not-a-rate",
        "NaN",
        "Infinity",
        True,
    ],
)
def test_applicable_contract_rejects_invalid_rates(invalid_rate):
    evidence = pd.DataFrame({
        "Invoice Line ID": [701],
        "Applicable": [True],
        "Basis": ["fixed"],
        "Rate": [invalid_rate],
    })

    with pytest.raises(ValueError, match="rate"):
        prepare_surcharge_contracts(evidence)


@pytest.mark.parametrize(
    "invalid_basis",
    ["percentage", "per_item", "", 1],
)
def test_applicable_contract_rejects_unsupported_basis(invalid_basis):
    evidence = pd.DataFrame({
        "Invoice Line ID": [801],
        "Applicable": [True],
        "Basis": [invalid_basis],
        "Rate": ["5.00"],
    })

    with pytest.raises(ValueError, match="basis"):
        prepare_surcharge_contracts(evidence)


def test_numpy_boolean_applicability_is_supported():
    import numpy as np

    evidence = pd.DataFrame({
        "Invoice Line ID": [901, 902],
        "Applicable": [np.bool_(True), np.bool_(False)],
        "Basis": ["fixed", None],
        "Rate": ["3.50", None],
    })

    result = prepare_surcharge_contracts(evidence)

    assert result[901]["applicable"] is True
    assert result[902]["applicable"] is False
    assert result[901]["rate"] == Decimal("3.50")


def test_empty_evidence_table_returns_empty_contract_mapping():
    evidence = pd.DataFrame(
        columns=[
            "Invoice Line ID",
            "Applicable",
            "Basis",
            "Rate",
        ]
    )

    assert prepare_surcharge_contracts(evidence) == {}


def test_spreadsheet_blank_values_preserve_unknown_applicability():
    import numpy as np

    evidence = pd.DataFrame({
        "Invoice Line ID": [1001],
        "Applicable": [np.nan],
        "Basis": [np.nan],
        "Rate": [np.nan],
    })

    result = prepare_surcharge_contracts(evidence)

    assert result[1001] == {
        "applicable": None,
        "basis": None,
        "rate": None,
    }


@pytest.mark.parametrize(
    "invalid_line_id",
    [
        0,
        -1,
        1.5,
        "101",
        "00101",
        "INV-101",
        "",
        " ",
        True,
    ],
)
def test_contract_evidence_rejects_non_integer_line_ids(
    invalid_line_id,
):
    evidence = pd.DataFrame({
        "Invoice Line ID": [invalid_line_id],
        "Applicable": [True],
        "Basis": ["fixed"],
        "Rate": ["8.50"],
    })

    with pytest.raises(ValueError, match="Invoice Line ID"):
        prepare_surcharge_contracts(evidence)


def test_contract_evidence_accepts_positive_integer_line_id():
    evidence = pd.DataFrame({
        "Invoice Line ID": [101],
        "Applicable": [True],
        "Basis": ["fixed"],
        "Rate": ["8.50"],
    })

    result = prepare_surcharge_contracts(evidence)

    assert list(result) == [101]

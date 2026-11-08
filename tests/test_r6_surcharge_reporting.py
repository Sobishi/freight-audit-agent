from decimal import Decimal

import pandas as pd
import pytest

from audit_engine.surcharge_reporting import (
    generate_surcharge_validation_results,
)


def _invoice():
    return pd.DataFrame(
        {
            "Invoice Line ID": [101, 102, 103, 104],
            "AWB": ["AWB-1", "AWB-1", "AWB-2", "AWB-3"],
            "Carrier": ["Carrier A"] * 4,
            "Charge Type": ["FREIGHT"] * 4,
            "Surcharge Amount": [
                "10.00",
                "12.50",
                "15.00",
                "8.00",
            ],
            "Total": [
                "110.00",
                "112.50",
                "115.00",
                "108.00",
            ],
        }
    )


def test_preserves_invoice_line_identity_and_order():
    invoice = _invoice()

    contracts = {
        101: {
            "applicable": True,
            "basis": "fixed",
            "rate": "10.00",
        },
        102: {
            "applicable": True,
            "basis": "fixed",
            "rate": "10.00",
        },
    }

    result = generate_surcharge_validation_results(
        invoice,
        contracts,
    )

    assert len(result) == len(invoice)
    assert result["Invoice Line ID"].tolist() == [101, 102, 103, 104]
    assert result["AWB"].tolist() == invoice["AWB"].tolist()


def test_missing_contract_evidence_requires_review():
    result = generate_surcharge_validation_results(
        _invoice(),
        {},
    )

    assert result["Surcharge Status"].eq("review").all()
    assert result["Potential Surcharge Overcharge"].isna().all()


def test_validates_individual_invoice_lines():
    contracts = {
        101: {
            "applicable": True,
            "basis": "fixed",
            "rate": "10.00",
        },
        102: {
            "applicable": True,
            "basis": "fixed",
            "rate": "10.00",
        },
        103: {
            "applicable": False,
            "basis": None,
            "rate": None,
        },
    }

    result = generate_surcharge_validation_results(
        _invoice(),
        contracts,
    ).set_index("Invoice Line ID")

    assert result.loc[101, "Surcharge Status"] == "matched"
    assert result.loc[102, "Surcharge Status"] == "potential_overcharge"
    assert result.loc[103, "Surcharge Status"] == "potential_overcharge"
    assert result.loc[104, "Surcharge Status"] == "review"

    assert result.loc[102, "Potential Surcharge Overcharge"] == Decimal("2.50")
    assert result.loc[103, "Potential Surcharge Overcharge"] == Decimal("15.00")
    assert pd.isna(result.loc[104, "Potential Surcharge Overcharge"])


def test_does_not_mutate_invoice():
    invoice = _invoice()
    original = invoice.copy(deep=True)

    generate_surcharge_validation_results(invoice, {})

    pd.testing.assert_frame_equal(invoice, original)


def test_rejects_duplicate_invoice_line_ids():
    invoice = _invoice()
    invoice.loc[1, "Invoice Line ID"] = 101

    with pytest.raises(ValueError, match="Invoice Line ID"):
        generate_surcharge_validation_results(invoice, {})


def test_rejects_missing_invoice_line_ids():
    invoice = _invoice()
    invoice.loc[1, "Invoice Line ID"] = None

    with pytest.raises(ValueError, match="Invoice Line ID"):
        generate_surcharge_validation_results(invoice, {})


def test_duplicate_dataframe_index_preserves_row_alignment():
    invoice = _invoice()
    invoice.index = [0, 0, 1, 1]

    contracts = {
        101: {"applicable": True, "basis": "fixed", "rate": "10"},
        102: {"applicable": True, "basis": "fixed", "rate": "10"},
        103: {"applicable": False, "basis": None, "rate": None},
    }

    result = generate_surcharge_validation_results(invoice, contracts)

    assert len(result) == 4
    assert result["Invoice Line ID"].tolist() == [101, 102, 103, 104]
    assert result["Surcharge Status"].tolist() == [
        "matched",
        "potential_overcharge",
        "potential_overcharge",
        "review",
    ]


def test_nonsequential_dataframe_index_preserves_row_alignment():
    invoice = _invoice()
    invoice.index = [40, 10, 90, 20]

    contracts = {
        101: {"applicable": True, "basis": "fixed", "rate": "10"},
        102: {"applicable": True, "basis": "fixed", "rate": "10"},
    }

    result = generate_surcharge_validation_results(invoice, contracts)

    assert result.index.tolist() == [40, 10, 90, 20]
    assert result["Surcharge Status"].tolist() == [
        "matched",
        "potential_overcharge",
        "review",
        "review",
    ]


def test_per_kg_uses_chargeable_weight():
    invoice = _invoice().iloc[[0]].copy()
    invoice["Chargeable Weight (kg)"] = [4]

    contracts = {
        101: {
            "applicable": True,
            "basis": "per_kg",
            "rate": "2.50",
        }
    }

    result = generate_surcharge_validation_results(invoice, contracts)

    assert result.iloc[0]["Surcharge Status"] == "matched"
    assert result.iloc[0]["Expected Surcharge"] == Decimal("10.00")


def test_missing_chargeable_weight_requires_review():
    invoice = _invoice().iloc[[0]].copy()

    contracts = {
        101: {
            "applicable": True,
            "basis": "per_kg",
            "rate": "2.50",
        }
    }

    result = generate_surcharge_validation_results(invoice, contracts)

    assert result.iloc[0]["Surcharge Status"] == "review"
    assert result.iloc[0]["Surcharge Reason"] == "invalid_weight"
    assert pd.isna(result.iloc[0]["Potential Surcharge Overcharge"])


def test_percentage_surcharge_uses_base_freight_not_total():
    invoice = _invoice().iloc[[0]].copy()
    invoice["Base Freight"] = ["100.00"]
    invoice["Total"] = ["500.00"]

    contracts = {
        101: {
            "applicable": True,
            "basis": "percent_of_freight",
            "rate": "0.10",
        }
    }

    result = generate_surcharge_validation_results(invoice, contracts)

    assert result.iloc[0]["Surcharge Status"] == "matched"
    assert result.iloc[0]["Expected Surcharge"] == Decimal("10.00")


def test_missing_base_freight_requires_review_without_total_fallback():
    invoice = _invoice().iloc[[0]].copy()
    invoice["Total"] = ["500.00"]

    contracts = {
        101: {
            "applicable": True,
            "basis": "percent_of_freight",
            "rate": "0.10",
        }
    }

    result = generate_surcharge_validation_results(invoice, contracts)

    assert result.iloc[0]["Surcharge Status"] == "review"
    assert result.iloc[0]["Surcharge Reason"] == "invalid_base_freight"


def test_invalid_contract_entry_is_rejected():
    invoice = _invoice()

    with pytest.raises(ValueError, match="Invalid surcharge contract"):
        generate_surcharge_validation_results(
            invoice,
            {101: "not a contract"},
        )


def test_rejects_existing_surcharge_result_columns():
    invoice = _invoice()
    invoice["Surcharge Status"] = "previous_result"

    with pytest.raises(ValueError, match="Surcharge Status"):
        generate_surcharge_validation_results(invoice, {})


def test_rejects_duplicate_invoice_column_names():
    invoice = _invoice()
    invoice.columns = [
        "Invoice Line ID",
        "AWB",
        "Carrier",
        "Charge Type",
        "Surcharge Amount",
        "Surcharge Amount",
    ]

    with pytest.raises(ValueError, match="duplicate"):
        generate_surcharge_validation_results(invoice, {})


def test_missing_billed_surcharge_is_not_zero():
    invoice = _invoice()
    invoice.loc[0, "Surcharge Amount"] = None

    result = generate_surcharge_validation_results(
        invoice,
        {
            101: {
                "applicable": False,
                "basis": None,
                "rate": None,
            }
        },
    )

    first = result.iloc[0]

    assert first["Surcharge Status"] == "review"
    assert first["Surcharge Reason"] == "invalid_billed_amount"
    assert pd.isna(first["Potential Surcharge Overcharge"])


@pytest.mark.parametrize(
    "credit_status",
    ["Fully Reversed", "Matched Full Reversal"],
)
def test_matched_full_reversal_excludes_surcharge_exposure(credit_status):
    invoice = _invoice().iloc[[0]].copy()
    invoice["Credit Match Status"] = [credit_status]
    invoice["Excluded From Exposure"] = [True]

    result = generate_surcharge_validation_results(
        invoice,
        {
            101: {
                "applicable": False,
                "basis": None,
                "rate": None,
            }
        },
    )

    row = result.iloc[0]

    assert row["Surcharge Status"] == "not_assessed"
    assert row["Surcharge Reason"] == "matched_full_reversal"
    assert row["Potential Surcharge Overcharge"] == Decimal("0")


@pytest.mark.parametrize(
    "credit_status",
    [
        "Unmatched Credit",
        "Ambiguous Credit",
        "Missing Match Information",
    ],
)
def test_unresolved_credit_requires_review(credit_status):
    invoice = _invoice().iloc[[0]].copy()
    invoice["Total"] = ["-110.00"]
    invoice["Surcharge Amount"] = ["-10.00"]
    invoice["Credit Match Status"] = [credit_status]
    invoice["Excluded From Exposure"] = [False]

    result = generate_surcharge_validation_results(
        invoice,
        {
            101: {
                "applicable": True,
                "basis": "fixed",
                "rate": "10.00",
            }
        },
    )

    row = result.iloc[0]

    assert row["Surcharge Status"] == "review"
    assert row["Surcharge Reason"] == "unresolved_credit"
    assert pd.isna(row["Potential Surcharge Overcharge"])


def test_negative_component_on_positive_line_requires_review():
    invoice = _invoice().iloc[[0]].copy()
    invoice["Surcharge Amount"] = ["-10.00"]
    invoice["Total"] = ["90.00"]
    invoice["Credit Match Status"] = ["Not a Credit"]
    invoice["Excluded From Exposure"] = [False]

    result = generate_surcharge_validation_results(
        invoice,
        {
            101: {
                "applicable": True,
                "basis": "fixed",
                "rate": "10.00",
            }
        },
    )

    row = result.iloc[0]

    assert row["Surcharge Status"] == "review"
    assert row["Surcharge Reason"] == "negative_surcharge_adjustment"
    assert pd.isna(row["Potential Surcharge Overcharge"])


def test_positive_surcharge_on_positive_line_remains_assessable():
    invoice = _invoice().iloc[[0]].copy()
    invoice["Credit Match Status"] = ["Not a Credit"]
    invoice["Excluded From Exposure"] = [False]

    result = generate_surcharge_validation_results(
        invoice,
        {
            101: {
                "applicable": True,
                "basis": "fixed",
                "rate": "8.00",
            }
        },
    )

    row = result.iloc[0]

    assert row["Surcharge Status"] == "potential_overcharge"
    assert row["Potential Surcharge Overcharge"] == Decimal("2.00")


def test_no_credit_metadata_preserves_standalone_validation():
    result = generate_surcharge_validation_results(
        _invoice().iloc[[0]].copy(),
        {
            101: {
                "applicable": True,
                "basis": "fixed",
                "rate": "8.00",
            }
        },
    )

    assert result.iloc[0]["Surcharge Status"] == "potential_overcharge"


def test_inconsistent_reversal_metadata_requires_review():
    invoice = _invoice().iloc[[0]].copy()
    invoice["Credit Match Status"] = ["Fully Reversed"]
    invoice["Excluded From Exposure"] = [False]

    result = generate_surcharge_validation_results(
        invoice,
        {
            101: {
                "applicable": False,
                "basis": None,
                "rate": None,
            }
        },
    )

    row = result.iloc[0]

    assert row["Surcharge Status"] == "review"
    assert row["Surcharge Reason"] == "inconsistent_credit_metadata"
    assert pd.isna(row["Potential Surcharge Overcharge"])


def test_real_r2_matched_reversal_flows_into_surcharge_reporting():
    from audit_engine.charges import analyze_charges

    invoice = pd.DataFrame({
        "Invoice Line ID": [201, 202],
        "AWB": ["REV-1", "REV-1"],
        "Carrier": ["Carrier A", "Carrier A"],
        "Currency": ["USD", "USD"],
        "Charge Type": ["FREIGHT", "FREIGHT"],
        "Service Type": ["Express", "Express"],
        "Base Freight": ["100.00", "-100.00"],
        "Surcharge Amount": ["10.00", "-10.00"],
        "Tax Amount": ["0.00", "0.00"],
        "Total": ["110.00", "-110.00"],
    })

    analyzed = analyze_charges(invoice)

    assert analyzed["Excluded From Exposure"].tolist() == [True, True]

    result = generate_surcharge_validation_results(
        analyzed,
        {
            201: {"applicable": False, "basis": None, "rate": None},
            202: {"applicable": False, "basis": None, "rate": None},
        },
    )

    assert result["Surcharge Status"].tolist() == [
        "not_assessed",
        "not_assessed",
    ]
    assert result["Potential Surcharge Overcharge"].tolist() == [
        Decimal("0"),
        Decimal("0"),
    ]


def test_real_r2_unmatched_credit_remains_under_review():
    from audit_engine.charges import analyze_charges

    invoice = pd.DataFrame({
        "Invoice Line ID": [301],
        "AWB": ["CREDIT-1"],
        "Carrier": ["Carrier A"],
        "Currency": ["USD"],
        "Charge Type": ["FREIGHT"],
        "Service Type": ["Express"],
        "Base Freight": ["-90.00"],
        "Surcharge Amount": ["-10.00"],
        "Tax Amount": ["0.00"],
        "Total": ["-100.00"],
    })

    analyzed = analyze_charges(invoice)

    assert analyzed.iloc[0]["Credit Match Status"] == "Unmatched Credit"

    result = generate_surcharge_validation_results(
        analyzed,
        {
            301: {
                "applicable": True,
                "basis": "fixed",
                "rate": "10.00",
            }
        },
    )

    assert result.iloc[0]["Surcharge Status"] == "review"
    assert result.iloc[0]["Surcharge Reason"] == "unresolved_credit"
    assert pd.isna(
        result.iloc[0]["Potential Surcharge Overcharge"]
    )


def test_real_r2_positive_charge_still_validates_surcharge():
    from audit_engine.charges import analyze_charges

    invoice = pd.DataFrame({
        "Invoice Line ID": [401],
        "AWB": ["SHIP-1"],
        "Carrier": ["Carrier A"],
        "Currency": ["USD"],
        "Charge Type": ["FREIGHT"],
        "Service Type": ["Express"],
        "Base Freight": ["100.00"],
        "Surcharge Amount": ["15.00"],
        "Tax Amount": ["0.00"],
        "Total": ["115.00"],
    })

    analyzed = analyze_charges(invoice)

    assert analyzed.iloc[0]["Credit Match Status"] == "Not a Credit"

    result = generate_surcharge_validation_results(
        analyzed,
        {
            401: {
                "applicable": True,
                "basis": "fixed",
                "rate": "10.00",
            }
        },
    )

    assert result.iloc[0]["Surcharge Status"] == "potential_overcharge"
    assert (
        result.iloc[0]["Potential Surcharge Overcharge"]
        == Decimal("5.00")
    )


@pytest.mark.parametrize(
    "missing_column",
    ["Credit Match Status", "Excluded From Exposure"],
)
def test_partial_r2_metadata_is_rejected(missing_column):
    invoice = _invoice().iloc[[0]].copy()
    invoice["Credit Match Status"] = ["Fully Reversed"]
    invoice["Excluded From Exposure"] = [True]
    invoice = invoice.drop(columns=[missing_column])

    with pytest.raises(ValueError, match="credit metadata"):
        generate_surcharge_validation_results(
            invoice,
            {
                101: {
                    "applicable": False,
                    "basis": None,
                    "rate": None,
                }
            },
        )


@pytest.mark.parametrize(
    "invalid_exclusion",
    [None, 1, 0, "True", "False", "yes", float("nan")],
)
def test_invalid_exposure_exclusion_requires_review(invalid_exclusion):
    invoice = _invoice().iloc[[0]].copy()
    invoice["Credit Match Status"] = ["Not a Credit"]
    invoice["Excluded From Exposure"] = [invalid_exclusion]

    result = generate_surcharge_validation_results(
        invoice,
        {
            101: {
                "applicable": False,
                "basis": None,
                "rate": None,
            }
        },
    )

    row = result.iloc[0]

    assert row["Surcharge Status"] == "review"
    assert row["Surcharge Reason"] == "invalid_credit_metadata"
    assert pd.isna(row["Potential Surcharge Overcharge"])


@pytest.mark.parametrize(
    "invalid_status",
    [None, "", "Unknown", "Reversed", 1, float("nan")],
)
def test_invalid_credit_match_status_requires_review(invalid_status):
    invoice = _invoice().iloc[[0]].copy()
    invoice["Credit Match Status"] = [invalid_status]
    invoice["Excluded From Exposure"] = [False]

    result = generate_surcharge_validation_results(
        invoice,
        {
            101: {
                "applicable": False,
                "basis": None,
                "rate": None,
            }
        },
    )

    row = result.iloc[0]

    assert row["Surcharge Status"] == "review"
    assert row["Surcharge Reason"] == "invalid_credit_metadata"
    assert pd.isna(row["Potential Surcharge Overcharge"])


def test_non_credit_cannot_be_marked_excluded():
    invoice = _invoice().iloc[[0]].copy()
    invoice["Credit Match Status"] = ["Not a Credit"]
    invoice["Excluded From Exposure"] = [True]

    result = generate_surcharge_validation_results(
        invoice,
        {
            101: {
                "applicable": False,
                "basis": None,
                "rate": None,
            }
        },
    )

    row = result.iloc[0]

    assert row["Surcharge Status"] == "review"
    assert row["Surcharge Reason"] == "inconsistent_credit_metadata"
    assert pd.isna(row["Potential Surcharge Overcharge"])


def test_valid_boolean_credit_metadata_still_allows_validation():
    invoice = _invoice().iloc[[0]].copy()
    invoice["Credit Match Status"] = ["Not a Credit"]
    invoice["Excluded From Exposure"] = [False]

    result = generate_surcharge_validation_results(
        invoice,
        {
            101: {
                "applicable": True,
                "basis": "fixed",
                "rate": "8.00",
            }
        },
    )

    assert result.iloc[0]["Surcharge Status"] == "potential_overcharge"
    assert (
        result.iloc[0]["Potential Surcharge Overcharge"]
        == Decimal("2.00")
    )

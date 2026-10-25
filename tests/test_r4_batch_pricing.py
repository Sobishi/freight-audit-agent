import pandas as pd
import pytest

from audit_engine.contract_pricing_reporting import (
    generate_contract_pricing_results,
)


@pytest.fixture
def invoice():
    return pd.DataFrame([
        {
            "Invoice Line ID": "INV-001",
            "AWB": "AWB-001",
            "Carrier ID": "swiftline",
            "Service Type": "Express",
            "Billed Zone": "A",
            "Ship Date": "2026-05-15",
            "Currency": "USD",
            "Base Freight": 120.0,
        },
        {
            "Invoice Line ID": "INV-002",
            "AWB": "AWB-002",
            "Carrier ID": "swiftline",
            "Service Type": "Express",
            "Billed Zone": "A",
            "Ship Date": "2026-05-15",
            "Currency": "USD",
            "Base Freight": 100.0,
        },
        {
            "Invoice Line ID": "INV-003",
            "AWB": "AWB-003",
            "Carrier ID": "swiftline",
            "Service Type": "Express",
            "Billed Zone": "A",
            "Ship Date": "2026-05-15",
            "Currency": "USD",
            "Base Freight": 130.0,
        },
    ])


@pytest.fixture
def weight_results():
    return pd.DataFrame([
        {
            "Invoice Line ID": "INV-002",
            "Weight Status": "calculated",
            "Weight Calculation Eligible": True,
            "Expected Chargeable Weight (kg)": 4.0,
        },
        {
            "Invoice Line ID": "INV-001",
            "Weight Status": "calculated",
            "Weight Calculation Eligible": True,
            "Expected Chargeable Weight (kg)": 4.0,
        },
        {
            "Invoice Line ID": "INV-003",
            "Weight Status": "calculation_review",
            "Weight Calculation Eligible": False,
            "Expected Chargeable Weight (kg)": None,
        },
    ])


@pytest.fixture
def contract_rates():
    return pd.DataFrame([
        {
            "Carrier ID": "swiftline",
            "Service Type": "Express",
            "Zone": "A",
            "Min Weight (kg)": 0,
            "Max Weight (kg)": 5,
            "Valid From": "2026-01-01",
            "Valid To": "2026-12-31",
            "Currency": "USD",
            "Agreed Base Freight": 100.0,
        },
    ])


def test_batch_pricing_joins_by_invoice_line_id(
    invoice,
    weight_results,
    contract_rates,
):
    result = generate_contract_pricing_results(
        invoice,
        weight_results,
        contract_rates,
    )

    assert result["Invoice Line ID"].tolist() == [
        "INV-001",
        "INV-002",
        "INV-003",
    ]

    assert result["Pricing Status"].tolist() == [
        "potential_overcharge",
        "matched",
        "review",
    ]

    assert result["Potential Contract Overcharge"].tolist()[:2] == [
        20.0,
        0.0,
    ]

    assert pd.isna(
        result.loc[2, "Potential Contract Overcharge"]
    )


def test_missing_weight_evidence_requires_review(
    invoice,
    weight_results,
    contract_rates,
):
    incomplete = weight_results.loc[
        weight_results["Invoice Line ID"] != "INV-002"
    ]

    result = generate_contract_pricing_results(
        invoice,
        incomplete,
        contract_rates,
    )

    row = result.loc[
        result["Invoice Line ID"] == "INV-002"
    ].iloc[0]

    assert row["Pricing Status"] == "review"
    assert row["Pricing Review Reason"] == "weight_evidence_missing"
    assert pd.isna(row["Potential Contract Overcharge"])


def test_duplicate_weight_evidence_is_rejected(
    invoice,
    weight_results,
    contract_rates,
):
    duplicate = pd.concat(
        [weight_results, weight_results.iloc[[0]]],
        ignore_index=True,
    )

    with pytest.raises(ValueError, match="unique"):
        generate_contract_pricing_results(
            invoice,
            duplicate,
            contract_rates,
        )


def test_duplicate_invoice_line_ids_are_rejected(
    invoice,
    weight_results,
    contract_rates,
):
    duplicate = invoice.copy()
    duplicate.loc[1, "Invoice Line ID"] = "INV-001"

    with pytest.raises(ValueError, match="unique"):
        generate_contract_pricing_results(
            duplicate,
            weight_results,
            contract_rates,
        )


def test_extra_weight_evidence_does_not_create_invoice_rows(
    invoice,
    weight_results,
    contract_rates,
):
    extra = pd.concat([
        weight_results,
        pd.DataFrame([{
            "Invoice Line ID": "NOT-IN-INVOICE",
            "Weight Status": "calculated",
            "Weight Calculation Eligible": True,
            "Expected Chargeable Weight (kg)": 4.0,
        }]),
    ], ignore_index=True)

    result = generate_contract_pricing_results(
        invoice,
        extra,
        contract_rates,
    )

    assert len(result) == len(invoice)
    assert "NOT-IN-INVOICE" not in result["Invoice Line ID"].tolist()


def test_batch_pricing_does_not_mutate_inputs(
    invoice,
    weight_results,
    contract_rates,
):
    original_invoice = invoice.copy(deep=True)
    original_weights = weight_results.copy(deep=True)
    original_rates = contract_rates.copy(deep=True)

    generate_contract_pricing_results(
        invoice,
        weight_results,
        contract_rates,
    )

    pd.testing.assert_frame_equal(invoice, original_invoice)
    pd.testing.assert_frame_equal(weight_results, original_weights)
    pd.testing.assert_frame_equal(contract_rates, original_rates)


def test_weight_evidence_carrier_mismatch_requires_review(
    invoice,
    weight_results,
    contract_rates,
):
    weights = weight_results.copy()
    weights["Carrier ID"] = "swiftline"
    weights.loc[
        weights["Invoice Line ID"] == "INV-001",
        "Carrier ID",
    ] = "another_carrier"

    result = generate_contract_pricing_results(
        invoice,
        weights,
        contract_rates,
    )

    row = result.loc[
        result["Invoice Line ID"] == "INV-001"
    ].iloc[0]

    assert row["Pricing Status"] == "review"
    assert row["Pricing Review Reason"] == "weight_evidence_carrier_mismatch"
    assert pd.isna(row["Potential Contract Overcharge"])


def test_weight_evidence_awb_mismatch_requires_review(
    invoice,
    weight_results,
    contract_rates,
):
    weights = weight_results.copy()
    weights["AWB"] = weights["Invoice Line ID"].map({
        "INV-001": "AWB-001",
        "INV-002": "AWB-002",
        "INV-003": "AWB-003",
    })

    weights.loc[
        weights["Invoice Line ID"] == "INV-001",
        "AWB",
    ] = "DIFFERENT-AWB"

    result = generate_contract_pricing_results(
        invoice,
        weights,
        contract_rates,
    )

    row = result.loc[
        result["Invoice Line ID"] == "INV-001"
    ].iloc[0]

    assert row["Pricing Status"] == "review"
    assert row["Pricing Review Reason"] == "weight_evidence_awb_mismatch"
    assert pd.isna(row["Potential Contract Overcharge"])


def test_matching_weight_evidence_identifiers_allow_pricing(
    invoice,
    weight_results,
    contract_rates,
):
    weights = weight_results.copy()
    weights["Carrier ID"] = "swiftline"
    weights["AWB"] = weights["Invoice Line ID"].map({
        "INV-001": "AWB-001",
        "INV-002": "AWB-002",
        "INV-003": "AWB-003",
    })

    result = generate_contract_pricing_results(
        invoice,
        weights,
        contract_rates,
    )

    row = result.loc[
        result["Invoice Line ID"] == "INV-001"
    ].iloc[0]

    assert row["Pricing Status"] == "potential_overcharge"
    assert row["Potential Contract Overcharge"] == 20.0


def test_missing_optional_weight_identifiers_remains_compatible(
    invoice,
    weight_results,
    contract_rates,
):
    result = generate_contract_pricing_results(
        invoice,
        weight_results,
        contract_rates,
    )

    assert result.loc[0, "Pricing Status"] == "potential_overcharge"
    assert result.loc[0, "Potential Contract Overcharge"] == 20.0


@pytest.mark.parametrize(
    "field, missing_value",
    [
        ("Carrier ID", None),
        ("Carrier ID", ""),
        ("Carrier ID", "   "),
        ("Carrier ID", pd.NA),
        ("AWB", None),
        ("AWB", ""),
        ("AWB", "   "),
        ("AWB", pd.NA),
    ],
)
def test_present_but_missing_weight_identifier_requires_review(
    invoice,
    weight_results,
    contract_rates,
    field,
    missing_value,
):
    weights = weight_results.copy()

    if field == "Carrier ID":
        weights[field] = "swiftline"
    else:
        weights[field] = weights["Invoice Line ID"].map({
            "INV-001": "AWB-001",
            "INV-002": "AWB-002",
            "INV-003": "AWB-003",
        })

    weights.loc[
        weights["Invoice Line ID"] == "INV-001",
        field,
    ] = missing_value

    result = generate_contract_pricing_results(
        invoice,
        weights,
        contract_rates,
    )

    row = result.loc[
        result["Invoice Line ID"] == "INV-001"
    ].iloc[0]

    assert row["Pricing Status"] == "review"

    expected_reason = (
        "weight_evidence_carrier_missing"
        if field == "Carrier ID"
        else "weight_evidence_awb_missing"
    )

    assert row["Pricing Review Reason"] == expected_reason
    assert pd.isna(row["Potential Contract Overcharge"])


def test_missing_invoice_awb_with_present_weight_awb_requires_review(
    invoice,
    weight_results,
    contract_rates,
):
    data = invoice.copy()
    data.loc[
        data["Invoice Line ID"] == "INV-001",
        "AWB",
    ] = None

    weights = weight_results.copy()
    weights["AWB"] = weights["Invoice Line ID"].map({
        "INV-001": "AWB-001",
        "INV-002": "AWB-002",
        "INV-003": "AWB-003",
    })

    result = generate_contract_pricing_results(
        data,
        weights,
        contract_rates,
    )

    row = result.loc[
        result["Invoice Line ID"] == "INV-001"
    ].iloc[0]

    assert row["Pricing Status"] == "review"
    assert row["Pricing Review Reason"] == "invoice_awb_missing"
    assert pd.isna(row["Potential Contract Overcharge"])

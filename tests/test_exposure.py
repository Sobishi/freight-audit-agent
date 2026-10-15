import pandas as pd
import pytest

from audit_engine.exposure import calculate_combined_exposure


def test_combined_exposure_avoids_double_counting():

    audited_invoice = pd.DataFrame({
        "AWB": ["ABC123", "XYZ456", "ABC123"],
        "Invoice Line ID": [1, 2, 3],
        "Invoice Ref": ["INV001", "INV002", "INV003"],
        "Total": [15000, 22000, 15000],
        "Is Exact Duplicate Charge": [False, False, True],
    })

    rate_results = pd.DataFrame({
        "AWB": ["ABC123", "XYZ456", "ABC123"],
        "Invoice Line ID": [1, 2, 3],
        "Invoice Ref": ["INV001", "INV002", "INV003"],
        "Potential Rate Overcharge": [3000, 4000, 3000],
    })

    result = calculate_combined_exposure(
        audited_invoice,
        rate_results,
    )

    assert result["Duplicate Exposure"].tolist() == [
        0, 0, 15000
    ]

    assert result["Rate Exposure"].tolist() == [
        3000, 4000, 3000
    ]

    assert result["Combined Potential Exposure"].tolist() == [
        3000, 4000, 15000
    ]

    assert result["Combined Potential Exposure"].sum() == 22000

def test_combined_exposure_handles_missing_rates():

    audited_invoice = pd.DataFrame({
        "AWB": ["ABC123"],
        "Invoice Line ID": [1],
        "Invoice Ref": ["INV001"],
        "Total": [15000],
        "Is Exact Duplicate Charge": [False],
    })

    rate_results = pd.DataFrame({
        "AWB": ["ABC123"],
        "Invoice Line ID": [1],
        "Invoice Ref": ["INV001"],
        "Potential Rate Overcharge": [float("nan")],
    })

    result = calculate_combined_exposure(
        audited_invoice,
        rate_results,
    )

    assert result.loc[0, "Duplicate Exposure"] == 0
    assert result.loc[0, "Rate Exposure"] == 0
    assert result.loc[0, "Combined Potential Exposure"] == 0

def test_combined_exposure_rejects_mismatched_row_counts():

    audited_invoice = pd.DataFrame({
        "AWB": ["ABC123", "XYZ456"],
        "Total": [15000, 22000],
        "Is Exact Duplicate Charge": [False, False],
    })

    rate_results = pd.DataFrame({
        "Potential Rate Overcharge": [3000],
    })

    with pytest.raises(
        ValueError,
        match="same number of rows",
    ):
        calculate_combined_exposure(
            audited_invoice,
            rate_results,
        )

def test_combined_exposure_matches_reordered_invoice_lines():

    audited_invoice = pd.DataFrame({
        "Invoice Line ID": [1, 2],
        "AWB": ["ABC123", "XYZ456"],
        "Invoice Ref": ["INV001", "INV002"],
        "Total": [15000, 22000],
        "Is Exact Duplicate Charge": [False, False],
    })

    rate_results = pd.DataFrame({
        "Invoice Line ID": [2, 1],
        "AWB": ["XYZ456", "ABC123"],
        "Invoice Ref": ["INV002", "INV001"],
        "Potential Rate Overcharge": [4000, 3000],
    })

    result = calculate_combined_exposure(
        audited_invoice,
        rate_results,
    )

    assert result["Invoice Line ID"].tolist() == [1, 2]

    assert result["Rate Exposure"].tolist() == [
        3000, 4000
    ]

    assert result["Combined Potential Exposure"].tolist() == [
        3000, 4000
    ]

    assert result["Combined Potential Exposure"].sum() == 7000

def test_combined_exposure_rejects_duplicate_line_ids():
    audited_invoice = pd.DataFrame({
        "Invoice Line ID": [1, 1],
        "AWB": ["ABC123", "XYZ456"],
        "Total": [15000, 22000],
        "Is Exact Duplicate Charge": [False, False],
    })

    rate_results = pd.DataFrame({
        "Invoice Line ID": [1, 2],
        "Potential Rate Overcharge": [3000, 4000],
    })

    with pytest.raises(ValueError, match="must be unique"):
        calculate_combined_exposure(
            audited_invoice,
            rate_results,
        )


def test_combined_exposure_rejects_missing_line_ids():
    audited_invoice = pd.DataFrame({
        "Invoice Line ID": [1, None],
        "AWB": ["ABC123", "XYZ456"],
        "Total": [15000, 22000],
        "Is Exact Duplicate Charge": [False, False],
    })

    rate_results = pd.DataFrame({
        "Invoice Line ID": [1, 2],
        "Potential Rate Overcharge": [3000, 4000],
    })

    with pytest.raises(ValueError, match="cannot contain missing"):
        calculate_combined_exposure(
            audited_invoice,
            rate_results,
        )


def test_combined_exposure_rejects_mismatched_line_ids():
    audited_invoice = pd.DataFrame({
        "Invoice Line ID": [1, 2],
        "AWB": ["ABC123", "XYZ456"],
        "Total": [15000, 22000],
        "Is Exact Duplicate Charge": [False, False],
    })

    rate_results = pd.DataFrame({
        "Invoice Line ID": [1, 3],
        "Potential Rate Overcharge": [3000, 4000],
    })

    with pytest.raises(ValueError, match="do not match"):
        calculate_combined_exposure(
            audited_invoice,
            rate_results,
        )

# ---------------------------------------------------------------
# Cleanup session: unknown exposure must never be shown as zero
# ---------------------------------------------------------------

def _status_inputs(overcharges):
    n = len(overcharges)

    audited_invoice = pd.DataFrame({
        "AWB": [f"AWB{i}" for i in range(n)],
        "Invoice Line ID": list(range(1, n + 1)),
        "Total": [15000] * n,
        "Is Exact Duplicate Charge": [False] * n,
    })

    rate_results = pd.DataFrame({
        "Invoice Line ID": list(range(1, n + 1)),
        "Potential Rate Overcharge": overcharges,
    })

    return audited_invoice, rate_results


def test_unknown_rate_exposure_is_flagged_and_held():
    audited, rates = _status_inputs([float("nan")])

    result = calculate_combined_exposure(audited, rates)

    assert result.loc[0, "Rate Exposure Status"] == "Unknown"
    assert result.loc[0, "Payment Treatment"] == "Hold"


def test_known_rate_exposure_is_quantified():
    audited, rates = _status_inputs([3000.0])

    result = calculate_combined_exposure(audited, rates)

    assert result.loc[0, "Rate Exposure Status"] == "Quantified"
    assert result.loc[0, "Payment Treatment"] == "Proceed"


def test_zero_overcharge_is_quantified_not_unknown():
    audited, rates = _status_inputs([0.0])

    result = calculate_combined_exposure(audited, rates)

    assert result.loc[0, "Rate Exposure Status"] == "Quantified"


def test_status_stays_with_the_correct_line_when_rows_are_reordered():
    audited, rates = _status_inputs([100.0, float("nan"), 0.0])
    rates = rates.iloc[[2, 0, 1]].reset_index(drop=True)

    result = calculate_combined_exposure(audited, rates)

    statuses = dict(zip(result["Invoice Line ID"], result["Rate Exposure Status"]))

    assert statuses == {1: "Quantified", 2: "Unknown", 3: "Quantified"}

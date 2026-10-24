import pandas as pd
import pytest

from audit_engine.weight_validation import (
    assess_mapped_package_weight_evidence,
)


def mapped_row(**overrides):
    values = {
        "Actual Weight": 5.0,
        "Length": 40.0,
        "Width": 30.0,
        "Height": 20.0,
        "Weight Unit": "kg",
        "Dimension Unit": "cm",
        "Pieces": 1.0,
    }
    values.update(overrides)
    return pd.Series(values)


@pytest.mark.parametrize(
    "field,expected",
    [
        ("Actual Weight", "missing_actual_weight"),
        ("Length", "incomplete_dimensions"),
        ("Width", "incomplete_dimensions"),
        ("Height", "incomplete_dimensions"),
    ],
)
def test_mapped_nan_is_missing_evidence(field, expected):
    result = assess_mapped_package_weight_evidence(
        mapped_row(**{field: float("nan")}),
        package_count_verified=True,
    )

    assert result["status"] == expected
    assert result["eligible"] is False


def test_mapped_pd_na_is_missing_evidence():
    result = assess_mapped_package_weight_evidence(
        mapped_row(**{"Height": pd.NA}),
        package_count_verified=True,
    )

    assert result["status"] == "incomplete_dimensions"


@pytest.mark.parametrize(
    "field,value",
    [
        ("Actual Weight", 0),
        ("Length", -1),
        ("Height", float("inf")),
    ],
)
def test_invalid_mapped_measurements_remain_invalid(field, value):
    result = assess_mapped_package_weight_evidence(
        mapped_row(**{field: value}),
        package_count_verified=True,
    )

    assert result["status"] == "invalid_measurement"


def test_valid_mapped_single_package_is_ready():
    result = assess_mapped_package_weight_evidence(
        mapped_row(),
        package_count_verified=True,
    )

    assert result["status"] == "ready"
    assert result["eligible"] is True


def test_unverified_package_count_requires_review():
    result = assess_mapped_package_weight_evidence(
        mapped_row(),
        package_count_verified=False,
    )

    assert result["status"] == "package_structure_review"


def test_multiple_packages_require_review():
    result = assess_mapped_package_weight_evidence(
        mapped_row(**{"Pieces": 2}),
        package_count_verified=True,
    )

    assert result["status"] == "package_structure_review"


def test_missing_package_count_is_invalid():
    result = assess_mapped_package_weight_evidence(
        mapped_row(**{"Pieces": float("nan")}),
        package_count_verified=True,
    )

    assert result["status"] == "invalid_package_count"

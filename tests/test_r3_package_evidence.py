import pytest

from audit_engine.weight_validation import assess_package_weight_evidence


def assess(**changes):
    values = {
        "actual_weight": 5.0,
        "length": 40.0,
        "width": 30.0,
        "height": 20.0,
        "weight_unit": "kg",
        "dimension_unit": "cm",
        "package_count": 1,
        "package_count_verified": True,
    }
    values.update(changes)
    return assess_package_weight_evidence(**values)


def test_complete_single_package_is_ready():
    result = assess()

    assert result["status"] == "ready"
    assert result["eligible"] is True


def test_missing_actual_weight_is_not_ready():
    result = assess(actual_weight=None)

    assert result["status"] == "missing_actual_weight"
    assert result["eligible"] is False


@pytest.mark.parametrize("field", ["length", "width", "height"])
def test_missing_dimension_is_not_ready(field):
    result = assess(**{field: None})

    assert result["status"] == "incomplete_dimensions"
    assert result["eligible"] is False


def test_multiple_packages_require_review():
    result = assess(package_count=3)

    assert result["status"] == "package_structure_review"
    assert result["eligible"] is False


@pytest.mark.parametrize(
    "count",
    [None, 0, -1, 1.5, "two", True],
)
def test_invalid_package_count_is_not_ready(count):
    result = assess(package_count=count)

    assert result["status"] == "invalid_package_count"
    assert result["eligible"] is False


def test_unverified_package_count_requires_review():
    result = assess(package_count_verified=False)

    assert result["status"] == "package_structure_review"
    assert result["eligible"] is False


@pytest.mark.parametrize(
    "field",
    ["weight_unit", "dimension_unit"],
)
def test_missing_unit_is_not_ready(field):
    result = assess(**{field: None})

    assert result["status"] == "missing_unit"
    assert result["eligible"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("actual_weight", 0),
        ("actual_weight", -2),
        ("length", 0),
        ("width", -5),
        ("height", float("nan")),
    ],
)
def test_invalid_measurement_is_not_ready(field, value):
    result = assess(**{field: value})

    assert result["status"] == "invalid_measurement"
    assert result["eligible"] is False


def test_ready_assessment_preserves_original_evidence():
    result = assess(
        actual_weight=10,
        weight_unit="lb",
        length=20,
        width=15,
        height=10,
        dimension_unit="in",
    )

    assert result["status"] == "ready"
    assert result["evidence"]["actual_weight"] == 10
    assert result["evidence"]["weight_unit"] == "lb"
    assert result["evidence"]["length"] == 20
    assert result["evidence"]["dimension_unit"] == "in"

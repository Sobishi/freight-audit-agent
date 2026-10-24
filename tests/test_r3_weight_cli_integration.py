import subprocess
import sys


def test_cli_exposes_explicit_weight_validation_options():
    result = subprocess.run(
        [sys.executable, "main.py", "--help"],
        capture_output=True,
        text=True,
        check=True,
    )

    help_text = result.stdout

    assert "--weight-tolerance" in help_text
    assert "--package-count-verified" in help_text


def test_weight_validation_requires_carrier_profile():
    result = subprocess.run(
        [
            sys.executable,
            "main.py",
            "nonexistent_invoice.csv",
            "--weight-tolerance",
            "0.1",
            "--package-count-verified",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "weight validation requires --carrier" in (
        result.stdout + result.stderr
    ).lower()


def test_weight_validation_requires_package_verification():
    result = subprocess.run(
        [
            sys.executable,
            "main.py",
            "nonexistent_invoice.csv",
            "--carrier",
            "demo_carrier",
            "--weight-tolerance",
            "0.1",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "package-count-verified" in (
        result.stdout + result.stderr
    ).lower()

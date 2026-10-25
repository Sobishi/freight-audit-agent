"""CLI integration tests for R4 contract pricing."""

import subprocess
import sys


def test_contract_rates_requires_weight_validation(tmp_path):
    """Contract pricing must not run without R3 weight evidence."""

    result = subprocess.run(
        [
            sys.executable,
            "main.py",
            str(tmp_path / "invoice.csv"),
            "--contract-rates",
            str(tmp_path / "contracts.csv"),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0

    assert (
        "--contract-rates requires --weight-tolerance"
        in result.stderr
    )


def test_contract_rates_does_not_replace_legacy_rates_argument():
    """Both rate validation options must remain independently available."""

    result = subprocess.run(
        [
            sys.executable,
            "main.py",
            "--help",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--rates" in result.stdout
    assert "--contract-rates" in result.stdout


def test_contract_rates_rejects_unsupported_file_format(tmp_path):
    """R4 accepts CSV and Excel contract rate cards only."""

    contract_file = tmp_path / "contracts.txt"
    contract_file.write_text("not a valid contract rate card")

    result = subprocess.run(
        [
            sys.executable,
            "main.py",
            str(tmp_path / "invoice.csv"),
            "--carrier",
            "swiftline",
            "--weight-tolerance",
            "0.1",
            "--package-count-verified",
            "--contract-rates",
            str(contract_file),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert (
        "Unsupported contract rate card format"
        in result.stderr
    )


def test_contract_rates_rejects_missing_contract_file(tmp_path):
    """A missing contract rate card must fail before invoice loading."""

    missing_contract = tmp_path / "missing_contracts.csv"

    result = subprocess.run(
        [
            sys.executable,
            "main.py",
            str(tmp_path / "invoice.csv"),
            "--carrier",
            "swiftline",
            "--weight-tolerance",
            "0.1",
            "--package-count-verified",
            "--contract-rates",
            str(missing_contract),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0

    assert (
        "Contract rate card not found"
        in result.stderr
    )


def test_cli_executes_contract_pricing_with_r3_evidence(
    tmp_path,
    monkeypatch,
):
    """The CLI must pass R3 weight evidence into R4 batch pricing."""

    import argparse
    import pandas as pd
    import main as cli

    contract_file = tmp_path / "contracts.csv"

    pd.DataFrame([{
        "Carrier ID": "swiftline",
        "Service Type": "express",
        "Zone": "A",
        "Min Weight (kg)": 0,
        "Max Weight (kg)": 10,
        "Valid From": "2026-01-01",
        "Valid To": "2026-12-31",
        "Agreed Base Freight": 100,
        "Currency": "USD",
    }]).to_csv(contract_file, index=False)

    invoice = pd.DataFrame([{
        "Invoice Line ID": "INV-001",
        "AWB": "AWB-001",
        "Carrier ID": "swiftline",
        "Service Type": "express",
        "Billed Zone": "A",
        "Ship Date": "2026-10-01",
        "Currency": "USD",
        "Base Freight": 120,
    }])

    weight_results = pd.DataFrame([{
        "Invoice Line ID": "INV-001",
        "AWB": "AWB-001",
        "Carrier ID": "swiftline",
        "Weight Status": "calculated",
        "Weight Calculation Eligible": True,
        "Expected Chargeable Weight (kg)": 5,
    }])

    captured = {}

    def fake_contract_pricing(
        received_invoice,
        received_weights,
        received_contracts,
        *,
        tolerance,
    ):
        captured["invoice"] = received_invoice.copy()
        captured["weights"] = received_weights.copy()
        captured["contracts"] = received_contracts.copy()
        captured["tolerance"] = tolerance

        return pd.DataFrame([{
            "Invoice Line ID": "INV-001",
            "Pricing Status": "potential_overcharge",
            "Potential Contract Overcharge": 20.0,
        }])

    monkeypatch.setattr(
        cli,
        "generate_contract_pricing_results",
        fake_contract_pricing,
        raising=False,
    )

    monkeypatch.setattr(
        cli,
        "generate_weight_validation_results",
        lambda *args, **kwargs: weight_results.copy(),
    )

    class FakeProfile:
        carrier_name = "Swiftline"
        carrier_id = "swiftline"
        currency = "USD"
        tolerance = 0.01

    class FakeCarrierConfig:
        profile = FakeProfile()
        mapping = {}

    monkeypatch.setattr(
        cli,
        "load_carrier_config",
        lambda *args, **kwargs: FakeCarrierConfig(),
    )

    monkeypatch.setattr(
        cli,
        "load_invoice_with_mapping",
        lambda *args, **kwargs: invoice.copy(),
    )

    class StopAfterPricing(Exception):
        pass

    class FakeRun:
        stage = None

        def __init__(self):
            self.data = {"settings": {}}

        def begin_rules(self, *rule_ids):
            raise StopAfterPricing()

    args = argparse.Namespace(
        carrier="swiftline",
        config_dir="config",
        invoice_file=str(tmp_path / "invoice.csv"),
        sheet=None,
        header_row=None,
        weight_tolerance=0.1,
        package_count_verified=True,
        rates=None,
        contract_rates=str(contract_file),
        allow_total_fallback=False,
        output=None,
    )

    try:
        cli._execute_audit(args, FakeRun())
    except StopAfterPricing:
        pass

    assert "contracts" in captured

    assert captured["contracts"].iloc[0][
        "Agreed Base Freight"
    ] == 100

    pd.testing.assert_frame_equal(
        captured["invoice"],
        invoice,
    )

    pd.testing.assert_frame_equal(
        captured["weights"],
        weight_results,
    )

    assert captured["tolerance"] == 0.01


def test_cli_passes_contract_pricing_results_to_excel_report():
    """The CLI must include R4 results in the Excel report call."""

    import ast
    import inspect
    import main as cli

    source = inspect.getsource(cli._execute_audit)
    tree = ast.parse(source)

    report_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "generate_excel_report"
    ]

    assert len(report_calls) == 1

    report_call = report_calls[0]

    keyword_arguments = {
        keyword.arg: keyword.value
        for keyword in report_call.keywords
    }

    assert "contract_pricing_results" in keyword_arguments

    argument = keyword_arguments["contract_pricing_results"]

    assert isinstance(argument, ast.Name)
    assert argument.id == "contract_pricing_results"



def test_contract_rates_rejects_empty_csv_with_clear_error(tmp_path):
    """An unreadable contract rate card must produce a clear CLI error."""

    import pandas as pd

    invoice_file = tmp_path / "invoice.csv"

    pd.DataFrame([{
        "Inv Ref": "INV001",
        "Waybill No": "AWB001",
        "Dispatch Date": "24/10/2026",
        "Product": "Express",
        "Zone": "A",
        "Chargeable Kg": 5.0,
        "Billed Unit": "kg",
        "Actual Kg": 3.0,
        "Actual Unit": "kg",
        "Length Cm": 40.0,
        "Width Cm": 30.0,
        "Height Cm": 20.0,
        "Dimension Unit": "cm",
        "Package Count": 1,
        "Freight": 100.0,
        "Surcharge": 0.0,
        "VAT": 0.0,
        "Amount Due": 100.0,
    }]).to_csv(invoice_file, index=False)

    contract_file = tmp_path / "empty_contracts.csv"
    contract_file.write_text("")

    result = subprocess.run(
        [
            sys.executable,
            "main.py",
            str(invoice_file),
            "--carrier",
            "swiftline",
            "--weight-tolerance",
            "0.1",
            "--package-count-verified",
            "--contract-rates",
            str(contract_file),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0

    assert "Error loading contract rate card" in result.stderr

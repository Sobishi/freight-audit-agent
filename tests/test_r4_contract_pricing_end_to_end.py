import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_cli_generates_r4_contract_pricing_workbook(tmp_path):
    config_dir = tmp_path / "config"
    carriers_dir = config_dir / "carriers"
    mappings_dir = config_dir / "mappings"

    carriers_dir.mkdir(parents=True)
    mappings_dir.mkdir(parents=True)

    (carriers_dir / "swiftline.yaml").write_text(
        (PROJECT_ROOT / "config/carriers/swiftline.yaml").read_text()
    )

    (mappings_dir / "swiftline_invoice.yaml").write_text(
        """
carrier_id: swiftline
carrier_name: Swiftline
header_row: 0
date_format: "%d/%m/%Y"
decimal: "."
thousands: ","
columns:
  "Inv Ref": Invoice Ref
  "Waybill No": AWB
  "Dispatch Date": Ship Date
  "Product": Service Type
  "Zone": Billed Zone
  "Chargeable Kg": Billed Weight
  "Billed Unit": Billed Weight Unit
  "Actual Kg": Actual Weight
  "Actual Unit": Weight Unit
  "Length Cm": Length
  "Width Cm": Width
  "Height Cm": Height
  "Dimension Unit": Dimension Unit
  "Package Count": Pieces
  "Freight": Base Freight
  "Surcharge": Surcharge Amount
  "VAT": Tax Amount
  "Amount Due": Total
""".strip() + "\n"
    )

    invoice_path = tmp_path / "invoice.csv"

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
    }]).to_csv(invoice_path, index=False)

    contract_path = tmp_path / "contracts.csv"

    pd.DataFrame([{
        "Carrier ID": "swiftline",
        "Service Type": "Express",
        "Zone": "A",
        "Min Weight (kg)": 0,
        "Max Weight (kg)": 10,
        "Valid From": "2026-01-01",
        "Valid To": "2026-12-31",
        "Agreed Base Freight": 80.0,
        "Currency": "USD",
    }]).to_csv(contract_path, index=False)

    report_path = tmp_path / "r4_audit.xlsx"

    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "main.py"),
            str(invoice_path),
            "--carrier",
            "swiftline",
            "--config-dir",
            str(config_dir),
            "--weight-tolerance",
            "0.1",
            "--package-count-verified",
            "--contract-rates",
            str(contract_path),
            "--output",
            str(report_path),
            "--log-dir",
            str(tmp_path / "logs"),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        result.stdout + "\n" + result.stderr
    )

    assert report_path.exists()

    workbook = load_workbook(
        report_path,
        read_only=True,
        data_only=True,
    )

    try:
        assert "Weight Validation" in workbook.sheetnames
        assert "Contract Pricing" in workbook.sheetnames

        weight_rows = list(workbook["Weight Validation"].values)
        weight_record = dict(zip(weight_rows[0], weight_rows[1]))

        assert weight_record["Weight Status"] == "calculated"
        assert weight_record["Expected Chargeable Weight (kg)"] == 4.0

        pricing_rows = list(workbook["Contract Pricing"].values)

        assert len(pricing_rows) == 2

        pricing_record = dict(
            zip(pricing_rows[0], pricing_rows[1])
        )

        assert pricing_record["AWB"] == "AWB001"
        assert pricing_record["Pricing Status"] == "potential_overcharge"
        assert pricing_record["Expected Chargeable Weight (kg)"] == 4.0
        assert pricing_record["Expected Base Freight"] == 80.0
        assert pricing_record["Invoiced Base Freight"] == 100.0
        assert pricing_record["Potential Contract Overcharge"] == 20.0
        assert pricing_record["Currency"] == "USD"

        summary_rows = list(workbook["Audit Summary"].values)

        summary_values = {
            row[0]: row[1]
            for row in summary_rows[1:]
            if row[0] is not None
        }

        assert (
            summary_values.get("Combined Potential Exposure", 0)
            == 0
        )

    finally:
        workbook.close()

    log_files = list((tmp_path / "logs").glob("*.json"))

    assert len(log_files) == 1

    run_data = json.loads(log_files[0].read_text())

    assert run_data["status"] == "succeeded"

    assert run_data["summary"]["contract_pricing_status_counts"] == {
        "potential_overcharge": 1
    }

    contract_inputs = [
        item
        for item in run_data["inputs"]
        if item["role"] == "contract_rate_card"
    ]

    assert len(contract_inputs) == 1
    assert contract_inputs[0]["name"] == "contracts.csv"
    assert contract_inputs[0]["status"] == "available"
    assert len(contract_inputs[0]["sha256"]) == 64


def test_r4_run_summary_contains_pricing_status_counts():
    """The audit summary must retain R4 pricing decisions."""

    import ast
    import inspect
    import main as cli

    source = inspect.getsource(cli._execute_audit)
    tree = ast.parse(source)

    summary_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "set_summary"
    ]

    assert len(summary_calls) == 1

    summary_argument = summary_calls[0].args[0]

    assert isinstance(summary_argument, ast.Dict)

    summary_keys = [
        key.value
        for key in summary_argument.keys
        if isinstance(key, ast.Constant)
    ]

    assert "contract_pricing_status_counts" in summary_keys

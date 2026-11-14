"""Real-engine integration test for the W1 audit service."""

import hashlib
import json
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

from services.audit_service import AuditRequest, run_audit


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_service_executes_real_swiftline_weight_audit(tmp_path):
    config_dir = tmp_path / "config"
    carriers_dir = config_dir / "carriers"
    mappings_dir = config_dir / "mappings"

    carriers_dir.mkdir(parents=True)
    mappings_dir.mkdir(parents=True)

    (carriers_dir / "swiftline.yaml").write_text(
        (PROJECT_ROOT / "config/carriers/swiftline.yaml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
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
""".strip() + "\n",
        encoding="utf-8",
    )

    invoice = tmp_path / "invoice.csv"

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
    }]).to_csv(invoice, index=False)

    report = tmp_path / "audit_report.xlsx"

    request = AuditRequest(
        invoice_file=invoice,
        output=report,
        log_dir=tmp_path / "logs",
        config_dir=config_dir,
        carrier="swiftline",
        weight_tolerance=0.1,
        package_count_verified=True,
    )

    result = run_audit(request)

    assert result.status == "succeeded"
    assert result.report_path == report
    assert report.is_file()
    assert result.log_path.is_file()

    workbook = load_workbook(report, read_only=True, data_only=True)

    try:
        assert "Invoice Data" in workbook.sheetnames
        assert "Audit Summary" in workbook.sheetnames
        assert "Weight Validation" in workbook.sheetnames

        rows = list(workbook["Weight Validation"].values)
        record = dict(zip(rows[0], rows[1]))

        assert record["AWB"] == "AWB001"
        assert record["Weight Status"] == "calculated"
        assert record["Expected Chargeable Weight (kg)"] == 4.0
        assert record["Billed Weight (kg)"] == 5.0
        assert record["Weight Difference (kg)"] == 1.0
        assert record["Weight Comparison Status"] == "billed_weight_high"

    finally:
        workbook.close()

    log = json.loads(result.log_path.read_text(encoding="utf-8"))

    assert log["run_id"] == result.run_id
    assert log["status"] == "succeeded"
    assert log["summary"]["invoice_lines"] == 1
    assert result.summary == log["summary"]

    assert log["settings"]["weight_validation_enabled"] is True
    assert log["settings"]["weight_tolerance_kg"] == 0.1
    assert log["settings"]["package_count_verified"] is True

    outputs = [
        item for item in log["outputs"]
        if item["role"] == "excel_report"
    ]

    assert len(outputs) == 1
    assert outputs[0]["name"] == report.name

    actual_hash = hashlib.sha256(report.read_bytes()).hexdigest()

    assert outputs[0]["sha256"] == actual_hash

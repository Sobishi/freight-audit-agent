"""Real-engine integration test for the W1 application controller."""

from pathlib import Path

from services.audit_controller import execute_workspace_audit
from services.workspace import create_audit_workspace, stage_audit_file


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_controller_executes_real_staged_swiftline_audit(tmp_path):
    import pandas as pd
    from openpyxl import load_workbook

    workspace = create_audit_workspace(tmp_path)

    config_dir = tmp_path / "config"
    carriers_dir = config_dir / "carriers"
    mappings_dir = config_dir / "mappings"

    carriers_dir.mkdir(parents=True)
    mappings_dir.mkdir(parents=True)

    for relative_path in (
        "carriers/swiftline.yaml",
        "mappings/swiftline_invoice.yaml",
    ):
        source = PROJECT_ROOT / "config" / relative_path
        destination = config_dir / relative_path

        destination.write_text(
            source.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    source_invoice = tmp_path / "swiftline_invoice.csv"

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
    }]).to_csv(source_invoice, index=False)

    staged_invoice = stage_audit_file(
        workspace,
        source_invoice,
        "swiftline_invoice.csv",
    )

    result = execute_workspace_audit(
        workspace=workspace,
        invoice_file=staged_invoice,
        config_dir=config_dir,
        carrier="swiftline",
        weight_tolerance=0.1,
        package_count_verified=True,
    )

    assert result.status == "succeeded"
    assert result.report_path == workspace.report_path
    assert result.report_path.is_file()
    assert result.log_path.is_file()
    assert result.log_path.parent == workspace.logs_dir
    assert result.summary["invoice_lines"] == 1

    workbook = load_workbook(
        result.report_path,
        read_only=True,
        data_only=True,
    )

    try:
        assert "Invoice Data" in workbook.sheetnames
        assert "Audit Summary" in workbook.sheetnames
        assert "Weight Validation" in workbook.sheetnames
    finally:
        workbook.close()

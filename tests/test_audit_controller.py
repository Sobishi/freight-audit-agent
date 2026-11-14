"""Tests for the W1 application controller."""

from pathlib import Path
from unittest.mock import patch

from services.audit_service import AuditResult
from services.workspace import create_audit_workspace


def test_controller_constructs_workspace_audit_request(tmp_path):
    from services.audit_controller import execute_workspace_audit

    workspace = create_audit_workspace(tmp_path)

    invoice = workspace.inputs_dir / "invoice.csv"
    invoice.write_text("Invoice Ref,Total\nINV001,100\n", encoding="utf-8")

    config_dir = tmp_path / "config"
    config_dir.mkdir()

    expected = AuditResult(
        run_id="test-run",
        status="succeeded",
        report_path=workspace.report_path,
        log_path=workspace.logs_dir / "test-run.json",
        summary={"invoice_lines": 1},
    )

    with patch(
        "services.audit_controller.run_audit",
        return_value=expected,
    ) as mocked_run:
        result = execute_workspace_audit(
            workspace=workspace,
            invoice_file=invoice,
            config_dir=config_dir,
            carrier="swiftline",
        )

    request = mocked_run.call_args.args[0]

    assert request.invoice_file == invoice
    assert request.output == workspace.report_path
    assert request.log_dir == workspace.logs_dir
    assert request.config_dir == config_dir
    assert request.carrier == "swiftline"

    assert result is expected


def test_controller_rejects_invoice_outside_workspace(tmp_path):
    import pytest

    from services.audit_controller import execute_workspace_audit

    workspace = create_audit_workspace(tmp_path)

    external_invoice = tmp_path / "external.csv"
    external_invoice.write_text("Invoice Ref\nINV001\n", encoding="utf-8")

    config_dir = tmp_path / "config"
    config_dir.mkdir()

    with pytest.raises(ValueError, match="must be staged"):
        execute_workspace_audit(
            workspace=workspace,
            invoice_file=external_invoice,
            config_dir=config_dir,
        )


def test_controller_rejects_missing_staged_invoice(tmp_path):
    import pytest

    from services.audit_controller import execute_workspace_audit

    workspace = create_audit_workspace(tmp_path)

    config_dir = tmp_path / "config"
    config_dir.mkdir()

    with pytest.raises(ValueError, match="does not exist"):
        execute_workspace_audit(
            workspace=workspace,
            invoice_file=workspace.inputs_dir / "missing.csv",
            config_dir=config_dir,
        )


def test_controller_rejects_symlinked_invoice(tmp_path):
    import pytest

    from services.audit_controller import execute_workspace_audit

    workspace = create_audit_workspace(tmp_path)

    external_invoice = tmp_path / "external.csv"
    external_invoice.write_text("Invoice Ref\nINV001\n", encoding="utf-8")

    linked_invoice = workspace.inputs_dir / "linked.csv"
    linked_invoice.symlink_to(external_invoice)

    config_dir = tmp_path / "config"
    config_dir.mkdir()

    with pytest.raises(ValueError, match="cannot be a symlink"):
        execute_workspace_audit(
            workspace=workspace,
            invoice_file=linked_invoice,
            config_dir=config_dir,
        )

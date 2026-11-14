"""Tests for browser-to-controller audit integration."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from services.audit_service import AuditResult
from services.workspace import create_audit_workspace
from web.audit_adapter import execute_staged_audit
from web.upload_adapter import StagedAudit


def make_staged_audit(tmp_path, *, include_invoice=True):
    workspace = create_audit_workspace(tmp_path)

    files = {}

    if include_invoice:
        files["invoice"] = workspace.inputs_dir / "invoice.csv"

    return StagedAudit(
        workspace=workspace,
        files=files,
    )


def test_executes_staged_invoice(monkeypatch, tmp_path):
    staged = make_staged_audit(tmp_path)

    expected = AuditResult(
        run_id="test-run",
        status="completed",
        report_path=Path("report.xlsx"),
        log_path=Path("audit.log"),
        summary={},
    )

    controller = Mock(return_value=expected)

    monkeypatch.setattr(
        "web.audit_adapter.execute_workspace_audit",
        controller,
    )

    result = execute_staged_audit(
        staged=staged,
        config_dir=Path("config"),
        carrier="northbridge_express",
    )

    assert result is expected

    controller.assert_called_once_with(
        workspace=staged.workspace,
        invoice_file=staged.files["invoice"],
        config_dir=Path("config"),
        carrier="northbridge_express",
        auto_detect_layout=True,
        rates=None,
        contract_rates=None,
        delivery_evidence=None,
        surcharge_evidence=None,
        tax_evidence=None,
    )


def test_passes_all_supporting_files(monkeypatch, tmp_path):
    staged = make_staged_audit(tmp_path)

    supporting = (
        "rates",
        "contract_rates",
        "delivery_evidence",
        "surcharge_evidence",
        "tax_evidence",
    )

    for label in supporting:
        staged.files[label] = (
            staged.workspace.inputs_dir / f"{label}.csv"
        )

    controller = Mock()

    monkeypatch.setattr(
        "web.audit_adapter.execute_workspace_audit",
        controller,
    )

    execute_staged_audit(
        staged=staged,
        config_dir=Path("config"),
        carrier="corvant",
    )

    kwargs = controller.call_args.kwargs

    for label in supporting:
        assert kwargs[label] == staged.files[label]


def test_missing_invoice_rejected(monkeypatch, tmp_path):
    staged = make_staged_audit(
        tmp_path,
        include_invoice=False,
    )

    controller = Mock()

    monkeypatch.setattr(
        "web.audit_adapter.execute_workspace_audit",
        controller,
    )

    with pytest.raises(
        ValueError,
        match="staged carrier invoice",
    ):
        execute_staged_audit(
            staged=staged,
            config_dir=Path("config"),
            carrier="corvant",
        )

    controller.assert_not_called()


def test_missing_carrier_rejected(monkeypatch, tmp_path):
    staged = make_staged_audit(tmp_path)

    controller = Mock()

    monkeypatch.setattr(
        "web.audit_adapter.execute_workspace_audit",
        controller,
    )

    with pytest.raises(
        ValueError,
        match="carrier must be selected",
    ):
        execute_staged_audit(
            staged=staged,
            config_dir=Path("config"),
            carrier="",
        )

    controller.assert_not_called()



def test_browser_converts_engine_system_exit(
    monkeypatch, tmp_path
):
    staged = make_staged_audit(tmp_path)

    def fake_controller(**kwargs):
        raise SystemExit("Sensitive invoice information")

    monkeypatch.setattr(
        "web.audit_adapter.execute_workspace_audit",
        fake_controller,
    )

    with pytest.raises(
        RuntimeError,
        match="Freight audit could not complete",
    ) as error:
        execute_staged_audit(
            staged=staged,
            config_dir=Path("config"),
            carrier="northbridge_express",
        )

    assert "Sensitive invoice information" not in str(error.value)
    assert isinstance(error.value.__cause__, SystemExit)

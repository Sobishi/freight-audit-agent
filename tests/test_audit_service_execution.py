"""W1 service execution lifecycle tests."""

import json
from pathlib import Path

import pytest

from services.audit_service import AuditRequest, run_audit


@pytest.fixture
def audit_request(tmp_path):
    invoice = tmp_path / "invoice.csv"
    invoice.write_text("AWB,Total\nA001,100\n", encoding="utf-8")

    return AuditRequest(
        invoice_file=invoice,
        output=tmp_path / "report.xlsx",
        log_dir=tmp_path / "logs",
        config_dir=tmp_path / "config",
    )


def test_successful_execution_returns_report_and_log(audit_request, monkeypatch):
    import main

    def fake_execute(args, run):
        assert args.invoice_file == str(audit_request.invoice_file)
        assert args.output == str(audit_request.output)
        assert run.data["inputs"][0]["role"] == "invoice"

        from openpyxl import Workbook

        workbook = Workbook()
        workbook.active["A1"] = "Audit report"
        workbook.save(args.output)

        run.set_summary({"invoice_lines": 1})
        run.add_output("excel_report", args.output)

    monkeypatch.setattr(main, "_execute_audit", fake_execute)

    result = run_audit(audit_request)

    assert result.status == "succeeded"
    assert result.report_path == audit_request.output
    assert result.log_path.is_file()
    assert result.summary["invoice_lines"] == 1

    log = json.loads(result.log_path.read_text(encoding="utf-8"))

    assert log["run_id"] == result.run_id
    assert log["status"] == "succeeded"
    assert log["inputs"][0]["role"] == "invoice"
    assert log["outputs"][0]["role"] == "excel_report"


def test_engine_failure_is_logged(audit_request, monkeypatch):
    import main

    def fake_execute(args, run):
        run.stage = "simulated_failure"
        raise ValueError("Sensitive invoice information")

    monkeypatch.setattr(main, "_execute_audit", fake_execute)

    with pytest.raises(ValueError, match="Sensitive invoice information"):
        run_audit(audit_request)

    logs = list(audit_request.log_dir.glob("audit_*.json"))
    assert len(logs) == 1

    log = json.loads(logs[0].read_text(encoding="utf-8"))

    assert log["status"] == "failed"
    assert log["error"]["type"] == "ValueError"
    assert log["error"]["stage"] == "simulated_failure"
    assert "Sensitive invoice information" not in logs[0].read_text(
        encoding="utf-8"
    )


def test_missing_report_is_rejected(audit_request, monkeypatch):
    import main

    def fake_execute(args, run):
        run.set_summary({"invoice_lines": 1})

    monkeypatch.setattr(main, "_execute_audit", fake_execute)

    with pytest.raises(
        RuntimeError,
        match="without an Excel report",
    ):
        run_audit(audit_request)


def test_system_exit_is_logged(audit_request, monkeypatch):
    import main

    def fake_execute(args, run):
        run.stage = "invoice_loading"
        raise SystemExit("Sensitive invoice error")

    monkeypatch.setattr(main, "_execute_audit", fake_execute)

    with pytest.raises(SystemExit):
        run_audit(audit_request)

    logs = list(audit_request.log_dir.glob("audit_*.json"))
    assert len(logs) == 1

    log = json.loads(logs[0].read_text(encoding="utf-8"))

    assert log["status"] == "failed"
    assert log["error"]["type"] == "SystemExit"
    assert log["error"]["stage"] == "invoice_loading"
    assert "Sensitive invoice error" not in logs[0].read_text(
        encoding="utf-8"
    )


def test_missing_report_records_failed_run(audit_request, monkeypatch):
    import main

    def fake_execute(args, run):
        run.set_summary({"invoice_lines": 1})

    monkeypatch.setattr(main, "_execute_audit", fake_execute)

    with pytest.raises(
        RuntimeError,
        match="without an Excel report",
    ):
        run_audit(audit_request)

    logs = list(audit_request.log_dir.glob("audit_*.json"))
    assert len(logs) == 1

    log = json.loads(logs[0].read_text(encoding="utf-8"))

    assert log["status"] == "failed"
    assert log["error"]["type"] == "RuntimeError"
    assert log["error"]["stage"] == "report_verification"
    assert not audit_request.output.exists()


def test_unregistered_report_is_rejected(audit_request, monkeypatch):
    import main
    from openpyxl import Workbook

    def fake_execute(args, run):
        workbook = Workbook()
        workbook.active["A1"] = "Audit report"
        workbook.save(args.output)
        run.set_summary({"invoice_lines": 1})
        # Deliberately omit run.add_output().

    monkeypatch.setattr(main, "_execute_audit", fake_execute)

    with pytest.raises(RuntimeError, match="report registration"):
        run_audit(audit_request)

    logs = list(audit_request.log_dir.glob("audit_*.json"))
    assert len(logs) == 1

    log = json.loads(logs[0].read_text(encoding="utf-8"))
    assert log["status"] == "failed"


def test_invalid_excel_report_is_rejected(audit_request, monkeypatch):
    import main

    def fake_execute(args, run):
        Path(args.output).write_bytes(b"not a valid Excel workbook")
        run.set_summary({"invoice_lines": 1})
        run.add_output("excel_report", args.output)

    monkeypatch.setattr(main, "_execute_audit", fake_execute)

    with pytest.raises(RuntimeError, match="invalid Excel workbook"):
        run_audit(audit_request)

    logs = list(audit_request.log_dir.glob("audit_*.json"))
    assert len(logs) == 1

    log = json.loads(logs[0].read_text(encoding="utf-8"))
    assert log["status"] == "failed"


def test_changed_report_after_registration_is_rejected(
    audit_request, monkeypatch
):
    import main
    from openpyxl import Workbook

    def fake_execute(args, run):
        workbook = Workbook()
        workbook.active["A1"] = "Original report"
        workbook.save(args.output)

        run.set_summary({"invoice_lines": 1})
        run.add_output("excel_report", args.output)

        workbook.active["A1"] = "Modified report"
        workbook.save(args.output)

    monkeypatch.setattr(main, "_execute_audit", fake_execute)

    with pytest.raises(RuntimeError, match="report integrity"):
        run_audit(audit_request)

    logs = list(audit_request.log_dir.glob("audit_*.json"))
    assert len(logs) == 1

    log = json.loads(logs[0].read_text(encoding="utf-8"))
    assert log["status"] == "failed"

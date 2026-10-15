import hashlib
import json
from datetime import datetime
from pathlib import Path
import pytest
from audit_engine.run_log import AuditRun
import main as app


def read_log(folder):
    files = list(folder.glob('*.json'))
    assert len(files) == 1
    return json.loads(files[0].read_text())


def test_success_log_hashes_and_utc(tmp_path):
    source = tmp_path / 'invoice.csv'; source.write_text('private shipment content')
    logs = tmp_path / 'logs'
    with AuditRun(logs) as run:
        run.add_input('invoice', source)
        run.begin_rules('REP-01'); run.complete_rules('REP-01')
        run.set_summary({'invoice_lines': 1})
    data = read_log(logs)
    assert data['status'] == 'succeeded'
    assert data['inputs'][0]['sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert data['inputs'][0]['name'] == 'invoice.csv'
    assert 'private shipment content' not in json.dumps(data)
    assert data['summary']['invoice_lines'] == 1
    assert data['rules_completed'][0]['rule_id'] == 'REP-01'
    assert datetime.fromisoformat(data['started_at']).utcoffset().total_seconds() == 0
    assert datetime.fromisoformat(data['finished_at']) >= datetime.fromisoformat(data['started_at'])


def test_failure_does_not_copy_exception_message(tmp_path):
    with pytest.raises(ValueError):
        with AuditRun(tmp_path / 'logs') as run:
            run.stage = 'invoice_loading'
            raise ValueError('secret customer ABC123')
    data = read_log(tmp_path / 'logs')
    assert data['status'] == 'failed'
    assert data['error'] == {'type': 'ValueError', 'stage': 'invoice_loading'}
    assert 'ABC123' not in json.dumps(data)


def test_system_exit_is_logged(tmp_path):
    with pytest.raises(SystemExit):
        with AuditRun(tmp_path / 'logs'):
            raise SystemExit('private details')
    assert read_log(tmp_path / 'logs')['status'] == 'failed'


def test_missing_input_is_recorded(tmp_path):
    with AuditRun(tmp_path / 'logs') as run:
        run.add_input('invoice', tmp_path / 'missing.csv')
    assert read_log(tmp_path / 'logs')['inputs'][0]['status'] == 'missing'


def test_two_runs_never_overwrite_each_other(tmp_path):
    for _ in range(2):
        with AuditRun(tmp_path / 'logs'):
            pass
    files = list((tmp_path / 'logs').glob('*.json'))
    assert len(files) == 2
    assert len({json.loads(p.read_text())['run_id'] for p in files}) == 2


def test_planned_rules_cannot_be_marked_executed(tmp_path):
    with pytest.raises(ValueError):
        with AuditRun(tmp_path / 'logs') as run:
            run.begin_rules('WT-01')


def test_changed_input_prevents_success(tmp_path):
    source = tmp_path / 'invoice.csv'; source.write_text('before')
    with pytest.raises(RuntimeError, match='changed'):
        with AuditRun(tmp_path / 'logs') as run:
            run.add_input('invoice', source)
            source.write_text('after')
    assert read_log(tmp_path / 'logs')['status'] == 'failed'


def test_invalid_log_folder_fails_explicitly(tmp_path):
    folder = tmp_path / 'not_a_folder'; folder.write_text('x')
    with pytest.raises(OSError):
        with AuditRun(folder):
            pass


def test_cli_success_and_counts(monkeypatch, tmp_path):
    invoice = tmp_path / 'invoice.csv'
    invoice.write_text('AWB,Carrier,Total,Base Freight,Service Type\nA,Demo,110,110,Express\n')
    rates = tmp_path / 'rates.csv'
    rates.write_text('Carrier,Service Type,Agreed Rate\nDemo,Express,100\n')
    monkeypatch.setattr('sys.argv', ['main.py', str(invoice), '--rates', str(rates), '--log-dir', str(tmp_path / 'logs')])
    app.main()
    data = read_log(tmp_path / 'logs')
    assert data['status'] == 'succeeded'
    assert data['summary']['invoice_lines'] == 1
    assert data['summary']['rate_status_counts']['Potential Overcharge'] == 1
    assert {r['rule_id'] for r in data['rules_completed']} >= {'REP-01', 'DUP-01', 'RATE-02'}
    assert 'A' not in [x.get('awb') for x in data['inputs']]


def test_cli_failure_creates_log(monkeypatch, tmp_path):
    monkeypatch.setattr('sys.argv', ['main.py', str(tmp_path / 'missing.csv'), '--log-dir', str(tmp_path / 'logs')])
    with pytest.raises(FileNotFoundError):
        app.main()
    assert read_log(tmp_path / 'logs')['status'] == 'failed'


def test_cli_config_references_are_hashed(monkeypatch, tmp_path):
    root = Path(app.__file__).parent
    invoice = root / 'tests/fixtures/carriers/swiftline_invoice.csv'
    monkeypatch.setattr('sys.argv', ['main.py', str(invoice), '--carrier', 'swiftline', '--log-dir', str(tmp_path / 'logs')])
    app.main()
    data = read_log(tmp_path / 'logs')
    roles = {x['role']: x for x in data['inputs']}
    assert len(roles['carrier_profile']['sha256']) == 64
    assert len(roles['invoice_mapping']['sha256']) == 64
    assert data['settings']['carrier_id'] == 'swiftline'


def test_rule_completion_requires_start(tmp_path):
    with pytest.raises(ValueError, match='not started'):
        with AuditRun(tmp_path / 'logs') as run:
            run.complete_rules('REP-01')


def test_rule_references_are_not_duplicated(tmp_path):
    with AuditRun(tmp_path / 'logs') as run:
        run.begin_rules('REP-01', 'REP-01')
        run.complete_rules('REP-01', 'REP-01')
    data = read_log(tmp_path / 'logs')
    assert len(data['rules_started']) == len(data['rules_completed']) == 1


def test_missing_base_freight_logs_failed_not_completed_rules(monkeypatch, tmp_path):
    invoice = tmp_path / 'invoice.csv'
    invoice.write_text('AWB,Carrier,Total,Service Type\nA,Demo,110,Express\n')
    rates = tmp_path / 'rates.csv'
    rates.write_text('Carrier,Service Type,Agreed Rate\nDemo,Express,100\n')
    monkeypatch.setattr('sys.argv', ['main.py', str(invoice), '--rates', str(rates), '--log-dir', str(tmp_path / 'logs')])
    with pytest.raises(SystemExit):
        app.main()
    data = read_log(tmp_path / 'logs')
    assert data['error']['stage'] == 'rate_validation'
    assert data['rules_started']
    assert data['rules_completed'] == []


def test_cli_report_contains_traceability(monkeypatch, tmp_path):
    import pandas as pd
    invoice = tmp_path / 'invoice.csv'
    invoice.write_text('AWB,Carrier,Total,Base Freight,Service Type\nA,Demo,110,110,Express\nA,Demo,110,110,Express\n')
    rates = tmp_path / 'rates.csv'
    rates.write_text('Carrier,Service Type,Agreed Rate\nDemo,Express,100\n')
    report = tmp_path / 'report.xlsx'
    monkeypatch.setattr('sys.argv', ['main.py', str(invoice), '--rates', str(rates), '--output', str(report), '--log-dir', str(tmp_path / 'logs')])
    app.main()
    data = read_log(tmp_path / 'logs')
    assert data['outputs'][0]['sha256'] == hashlib.sha256(report.read_bytes()).hexdigest()
    findings = pd.read_excel(report, sheet_name='Audit Findings', engine='openpyxl')
    rate_sheet = pd.read_excel(report, sheet_name='Rate Validation', engine='openpyxl')
    summary = pd.read_excel(report, sheet_name='Audit Summary', engine='openpyxl')
    exposure = pd.read_excel(report, sheet_name='Exposure Reconciliation', engine='openpyxl')
    assert findings.loc[0, 'Rule ID'] == 'DUP-01'
    assert findings.loc[0, 'Invoice Line ID'] == 2
    assert rate_sheet['Rule IDs'].eq('RATE-02').all()
    assert summary.loc[summary['Metric'].eq('Audit Run ID'), 'Value'].iloc[0] == data['run_id']
    assert {'Rate Exposure Status', 'Payment Treatment'} <= set(exposure)
    assert exposure['Combined Potential Exposure'].tolist() == [10, 110]


def test_report_failure_is_logged(monkeypatch, tmp_path):
    invoice = tmp_path / 'invoice.csv'
    invoice.write_text('AWB,Carrier,Total\nA,Demo,100\n')
    def fail(*args, **kwargs):
        raise OSError('sensitive output path')
    monkeypatch.setattr(app, 'generate_excel_report', fail)
    monkeypatch.setattr('sys.argv', ['main.py', str(invoice), '--output', str(tmp_path / 'report.xlsx'), '--log-dir', str(tmp_path / 'logs')])
    with pytest.raises(OSError):
        app.main()
    data = read_log(tmp_path / 'logs')
    assert data['error'] == {'type': 'OSError', 'stage': 'report_generation'}
    assert data['status'] == 'failed'


def test_log_write_failure_is_not_silently_ignored(monkeypatch, tmp_path):
    import audit_engine.run_log as module
    def fail(*args):
        raise OSError('disk full')
    monkeypatch.setattr(module.os, 'replace', fail)
    with pytest.raises(OSError):
        with AuditRun(tmp_path / 'logs'):
            pass
    assert not list((tmp_path / 'logs').glob('*.tmp'))

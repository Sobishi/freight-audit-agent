"""Local JSON audit records. These are not a tamper-proof compliance store."""
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import hashlib
import json
import os
import platform
from importlib.metadata import version, PackageNotFoundError
import time
from audit_engine.rules import CATALOGUE_VERSION, rule_reference

LOG_SCHEMA_VERSION = '1.0.0'


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


class AuditRun:
    """One record per CLI execution, including failed runs.

    Logs contain basenames, hashes, settings and aggregate counts, never
    invoice rows, shipment identifiers or exception messages. Filenames
    themselves may be sensitive; keep the log folder private.
    """
    def __init__(self, log_dir, settings=None):
        self.log_dir = Path(log_dir)
        self.run_id = str(uuid4())
        self.path = self.log_dir / f'audit_{self.run_id}.json'
        self.stage = 'initialization'
        self._inputs = []
        self._clock = time.monotonic()
        self.data = {
            'schema_version': LOG_SCHEMA_VERSION,
            'catalogue_version': CATALOGUE_VERSION,
            'run_id': self.run_id,
            'started_at': _utc_now(), 'finished_at': None,
            'duration_seconds': None, 'status': 'running',
            'settings': dict(settings or {}), 'inputs': [], 'outputs': [],
            'rules_started': [], 'rules_completed': [],
            'summary': {}, 'error': None,
            'runtime': {'python': platform.python_version()},
            'code_sha256': {},
        }
        for package in ('pandas', 'numpy', 'openpyxl', 'PyYAML'):
            try:
                self.data['runtime'][package] = version(package)
            except PackageNotFoundError:
                self.data['runtime'][package] = None
        root = Path(__file__).resolve().parent.parent
        paths = [root / 'main.py']
        for folder in ('audit_engine', 'data', 'reporting'):
            paths.extend(sorted((root / folder).glob('*.py')))
        self.data['code_sha256'] = {
            str(path.relative_to(root)): sha256_file(path) for path in paths if path.is_file()
        }

    def _write(self):
        self.log_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        try:
            with temporary.open('w', encoding='utf-8') as stream:
                json.dump(self.data, stream, indent=2, allow_nan=False)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def __enter__(self):
        self._write()
        return self

    def add_input(self, role, path):
        path = Path(path)
        entry = {'role': role, 'name': path.name,
                 'status': 'available' if path.is_file() else 'missing',
                 'sha256': sha256_file(path) if path.is_file() else None}
        self.data['inputs'].append(entry)
        self._inputs.append((path, entry))
        self._write()

    def add_output(self, role, path):
        path = Path(path)
        self.data['outputs'].append({'role': role, 'name': path.name,
                                     'sha256': sha256_file(path)})

    def begin_rules(self, *ids):
        for rule_id in ids:
            reference = rule_reference(rule_id)
            if reference not in self.data['rules_started']:
                self.data['rules_started'].append(reference)
        self._write()

    def complete_rules(self, *ids):
        for rule_id in ids:
            reference = rule_reference(rule_id)
            if reference not in self.data['rules_started']:
                raise ValueError(f'{rule_id} was not started.')
            if reference not in self.data['rules_completed']:
                self.data['rules_completed'].append(reference)
        self._write()

    def set_summary(self, summary):
        self.data['summary'] = dict(summary)

    def __exit__(self, exc_type, exc, traceback):
        changed = False
        if exc_type is None:
            for path, entry in self._inputs:
                if entry['status'] == 'available':
                    try:
                        current = sha256_file(path)
                    except OSError:
                        current = None
                    if current != entry['sha256']:
                        changed = True
                        entry['changed_during_run'] = True
            if changed:
                exc_type = RuntimeError
                self.stage = 'input_integrity'
        self.data['status'] = 'failed' if exc_type else 'succeeded'
        self.data['finished_at'] = _utc_now()
        self.data['duration_seconds'] = round(time.monotonic() - self._clock, 6)
        self.data['error'] = {'type': exc_type.__name__, 'stage': self.stage} if exc_type else None
        self._write()
        if changed:
            raise RuntimeError('An input file changed during the audit; do not use its outputs.')
        return False

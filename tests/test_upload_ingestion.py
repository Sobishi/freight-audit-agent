"""Tests for browser-upload ingestion into an audit workspace."""

import pytest

from services.upload_ingestion import ingest_uploaded_file
from services.workspace import create_audit_workspace


def test_ingests_uploaded_csv_bytes(tmp_path):
    workspace = create_audit_workspace(tmp_path)

    content = b"invoice_id,amount\nINV001,100\n"

    destination = ingest_uploaded_file(
        workspace=workspace,
        filename="invoice.csv",
        content=content,
    )

    assert destination == workspace.inputs_dir / "invoice.csv"
    assert destination.is_file()
    assert destination.read_bytes() == content


@pytest.mark.parametrize(
    "filename",
    [
        "../invoice.csv",
        "folder/invoice.csv",
        r"folder\invoice.csv",
        "/tmp/invoice.csv",
        "",
        ".",
        "..",
    ],
)
def test_rejects_unsafe_filenames(tmp_path, filename):
    workspace = create_audit_workspace(tmp_path)

    with pytest.raises(ValueError):
        ingest_uploaded_file(
            workspace=workspace,
            filename=filename,
            content=b"test",
        )


def test_rejects_unsupported_extension(tmp_path):
    workspace = create_audit_workspace(tmp_path)

    with pytest.raises(ValueError):
        ingest_uploaded_file(
            workspace=workspace,
            filename="invoice.exe",
            content=b"test",
        )


def test_rejects_oversized_upload(tmp_path):
    workspace = create_audit_workspace(tmp_path)

    with pytest.raises(ValueError):
        ingest_uploaded_file(
            workspace=workspace,
            filename="invoice.csv",
            content=b"x" * (25 * 1024 * 1024 + 1),
        )


def test_rejects_existing_destination(tmp_path):
    workspace = create_audit_workspace(tmp_path)

    destination = workspace.inputs_dir / "invoice.csv"
    destination.write_bytes(b"original")

    with pytest.raises(FileExistsError):
        ingest_uploaded_file(
            workspace=workspace,
            filename="invoice.csv",
            content=b"replacement",
        )

    assert destination.read_bytes() == b"original"


def test_rejects_symlink_destination(tmp_path):
    workspace = create_audit_workspace(tmp_path)

    outside = tmp_path / "outside.csv"
    outside.write_bytes(b"protected")

    destination = workspace.inputs_dir / "invoice.csv"
    destination.symlink_to(outside)

    with pytest.raises((ValueError, FileExistsError)):
        ingest_uploaded_file(
            workspace=workspace,
            filename="invoice.csv",
            content=b"replacement",
        )

    assert outside.read_bytes() == b"protected"


def test_uploaded_file_has_private_permissions(tmp_path):
    import stat

    workspace = create_audit_workspace(tmp_path)

    destination = ingest_uploaded_file(
        workspace=workspace,
        filename="private.csv",
        content=b"invoice_id,amount\nINV001,100\n",
    )

    permissions = stat.S_IMODE(destination.stat().st_mode)

    assert permissions == 0o600


def test_empty_upload_is_handled_explicitly(tmp_path):
    workspace = create_audit_workspace(tmp_path)

    with pytest.raises(ValueError, match="cannot be empty"):
        ingest_uploaded_file(
            workspace=workspace,
            filename="empty.csv",
            content=b"",
        )

    assert not (workspace.inputs_dir / "empty.csv").exists()


def test_partial_write_failure_removes_destination(tmp_path, monkeypatch):
    import builtins

    workspace = create_audit_workspace(tmp_path)

    original_fdopen = __import__("os").fdopen

    class FailingWriter:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def __enter__(self):
            self.wrapped.__enter__()
            return self

        def __exit__(self, exc_type, exc, tb):
            return self.wrapped.__exit__(exc_type, exc, tb)

        def fileno(self):
            return self.wrapped.fileno()

        def write(self, data):
            self.wrapped.write(data[:3])
            raise OSError("Simulated interrupted upload")

    def failing_fdopen(fd, mode, **kwargs):
        return FailingWriter(
            original_fdopen(fd, mode, **kwargs)
        )

    monkeypatch.setattr(
        "services.upload_ingestion.os.fdopen",
        failing_fdopen,
    )

    with pytest.raises(OSError, match="Simulated interrupted upload"):
        ingest_uploaded_file(
            workspace=workspace,
            filename="interrupted.csv",
            content=b"invoice_id,amount\nINV001,100\n",
        )

    assert not (workspace.inputs_dir / "interrupted.csv").exists()


def test_rejects_invalid_xlsx_content(tmp_path):
    workspace = create_audit_workspace(tmp_path)

    with pytest.raises(ValueError, match="Invalid XLSX"):
        ingest_uploaded_file(
            workspace=workspace,
            filename="invalid.xlsx",
            content=b"This is not an Excel workbook",
        )

    assert not (workspace.inputs_dir / "invalid.xlsx").exists()


def test_rejects_invalid_xls_content(tmp_path):
    workspace = create_audit_workspace(tmp_path)

    with pytest.raises(ValueError, match="Invalid XLS"):
        ingest_uploaded_file(
            workspace=workspace,
            filename="invalid.xls",
            content=b"This is not an Excel workbook",
        )

    assert not (workspace.inputs_dir / "invalid.xls").exists()


def test_rejects_binary_content_disguised_as_csv(tmp_path):
    workspace = create_audit_workspace(tmp_path)

    with pytest.raises(ValueError, match="Invalid CSV"):
        ingest_uploaded_file(
            workspace=workspace,
            filename="invalid.csv",
            content=b"\x00\x01\x02\x03\xff",
        )

    assert not (workspace.inputs_dir / "invalid.csv").exists()


def test_accepts_valid_xlsx_content(tmp_path):
    from io import BytesIO
    from openpyxl import Workbook

    workspace = create_audit_workspace(tmp_path)

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["invoice_id", "amount"])
    sheet.append(["INV001", 100])

    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()

    content = buffer.getvalue()

    destination = ingest_uploaded_file(
        workspace=workspace,
        filename="valid.xlsx",
        content=content,
    )

    assert destination.is_file()
    assert destination.read_bytes() == content


def test_rejects_symlinked_inputs_directory(tmp_path):
    workspace = create_audit_workspace(tmp_path)

    outside = tmp_path / "outside"
    outside.mkdir()

    workspace.inputs_dir.rmdir()
    workspace.inputs_dir.symlink_to(
        outside,
        target_is_directory=True,
    )

    with pytest.raises((ValueError, OSError)):
        ingest_uploaded_file(
            workspace=workspace,
            filename="invoice.csv",
            content=b"invoice_id,amount\nINV001,100\n",
        )

    assert not (outside / "invoice.csv").exists()


def test_rejects_replaced_inputs_directory(tmp_path):
    workspace = create_audit_workspace(tmp_path)

    original_inputs = workspace.inputs_dir
    moved_inputs = tmp_path / "moved_inputs"

    original_inputs.rename(moved_inputs)
    original_inputs.mkdir()

    with pytest.raises((ValueError, OSError)):
        ingest_uploaded_file(
            workspace=workspace,
            filename="invoice.csv",
            content=b"invoice_id,amount\nINV001,100\n",
        )

    assert not (original_inputs / "invoice.csv").exists()


def test_final_filename_is_not_visible_during_upload(tmp_path, monkeypatch):
    import os

    workspace = create_audit_workspace(tmp_path)
    filename = "atomic_invoice.csv"
    content = b"invoice_id,amount\nINV001,100\n"

    original_fdopen = os.fdopen
    observed = {"checked": False}

    class ObservingWriter:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def __enter__(self):
            self.wrapped.__enter__()
            return self

        def __exit__(self, exc_type, exc, tb):
            return self.wrapped.__exit__(exc_type, exc, tb)

        def fileno(self):
            return self.wrapped.fileno()

        def write(self, data):
            assert not (workspace.inputs_dir / filename).exists(), (
                "Final filename became visible before upload completed."
            )
            observed["checked"] = True
            return self.wrapped.write(data)

        def flush(self):
            return self.wrapped.flush()

    def observing_fdopen(fd, mode, **kwargs):
        return ObservingWriter(
            original_fdopen(fd, mode, **kwargs)
        )

    monkeypatch.setattr(
        "services.upload_ingestion.os.fdopen",
        observing_fdopen,
    )

    result = ingest_uploaded_file(
        workspace=workspace,
        filename=filename,
        content=content,
    )

    assert observed["checked"]
    assert result.read_bytes() == content


def test_cleanup_failure_after_publication_is_reported(
    tmp_path, monkeypatch
):
    import os

    from services.workspace import PublishedFileCleanupError

    workspace = create_audit_workspace(tmp_path)
    content = b"invoice_id,amount\nINV001,100\n"
    filename = "cleanup_failure.csv"

    original_unlink = os.unlink

    def failing_unlink(path, *args, **kwargs):
        if isinstance(path, str) and path.startswith(".upload_"):
            raise OSError("Simulated temporary cleanup failure")

        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(
        "services.upload_ingestion.os.unlink",
        failing_unlink,
    )

    with pytest.raises(PublishedFileCleanupError):
        ingest_uploaded_file(
            workspace=workspace,
            filename=filename,
            content=content,
        )

    assert (workspace.inputs_dir / filename).read_bytes() == content

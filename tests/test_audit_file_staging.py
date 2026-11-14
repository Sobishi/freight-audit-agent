"""Tests for controlled local freight audit file staging."""

import pytest

from services.workspace import (
    MAX_UPLOAD_BYTES,
    create_audit_workspace,
    stage_audit_file,
)


@pytest.fixture
def workspace(tmp_path):
    return create_audit_workspace(tmp_path)


@pytest.fixture
def source_file(tmp_path):
    source = tmp_path / "invoice.csv"
    source.write_text("AWB,Total\nA001,100\n", encoding="utf-8")
    return source


def test_file_is_staged_inside_workspace(workspace, source_file):
    staged = stage_audit_file(workspace, source_file, "invoice.csv")

    assert staged == workspace.inputs_dir / "invoice.csv"
    assert staged.read_bytes() == source_file.read_bytes()
    assert staged != source_file


def test_unsafe_filename_is_rejected(workspace, source_file):
    for filename in (
        "../invoice.csv",
        "folder/invoice.csv",
        "..\\invoice.csv",
        "..invoice.csv",
        ".hidden.csv",
    ):
        with pytest.raises(ValueError, match="Unsafe upload filename"):
            stage_audit_file(workspace, source_file, filename)


def test_unsupported_extension_is_rejected(workspace, source_file):
    with pytest.raises(ValueError, match="Unsupported upload"):
        stage_audit_file(workspace, source_file, "invoice.exe")


def test_existing_staged_file_cannot_be_overwritten(
    workspace, source_file
):
    staged = stage_audit_file(workspace, source_file, "invoice.csv")
    original = staged.read_bytes()

    with pytest.raises(ValueError, match="already exists"):
        stage_audit_file(workspace, source_file, "invoice.csv")

    assert staged.read_bytes() == original


def test_symlinked_source_is_rejected(workspace, source_file, tmp_path):
    link = tmp_path / "linked.csv"
    link.symlink_to(source_file)

    with pytest.raises(ValueError, match="Symlinked source"):
        stage_audit_file(workspace, link, "invoice.csv")


def test_oversized_source_is_rejected(workspace, tmp_path):
    source = tmp_path / "large.csv"

    with source.open("wb") as file:
        file.truncate(MAX_UPLOAD_BYTES + 1)

    with pytest.raises(ValueError, match="maximum file size"):
        stage_audit_file(workspace, source, "large.csv")

    assert not (workspace.inputs_dir / "large.csv").exists()


def test_staged_file_has_private_permissions(workspace, source_file):
    staged = stage_audit_file(workspace, source_file, "invoice.csv")

    assert staged.stat().st_mode & 0o777 == 0o600


def test_symlinked_input_directory_is_rejected(
    workspace, source_file, tmp_path
):
    workspace.inputs_dir.rmdir()

    external = tmp_path / "external"
    external.mkdir()

    workspace.inputs_dir.symlink_to(
        external,
        target_is_directory=True,
    )

    with pytest.raises(ValueError, match="cannot be a symlink"):
        stage_audit_file(workspace, source_file, "invoice.csv")

    assert not (external / "invoice.csv").exists()


def test_staging_invokes_directory_identity_checks(
    workspace, source_file, monkeypatch
):
    import services.workspace as workspace_module

    original = workspace_module.verify_open_directory_identity
    verified_paths = []

    def recording_verifier(directory_fd, expected_path):
        verified_paths.append(expected_path)
        return original(directory_fd, expected_path)

    monkeypatch.setattr(
        workspace_module,
        "verify_open_directory_identity",
        recording_verifier,
    )

    staged = stage_audit_file(
        workspace,
        source_file,
        "verified_invoice.csv",
    )

    assert staged.is_file()
    assert verified_paths == [
        workspace.root,
        workspace.inputs_dir,
        workspace.inputs_dir,
    ]


def test_failed_copy_does_not_publish_final_filename(
    workspace, source_file, monkeypatch
):
    import builtins
    import services.workspace as workspace_module

    original_fdopen = workspace_module.os.fdopen if hasattr(
        workspace_module, "os"
    ) else __import__("os").fdopen

    class FailingWriter:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def __enter__(self):
            self.wrapped.__enter__()
            return self

        def __exit__(self, *args):
            return self.wrapped.__exit__(*args)

        def write(self, data):
            raise OSError("Simulated disk write failure")

    def failing_fdopen(fd, mode, *args, **kwargs):
        opened = original_fdopen(fd, mode, *args, **kwargs)
        if mode == "wb":
            return FailingWriter(opened)
        return opened

    monkeypatch.setattr(
        __import__("os"),
        "fdopen",
        failing_fdopen,
    )

    with pytest.raises(OSError, match="Simulated disk write failure"):
        stage_audit_file(
            workspace,
            source_file,
            "failed_invoice.csv",
        )

    assert not (
        workspace.inputs_dir / "failed_invoice.csv"
    ).exists()


def test_successful_staging_leaves_no_temporary_files(
    workspace, source_file
):
    staged = stage_audit_file(
        workspace,
        source_file,
        "completed_invoice.csv",
    )

    assert staged.is_file()

    assert sorted(
        path.name for path in workspace.inputs_dir.iterdir()
    ) == ["completed_invoice.csv"]


def test_final_filename_is_not_visible_during_copy(
    workspace, source_file, monkeypatch
):
    import os

    original_fdopen = os.fdopen
    observed = []

    class InspectingWriter:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def __enter__(self):
            self.wrapped.__enter__()
            return self

        def __exit__(self, *args):
            return self.wrapped.__exit__(*args)

        def write(self, data):
            observed.append(
                (workspace.inputs_dir / "invoice.csv").exists()
            )
            return self.wrapped.write(data)

        def flush(self):
            return self.wrapped.flush()

    def inspecting_fdopen(fd, mode, *args, **kwargs):
        opened = original_fdopen(fd, mode, *args, **kwargs)

        if mode == "wb":
            return InspectingWriter(opened)

        return opened

    monkeypatch.setattr(
        os,
        "fdopen",
        inspecting_fdopen,
    )

    staged = stage_audit_file(
        workspace,
        source_file,
        "invoice.csv",
    )

    assert observed, "The test did not observe a write."
    assert all(visible is False for visible in observed)
    assert staged.is_file()
    assert staged.read_bytes() == source_file.read_bytes()


def test_atomic_publication_does_not_overwrite_existing_file(
    workspace, source_file
):
    destination = workspace.inputs_dir / "existing_invoice.csv"
    destination.write_bytes(b"ORIGINAL CONTENT")

    with pytest.raises(
        ValueError,
        match="Staged filename already exists",
    ):
        stage_audit_file(
            workspace,
            source_file,
            "existing_invoice.csv",
        )

    assert destination.read_bytes() == b"ORIGINAL CONTENT"

    assert sorted(
        path.name for path in workspace.inputs_dir.iterdir()
    ) == ["existing_invoice.csv"]


def test_atomic_publication_failure_cleans_temporary_file(
    workspace, source_file, monkeypatch
):
    import os

    def failing_link(*args, **kwargs):
        raise OSError("Simulated publication failure")

    monkeypatch.setattr(os, "link", failing_link)
    monkeypatch.setattr(
        os,
        "supports_dir_fd",
        os.supports_dir_fd | {failing_link},
    )

    with pytest.raises(
        OSError,
        match="Simulated publication failure",
    ):
        stage_audit_file(
            workspace,
            source_file,
            "failed_publication.csv",
        )

    assert not (
        workspace.inputs_dir / "failed_publication.csv"
    ).exists()

    assert list(workspace.inputs_dir.iterdir()) == []


def test_temporary_descriptor_closes_when_cleanup_fails(
    workspace, source_file, monkeypatch
):
    import os
    import services.workspace as workspace_module

    original_open = os.open
    original_close = os.close
    temporary_descriptors = []
    closed_descriptors = []

    def recording_open(path, flags, *args, **kwargs):
        fd = original_open(path, flags, *args, **kwargs)

        if isinstance(path, str) and path.startswith(".staging_"):
            temporary_descriptors.append(fd)

        return fd

    def recording_close(fd):
        if fd in temporary_descriptors:
            closed_descriptors.append(fd)
        return original_close(fd)

    def failing_cleanup(*args, **kwargs):
        raise OSError("Simulated cleanup failure")

    monkeypatch.setattr(os, "open", recording_open)
    monkeypatch.setattr(os, "close", recording_close)
    monkeypatch.setattr(
        workspace_module,
        "cleanup_partial_staged_file",
        failing_cleanup,
    )

    with pytest.raises(
        OSError,
        match="Simulated cleanup failure",
    ):
        stage_audit_file(
            workspace,
            source_file,
            "cleanup_failure.csv",
        )

    assert len(temporary_descriptors) == 1
    assert closed_descriptors == temporary_descriptors


def test_original_copy_error_is_preserved_when_cleanup_fails(
    workspace, source_file, monkeypatch
):
    import os
    import services.workspace as workspace_module

    original_fdopen = os.fdopen

    class FailingWriter:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def __enter__(self):
            self.wrapped.__enter__()
            return self

        def __exit__(self, *args):
            return self.wrapped.__exit__(*args)

        def write(self, data):
            raise OSError("Original copy failure")

    def failing_fdopen(fd, mode, *args, **kwargs):
        opened = original_fdopen(fd, mode, *args, **kwargs)

        if mode == "wb":
            return FailingWriter(opened)

        return opened

    def failing_cleanup(*args, **kwargs):
        raise OSError("Secondary cleanup failure")

    monkeypatch.setattr(os, "fdopen", failing_fdopen)
    monkeypatch.setattr(
        workspace_module,
        "cleanup_partial_staged_file",
        failing_cleanup,
    )

    with pytest.raises(
        OSError,
        match="Original copy failure",
    ):
        stage_audit_file(
            workspace,
            source_file,
            "copy_failure.csv",
        )


def test_cleanup_failure_after_publication_preserves_final_file(
    workspace, source_file, monkeypatch
):
    import os
    import services.workspace as workspace_module

    original_cleanup = (
        workspace_module.cleanup_partial_staged_file
    )

    def failing_cleanup(directory_fd, filename, created_fd):
        if filename.startswith(".staging_"):
            raise OSError("Simulated post-publication cleanup failure")

        return original_cleanup(
            directory_fd,
            filename,
            created_fd,
        )

    monkeypatch.setattr(
        workspace_module,
        "cleanup_partial_staged_file",
        failing_cleanup,
    )

    destination = workspace.inputs_dir / "published_invoice.csv"

    with pytest.raises(
        OSError,
        match="Simulated post-publication cleanup failure",
    ):
        stage_audit_file(
            workspace,
            source_file,
            "published_invoice.csv",
        )

    assert destination.is_file()
    assert destination.read_bytes() == source_file.read_bytes()

    temporary_files = [
        path
        for path in workspace.inputs_dir.iterdir()
        if path.name.startswith(".staging_")
    ]

    assert len(temporary_files) == 1
    assert os.stat(destination).st_ino == os.stat(
        temporary_files[0]
    ).st_ino


def test_cleanup_failure_after_publication_is_distinguishable(
    workspace, source_file, monkeypatch
):
    import os
    import services.workspace as workspace_module

    def failing_cleanup(*args, **kwargs):
        raise OSError("Simulated cleanup failure")

    monkeypatch.setattr(
        workspace_module,
        "cleanup_partial_staged_file",
        failing_cleanup,
    )

    destination = workspace.inputs_dir / "state_invoice.csv"

    with pytest.raises(
        OSError,
        match="Simulated cleanup failure",
    ):
        stage_audit_file(
            workspace,
            source_file,
            "state_invoice.csv",
        )

    assert destination.is_file()
    assert destination.read_bytes() == source_file.read_bytes()

    temporary_files = [
        path
        for path in workspace.inputs_dir.iterdir()
        if path.name.startswith(".staging_")
    ]

    assert len(temporary_files) == 1

    final_stat = os.stat(destination)
    temporary_stat = os.stat(temporary_files[0])

    assert final_stat.st_dev == temporary_stat.st_dev
    assert final_stat.st_ino == temporary_stat.st_ino


def test_published_cleanup_exception_identifies_completed_file(
    workspace, source_file, monkeypatch
):
    import services.workspace as workspace_module

    def failing_cleanup(*args, **kwargs):
        raise OSError("Simulated cleanup failure")

    monkeypatch.setattr(
        workspace_module,
        "cleanup_partial_staged_file",
        failing_cleanup,
    )

    destination = workspace.inputs_dir / "published_contract.csv"

    with pytest.raises(
        workspace_module.PublishedFileCleanupError
    ) as captured:
        stage_audit_file(
            workspace,
            source_file,
            "published_contract.csv",
        )

    error = captured.value

    assert error.published_path == destination
    assert isinstance(error.cleanup_error, OSError)
    assert "Simulated cleanup failure" in str(
        error.cleanup_error
    )

    assert destination.is_file()
    assert destination.read_bytes() == source_file.read_bytes()


def test_staging_rejects_insecure_inputs_permissions(
    workspace, source_file
):
    import os

    inputs = workspace.inputs_dir
    original_mode = inputs.stat().st_mode & 0o777

    try:
        os.chmod(inputs, 0o777)

        with pytest.raises(
            (ValueError, PermissionError),
            match="(?i)(permission|insecure|mode)",
        ):
            stage_audit_file(
                workspace,
                source_file,
                "insecure_invoice.csv",
            )

        assert not (
            workspace.inputs_dir / "insecure_invoice.csv"
        ).exists()

    finally:
        os.chmod(inputs, original_mode)


def test_staging_rejects_insecure_workspace_root_permissions(
    workspace, source_file
):
    import os
    import stat

    root = workspace.root
    original_mode = stat.S_IMODE(root.stat().st_mode)

    try:
        os.chmod(root, 0o777)

        with pytest.raises(
            PermissionError,
            match="Insecure workspace directory permissions",
        ):
            stage_audit_file(
                workspace,
                source_file,
                "insecure_root_invoice.csv",
            )

        assert not (
            workspace.inputs_dir / "insecure_root_invoice.csv"
        ).exists()

    finally:
        os.chmod(root, original_mode)


def test_false_cleanup_result_after_publication_is_reported(
    workspace, source_file, monkeypatch
):
    import services.workspace as workspace_module

    def unsuccessful_cleanup(*args, **kwargs):
        return False

    monkeypatch.setattr(
        workspace_module,
        "cleanup_partial_staged_file",
        unsuccessful_cleanup,
    )

    destination = workspace.inputs_dir / "cleanup_false.csv"

    with pytest.raises(
        workspace_module.PublishedFileCleanupError
    ) as captured:
        stage_audit_file(
            workspace,
            source_file,
            "cleanup_false.csv",
        )

    assert captured.value.published_path == destination
    assert destination.is_file()
    assert destination.read_bytes() == source_file.read_bytes()

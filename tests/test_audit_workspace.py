"""Tests for controlled audit workspace allocation."""

import pytest

from services.workspace import create_audit_workspace


def test_workspace_has_expected_directories(tmp_path):
    workspace = create_audit_workspace(tmp_path)

    assert workspace.root.is_dir()
    assert workspace.inputs_dir.is_dir()
    assert workspace.reports_dir.is_dir()
    assert workspace.logs_dir.is_dir()

    assert workspace.root.parent == tmp_path.resolve()
    assert workspace.report_path == (
        workspace.reports_dir / "audit_report.xlsx"
    )


def test_workspaces_are_unique(tmp_path):
    first = create_audit_workspace(tmp_path)
    second = create_audit_workspace(tmp_path)

    assert first.workspace_id != second.workspace_id
    assert first.root != second.root
    assert first.report_path != second.report_path
    assert first.logs_dir != second.logs_dir


def test_missing_base_directory_is_rejected(tmp_path):
    missing = tmp_path / "missing"

    with pytest.raises(ValueError, match="does not exist"):
        create_audit_workspace(missing)

    assert not missing.exists()


def test_symlink_base_directory_is_rejected(tmp_path):
    actual = tmp_path / "actual"
    actual.mkdir()

    link = tmp_path / "linked"
    link.symlink_to(actual, target_is_directory=True)

    with pytest.raises(ValueError, match="cannot be a symlink"):
        create_audit_workspace(link)


def test_base_directory_must_be_path():
    with pytest.raises(TypeError, match="must be a Path"):
        create_audit_workspace("audit_workspaces")


def test_workspace_permissions_are_owner_only(tmp_path):
    workspace = create_audit_workspace(tmp_path)

    for directory in (
        workspace.root,
        workspace.inputs_dir,
        workspace.reports_dir,
        workspace.logs_dir,
    ):
        assert directory.stat().st_mode & 0o777 == 0o700


def test_valid_workspace_identity(tmp_path):
    from services.workspace import validate_workspace_identity

    workspace = create_audit_workspace(tmp_path)

    validate_workspace_identity(workspace)


def test_mismatched_workspace_identifier_is_rejected(tmp_path):
    from dataclasses import replace
    from services.workspace import validate_workspace_identity

    workspace = create_audit_workspace(tmp_path)
    invalid = replace(workspace, workspace_id="0" * 32)

    with pytest.raises(ValueError, match="does not match identifier"):
        validate_workspace_identity(invalid)


def test_mismatched_input_directory_is_rejected(tmp_path):
    from dataclasses import replace
    from services.workspace import validate_workspace_identity

    workspace = create_audit_workspace(tmp_path)
    invalid = replace(
        workspace,
        inputs_dir=tmp_path / "external",
    )

    with pytest.raises(ValueError, match="structure is invalid"):
        validate_workspace_identity(invalid)


def test_missing_workspace_directory_is_rejected(tmp_path):
    from services.workspace import validate_workspace_identity

    workspace = create_audit_workspace(tmp_path)
    workspace.logs_dir.rmdir()

    with pytest.raises(ValueError, match="does not exist"):
        validate_workspace_identity(workspace)


def test_symlinked_workspace_directory_is_rejected(tmp_path):
    from services.workspace import validate_workspace_identity

    workspace = create_audit_workspace(tmp_path)

    workspace.logs_dir.rmdir()
    workspace.logs_dir.symlink_to(
        workspace.inputs_dir,
        target_is_directory=True,
    )

    with pytest.raises(ValueError, match="cannot be a symlink"):
        validate_workspace_identity(workspace)


def test_workspace_creation_cleans_up_partial_allocation(
    tmp_path, monkeypatch
):
    from pathlib import Path

    import pytest

    from services.workspace import create_audit_workspace

    original_mkdir = Path.mkdir

    def failing_mkdir(self, *args, **kwargs):
        if self.name == "reports":
            raise OSError("Simulated reports directory failure")

        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", failing_mkdir)

    with pytest.raises(
        OSError,
        match="Simulated reports directory failure",
    ):
        create_audit_workspace(tmp_path)

    remaining = list(tmp_path.iterdir())

    assert remaining == [], (
        "Failed workspace allocation left directories behind: "
        f"{remaining}"
    )

"""Tests for opened workspace directory identity checks."""

import os

import pytest

from services.workspace import verify_open_directory_identity


def test_matching_directory_identity(tmp_path):
    fd = os.open(tmp_path, os.O_RDONLY)

    try:
        verify_open_directory_identity(fd, tmp_path)
    finally:
        os.close(fd)


def test_replaced_directory_is_rejected(tmp_path):
    original = tmp_path / "original"
    original.mkdir()

    fd = os.open(original, os.O_RDONLY)

    try:
        original.rename(tmp_path / "moved")
        original.mkdir()

        with pytest.raises(
            ValueError,
            match="identity changed",
        ):
            verify_open_directory_identity(fd, original)
    finally:
        os.close(fd)


def test_symlink_replacement_is_rejected(tmp_path):
    original = tmp_path / "original"
    original.mkdir()

    fd = os.open(original, os.O_RDONLY)

    try:
        moved = tmp_path / "moved"
        original.rename(moved)
        original.symlink_to(moved, target_is_directory=True)

        with pytest.raises(
            ValueError,
            match="not a directory",
        ):
            verify_open_directory_identity(fd, original)
    finally:
        os.close(fd)


def test_file_descriptor_is_rejected(tmp_path):
    file_path = tmp_path / "file.txt"
    file_path.write_text("test")

    fd = os.open(file_path, os.O_RDONLY)

    try:
        with pytest.raises(
            ValueError,
            match="not a directory",
        ):
            verify_open_directory_identity(fd, tmp_path)
    finally:
        os.close(fd)


def test_private_directory_rejects_owner_mismatch(
    tmp_path, monkeypatch
):
    import os
    from types import SimpleNamespace

    import pytest
    import services.workspace as workspace_module

    directory = tmp_path / "private_directory"
    directory.mkdir(mode=0o700)

    directory_fd = os.open(directory, os.O_RDONLY)

    try:
        actual_info = os.fstat(directory_fd)

        fake_info = SimpleNamespace(
            st_mode=actual_info.st_mode,
            st_uid=os.getuid() + 1,
        )

        original_fstat = os.fstat

        def simulated_fstat(fd):
            if fd == directory_fd:
                return fake_info
            return original_fstat(fd)

        monkeypatch.setattr(
            os,
            "fstat",
            simulated_fstat,
        )

        with pytest.raises(
            PermissionError,
            match="owner does not match process owner",
        ):
            workspace_module.verify_private_workspace_directory(
                directory_fd
            )

    finally:
        os.close(directory_fd)

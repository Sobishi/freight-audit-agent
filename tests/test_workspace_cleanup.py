"""Tests for identity-aware partial-file cleanup."""

import os

import pytest

from services.workspace import (
    TemporaryFileIdentityError,
    cleanup_partial_staged_file,
)


def test_matching_partial_file_is_removed(tmp_path):
    filename = "partial.csv"
    path = tmp_path / filename
    path.write_bytes(b"partial")

    directory_fd = os.open(tmp_path, os.O_RDONLY)
    created_fd = os.open(path, os.O_RDONLY)

    try:
        removed = cleanup_partial_staged_file(
            directory_fd,
            filename,
            created_fd,
        )

        assert removed is True
        assert not path.exists()
    finally:
        os.close(created_fd)
        os.close(directory_fd)


def test_replaced_file_is_not_removed(tmp_path):
    filename = "partial.csv"
    path = tmp_path / filename
    path.write_bytes(b"original")

    directory_fd = os.open(tmp_path, os.O_RDONLY)
    created_fd = os.open(path, os.O_RDONLY)

    try:
        path.unlink()
        path.write_bytes(b"replacement")

        with pytest.raises(
            TemporaryFileIdentityError,
            match="identity changed",
        ):
            cleanup_partial_staged_file(
                directory_fd,
                filename,
                created_fd,
            )

        assert path.read_bytes() == b"replacement"
    finally:
        os.close(created_fd)
        os.close(directory_fd)


def test_missing_partial_file_returns_false(tmp_path):
    filename = "partial.csv"
    path = tmp_path / filename
    path.write_bytes(b"original")

    directory_fd = os.open(tmp_path, os.O_RDONLY)
    created_fd = os.open(path, os.O_RDONLY)

    try:
        path.unlink()

        removed = cleanup_partial_staged_file(
            directory_fd,
            filename,
            created_fd,
        )

        assert removed is False
    finally:
        os.close(created_fd)
        os.close(directory_fd)

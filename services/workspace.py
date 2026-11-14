"""Workspace allocation for controlled freight audit execution."""

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class AuditWorkspace:
    """Filesystem locations allocated to one audit submission."""

    workspace_id: str
    root: Path
    inputs_dir: Path
    reports_dir: Path
    logs_dir: Path
    inputs_identity: tuple[int, int] | None = None

    @property
    def report_path(self) -> Path:
        return self.reports_dir / "audit_report.xlsx"


def create_audit_workspace(base_dir: Path) -> AuditWorkspace:
    """Allocate a unique workspace beneath a trusted base directory."""

    if not isinstance(base_dir, Path):
        raise TypeError("Workspace base directory must be a Path.")

    if base_dir.is_symlink():
        raise ValueError("Workspace base directory cannot be a symlink.")

    base_dir = base_dir.resolve()

    if not base_dir.is_dir():
        raise ValueError("Workspace base directory does not exist.")

    for _ in range(10):
        workspace_id = uuid4().hex
        root = base_dir / workspace_id

        try:
            root.mkdir(mode=0o700)
        except FileExistsError:
            continue

        inputs_dir = root / "inputs"
        reports_dir = root / "reports"
        logs_dir = root / "logs"

        created_directories = []

        try:
            for directory in (inputs_dir, reports_dir, logs_dir):
                directory.mkdir(mode=0o700)
                created_directories.append(directory)
        except Exception as allocation_error:
            try:
                for directory in reversed(created_directories):
                    directory.rmdir()

                root.rmdir()
            except OSError as cleanup_error:
                allocation_error.add_note(
                    "Workspace allocation rollback also failed: "
                    f"{cleanup_error!r}"
                )

            raise

        return AuditWorkspace(
            workspace_id=workspace_id,
            root=root,
            inputs_dir=inputs_dir,
            reports_dir=reports_dir,
            logs_dir=logs_dir,
            inputs_identity=(
                inputs_dir.stat().st_dev,
                inputs_dir.stat().st_ino,
            ),
        )

    raise RuntimeError("Unable to allocate a unique audit workspace.")


MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ALLOWED_UPLOAD_EXTENSIONS = frozenset({".csv", ".xlsx", ".xls"})


class PublishedFileCleanupError(OSError):
    """A completed file was published, but temporary cleanup failed."""

    def __init__(self, published_path: Path, cleanup_error: Exception):
        self.published_path = published_path
        self.cleanup_error = cleanup_error
        super().__init__(
            f"File was published at {published_path}, "
            f"but temporary cleanup failed: {cleanup_error}"
        )


def verify_private_workspace_directory(directory_fd: int) -> None:
    """Require an opened workspace directory to be owner-private."""
    import os
    import stat

    info = os.fstat(directory_fd)

    if not stat.S_ISDIR(info.st_mode):
        raise ValueError("Workspace descriptor is not a directory.")

    if info.st_uid != os.getuid():
        raise PermissionError(
            "Workspace directory owner does not match process owner."
        )

    if stat.S_IMODE(info.st_mode) != 0o700:
        raise PermissionError(
            "Insecure workspace directory permissions."
        )


def stage_audit_file(
    workspace: AuditWorkspace,
    source: Path,
    filename: str,
) -> Path:
    """Stage a file and publish it only after copying completes."""
    import os
    import re
    import stat
    from uuid import uuid4

    validate_workspace_identity(workspace)

    if not isinstance(source, Path):
        raise TypeError("Source must be a Path.")

    if not isinstance(filename, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", filename
    ):
        raise ValueError("Unsafe upload filename.")

    if filename in (".", "..") or ".." in filename:
        raise ValueError("Unsafe upload filename.")

    if Path(filename).suffix.lower() not in ALLOWED_UPLOAD_EXTENSIONS:
        raise ValueError("Unsupported upload file format.")

    if source.is_symlink():
        raise ValueError("Symlinked source files are not allowed.")

    required = (
        "O_NOFOLLOW",
        "O_DIRECTORY",
        "O_EXCL",
    )
    if not all(hasattr(os, name) for name in required):
        raise RuntimeError("Secure filesystem operations are unsupported.")

    if os.link not in os.supports_dir_fd:
        raise RuntimeError("Atomic publication is unsupported.")

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW

    base_fd = os.open(workspace.root.parent, directory_flags)

    try:
        root_fd = os.open(
            workspace.workspace_id,
            directory_flags,
            dir_fd=base_fd,
        )

        try:
            verify_open_directory_identity(root_fd, workspace.root)
            verify_private_workspace_directory(root_fd)

            inputs_fd = os.open(
                "inputs",
                directory_flags,
                dir_fd=root_fd,
            )

            try:
                verify_open_directory_identity(
                    inputs_fd,
                    workspace.inputs_dir,
                )
                verify_private_workspace_directory(inputs_fd)

                source_fd = os.open(
                    source,
                    os.O_RDONLY | os.O_NOFOLLOW,
                )

                try:
                    source_stat = os.fstat(source_fd)

                    if not stat.S_ISREG(source_stat.st_mode):
                        raise ValueError("Source must be a regular file.")

                    if source_stat.st_size > MAX_UPLOAD_BYTES:
                        raise ValueError("Upload exceeds maximum file size.")

                    temporary_name = ".staging_" + uuid4().hex

                    temporary_fd = os.open(
                        temporary_name,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600,
                        dir_fd=inputs_fd,
                    )

                    published = False

                    try:
                        total = 0

                        with os.fdopen(
                            source_fd, "rb", closefd=False
                        ) as input_file:
                            with os.fdopen(
                                temporary_fd, "wb", closefd=False
                            ) as output_file:
                                while True:
                                    chunk = input_file.read(1024 * 1024)

                                    if not chunk:
                                        break

                                    total += len(chunk)

                                    if total > MAX_UPLOAD_BYTES:
                                        raise ValueError(
                                            "Upload exceeds maximum file size."
                                        )

                                    output_file.write(chunk)

                                output_file.flush()
                                os.fsync(temporary_fd)

                        verify_open_directory_identity(
                            inputs_fd,
                            workspace.inputs_dir,
                        )
                        verify_private_workspace_directory(inputs_fd)

                        try:
                            os.link(
                                temporary_name,
                                filename,
                                src_dir_fd=inputs_fd,
                                dst_dir_fd=inputs_fd,
                                follow_symlinks=False,
                            )
                        except FileExistsError as exc:
                            raise ValueError(
                                "Staged filename already exists."
                            ) from exc

                        published = True

                    finally:
                        import sys

                        original_error = sys.exc_info()[1]

                        try:
                            removed = cleanup_partial_staged_file(
                                inputs_fd,
                                temporary_name,
                                temporary_fd,
                            )

                            if not removed:
                                raise OSError(
                                    "Temporary-file cleanup was not confirmed."
                                )
                        except Exception as cleanup_error:
                            if original_error is not None:
                                original_error.add_note(
                                    "Temporary-file cleanup also failed: "
                                    f"{cleanup_error!r}"
                                )
                            elif published:
                                raise PublishedFileCleanupError(
                                    workspace.inputs_dir / filename,
                                    cleanup_error,
                                ) from cleanup_error
                            else:
                                raise
                        finally:
                            os.close(temporary_fd)

                finally:
                    os.close(source_fd)

            finally:
                os.close(inputs_fd)

        finally:
            os.close(root_fd)

    finally:
        os.close(base_fd)

    return workspace.inputs_dir / filename


def validate_workspace_identity(workspace: AuditWorkspace) -> None:
    """Validate the expected structure of an allocated workspace."""

    import re

    if not isinstance(workspace, AuditWorkspace):
        raise TypeError("Expected an AuditWorkspace.")

    if not isinstance(workspace.workspace_id, str) or not re.fullmatch(
        r"[0-9a-f]{32}", workspace.workspace_id
    ):
        raise ValueError("Invalid workspace identifier.")

    paths = (
        workspace.root,
        workspace.inputs_dir,
        workspace.reports_dir,
        workspace.logs_dir,
    )

    if not all(isinstance(path, Path) for path in paths):
        raise TypeError("Workspace locations must be Paths.")

    if workspace.root.name != workspace.workspace_id:
        raise ValueError("Workspace root does not match identifier.")

    expected = (
        workspace.root / "inputs",
        workspace.root / "reports",
        workspace.root / "logs",
    )

    if paths[1:] != expected:
        raise ValueError("Workspace directory structure is invalid.")

    for path in paths:
        if path.is_symlink():
            raise ValueError("Workspace directory cannot be a symlink.")

        if not path.is_dir():
            raise ValueError("Workspace directory does not exist.")


def verify_open_directory_identity(
    directory_fd: int,
    expected_path: Path,
) -> None:
    """Check that an opened directory matches its expected path."""
    import os
    import stat

    opened = os.fstat(directory_fd)
    current = os.stat(expected_path, follow_symlinks=False)

    if not stat.S_ISDIR(opened.st_mode):
        raise ValueError("Opened descriptor is not a directory.")

    if not stat.S_ISDIR(current.st_mode):
        raise ValueError("Expected path is not a directory.")

    if (
        opened.st_dev != current.st_dev
        or opened.st_ino != current.st_ino
    ):
        raise ValueError("Workspace directory identity changed.")


class TemporaryFileIdentityError(OSError):
    """A temporary filename no longer identifies the created file."""


def cleanup_partial_staged_file(
    directory_fd: int,
    filename: str,
    created_fd: int,
) -> bool:
    """Remove a partial file only when its identity still matches.

    Returns True if removed, False if missing or replaced.
    This check is not atomic with unlink.
    """
    import os

    created = os.fstat(created_fd)

    try:
        current = os.stat(
            filename,
            dir_fd=directory_fd,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return False

    if (
        created.st_dev != current.st_dev
        or created.st_ino != current.st_ino
    ):
        raise TemporaryFileIdentityError(
            "Temporary-file identity changed during cleanup."
        )

    os.unlink(filename, dir_fd=directory_fd)
    return True

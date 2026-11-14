"""Controlled ingestion of browser-uploaded files into audit workspaces."""

import csv
import io
import os
import re
import stat
import zipfile
from uuid import uuid4
from pathlib import Path

from services.workspace import (
    AuditWorkspace,
    PublishedFileCleanupError,
    validate_workspace_identity,
    verify_open_directory_identity,
    verify_private_workspace_directory,
)


MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ALLOWED_EXTENSIONS = frozenset({".csv", ".xlsx", ".xls"})

_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]*$")


def _validate_filename(filename: str) -> str:
    """Reject unsafe or unsupported browser-supplied filenames."""

    if not isinstance(filename, str):
        raise ValueError("Upload filename must be a string.")

    if (
        not filename
        or filename in {".", ".."}
        or len(filename) > 255
        or not _SAFE_FILENAME.fullmatch(filename)
    ):
        raise ValueError("Upload filename is invalid.")

    if "/" in filename or "\\" in filename:
        raise ValueError("Upload filename cannot contain paths.")

    if Path(filename).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported upload file extension.")

    return filename



def _validate_file_content(filename: str, content: bytes) -> None:
    """Perform preliminary format checks before storing an upload."""

    extension = Path(filename).suffix.lower()

    if extension == ".csv":
        try:
            decoded = content.decode("utf-8-sig")

            if "\\x00" in decoded:
                raise ValueError("Invalid CSV: NUL character detected.")

            rows = csv.reader(io.StringIO(decoded, newline=""))
            first_row = next(rows, None)

            if not first_row or not any(cell.strip() for cell in first_row):
                raise ValueError("Invalid CSV: missing header row.")

            for _ in rows:
                pass

        except (UnicodeError, csv.Error) as exc:
            raise ValueError("Invalid CSV content.") from exc

    elif extension == ".xlsx":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = set(archive.namelist())

                if not {
                    "[Content_Types].xml",
                    "xl/workbook.xml",
                }.issubset(names):
                    raise ValueError("Invalid XLSX workbook structure.")

                if archive.testzip() is not None:
                    raise ValueError("Invalid XLSX archive content.")

        except (zipfile.BadZipFile, OSError, EOFError) as exc:
            raise ValueError("Invalid XLSX content.") from exc

    elif extension == ".xls":
        signature = bytes.fromhex("D0 CF 11 E0 A1 B1 1A E1")

        if not content.startswith(signature):
            raise ValueError("Invalid XLS file signature.")


def ingest_uploaded_file(
    *,
    workspace: AuditWorkspace,
    filename: str,
    content: bytes,
) -> Path:
    """Validate and publish uploaded bytes into the original workspace."""

    validate_workspace_identity(workspace)

    safe_filename = _validate_filename(filename)

    if not isinstance(content, bytes):
        raise TypeError("Uploaded content must be bytes.")

    if not content:
        raise ValueError("Uploaded file cannot be empty.")

    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("Uploaded file exceeds the 25 MiB limit.")

    _validate_file_content(safe_filename, content)

    if workspace.inputs_identity is None:
        raise ValueError("Workspace inputs identity is not recorded.")

    required_flags = ("O_DIRECTORY", "O_NOFOLLOW", "O_EXCL")

    if not all(hasattr(os, name) for name in required_flags):
        raise RuntimeError("Secure filesystem operations are unsupported.")

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

                info = os.fstat(inputs_fd)

                if (info.st_dev, info.st_ino) != workspace.inputs_identity:
                    raise ValueError(
                        "Original workspace inputs directory identity changed."
                    )

                if os.link not in os.supports_dir_fd:
                    raise RuntimeError(
                        "Atomic upload publication is unsupported."
                    )

                temporary_name = ".upload_" + uuid4().hex
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW

                file_fd = os.open(
                    temporary_name,
                    flags,
                    0o600,
                    dir_fd=inputs_fd,
                )

                published = False

                try:
                    with os.fdopen(file_fd, "wb", closefd=False) as output:
                        if not stat.S_ISREG(os.fstat(file_fd).st_mode):
                            raise ValueError(
                                "Upload destination is not a regular file."
                            )

                        output.write(content)
                        output.flush()
                        os.fsync(file_fd)

                    verify_open_directory_identity(
                        inputs_fd,
                        workspace.inputs_dir,
                    )
                    verify_private_workspace_directory(inputs_fd)

                    current = os.fstat(inputs_fd)

                    if (
                        current.st_dev,
                        current.st_ino,
                    ) != workspace.inputs_identity:
                        raise ValueError(
                            "Original workspace inputs directory identity changed."
                        )

                    try:
                        os.link(
                            temporary_name,
                            safe_filename,
                            src_dir_fd=inputs_fd,
                            dst_dir_fd=inputs_fd,
                            follow_symlinks=False,
                        )
                    except FileExistsError as exc:
                        raise FileExistsError(
                            "Uploaded filename already exists."
                        ) from exc

                    published = True

                finally:
                    import sys

                    original_error = sys.exc_info()[1]

                    try:
                        os.unlink(
                            temporary_name,
                            dir_fd=inputs_fd,
                        )
                    except Exception as cleanup_error:
                        if original_error is not None:
                            original_error.add_note(
                                "Temporary upload cleanup also failed: "
                                f"{cleanup_error!r}"
                            )
                        elif published:
                            raise PublishedFileCleanupError(
                                workspace.inputs_dir / safe_filename,
                                cleanup_error,
                            ) from cleanup_error
                        else:
                            raise
                    finally:
                        os.close(file_fd)

            finally:
                os.close(inputs_fd)

        finally:
            os.close(root_fd)

    finally:
        os.close(base_fd)

    return workspace.inputs_dir / safe_filename

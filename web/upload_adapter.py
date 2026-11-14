"""Browser-independent adapter for staging freight audit uploads."""

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from services.upload_ingestion import ingest_uploaded_file
from services.workspace import AuditWorkspace, create_audit_workspace


@dataclass(frozen=True)
class UploadPayload:
    filename: str
    content: bytes


@dataclass(frozen=True)
class StagedAudit:
    workspace: AuditWorkspace
    files: dict[str, Path]


def stage_browser_uploads(
    *,
    workspace_base: Path,
    uploads: Mapping[str, UploadPayload | None],
) -> StagedAudit:
    """Create an isolated workspace and stage submitted files."""

    invoice = uploads.get("invoice")

    if invoice is None:
        raise ValueError("A carrier invoice is required.")

    workspace = create_audit_workspace(workspace_base)
    staged_files: dict[str, Path] = {}

    # Retain incomplete workspaces on failure.
    # Automatic deletion is disabled until a separately
    # controlled cleanup policy is implemented.
    for label, uploaded in uploads.items():
        if uploaded is None:
            continue

        staged_files[label] = ingest_uploaded_file(
            workspace=workspace,
            filename=uploaded.filename,
            content=uploaded.content,
        )

    return StagedAudit(
        workspace=workspace,
        files=staged_files,
    )

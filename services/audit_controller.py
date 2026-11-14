"""Application controller for audits using an existing workspace."""

from pathlib import Path

from services.audit_service import AuditRequest, AuditResult, run_audit
from services.workspace import AuditWorkspace, validate_workspace_identity


def _require_staged_file(
    workspace: AuditWorkspace,
    path: Path | None,
    label: str,
) -> Path | None:
    """Require an input to be an existing file inside workspace inputs."""

    if path is None:
        return None

    if not isinstance(path, Path):
        raise TypeError(f"{label} must be a Path.")

    if path.is_symlink():
        raise ValueError(f"{label} cannot be a symlink.")

    if path.parent != workspace.inputs_dir:
        raise ValueError(f"{label} must be staged in workspace inputs.")

    if not path.is_file():
        raise ValueError(f"{label} file does not exist.")

    return path


def execute_workspace_audit(
    *,
    workspace: AuditWorkspace,
    invoice_file: Path,
    config_dir: Path,
    carrier: str | None = None,
    sheet: str | None = None,
    header_row: int | None = None,
    rates: Path | None = None,
    contract_rates: Path | None = None,
    delivery_evidence: Path | None = None,
    surcharge_evidence: Path | None = None,
    tax_evidence: Path | None = None,
    weight_tolerance: float | None = None,
    package_count_verified: bool = False,
    allow_total_fallback: bool = False,
) -> AuditResult:
    """Run an audit using files already staged in an isolated workspace."""

    validate_workspace_identity(workspace)

    if not isinstance(config_dir, Path) or not config_dir.is_dir():
        raise ValueError("Configuration directory is invalid.")

    request = AuditRequest(
        invoice_file=_require_staged_file(
            workspace, invoice_file, "Invoice"
        ),
        output=workspace.report_path,
        log_dir=workspace.logs_dir,
        config_dir=config_dir,
        carrier=carrier,
        sheet=sheet,
        header_row=header_row,
        rates=_require_staged_file(workspace, rates, "Rate card"),
        contract_rates=_require_staged_file(
            workspace, contract_rates, "Contract rates"
        ),
        delivery_evidence=_require_staged_file(
            workspace, delivery_evidence, "Delivery evidence"
        ),
        surcharge_evidence=_require_staged_file(
            workspace, surcharge_evidence, "Surcharge evidence"
        ),
        tax_evidence=_require_staged_file(
            workspace, tax_evidence, "Tax evidence"
        ),
        weight_tolerance=weight_tolerance,
        package_count_verified=package_count_verified,
        allow_total_fallback=allow_total_fallback,
    )

    return run_audit(request)

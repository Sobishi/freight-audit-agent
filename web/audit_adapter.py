"""Connect staged browser uploads to the freight audit controller."""

from pathlib import Path

from services.audit_controller import execute_workspace_audit
from services.audit_service import AuditResult
from web.upload_adapter import StagedAudit


def execute_staged_audit(
    *,
    staged: StagedAudit,
    config_dir: Path,
    carrier: str,
) -> AuditResult:
    """Execute an audit using files staged by the browser adapter."""

    invoice = staged.files.get("invoice")

    if invoice is None:
        raise ValueError("A staged carrier invoice is required.")

    if not carrier:
        raise ValueError("A carrier must be selected.")

    try:
        return execute_workspace_audit(
            workspace=staged.workspace,
            invoice_file=invoice,
            config_dir=config_dir,
            carrier=carrier,
            auto_detect_layout=True,
            rates=staged.files.get("rates"),
            contract_rates=staged.files.get("contract_rates"),
            delivery_evidence=staged.files.get("delivery_evidence"),
            surcharge_evidence=staged.files.get("surcharge_evidence"),
            tax_evidence=staged.files.get("tax_evidence"),
        )
    except SystemExit as exc:
        raise RuntimeError(
            "Freight audit could not complete. "
            "Check the invoice format and carrier selection."
        ) from exc

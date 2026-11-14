"""Validated service contract for controlled freight audit execution."""

from dataclasses import dataclass
from pathlib import Path
import math
import re


SUPPORTED_DATA_FORMATS = frozenset({".csv", ".xlsx", ".xls"})
SUPPORTED_DELIVERY_FORMATS = frozenset({".xlsx", ".xls"})


@dataclass(frozen=True)
class AuditRequest:
    invoice_file: Path
    output: Path
    log_dir: Path
    config_dir: Path
    carrier: str | None = None
    sheet: str | None = None
    header_row: int | None = None
    rates: Path | None = None
    contract_rates: Path | None = None
    delivery_evidence: Path | None = None
    surcharge_evidence: Path | None = None
    tax_evidence: Path | None = None
    weight_tolerance: float | None = None
    package_count_verified: bool = False
    allow_total_fallback: bool = False


def _validate_file(path, label, allowed_formats):
    if path is None:
        return

    if not isinstance(path, Path):
        raise ValueError(f"{label} must be a Path object.")

    if path.suffix.lower() not in allowed_formats:
        raise ValueError(f"Unsupported {label} format.")

    if not path.is_file():
        raise ValueError(f"{label} file not found.")


def validate_audit_request(request: AuditRequest) -> None:
    """Validate an audit request without running the engine."""

    if not isinstance(request, AuditRequest):
        raise TypeError("Expected an AuditRequest.")

    if request.invoice_file is None:
        raise ValueError("Invoice file is required.")

    _validate_file(
        request.invoice_file,
        "invoice",
        SUPPORTED_DATA_FORMATS,
    )

    for label, path in (
        ("rate card", request.rates),
        ("contract rate card", request.contract_rates),
        ("surcharge evidence", request.surcharge_evidence),
        ("tax evidence", request.tax_evidence),
    ):
        _validate_file(path, label, SUPPORTED_DATA_FORMATS)

    _validate_file(
        request.delivery_evidence,
        "delivery evidence",
        SUPPORTED_DELIVERY_FORMATS,
    )

    if request.carrier is not None:
        if not isinstance(request.carrier, str) or not re.fullmatch(
            r"[a-z0-9_]+", request.carrier
        ):
            raise ValueError("Invalid carrier identifier.")

    if request.header_row is not None:
        if type(request.header_row) is not int or request.header_row < 0:
            raise ValueError("Header row must be a nonnegative integer.")

    if request.weight_tolerance is not None:
        if (
            isinstance(request.weight_tolerance, bool)
            or not isinstance(request.weight_tolerance, (int, float))
            or not math.isfinite(request.weight_tolerance)
            or request.weight_tolerance < 0
        ):
            raise ValueError(
                "Weight tolerance must be finite and nonnegative."
            )

        if not request.carrier:
            raise ValueError("Weight validation requires a carrier.")

        if not request.package_count_verified:
            raise ValueError(
                "Weight validation requires verified package counts."
            )

    elif request.package_count_verified:
        raise ValueError(
            "Package-count verification requires weight validation."
        )

    if request.contract_rates is not None:
        if request.weight_tolerance is None:
            raise ValueError(
                "Contract pricing requires weight validation."
            )

    if not isinstance(request.output, Path):
        raise ValueError("Output must be a Path object.")

    if request.output.suffix.lower() != ".xlsx":
        raise ValueError("Audit report must be an .xlsx file.")

    if request.output.exists():
        raise ValueError("Audit report output already exists.")

    for label, path in (
        ("log directory", request.log_dir),
        ("configuration directory", request.config_dir),
    ):
        if not isinstance(path, Path):
            raise ValueError(f"{label} must be a Path object.")


@dataclass(frozen=True)
class AuditResult:
    """Result of one controlled audit execution."""

    run_id: str
    status: str
    report_path: Path | None
    log_path: Path
    summary: dict


def run_audit(request: AuditRequest) -> AuditResult:
    """Execute an already-staged audit using the existing engine.

    This is a local service boundary, not a public upload endpoint.
    Callers must stage files in a trusted, isolated workspace.
    """
    from types import SimpleNamespace

    from audit_engine.run_log import AuditRun
    from main import _execute_audit

    validate_audit_request(request)

    args = SimpleNamespace(
        invoice_file=str(request.invoice_file),
        output=str(request.output),
        log_dir=str(request.log_dir),
        config_dir=str(request.config_dir),
        carrier=request.carrier,
        sheet=request.sheet,
        header_row=request.header_row,
        rates=str(request.rates) if request.rates else None,
        contract_rates=(
            str(request.contract_rates)
            if request.contract_rates else None
        ),
        delivery_evidence=(
            str(request.delivery_evidence)
            if request.delivery_evidence else None
        ),
        surcharge_evidence=(
            str(request.surcharge_evidence)
            if request.surcharge_evidence else None
        ),
        tax_evidence=(
            str(request.tax_evidence)
            if request.tax_evidence else None
        ),
        weight_tolerance=request.weight_tolerance,
        package_count_verified=request.package_count_verified,
        allow_total_fallback=request.allow_total_fallback,
    )

    settings = {
        "carrier_id": request.carrier,
        "sheet": request.sheet,
        "header_row": request.header_row,
        "allow_total_fallback": request.allow_total_fallback,
        "weight_validation_enabled": request.weight_tolerance is not None,
        "weight_tolerance_kg": request.weight_tolerance,
        "package_count_verified": request.package_count_verified,
        "tax_validation_enabled": request.tax_evidence is not None,
        "surcharge_validation_enabled": (
            request.surcharge_evidence is not None
        ),
    }

    run = AuditRun(request.log_dir, settings=settings)

    with run:
        run.stage = "input_snapshot"
        run.add_input("invoice", request.invoice_file)

        for role, path in (
            ("rate_card", request.rates),
            ("contract_rate_card", request.contract_rates),
            ("delivery_evidence", request.delivery_evidence),
            ("tax_evidence", request.tax_evidence),
            ("surcharge_evidence", request.surcharge_evidence),
        ):
            if path is not None:
                run.add_input(role, path)

        if request.carrier:
            root = request.config_dir
            run.add_input(
                "carrier_profile",
                root / "carriers" / f"{request.carrier}.yaml",
            )
            run.add_input(
                "invoice_mapping",
                root / "mappings" / f"{request.carrier}_invoice.yaml",
            )

        _execute_audit(args, run)

        _verify_audit_report(run, request.output)

    if run.data["status"] != "succeeded":
        raise RuntimeError("Audit did not complete successfully.")

    return AuditResult(
        run_id=run.run_id,
        status=run.data["status"],
        report_path=request.output,
        log_path=run.path,
        summary=dict(run.data["summary"]),
    )


def _verify_audit_report(run, report_path: Path) -> None:
    """Verify report existence, registration, hash and Excel structure."""
    import hashlib
    from zipfile import BadZipFile
    from openpyxl import load_workbook

    run.stage = "report_verification"

    if not report_path.is_file():
        raise RuntimeError(
            "Audit completed without an Excel report."
        )

    registrations = [
        entry
        for entry in run.data["outputs"]
        if entry.get("role") == "excel_report"
    ]

    if len(registrations) != 1:
        raise RuntimeError(
            "Audit report registration is missing or ambiguous."
        )

    registration = registrations[0]

    if registration.get("name") != report_path.name:
        raise RuntimeError(
            "Audit report registration does not match the output."
        )

    digest = hashlib.sha256()

    with report_path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    if digest.hexdigest() != registration.get("sha256"):
        raise RuntimeError(
            "Audit report integrity verification failed."
        )

    try:
        workbook = load_workbook(
            report_path,
            read_only=True,
            data_only=True,
        )
        try:
            if not workbook.sheetnames:
                raise ValueError("Workbook has no worksheets.")
        finally:
            workbook.close()
    except (OSError, ValueError, KeyError, ImportError, BadZipFile) as exc:
        raise RuntimeError(
            "Audit produced an invalid Excel workbook."
        ) from exc

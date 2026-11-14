"""Tests for the W1 audit service request contract."""

from dataclasses import replace
from pathlib import Path

import pytest

from services.audit_service import (
    AuditRequest,
    validate_audit_request,
)


@pytest.fixture
def valid_request(tmp_path):
    invoice = tmp_path / "invoice.csv"
    invoice.write_text("AWB,Total\nA001,100\n", encoding="utf-8")

    return AuditRequest(
        invoice_file=invoice,
        output=tmp_path / "report.xlsx",
        log_dir=tmp_path / "logs",
        config_dir=tmp_path / "config",
    )


def test_valid_request_is_accepted(valid_request):
    assert validate_audit_request(valid_request) is None


def test_missing_invoice_is_rejected(valid_request):
    request = replace(
        valid_request,
        invoice_file=valid_request.invoice_file.parent / "missing.csv",
    )

    with pytest.raises(ValueError, match="invoice file not found"):
        validate_audit_request(request)


def test_unsupported_invoice_format_is_rejected(valid_request):
    invoice = valid_request.invoice_file.parent / "invoice.txt"
    invoice.write_text("test", encoding="utf-8")

    request = replace(valid_request, invoice_file=invoice)

    with pytest.raises(ValueError, match="Unsupported invoice format"):
        validate_audit_request(request)


def test_invalid_carrier_identifier_is_rejected(valid_request):
    request = replace(valid_request, carrier="../other")

    with pytest.raises(ValueError, match="Invalid carrier identifier"):
        validate_audit_request(request)


@pytest.mark.parametrize("tolerance", [-1, float("nan"), float("inf"), True])
def test_invalid_weight_tolerance_is_rejected(valid_request, tolerance):
    request = replace(
        valid_request,
        carrier="swiftline",
        package_count_verified=True,
        weight_tolerance=tolerance,
    )

    with pytest.raises(ValueError, match="Weight tolerance"):
        validate_audit_request(request)


def test_weight_validation_requires_carrier(valid_request):
    request = replace(
        valid_request,
        weight_tolerance=0.5,
        package_count_verified=True,
    )

    with pytest.raises(ValueError, match="requires a carrier"):
        validate_audit_request(request)


def test_weight_validation_requires_verified_packages(valid_request):
    request = replace(
        valid_request,
        carrier="swiftline",
        weight_tolerance=0.5,
    )

    with pytest.raises(ValueError, match="verified package counts"):
        validate_audit_request(request)


def test_package_verification_requires_weight_validation(valid_request):
    request = replace(
        valid_request,
        package_count_verified=True,
    )

    with pytest.raises(ValueError, match="requires weight validation"):
        validate_audit_request(request)


def test_contract_pricing_requires_weight_validation(valid_request):
    rate_card = valid_request.invoice_file.parent / "contract.csv"
    rate_card.write_text("Carrier,Rate\nSwiftline,100\n", encoding="utf-8")

    request = replace(valid_request, contract_rates=rate_card)

    with pytest.raises(ValueError, match="requires weight validation"):
        validate_audit_request(request)


def test_delivery_evidence_must_be_excel(valid_request):
    evidence = valid_request.invoice_file.parent / "delivery.csv"
    evidence.write_text("AWB,Status\nA001,Delivered\n", encoding="utf-8")

    request = replace(valid_request, delivery_evidence=evidence)

    with pytest.raises(ValueError, match="Unsupported delivery evidence format"):
        validate_audit_request(request)


def test_report_must_be_xlsx(valid_request):
    request = replace(
        valid_request,
        output=valid_request.output.with_suffix(".csv"),
    )

    with pytest.raises(ValueError, match="must be an .xlsx"):
        validate_audit_request(request)


def test_negative_header_row_is_rejected(valid_request):
    request = replace(valid_request, header_row=-1)

    with pytest.raises(ValueError, match="Header row"):
        validate_audit_request(request)


def test_valid_weight_configuration_is_accepted(valid_request):
    request = replace(
        valid_request,
        carrier="swiftline",
        weight_tolerance=0.5,
        package_count_verified=True,
    )

    assert validate_audit_request(request) is None


def test_request_must_be_audit_request():
    with pytest.raises(TypeError, match="Expected an AuditRequest"):
        validate_audit_request(object())


def test_invoice_is_required(valid_request):
    request = replace(valid_request, invoice_file=None)

    with pytest.raises(ValueError, match="Invoice file is required"):
        validate_audit_request(request)


def test_existing_report_is_rejected(valid_request):
    valid_request.output.write_text("existing report", encoding="utf-8")

    with pytest.raises(ValueError, match="output already exists"):
        validate_audit_request(valid_request)


def test_missing_optional_evidence_is_allowed(valid_request):
    assert valid_request.rates is None
    assert valid_request.delivery_evidence is None
    assert valid_request.tax_evidence is None

    assert validate_audit_request(valid_request) is None

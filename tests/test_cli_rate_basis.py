import pytest

import main as freight_main


INVOICE_WITHOUT_FREIGHT = (
    "Tracking Number,Courier,Invoice Number,Invoice Amount,Service Type\n"
    "ABC123,DHL,INV001,13500,Express\n"
)

INVOICE_WITH_FREIGHT = (
    "Tracking Number,Courier,Invoice Number,Invoice Amount,"
    "Service Type,Base Freight\n"
    "ABC123,DHL,INV001,13500,Express,12000\n"
)

RATES = (
    "Carrier,Service Type,Agreed Rate\n"
    "DHL,Express,12000\n"
)


def _run(monkeypatch, tmp_path, invoice_text, *extra_args):
    invoice = tmp_path / "invoice.csv"
    rates = tmp_path / "rates.csv"
    invoice.write_text(invoice_text)
    rates.write_text(RATES)

    monkeypatch.setattr(
        "sys.argv",
        ["main.py", str(invoice), "--rates", str(rates), *extra_args],
    )

    freight_main.main()


def test_cli_rejects_invoice_without_base_freight(
    monkeypatch, tmp_path, capsys
):
    with pytest.raises(SystemExit) as exit_info:
        _run(monkeypatch, tmp_path, INVOICE_WITHOUT_FREIGHT)

    message = str(exit_info.value)

    assert "Base Freight" in message
    assert "--allow-total-fallback" in message


def test_cli_accepts_invoice_with_base_freight(
    monkeypatch, tmp_path, capsys
):
    _run(monkeypatch, tmp_path, INVOICE_WITH_FREIGHT)

    output = capsys.readouterr().out

    assert "Rate Matched" in output
    assert "Potential Overcharge" not in output


def test_cli_total_fallback_flag_allows_old_behaviour(
    monkeypatch, tmp_path, capsys
):
    with pytest.warns(UserWarning, match="Base Freight"):
        _run(
            monkeypatch,
            tmp_path,
            INVOICE_WITHOUT_FREIGHT,
            "--allow-total-fallback",
        )

    output = capsys.readouterr().out

    assert "Potential Overcharge" in output

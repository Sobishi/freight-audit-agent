import shutil
from pathlib import Path

import pytest

import main as freight_main

FIXTURES = Path(__file__).parent / "fixtures" / "carriers"
PROJECT_ROOT = Path(__file__).resolve().parent.parent

SWIFTLINE_RATES = (
    "Carrier,Service Type,Agreed Rate\n"
    "Swiftline,Priority,1250\n"
    "Swiftline,Standard,200\n"
)


def _run(monkeypatch, tmp_path, *args, invoice="swiftline_invoice.csv"):
    monkeypatch.setattr(
        "sys.argv",
        ["main.py", str(FIXTURES / invoice), *args],
    )
    freight_main.main()


def _rates(tmp_path, text=SWIFTLINE_RATES):
    path = tmp_path / "rates.csv"
    path.write_text(text)
    return str(path)


def test_carrier_option_loads_the_invoice_through_its_mapping(monkeypatch, tmp_path, capsys):
    _run(monkeypatch, tmp_path, "--carrier", "swiftline", "--rates", _rates(tmp_path))

    output = capsys.readouterr().out

    assert "Swiftline (swiftline)" in output
    assert "SFL7000000001" in output
    assert "Rate Matched" in output


def test_overcharge_is_reported_for_the_mapped_invoice(monkeypatch, tmp_path, capsys):
    _run(monkeypatch, tmp_path, "--carrier", "swiftline", "--rates", _rates(tmp_path))

    output = capsys.readouterr().out

    # Standard line billed 210.00 against an agreed 200.00.
    assert "Potential Overcharge" in output
    assert "Total Potential Rate Overcharge: 10.00" in output


def test_profile_tolerance_is_applied(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / "config"
    shutil.copytree(PROJECT_ROOT / "config", config_dir)

    profile = config_dir / "carriers" / "swiftline.yaml"
    profile.write_text(profile.read_text().replace("tolerance: 0.01", "tolerance: 15"))

    _run(
        monkeypatch, tmp_path,
        "--carrier", "swiftline",
        "--config-dir", str(config_dir),
        "--rates", _rates(tmp_path),
    )

    output = capsys.readouterr().out

    assert "Potential Overcharge" not in output
    assert "Total Potential Rate Overcharge: 0.00" in output


def test_excel_report_can_be_written_for_a_mapped_invoice(monkeypatch, tmp_path, capsys):
    report = tmp_path / "report.xlsx"

    _run(
        monkeypatch, tmp_path,
        "--carrier", "corvant",
        "--rates", _rates(tmp_path, "Carrier,Service Type,Agreed Rate\nCorvant,Express,24.10\n"),
        "--output", str(report),
        invoice="corvant_invoice.csv",
    )

    assert report.exists()
    assert report.stat().st_size > 0


def test_unknown_carrier_gives_a_clear_message(monkeypatch, tmp_path):
    with pytest.raises(SystemExit) as exit_info:
        _run(monkeypatch, tmp_path, "--carrier", "nobody")

    message = str(exit_info.value)

    assert "nobody" in message
    assert "swiftline" in message


def test_wrong_carrier_for_the_file_gives_a_clear_message(monkeypatch, tmp_path):
    with pytest.raises(SystemExit) as exit_info:
        _run(monkeypatch, tmp_path, "--carrier", "corvant")

    assert "Error" in str(exit_info.value)


def test_without_carrier_option_the_old_loader_is_still_used(monkeypatch, tmp_path, capsys):
    invoice = tmp_path / "invoice.csv"
    invoice.write_text(
        "Tracking Number,Courier,Invoice Number,Invoice Amount,Service Type\n"
        "ABC123,DHL,INV001,100,Express\n"
    )
    monkeypatch.setattr("sys.argv", ["main.py", str(invoice)])

    freight_main.main()

    output = capsys.readouterr().out

    assert "Total Invoice Lines: 1" in output
    assert "Carrier profile" not in output

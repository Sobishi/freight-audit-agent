"""Tests for browser-independent upload staging."""

import pytest

from web.upload_adapter import UploadPayload, stage_browser_uploads


def csv_upload(name="invoice.csv"):
    return UploadPayload(
        filename=name,
        content=b"invoice_id,amount\nINV001,100\n",
    )


def test_invoice_is_staged_in_private_workspace(tmp_path):
    result = stage_browser_uploads(
        workspace_base=tmp_path,
        uploads={"invoice": csv_upload()},
    )

    invoice = result.files["invoice"]

    assert invoice.is_file()
    assert invoice.read_bytes() == csv_upload().content
    assert invoice.parent == result.workspace.inputs_dir
    assert invoice.stat().st_mode & 0o777 == 0o600
    assert result.workspace.root.stat().st_mode & 0o777 == 0o700


def test_each_submission_creates_unique_workspace(tmp_path):
    first = stage_browser_uploads(
        workspace_base=tmp_path,
        uploads={"invoice": csv_upload()},
    )

    second = stage_browser_uploads(
        workspace_base=tmp_path,
        uploads={"invoice": csv_upload()},
    )

    assert first.workspace.workspace_id != second.workspace.workspace_id
    assert first.files["invoice"] != second.files["invoice"]


def test_missing_invoice_is_rejected_without_workspace(tmp_path):
    with pytest.raises(ValueError, match="invoice is required"):
        stage_browser_uploads(
            workspace_base=tmp_path,
            uploads={"invoice": None},
        )

    assert list(tmp_path.iterdir()) == []


def test_optional_supporting_file_is_staged(tmp_path):
    result = stage_browser_uploads(
        workspace_base=tmp_path,
        uploads={
            "invoice": csv_upload(),
            "rates": csv_upload("rates.csv"),
        },
    )

    assert set(result.files) == {"invoice", "rates"}
    assert result.files["rates"].is_file()


def test_duplicate_filenames_are_rejected(tmp_path):
    with pytest.raises(FileExistsError):
        stage_browser_uploads(
            workspace_base=tmp_path,
            uploads={
                "invoice": csv_upload("same.csv"),
                "rates": csv_upload("same.csv"),
            },
        )


def test_invalid_upload_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        stage_browser_uploads(
            workspace_base=tmp_path,
            uploads={
                "invoice": UploadPayload(
                    filename="invoice.csv",
                    content=b"",
                ),
            },
        )


def test_failed_supporting_upload_retains_workspace(tmp_path):
    """Failed submissions retain valid files for controlled cleanup."""

    invoice = csv_upload("invoice.csv")

    with pytest.raises(ValueError):
        stage_browser_uploads(
            workspace_base=tmp_path,
            uploads={
                "invoice": invoice,
                "rates": UploadPayload(
                    filename="invalid.csv",
                    content=b"",
                ),
            },
        )

    workspaces = list(tmp_path.iterdir())

    assert len(workspaces) == 1

    inputs = workspaces[0] / "inputs"

    assert inputs.is_dir()
    assert (inputs / "invoice.csv").read_bytes() == invoice.content
    assert not (inputs / "invalid.csv").exists()

def test_failed_upload_preserves_existing_staged_invoice(tmp_path):
    """Failed uploads must not silently delete staged invoice data."""

    from web.upload_adapter import UploadPayload, stage_browser_uploads

    with pytest.raises(ValueError):
        stage_browser_uploads(
            workspace_base=tmp_path,
            uploads={
                "invoice": csv_upload("invoice.csv"),
                "rates": UploadPayload(
                    filename="invalid.csv",
                    content=b"",
                ),
            },
        )

    workspaces = list(tmp_path.iterdir())

    assert len(workspaces) == 1

    staged_invoice = workspaces[0] / "inputs" / "invoice.csv"

    assert staged_invoice.is_file()
    assert staged_invoice.read_bytes() == csv_upload().content

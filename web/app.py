"""Local Streamlit interface for the Freight Audit Agent."""

from pathlib import Path

import streamlit as st
import yaml

from web.audit_adapter import execute_staged_audit
from web.upload_adapter import (
    UploadPayload,
    stage_browser_uploads,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
CARRIER_DIR = CONFIG_DIR / "carriers"

st.set_page_config(
    page_title="Freight Audit Agent",
    page_icon="📦",
    layout="wide",
)


def discover_carriers() -> dict[str, str]:
    """Discover configured carriers with matching invoice mappings."""
    carriers = {}

    for path in sorted(CARRIER_DIR.glob("*.yaml")):
        mapping = CONFIG_DIR / "mappings" / f"{path.stem}_invoice.yaml"

        if not mapping.is_file():
            continue

        with path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle)

        if not isinstance(data, dict):
            continue

        carrier_id = data.get("carrier_id")
        carrier_name = data.get("carrier_name")

        if carrier_id == path.stem and isinstance(carrier_name, str):
            carriers[carrier_id] = carrier_name

    return carriers


st.title("Freight Audit Agent")
st.caption("Controlled local audit interface | W1 Pilot")

st.write(
    "Upload a carrier invoice, select its configuration, "
    "and run a freight audit."
)

carriers = discover_carriers()

if not carriers:
    st.error("No valid carrier configurations were found.")
    st.stop()

st.subheader("1. Carrier configuration")

carrier = st.selectbox(
    "Select carrier",
    options=list(carriers),
    format_func=lambda value: carriers[value],
)

st.subheader("2. Upload files")

invoice = st.file_uploader(
    "Carrier invoice (required)",
    type=["csv", "xlsx", "xls"],
)

with st.expander("Optional supporting files"):
    rates = st.file_uploader(
        "Rate card",
        type=["csv", "xlsx", "xls"],
    )

    contract_rates = st.file_uploader(
        "Contract rates",
        type=["csv", "xlsx", "xls"],
    )

    delivery_evidence = st.file_uploader(
        "Delivery evidence",
        type=["csv", "xlsx", "xls"],
    )

    surcharge_evidence = st.file_uploader(
        "Surcharge evidence",
        type=["csv", "xlsx", "xls"],
    )

    tax_evidence = st.file_uploader(
        "Tax evidence",
        type=["csv", "xlsx", "xls"],
    )

st.subheader("3. Audit execution")

if invoice is None:
    st.info("Upload a carrier invoice to continue.")

run_clicked = st.button(
    "Run freight audit",
    type="primary",
    disabled=invoice is None,
)

if run_clicked:
    uploads = {
        "invoice": invoice,
        "rates": rates,
        "contract_rates": contract_rates,
        "delivery_evidence": delivery_evidence,
        "surcharge_evidence": surcharge_evidence,
        "tax_evidence": tax_evidence,
    }

    try:
        workspace_base = (
            Path.home() / ".freight_audit_agent" / "workspaces"
        )

        payloads = {
            label: (
                UploadPayload(
                    filename=uploaded.name,
                    content=uploaded.getvalue(),
                )
                if uploaded is not None
                else None
            )
            for label, uploaded in uploads.items()
        }

        staged = stage_browser_uploads(
            workspace_base=workspace_base,
            uploads=payloads,
        )

        with st.spinner("Running freight audit..."):
            result = execute_staged_audit(
                staged=staged,
                config_dir=CONFIG_DIR,
                carrier=carrier,
            )

    except (ValueError, TypeError, OSError, RuntimeError) as exc:
        st.error(f"Freight audit failed: {exc}")
    else:
        st.write("Workspace ID:", staged.workspace.workspace_id)
        st.write("Selected carrier:", carriers[carrier])
        st.write("Audit run ID:", result.run_id)
        st.write("Audit status:", result.status)

        st.subheader("Audit summary")
        st.json(result.summary)

        if (
            result.status == "succeeded"
            and result.report_path is not None
            and result.report_path.is_file()
        ):
            st.success("Audit report generated successfully.")

            st.download_button(
                label="Download Excel Report",
                data=result.report_path.read_bytes(),
                file_name="audit_report.xlsx",
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                key=f"download_{result.run_id}",
            )
        else:
            st.warning("No downloadable audit report was returned.")

        st.caption(
            "Controlled local pilot. Audit results are not "
            "authorization to pay carrier invoices."
        )

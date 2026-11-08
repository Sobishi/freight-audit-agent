"""Align R6 TAX-01 contract evidence with audited invoice lines."""

from copy import deepcopy

import numpy as np
import pandas as pd


def _valid_line_id(value):
    """Accept positive integer IDs, excluding booleans and floats."""
    return (
        not isinstance(value, (bool, np.bool_))
        and isinstance(value, (int, np.integer))
        and value > 0
    )


def align_tax_evidence(
    invoice: pd.DataFrame,
    tax_contracts: dict,
) -> dict:
    """Validate tax evidence against invoice-generated line IDs.

    Partial or empty evidence is permitted. Missing tax contracts
    remain unresolved and are handled by the tax reporting engine.

    Evidence referencing nonexistent invoice lines is rejected.

    Neither input is modified. A deep copy of the contracts is
    returned to prevent downstream mutation of source evidence.
    """
    if not isinstance(invoice, pd.DataFrame):
        raise TypeError(
            "Invoice must be a pandas DataFrame."
        )

    if not isinstance(tax_contracts, dict):
        raise TypeError(
            "Tax contracts must be supplied as a dictionary."
        )

    if not invoice.columns.is_unique:
        raise ValueError(
            "Invoice contains duplicate column names."
        )

    if "Invoice Line ID" not in invoice.columns:
        raise ValueError(
            "Invoice requires an Invoice Line ID column."
        )

    line_ids = invoice["Invoice Line ID"]

    if line_ids.isna().any():
        raise ValueError(
            "Invoice contains missing Invoice Line ID values."
        )

    for line_id in line_ids:
        if not _valid_line_id(line_id):
            raise ValueError(
                "Invalid Invoice Line ID in invoice: "
                f"{line_id!r}. Expected a positive integer."
            )

    if line_ids.duplicated().any():
        raise ValueError(
            "Invoice contains duplicate Invoice Line ID values."
        )

    invoice_ids = set(line_ids.tolist())

    for evidence_id in tax_contracts:
        if not _valid_line_id(evidence_id):
            raise ValueError(
                "Invalid Invoice Line ID in tax evidence: "
                f"{evidence_id!r}."
            )

        if evidence_id not in invoice_ids:
            raise ValueError(
                "Tax evidence contains an unknown "
                f"Invoice Line ID: {evidence_id!r}."
            )

    return deepcopy(tax_contracts)

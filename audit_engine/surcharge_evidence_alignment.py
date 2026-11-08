"""Align R6 surcharge contract evidence with the audited invoice."""

from copy import deepcopy

import numpy as np
import pandas as pd


def _valid_line_id(value):
    """Accept positive Python or NumPy integers, excluding booleans."""
    return (
        not isinstance(value, (bool, np.bool_))
        and isinstance(value, (int, np.integer))
        and value > 0
    )


def align_surcharge_evidence(
    invoice: pd.DataFrame,
    surcharge_contracts: dict,
) -> dict:
    """
    Validate surcharge evidence against invoice-generated line IDs.

    Partial evidence is permitted. Missing contractual evidence is
    handled by the surcharge reporting engine.

    Evidence for invoice lines that do not exist is rejected.

    Neither input is modified.
    """
    if not isinstance(invoice, pd.DataFrame):
        raise TypeError("Invoice must be a pandas DataFrame.")

    if not isinstance(surcharge_contracts, dict):
        raise TypeError(
            "Surcharge contracts must be supplied as a dictionary."
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

    for evidence_id in surcharge_contracts:
        if not _valid_line_id(evidence_id):
            raise ValueError(
                "Invalid Invoice Line ID in surcharge evidence: "
                f"{evidence_id!r}."
            )

        if evidence_id not in invoice_ids:
            raise ValueError(
                "Surcharge evidence contains an unknown "
                f"Invoice Line ID: {evidence_id!r}."
            )

    return deepcopy(surcharge_contracts)

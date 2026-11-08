import pandas as pd


def calculate_combined_exposure(
    audited_invoice: pd.DataFrame,
    rate_results: pd.DataFrame,
) -> pd.DataFrame:
    """
    Calculate preliminary combined exposure per invoice line.

    For each line, use the larger of:
    - Potential duplicate billing exposure
    - Potential contractual rate overcharge

    This prevents simple double-counting when both
    audit rules flag the same invoice line.

    A line whose rate exposure cannot be calculated, for example when
    no contract rate exists, is marked "Unknown" and "Hold". Its numeric
    rate exposure stays at 0 only so totals can be summed. The numeric
    value must never be read as "no exposure" for these lines.
    """

    if len(audited_invoice) != len(rate_results):
        raise ValueError(
            "Invoice and rate validation results must have "
            "the same number of rows."
        )

    required_columns = {
        "Total",
        "Is Exact Duplicate Charge",
    }

    if not required_columns.issubset(audited_invoice.columns):
        raise ValueError(
            "Audited invoice is missing required exposure columns."
        )

    if "Potential Rate Overcharge" not in rate_results.columns:
        raise ValueError(
            "Rate results are missing Potential Rate Overcharge."
        )

    result = audited_invoice.copy().reset_index(drop=True)
    rates = rate_results.reset_index(drop=True)

    # Verify that rate results correspond to the correct invoice lines.
    # Match rate validation results using unique invoice-line IDs.
    id_column = "Invoice Line ID"

    if id_column not in result.columns or id_column not in rates.columns:
        raise ValueError(
            "Both datasets must contain Invoice Line ID."
        )

    if result[id_column].isna().any() or rates[id_column].isna().any():
        raise ValueError(
            "Invoice Line ID cannot contain missing values."
        )

    if result[id_column].duplicated().any() or rates[id_column].duplicated().any():
        raise ValueError(
            "Invoice Line ID must be unique within each dataset."
        )

    # Confirm both datasets contain exactly the same invoice lines.
    if set(result[id_column]) != set(rates[id_column]):
        raise ValueError(
            "Invoice Line IDs do not match between datasets."
        )

    # Reorder rate results to match the audited invoice.
    rates = (
        rates.set_index(id_column)
        .loc[result[id_column]]
        .reset_index()
    )

    result["Duplicate Exposure"] = (
        pd.to_numeric(result["Total"], errors="coerce")
        .clip(lower=0)
        .where(result["Is Exact Duplicate Charge"], 0)
    )

    rate_overcharge = pd.to_numeric(
        rates["Potential Rate Overcharge"],
        errors="coerce",
    )

    # A missing overcharge means it could not be calculated.
    unknown_rate_exposure = rate_overcharge.isna().to_numpy()

    result["Rate Exposure"] = (
        rate_overcharge
        .fillna(0)
        .clip(lower=0)
    )

    result["Rate Exposure Status"] = "Quantified"
    result.loc[unknown_rate_exposure, "Rate Exposure Status"] = "Unknown"

    result["Payment Treatment"] = "Proceed"
    result.loc[unknown_rate_exposure, "Payment Treatment"] = "Hold"

    result["Combined Potential Exposure"] = result[
        ["Duplicate Exposure", "Rate Exposure"]
    ].max(axis=1)

    result["Duplicate Exposure Status"] = "Quantified"
    if "Needs Charge Review" in result:
        uncertain_duplicate = (result["Needs Charge Review"] & ~result["Is Exact Duplicate Charge"])
        result.loc[uncertain_duplicate, "Duplicate Exposure Status"] = "Unknown"
        result.loc[uncertain_duplicate, "Payment Treatment"] = "Hold"
    if "Excluded From Exposure" in result:
        reversed_lines = result["Excluded From Exposure"].fillna(False).astype(bool)
        result.loc[reversed_lines, ["Duplicate Exposure", "Rate Exposure", "Combined Potential Exposure"]] = 0.0
        result.loc[reversed_lines, "Payment Treatment"] = "No Payment - Reversed"
    if "Charge Type" in result:
        amounts = pd.to_numeric(result["Total"], errors="coerce")
        credit_review = amounts.lt(0) & ~result["Excluded From Exposure"]
        result.loc[credit_review, "Payment Treatment"] = "Review Credit"
        result.loc[amounts.eq(0), "Payment Treatment"] = "No Payment - Zero"

    return result



def finalize_payment_decisions(
    audited_invoice: pd.DataFrame,
    *,
    combined_exposure: pd.DataFrame | None = None,
    tax_results: pd.DataFrame | None = None,
    surcharge_results: pd.DataFrame | None = None,
    weight_results: pd.DataFrame | None = None,
    contract_pricing_results: pd.DataFrame | None = None,
    delivery_evidence_results: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Consolidate invoice-line checks into conservative payment decisions."""
    from decimal import Decimal, InvalidOperation
    import numpy as np

    if not isinstance(audited_invoice, pd.DataFrame):
        raise TypeError("Audited invoice must be a DataFrame.")

    if not audited_invoice.columns.is_unique:
        raise ValueError("Duplicate invoice column names.")

    required = {"Invoice Line ID", "Total"}
    if not required.issubset(audited_invoice.columns):
        raise ValueError("Invoice Line ID and Total are required.")

    result = audited_invoice.copy(deep=True).reset_index(drop=True)
    ids = result["Invoice Line ID"]

    if ids.isna().any() or ids.duplicated().any():
        raise ValueError("Invoice Line ID must be unique and non-null.")

    generated = {
        "Final Payment Treatment", "Decision Completeness",
        "Decision Reason", "Tax Check", "Surcharge Check",
        "Weight Check", "Weight Comparison Check",
        "Delivery Check", "Contract Pricing Check",
        "Tax Exposure Status", "Surcharge Exposure Status",
        "Contract Pricing Exposure Status",
    }
    if generated.intersection(result.columns):
        raise ValueError("Invoice contains final decision columns.")

    def align(frame, label, columns):
        if frame is None:
            return None
        if not isinstance(frame, pd.DataFrame):
            raise TypeError(f"{label} must be a DataFrame.")
        if not frame.columns.is_unique:
            raise ValueError(f"{label} has duplicate columns.")
        missing = set(columns).difference(frame.columns)
        if missing:
            raise ValueError(
                f"{label} missing columns: {sorted(missing)}"
            )
        keys = frame["Invoice Line ID"]
        if keys.isna().any() or keys.duplicated().any():
            raise ValueError(
                f"{label} Invoice Line ID must be unique and non-null."
            )
        if len(frame) != len(result) or set(keys) != set(ids):
            raise ValueError(
                f"{label} Invoice Line ID values do not match."
            )
        return frame.set_index("Invoice Line ID").loc[
            ids.tolist()
        ].reset_index()

    frames = {
        "tax": align(
            tax_results, "Tax results",
            ["Invoice Line ID", "Tax Status",
             "Potential Tax Overcharge"],
        ),
        "surcharge": align(
            surcharge_results, "Surcharge results",
            ["Invoice Line ID", "Surcharge Status",
             "Potential Surcharge Overcharge"],
        ),
        "weight": align(
            weight_results, "Weight results",
            ["Invoice Line ID", "Weight Status",
             "Weight Comparison Status"],
        ),
        "pricing": align(
            contract_pricing_results, "Contract pricing results",
            ["Invoice Line ID", "Pricing Status",
             "Potential Contract Overcharge"],
        ),
        "delivery": align(
            delivery_evidence_results, "Delivery results",
            ["Invoice Line ID", "Delivery Status"],
        ),
        "exposure": align(
            combined_exposure, "Combined exposure",
            ["Invoice Line ID", "Payment Treatment",
             "Rate Exposure", "Rate Exposure Status",
             "Combined Potential Exposure"],
        ),
    }

    def number(value):
        if isinstance(value, (bool, np.bool_)):
            return None
        try:
            n = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return None
        return n if n.is_finite() else None

    def flag(value):
        return isinstance(value, (bool, np.bool_)) and bool(value)

    matched_reversals = {
        "Fully Reversed", "Matched Full Reversal"
    }
    unresolved_credits = {
        "Unmatched Credit", "Ambiguous Credit",
        "Missing Match Information"
    }
    ordinary_credits = {
        "Not a Credit", "Not Applicable", "Not a Credit Line"
    }

    records = []

    for i in range(len(result)):
        line = result.iloc[i]
        reasons = []
        checks = {}
        exposure_statuses = {}

        def hold(reason):
            reasons.append(reason)

        def assess_money(name, status_col, amount_col, allowed):
            frame = frames[name]
            display = {
                "tax": "Tax",
                "surcharge": "Surcharge",
                "pricing": "Contract Pricing",
            }[name]

            if frame is None:
                checks[f"{display} Check"] = "Not Run"
                exposure_statuses[
                    f"{display} Exposure Status"
                ] = "Not Run"
                return

            entry = frame.iloc[i]
            status = entry[status_col]
            amount = number(entry[amount_col])

            checks[f"{display} Check"] = status

            if status not in allowed:
                hold(f"{name}_unrecognized_status")

            if status == "review":
                hold(f"{name}_review")

            if amount is None:
                hold(f"{name}_unknown_exposure")
                exposure_state = "Unknown"
            elif amount < 0:
                hold(f"{name}_negative_exposure")
                exposure_state = "Invalid"
            else:
                exposure_state = "Quantified"
                if amount > 0:
                    hold(f"{name}_positive_exposure")

            if status == "potential_overcharge":
                hold(f"{name}_overcharge")

            exposure_statuses[
                f"{display} Exposure Status"
            ] = exposure_state

        assess_money(
            "tax", "Tax Status", "Potential Tax Overcharge",
            {"matched", "potential_overcharge",
             "below_contract", "review", "not_assessed"},
        )
        assess_money(
            "surcharge", "Surcharge Status",
            "Potential Surcharge Overcharge",
            {"matched", "potential_overcharge",
             "below_contract", "review", "not_assessed"},
        )
        assess_money(
            "pricing", "Pricing Status",
            "Potential Contract Overcharge",
            {"matched", "potential_overcharge",
             "below_contract_rate", "review"},
        )

        weight = frames["weight"]
        if weight is None:
            checks["Weight Check"] = "Not Run"
            checks["Weight Comparison Check"] = "Not Run"
        else:
            entry = weight.iloc[i]
            status = entry["Weight Status"]
            comparison = entry["Weight Comparison Status"]
            checks["Weight Check"] = status
            checks["Weight Comparison Check"] = (
                comparison if pd.notna(comparison) else "Not Run"
            )
            if status != "calculated":
                hold("weight_review")
            if comparison not in {
                "match", None, "billed_weight_high",
                "billed_weight_low",
            }:
                if pd.notna(comparison):
                    hold("weight_unrecognized_comparison")
            if comparison in {
                "billed_weight_high", "billed_weight_low"
            }:
                hold("weight_discrepancy")
            if pd.isna(comparison):
                hold("weight_comparison_not_performed")

        delivery = frames["delivery"]
        if delivery is None:
            checks["Delivery Check"] = "Not Run"
        else:
            status = delivery.iloc[i]["Delivery Status"]
            checks["Delivery Check"] = status
            if status != "confirmed":
                hold("delivery_not_confirmed")

        exposure = frames["exposure"]
        if exposure is not None:
            entry = exposure.iloc[i]
            if entry["Payment Treatment"] != "Proceed":
                hold("preliminary_payment_review")
            if entry["Rate Exposure Status"] != "Quantified":
                hold("unknown_rate_exposure")
            for field in (
                "Rate Exposure", "Combined Potential Exposure"
            ):
                value = number(entry[field])
                if value is None or value < 0:
                    hold("invalid_preliminary_exposure")
                elif value > 0:
                    hold("preliminary_overcharge")

        if flag(line.get("Needs Charge Review", False)):
            hold("charge_review")
        if flag(line.get("Is Exact Duplicate Charge", False)):
            hold("exact_duplicate_charge")

        total = number(line["Total"])
        credit = line.get("Credit Match Status", "Not a Credit")
        excluded = line.get("Excluded From Exposure", False)

        valid_exclusion = isinstance(
            excluded, (bool, np.bool_)
        )

        if total is None:
            hold("invalid_invoice_total")

        if not valid_exclusion:
            hold("invalid_exclusion_flag")

        if credit not in (
            matched_reversals
            | unresolved_credits
            | ordinary_credits
        ):
            hold("unrecognized_credit_status")

        reversed_ok = (
            credit in matched_reversals
            and valid_exclusion
            and flag(excluded)
        )

        if credit in matched_reversals and not reversed_ok:
            hold("inconsistent_reversal_metadata")

        if (
            credit not in matched_reversals
            and valid_exclusion
            and flag(excluded)
        ):
            hold("unexpected_exposure_exclusion")

        if reversed_ok:
            treatment = "No Payment - Reversed"
            reasons = ["matched_full_reversal"]
        elif credit in unresolved_credits or (
            total is not None and total < 0
        ):
            treatment = "Review Credit"
            reasons = ["unresolved_credit"]
        elif total is not None and total == 0:
            treatment = "No Payment - Zero"
            reasons = ["zero_value_line"]
        elif reasons:
            treatment = "Hold"
        else:
            treatment = "Proceed"
            reasons = ["available_checks_clear"]

        # Missing modules are never represented as passed checks.
        completeness = (
            "Complete"
            if all(f is not None for f in frames.values())
            else "Partial"
        )

        records.append({
            "Final Payment Treatment": treatment,
            "Decision Completeness": completeness,
            "Decision Reason": "; ".join(
                dict.fromkeys(reasons)
            ),
            **checks,
            **exposure_statuses,
        })

    return pd.concat(
        [result, pd.DataFrame(records, index=result.index)],
        axis=1,
    )

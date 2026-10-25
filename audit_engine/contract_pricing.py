"""Contract rate selection for R4 freight pricing."""

import math
import re
from datetime import date, datetime

import pandas as pd


REQUIRED_RATE_COLUMNS = {
    "Carrier ID",
    "Service Type",
    "Zone",
    "Min Weight (kg)",
    "Max Weight (kg)",
    "Valid From",
    "Valid To",
    "Currency",
    "Agreed Base Freight",
}


def _normalise_text(value):
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip().upper()


def _valid_positive_number(value):
    if isinstance(value, bool):
        return False

    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return False

    return math.isfinite(number) and number > 0


def _review(reason):
    return {
        "status": "review",
        "reason": reason,
        "expected_base_freight": None,
        "currency": None,
    }


def _parse_contract_date(value):
    """Accept ISO date strings or genuine date objects only."""

    import re
    from datetime import date, datetime

    if isinstance(value, str):
        if not re.fullmatch("[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            return pd.NaT

        return pd.to_datetime(
            value,
            format="%Y-%m-%d",
            errors="coerce",
        )

    if isinstance(value, (datetime, date, pd.Timestamp)):
        return pd.to_datetime(value, errors="coerce")

    return pd.NaT




def _valid_contract_candidates(candidates):
    """Validate contract rows relevant to the shipment's route."""

    for row in candidates.to_dict("records"):
        minimum = row["Min Weight (kg)"]
        maximum = row["Max Weight (kg)"]
        agreed_rate = row["Agreed Base Freight"]

        try:
            minimum = float(minimum)
            maximum = float(maximum)
            agreed_rate = float(agreed_rate)
        except (TypeError, ValueError, OverflowError):
            return False

        if not all(
            math.isfinite(value)
            for value in (minimum, maximum, agreed_rate)
        ):
            return False

        if minimum < 0 or maximum <= minimum:
            return False

        if agreed_rate <= 0:
            return False

        if _normalise_text(row["Currency"]) is None:
            return False

        valid_from = _parse_contract_date(row["Valid From"])
        valid_to = _parse_contract_date(row["Valid To"])

        if pd.isna(valid_from) or pd.isna(valid_to):
            return False

        if valid_from > valid_to:
            return False

    return True


def select_contract_rate(shipment, contract_rates):
    """
    Select exactly one applicable contractual base freight rate.

    Weight bands use:
        Min Weight (kg) < chargeable weight <= Max Weight (kg)

    Contract validity dates are inclusive.

    This function selects a rate but does not calculate financial
    overcharges or alter existing rate validation results.
    """

    if not isinstance(shipment, (dict, pd.Series)):
        raise TypeError("Shipment must be a dictionary or pandas Series.")

    if not isinstance(contract_rates, pd.DataFrame):
        raise TypeError("Contract rates must be a pandas DataFrame.")

    missing_columns = REQUIRED_RATE_COLUMNS - set(contract_rates.columns)

    if missing_columns:
        raise ValueError(
            "Contract rate card is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    carrier = _normalise_text(shipment.get("Carrier ID"))
    service = _normalise_text(shipment.get("Service Type"))
    zone = _normalise_text(shipment.get("Zone"))
    currency = _normalise_text(shipment.get("Currency"))

    if carrier is None:
        return _review("missing_carrier")

    if service is None:
        return _review("missing_service")

    if zone is None:
        return _review("missing_zone")

    if currency is None:
        return _review("missing_currency")

    weight = shipment.get("Chargeable Weight (kg)")

    if not _valid_positive_number(weight):
        return _review("invalid_chargeable_weight")

    weight = float(weight)

    ship_date = _parse_contract_date(shipment.get("Ship Date"))

    if pd.isna(ship_date):
        return _review("missing_or_invalid_ship_date")

    rates = contract_rates.copy()

    for column in (
        "Carrier ID",
        "Service Type",
        "Zone",
        "Currency",
    ):
        rates[column] = (
            rates[column]
            .astype("string")
            .str.strip()
            .str.upper()
        )

    candidates = rates.loc[
        (rates["Carrier ID"] == carrier)
        & (rates["Service Type"] == service)
        & (rates["Zone"] == zone)
    ].copy()

    if candidates.empty:
        return _review("rate_not_found")

    if not _valid_contract_candidates(candidates):
        return _review("invalid_contract_data")

    candidates["Valid From"] = candidates["Valid From"].map(
        _parse_contract_date
    )

    candidates["Valid To"] = candidates["Valid To"].map(
        _parse_contract_date
    )

    candidates["Min Weight (kg)"] = pd.to_numeric(
        candidates["Min Weight (kg)"],
        errors="coerce",
    )

    candidates["Max Weight (kg)"] = pd.to_numeric(
        candidates["Max Weight (kg)"],
        errors="coerce",
    )

    candidates["Agreed Base Freight"] = pd.to_numeric(
        candidates["Agreed Base Freight"],
        errors="coerce",
    )

    applicable = candidates.loc[
        (candidates["Min Weight (kg)"] < weight)
        & (weight <= candidates["Max Weight (kg)"])
        & (candidates["Valid From"] <= ship_date)
        & (ship_date <= candidates["Valid To"])
    ]

    if applicable.empty:
        return _review("rate_not_found")

    currency_matches = applicable.loc[
        applicable["Currency"] == currency
    ]

    if currency_matches.empty:
        return _review("currency_mismatch")

    if len(currency_matches) != 1:
        return _review("ambiguous_contract_rate")

    selected = currency_matches.iloc[0]

    agreed_rate = selected["Agreed Base Freight"]

    if not _valid_positive_number(agreed_rate):
        return _review("invalid_contract_data")

    return {
        "status": "matched",
        "reason": None,
        "expected_base_freight": float(agreed_rate),
        "currency": currency,
    }

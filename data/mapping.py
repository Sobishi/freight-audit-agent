import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from pandas.api import types as pandas_types

from data.schema import clean_column_name
from data.standard import (
    DATE,
    NUMBER,
    REQUIRED_MAPPED_FIELDS,
    STANDARD_INVOICE_FIELDS,
    TEXT,
    WEIGHT_UNITS,
)
from data.yaml_io import read_yaml_mapping

_ID_PATTERN = re.compile(r"^[a-z0-9_]+$")
_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")

_ALLOWED_KEYS = {
    "carrier_id",
    "carrier_name",
    "columns",
    "defaults",
    "header_row",
    "sheet",
    "date_format",
    "decimal",
    "thousands",
}


@dataclass(frozen=True)
class InvoiceMapping:
    """
    How one carrier's invoice columns map to the standard invoice format.

    columns      carrier column name -> standard field
    defaults     standard field -> fixed value, for fields the file lacks
    header_row   zero based row holding the column names
    date_format  how the carrier writes dates, for example %d/%m/%Y.
                 When not set, only ISO dates (YYYY-MM-DD) are accepted,
                 so a day first date is never silently read month first.
    decimal      decimal separator used in amounts
    thousands    thousands separator used in amounts, or None
    """

    carrier_id: str
    carrier_name: str
    columns: dict
    defaults: dict = field(default_factory=dict)
    header_row: int = 0
    sheet: object = None
    date_format: object = None
    decimal: str = "."
    thousands: object = ","


# ---------------------------------------------------------------
# Reading and validating a mapping
# ---------------------------------------------------------------

def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_default(name, kind, value):
    if kind == DATE:
        raise ValueError(f"defaults are not supported for the date field '{name}'.")

    if kind == NUMBER and not _is_number(value):
        raise ValueError(f"default for '{name}' must be a number, found {value!r}.")

    if kind == TEXT and (not isinstance(value, str) or not value.strip()):
        raise ValueError(
            f"default for '{name}' must be text, found {value!r}. "
            f"Put the value in quotes, because YAML reads words like "
            f"NO or yes as true or false."
        )

    if name == "Currency" and not _CURRENCY_PATTERN.match(value.strip().upper()):
        raise ValueError(f"default for 'Currency' must be a code such as USD, found {value!r}.")

    if name == "Weight Unit" and value.strip().lower() not in WEIGHT_UNITS:
        raise ValueError(
            f"default for 'Weight Unit' must be one of {', '.join(WEIGHT_UNITS)}, "
            f"found {value!r}."
        )


def parse_mapping(data):
    """
    Build a validated InvoiceMapping from a dictionary.

    Raises ValueError, naming the problem, for anything missing or invalid.
    Unknown keys are rejected so that a typo cannot be silently ignored.
    """

    if not isinstance(data, dict):
        raise ValueError("expected a list of settings (key: value).")

    unknown = sorted(str(key) for key in set(data) - _ALLOWED_KEYS)

    if unknown:
        raise ValueError(f"unknown setting(s): {', '.join(unknown)}.")

    carrier_id = data.get("carrier_id")

    if not isinstance(carrier_id, str) or not _ID_PATTERN.match(carrier_id):
        raise ValueError(
            "carrier_id must use lowercase letters, numbers and underscores."
        )

    carrier_name = data.get("carrier_name")

    if not isinstance(carrier_name, str) or not carrier_name.strip():
        raise ValueError("carrier_name is required and must be text.")

    columns = data.get("columns")

    if not isinstance(columns, dict) or not columns:
        raise ValueError(
            "columns must list each carrier column and the standard field "
            "it maps to."
        )

    targets = {}
    cleaned_sources = {}

    for source, target in columns.items():
        if not isinstance(source, str):
            raise ValueError(
                f"column name {source!r} must be text. Put it in quotes."
            )

        if target not in STANDARD_INVOICE_FIELDS:
            raise ValueError(
                f"'{target}' is not a standard invoice field. "
                f"Valid fields: {', '.join(STANDARD_INVOICE_FIELDS)}."
            )

        cleaned = clean_column_name(source)

        if cleaned in cleaned_sources:
            raise ValueError(
                f"'{cleaned_sources[cleaned]}' and '{source}' are treated as "
                f"the same column name."
            )

        if target in targets:
            raise ValueError(
                f"Two columns map to '{target}': '{targets[target]}' and '{source}'."
            )

        cleaned_sources[cleaned] = source
        targets[target] = source

    for required in REQUIRED_MAPPED_FIELDS:
        if required not in targets:
            raise ValueError(f"columns must map a carrier column to '{required}'.")

    defaults = data.get("defaults") or {}

    if not isinstance(defaults, dict):
        raise ValueError("defaults must list a standard field and its value.")

    for name, value in defaults.items():
        if name not in STANDARD_INVOICE_FIELDS:
            raise ValueError(f"defaults: '{name}' is not a standard invoice field.")

        if name in targets:
            raise ValueError(
                f"defaults cannot set '{name}' because it is already mapped "
                f"from the column '{targets[name]}'."
            )

        _validate_default(name, STANDARD_INVOICE_FIELDS[name], value)

    header_row = data.get("header_row", 0)

    if not isinstance(header_row, int) or isinstance(header_row, bool) or header_row < 0:
        raise ValueError(
            f"header_row must be a whole number from 0 upwards, found {header_row!r}."
        )

    sheet = data.get("sheet")

    if sheet is not None and (not isinstance(sheet, str) or not sheet.strip()):
        raise ValueError("sheet must be the worksheet name, as text.")

    date_format = data.get("date_format")

    if date_format is not None and (not isinstance(date_format, str) or not date_format.strip()):
        raise ValueError("date_format must be text such as %d/%m/%Y.")

    decimal = data.get("decimal", ".")
    thousands = data.get("thousands", ",")

    if not isinstance(decimal, str) or len(decimal) != 1:
        raise ValueError("decimal must be a single character.")

    if thousands is not None and (not isinstance(thousands, str) or len(thousands) != 1):
        raise ValueError("thousands must be a single character, or left empty.")

    if decimal == thousands:
        raise ValueError("decimal and thousands separators must be different characters.")

    return InvoiceMapping(
        carrier_id=carrier_id,
        carrier_name=carrier_name.strip(),
        columns=dict(columns),
        defaults=dict(defaults),
        header_row=header_row,
        sheet=sheet,
        date_format=date_format,
        decimal=decimal,
        thousands=thousands,
    )


def load_mapping(path):
    """Read and validate an invoice mapping from a YAML file."""

    path = Path(path)
    data = read_yaml_mapping(path)

    try:
        return parse_mapping(data)
    except ValueError as error:
        raise ValueError(f"{path.name}: {error}") from error


# ---------------------------------------------------------------
# Converting a raw invoice to the standard format
# ---------------------------------------------------------------

def _blank(values):
    """True where a cell is missing or only whitespace."""

    text = values.astype("string").str.strip()

    return (text.isna() | text.eq("").fillna(False)).astype(bool)


def _text(values):
    text = values.astype("string").str.strip()
    blank = _blank(values)

    return text.astype(object).where(~blank, None)


def _number(values, mapping, label, required):
    if pandas_types.is_numeric_dtype(values) and not pandas_types.is_bool_dtype(values):
        numbers = pd.to_numeric(values, errors="coerce").astype(float)
        blank = values.isna()
    else:
        blank = _blank(values)
        cleaned = values.astype("string").str.strip().mask(blank)

        if mapping.thousands:
            cleaned = cleaned.str.replace(mapping.thousands, "", regex=False)

        if mapping.decimal != ".":
            cleaned = cleaned.str.replace(mapping.decimal, ".", regex=False)

        numbers = pd.to_numeric(cleaned, errors="coerce").astype(float)

    invalid = numbers.isna() & ~blank

    if required:
        invalid = invalid | blank

    if invalid.any():
        raise ValueError(
            f"Column '{label}' has {int(invalid.sum())} blank or non-numeric "
            f"value(s)." if required else
            f"Column '{label}' has {int(invalid.sum())} non-numeric value(s)."
        )

    return numbers


def _date(values, mapping, label):
    if pandas_types.is_datetime64_any_dtype(values):
        return pd.to_datetime(values)

    blank = _blank(values)
    text = values.astype("string").str.strip().mask(blank)

    if mapping.date_format:
        parsed = pd.to_datetime(text, format=mapping.date_format, errors="coerce")

        # Excel exports often hold ISO timestamps even when the carrier
        # prints another format. ISO is unambiguous, so it is a safe fallback.
        retry = parsed.isna() & ~blank

        if retry.any():
            parsed.loc[retry] = pd.to_datetime(
                text[retry], format="ISO8601", errors="coerce"
            )
    else:
        parsed = pd.to_datetime(text, format="ISO8601", errors="coerce")

    invalid = parsed.isna() & ~blank

    if invalid.any():
        if mapping.date_format:
            advice = (
                f"The mapping expects dates written as {mapping.date_format} "
                f"(or YYYY-MM-DD). Check the file, or correct date_format "
                f"in the mapping."
            )
        else:
            advice = (
                "If the carrier does not write dates as YYYY-MM-DD, "
                "set date_format in the mapping."
            )

        raise ValueError(
            f"Column '{label}' has {int(invalid.sum())} date value(s) that "
            f"could not be read. {advice}"
        )

    return parsed


def _resolve_columns(data, mapping):
    """Find each mapped carrier column in the file, tolerating case and punctuation."""

    lookup = {}

    for column in data.columns:
        lookup.setdefault(clean_column_name(column), []).append(column)

    resolved = {}

    for source, target in mapping.columns.items():
        matches = lookup.get(clean_column_name(source), [])

        if not matches:
            raise ValueError(
                f"Invoice is missing the column '{source}' (mapped to "
                f"'{target}' for {mapping.carrier_id}). If the carrier changed "
                f"its layout, update the mapping file."
            )

        if len(matches) > 1:
            raise ValueError(
                f"Invoice has more than one column matching '{source}': "
                f"{', '.join(map(str, matches))}."
            )

        resolved[target] = matches[0]

    return resolved


def standardize_invoice(raw, mapping, keep_unmapped=False):
    """
    Convert a raw carrier invoice into the standard invoice format.

    The input is not modified. The result has Invoice Line ID and
    Carrier ID first, then the standard fields in standard order.
    Columns the mapping does not mention are dropped unless
    keep_unmapped is True.
    """

    if not isinstance(raw, pd.DataFrame):
        raise TypeError("Expected a DataFrame.")

    data = raw.dropna(how="all").reset_index(drop=True)

    if data.empty:
        raise ValueError(
            f"The invoice has no data rows below the header "
            f"(row {mapping.header_row + 1}). Check header_row in the mapping."
        )

    resolved = _resolve_columns(data, mapping)
    result = pd.DataFrame(index=data.index)

    for name, kind in STANDARD_INVOICE_FIELDS.items():
        if name in resolved:
            values = data[resolved[name]]
            label = resolved[name]
        elif name in mapping.defaults:
            values = pd.Series([mapping.defaults[name]] * len(data), index=data.index)
            label = f"default for {name}"
        elif name == "Carrier":
            values = pd.Series([None] * len(data), index=data.index, dtype=object)
            label = name
        else:
            continue

        if kind == TEXT:
            column = _text(values)
        elif kind == NUMBER:
            column = _number(values, mapping, label, required=(name == "Total"))
        else:
            column = _date(values, mapping, label)

        if name == "Carrier":
            column = column.where(column.notna(), mapping.carrier_name)

        result[name] = column

    _check_awb(result, resolved)
    _check_currency(result)
    _check_weight_unit(result)

    if keep_unmapped:
        used = set(resolved.values())

        for column in data.columns:
            if column not in used:
                name = f"{column} (original)" if column in result.columns else column
                result[name] = data[column]

    result.insert(0, "Carrier ID", mapping.carrier_id)
    result.insert(0, "Invoice Line ID", range(1, len(result) + 1))

    return result


def _check_awb(result, resolved):
    missing = result["AWB"].isna()

    if missing.any():
        raise ValueError(
            f"Invoice contains {int(missing.sum())} record(s) with a "
            f"missing AWB (column '{resolved['AWB']}')."
        )


def _check_currency(result):
    if "Currency" not in result.columns:
        return

    result["Currency"] = result["Currency"].map(
        lambda value: value.upper(), na_action="ignore"
    )

    bad = sorted({v for v in result["Currency"].dropna() if not _CURRENCY_PATTERN.match(v)})

    if bad:
        raise ValueError(
            f"Currency has invalid value(s): {', '.join(bad)}. "
            f"Use a three letter code such as USD."
        )


def _check_weight_unit(result):
    if "Weight Unit" not in result.columns:
        return

    result["Weight Unit"] = result["Weight Unit"].map(
        lambda value: value.lower(), na_action="ignore"
    )

    bad = sorted({v for v in result["Weight Unit"].dropna() if v not in WEIGHT_UNITS})

    if bad:
        raise ValueError(
            f"Weight Unit has invalid value(s): {', '.join(bad)}. "
            f"Use one of {', '.join(WEIGHT_UNITS)}."
        )

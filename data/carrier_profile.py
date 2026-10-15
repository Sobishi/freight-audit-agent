import datetime
import re
from dataclasses import dataclass
from pathlib import Path

from data.yaml_io import read_yaml_mapping

PRICING_METHODS = ("parcel_zone_weight",)
UNIT_SYSTEMS = ("metric", "imperial")
SURCHARGE_BASES = ("per_kg", "fixed", "percent_of_freight")

_ID_PATTERN = re.compile(r"^[a-z0-9_]+$")
_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")

_REQUIRED_KEYS = (
    "carrier_id",
    "carrier_name",
    "currency",
    "pricing_method",
    "unit_system",
    "dim_divisor",
    "rounding",
)

_OPTIONAL_KEYS = (
    "tolerance",
    "max_band",
    "excess_band_code",
    "tax_rate",
    "tax_inclusive",
    "surcharge_basis",
    "valid_from",
    "valid_to",
)

_ROUNDING_KEYS = {"step_low", "threshold", "step_high"}


@dataclass(frozen=True)
class RoundingRule:
    """
    Billable weight rounding.

    Weights up to the threshold round up to the next step_low.
    Heavier weights round up to the next step_high.
    """

    step_low: float
    threshold: float
    step_high: float


@dataclass(frozen=True)
class CarrierProfile:
    """
    One carrier's contract rules, held as data.

    Fields beyond tolerance are validated and stored now, and used by
    the pricing engine in a later phase.
    """

    carrier_id: str
    carrier_name: str
    currency: str
    pricing_method: str
    unit_system: str
    dim_divisor: float
    rounding: RoundingRule
    tolerance: float = 0.01
    max_band: object = None
    excess_band_code: object = None
    tax_rate: float = 0.0
    tax_inclusive: bool = False
    surcharge_basis: object = None
    valid_from: object = None
    valid_to: object = None


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _number(value, name, *, minimum=None, maximum=None, allow_equal_minimum=False):
    if not _is_number(value):
        raise ValueError(f"{name} must be a number, found {value!r}.")

    if minimum is not None:
        too_low = value < minimum if allow_equal_minimum else value <= minimum

        if too_low:
            relation = "at least" if allow_equal_minimum else "greater than"
            raise ValueError(f"{name} must be {relation} {minimum}, found {value}.")

    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be at most {maximum}, found {value}.")

    return value


def _choice(value, name, options):
    if value not in options:
        raise ValueError(
            f"{name} must be one of {', '.join(options)}, found {value!r}."
        )

    return value


def _date(value, name):
    if value is None:
        return None

    if isinstance(value, datetime.datetime):
        return value.date()

    if isinstance(value, datetime.date):
        return value

    if isinstance(value, str):
        try:
            return datetime.date.fromisoformat(value.strip())
        except ValueError:
            pass

    raise ValueError(
        f"{name} must be a date written YYYY-MM-DD, found {value!r}."
    )


def _rounding(value):
    if not isinstance(value, dict):
        raise ValueError("rounding must contain step_low, threshold and step_high.")

    missing = _ROUNDING_KEYS - set(value)
    extra = set(value) - _ROUNDING_KEYS

    if missing or extra:
        raise ValueError(
            "rounding must contain exactly step_low, threshold and step_high"
            + (f" (missing: {', '.join(sorted(missing))})" if missing else "")
            + (f" (unexpected: {', '.join(sorted(map(str, extra)))})" if extra else "")
            + "."
        )

    try:
        return RoundingRule(
            step_low=_number(value["step_low"], "step_low", minimum=0),
            threshold=_number(value["threshold"], "threshold", minimum=0),
            step_high=_number(value["step_high"], "step_high", minimum=0),
        )
    except ValueError as error:
        raise ValueError(f"rounding: {error}") from error


def parse_profile(data):
    """
    Build a validated CarrierProfile from a dictionary.

    Raises ValueError, naming the field, for anything missing or invalid.
    Unknown keys are rejected so that a typo cannot be silently ignored.
    """

    if not isinstance(data, dict):
        raise ValueError("expected a list of settings (key: value).")

    allowed = set(_REQUIRED_KEYS) | set(_OPTIONAL_KEYS)
    unknown = sorted(str(key) for key in set(data) - allowed)

    if unknown:
        raise ValueError(f"unknown setting(s): {', '.join(unknown)}.")

    for key in _REQUIRED_KEYS:
        if key not in data:
            raise ValueError(f"{key} is required.")

    carrier_id = data["carrier_id"]

    if not isinstance(carrier_id, str) or not _ID_PATTERN.match(carrier_id):
        raise ValueError(
            "carrier_id must use lowercase letters, numbers and underscores."
        )

    carrier_name = data["carrier_name"]

    if not isinstance(carrier_name, str) or not carrier_name.strip():
        raise ValueError("carrier_name must be text.")

    currency = data["currency"]

    if not isinstance(currency, str) or not _CURRENCY_PATTERN.match(currency):
        raise ValueError(
            f"currency must be a three letter uppercase code such as USD, "
            f"found {currency!r}."
        )

    tax_inclusive = data.get("tax_inclusive", False)

    if not isinstance(tax_inclusive, bool):
        raise ValueError(f"tax_inclusive must be true or false, found {tax_inclusive!r}.")

    surcharge_basis = data.get("surcharge_basis")

    if surcharge_basis is not None:
        _choice(surcharge_basis, "surcharge_basis", SURCHARGE_BASES)

    max_band = data.get("max_band")

    if max_band is not None:
        _number(max_band, "max_band", minimum=0)

    excess_band_code = data.get("excess_band_code")

    if excess_band_code is not None and not isinstance(excess_band_code, str):
        raise ValueError("excess_band_code must be text.")

    valid_from = _date(data.get("valid_from"), "valid_from")
    valid_to = _date(data.get("valid_to"), "valid_to")

    if valid_from and valid_to and valid_to < valid_from:
        raise ValueError("valid_to cannot be before valid_from.")

    return CarrierProfile(
        carrier_id=carrier_id,
        carrier_name=carrier_name.strip(),
        currency=currency,
        pricing_method=_choice(data["pricing_method"], "pricing_method", PRICING_METHODS),
        unit_system=_choice(data["unit_system"], "unit_system", UNIT_SYSTEMS),
        dim_divisor=_number(data["dim_divisor"], "dim_divisor", minimum=0),
        rounding=_rounding(data["rounding"]),
        tolerance=_number(
            data.get("tolerance", 0.01), "tolerance",
            minimum=0, allow_equal_minimum=True,
        ),
        max_band=max_band,
        excess_band_code=excess_band_code,
        tax_rate=_number(
            data.get("tax_rate", 0.0), "tax_rate",
            minimum=0, maximum=1, allow_equal_minimum=True,
        ),
        tax_inclusive=tax_inclusive,
        surcharge_basis=surcharge_basis,
        valid_from=valid_from,
        valid_to=valid_to,
    )


def load_profile(path):
    """Read and validate a carrier profile from a YAML file."""

    path = Path(path)
    data = read_yaml_mapping(path)

    try:
        return parse_profile(data)
    except ValueError as error:
        raise ValueError(f"{path.name}: {error}") from error

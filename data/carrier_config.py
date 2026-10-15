import re
from dataclasses import dataclass, replace
from pathlib import Path

from data.carrier_profile import CarrierProfile, load_profile
from data.mapping import InvoiceMapping, load_mapping

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

_ID_PATTERN = re.compile(r"^[a-z0-9_]+$")


@dataclass(frozen=True)
class CarrierConfig:
    """Everything the engine needs to know about one carrier."""

    profile: CarrierProfile
    mapping: InvoiceMapping


def _config_root(config_dir):
    return Path(config_dir) if config_dir is not None else DEFAULT_CONFIG_DIR


def list_carriers(config_dir=None):
    """Carrier ids that have a profile file, in alphabetical order."""

    folder = _config_root(config_dir) / "carriers"

    if not folder.is_dir():
        return []

    return sorted(path.stem for path in folder.glob("*.yaml"))


def load_carrier_config(carrier_id, config_dir=None):
    """
    Load a carrier's profile and invoice mapping by id.

    Files are expected at:
        <config>/carriers/<carrier_id>.yaml
        <config>/mappings/<carrier_id>_invoice.yaml

    Currency and weight unit are taken from the profile when the
    mapping does not set them, so they are only written down once.
    """

    if not isinstance(carrier_id, str) or not _ID_PATTERN.match(carrier_id):
        raise ValueError(
            f"Invalid carrier id {carrier_id!r}. "
            f"Use lowercase letters, numbers and underscores."
        )

    root = _config_root(config_dir)
    profile_path = root / "carriers" / f"{carrier_id}.yaml"
    mapping_path = root / "mappings" / f"{carrier_id}_invoice.yaml"

    if not profile_path.exists():
        available = ", ".join(list_carriers(root)) or "none"

        raise FileNotFoundError(
            f"No carrier profile for '{carrier_id}' ({profile_path}). "
            f"Available carriers: {available}."
        )

    if not mapping_path.exists():
        raise FileNotFoundError(
            f"Carrier '{carrier_id}' has no invoice mapping file: {mapping_path}"
        )

    profile = load_profile(profile_path)
    mapping = load_mapping(mapping_path)

    if profile.carrier_id != carrier_id:
        raise ValueError(
            f"{profile_path.name} declares carrier_id '{profile.carrier_id}', "
            f"but '{carrier_id}' was requested."
        )

    if mapping.carrier_id != carrier_id:
        raise ValueError(
            f"{mapping_path.name} declares carrier_id '{mapping.carrier_id}', "
            f"but '{carrier_id}' was requested."
        )

    return CarrierConfig(profile=profile, mapping=_with_profile_defaults(profile, mapping))


def _with_profile_defaults(profile, mapping):
    defaults = dict(mapping.defaults)
    mapped_fields = set(mapping.columns.values())

    if "Currency" in defaults:
        if str(defaults["Currency"]).strip().upper() != profile.currency:
            raise ValueError(
                f"Currency mismatch for '{profile.carrier_id}': the mapping "
                f"sets {defaults['Currency']} but the profile says {profile.currency}."
            )
    elif "Currency" not in mapped_fields:
        defaults["Currency"] = profile.currency

    if "Weight Unit" not in defaults and "Weight Unit" not in mapped_fields:
        defaults["Weight Unit"] = "kg" if profile.unit_system == "metric" else "lb"

    return replace(mapping, defaults=defaults)

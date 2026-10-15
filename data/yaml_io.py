from pathlib import Path


def read_yaml_mapping(path):
    """
    Read a YAML file that must contain a mapping of settings.

    Raises FileNotFoundError if the file is missing, and ValueError,
    naming the file, if it is not valid YAML or not a mapping.
    """

    try:
        import yaml
    except ImportError as error:
        raise ImportError(
            "PyYAML is required to read carrier configuration files. "
            "Install it with: pip install PyYAML"
        ) from error

    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ValueError(f"{path.name}: not valid YAML ({error})") from error

    if not isinstance(data, dict):
        raise ValueError(
            f"{path.name}: expected a list of settings (key: value), "
            f"found {type(data).__name__}."
        )

    return data

import base64
from typing import Any, Dict, List
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Custom YAML dumper — uses | (literal block scalar) for multiline strings
# ---------------------------------------------------------------------------

class _LiteralStr(str):
    """Marker subclass so the representer can target just these strings."""


def _literal_str_representer(dumper: yaml.Dumper, data: str) -> yaml.ScalarNode:
    """Emit multi-line strings as YAML literal block scalars (|)."""
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


class LiteralBlockDumper(yaml.Dumper):
    """yaml.Dumper subclass that renders multi-line strings with the | style."""


LiteralBlockDumper.add_representer(str, _literal_str_representer)

def decode_secret_data(data: dict) -> dict:
    decoded = {}
    if not data:
        return decoded
    for k, v in data.items():
        try:
            decoded[k] = base64.b64decode(v).decode('utf-8')
        except Exception:
            decoded[k] = v
    return decoded

def encode_secret_data(data: dict) -> dict:
    encoded = {}
    if not data:
        return encoded
    for k, v in data.items():
        encoded[k] = base64.b64encode(str(v).encode('utf-8')).decode('utf-8')
    return encoded

def load_yaml(path: str) -> dict:
    with open(path, 'r') as f:
        return yaml.safe_load(f) or {}

def save_yaml(path: str, data: Any) -> None:
    """Write *data* to a YAML file using the literal block style for multi-line strings."""
    with open(path, "w") as f:
        yaml.dump(data, f, Dumper=LiteralBlockDumper, default_flow_style=False, sort_keys=False)


def yaml_dumps(data: Any) -> str:
    """Serialise *data* to a YAML string using the literal block style for multi-line strings."""
    return yaml.dump(data, Dumper=LiteralBlockDumper, default_flow_style=False, sort_keys=False)

def diff_dicts(old: dict, new: dict) -> dict:
    changed = {}
    for k, v in new.items():
        if k not in old or old[k] != v:
            changed[k] = v
    return changed

def parse_env_pairs(pairs: List[str]) -> dict:
    result = {}
    for pair in pairs:
        if "=" in pair:
            k, v = pair.split("=", 1)
            result[k] = v
    return result

def parse_env_file(path: str) -> dict:
    result = {}
    if not Path(path).exists():
        return result
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('export '):
                line = line[len('export '):]
            if '=' in line:
                k, v = line.split('=', 1)
                result[k] = v
    return result

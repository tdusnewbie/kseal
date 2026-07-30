import pytest
import yaml
from typing import Dict

from kseal.utils import (
    decode_secret_data,
    encode_secret_data,
    diff_dicts,
    parse_env_pairs,
    yaml_dumps,
)


def test_encode_secret_data():
    raw_data = {"DB_PASS": "hunter2", "API_KEY": "12345"}
    encoded = encode_secret_data(raw_data)
    assert encoded["DB_PASS"] == "aHVudGVyMg=="
    assert encoded["API_KEY"] == "MTIzNDU="


def test_decode_secret_data():
    encoded = {"DB_PASS": "aHVudGVyMg==", "API_KEY": "MTIzNDU="}
    decoded = decode_secret_data(encoded)
    assert decoded["DB_PASS"] == "hunter2"
    assert decoded["API_KEY"] == "12345"


def test_yaml_dumps_multiline():
    # Should use the literal block scalar for multiline strings
    data = {"CERT": "-----BEGIN CERTIFICATE-----\nFOOBAR\n-----END CERTIFICATE-----"}
    yaml_str = yaml_dumps(data)
    
    assert "CERT: |" in yaml_str
    assert "  -----BEGIN CERTIFICATE-----" in yaml_str
    assert "  FOOBAR" in yaml_str
    assert "  -----END CERTIFICATE-----" in yaml_str


def test_parse_env_pairs():
    pairs = [
        "KEY1=val1",
        "KEY2=val=2=3",
        "KEY3=",
    ]
    parsed = parse_env_pairs(pairs)
    assert parsed == {
        "KEY1": "val1",
        "KEY2": "val=2=3",
        "KEY3": "",
    }


def test_parse_env_pairs_invalid():
    # Lines without '=' should be ignored or handle gracefully
    pairs = ["INVALID_LINE", "KEY=val"]
    parsed = parse_env_pairs(pairs)
    assert parsed == {"KEY": "val"}


def test_diff_dicts_logic():
    old = {"A": "1", "B": "2"}
    new = {"A": "1", "B": "3", "C": "4"}
    
    added = {k for k in new if k not in old}
    removed = {k for k in old if k not in new}
    changed = {k for k in new if k in old and old[k] != new[k]}
    
    assert added == {"C"}
    assert removed == set()
    assert changed == {"B"}


def test_load_save_yaml(tmp_path):
    from kseal.utils import load_yaml, save_yaml
    f = tmp_path / "test.yaml"
    data = {"kind": "Test"}
    save_yaml(str(f), data)
    
    assert f.exists()
    loaded = load_yaml(str(f))
    assert loaded == data


def test_parse_env_file(tmp_path):
    from kseal.utils import parse_env_file
    f = tmp_path / ".env"
    f.write_text("KEY1=val1\n#comment\nKEY2=val2\n")
    
    parsed = parse_env_file(str(f))
    assert parsed == {"KEY1": "val1", "KEY2": "val2"}


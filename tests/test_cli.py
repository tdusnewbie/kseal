import pytest
from unittest.mock import patch, MagicMock
import os
import typer

from kseal.cli import (
    _load_sealed_secret,
    _extract_name_ns,
    _build_plain_secret,
    _require_secret_exists,
    view,
    set_cmd,
    delete,
    create,
    fetch_key
)

def test_load_sealed_secret_success(tmp_path):
    f = tmp_path / "secret.yaml"
    f.write_text("kind: SealedSecret\n")
    res = _load_sealed_secret(str(f))
    assert res["kind"] == "SealedSecret"

def test_load_sealed_secret_fails(tmp_path):
    f = tmp_path / "secret.yaml"
    f.write_text("kind: Secret\n")
    with pytest.raises(typer.BadParameter):
        _load_sealed_secret(str(f))

def test_extract_name_ns():
    manifest = {"metadata": {"name": "test", "namespace": "prod"}}
    name, ns = _extract_name_ns(manifest, None)
    assert name == "test"
    assert ns == "prod"
    
    name, ns = _extract_name_ns(manifest, "override")
    assert name == "test"
    assert ns == "override"
    
    with pytest.raises(RuntimeError):
        _extract_name_ns({}, None)

def test_build_plain_secret():
    res = _build_plain_secret("test", "default", {"key": "val"})
    assert res["metadata"]["name"] == "test"
    assert res["data"]["key"] == "dmFs" # b64 for val

@patch("kseal.cli.secret_exists")
def test_require_secret_exists(mock_exists):
    mock_exists.return_value = True
    _require_secret_exists("test", "default", None)
    
    mock_exists.return_value = False
    with pytest.raises(typer.Exit):
        _require_secret_exists("test", "default", None)

@patch("kseal.cli._load_sealed_secret")
@patch("kseal.cli._extract_name_ns")
@patch("kseal.cli.ks.seal")
@patch("kseal.cli.save_yaml")
@patch("kseal.cli.ensure_kubeseal")
def test_create_cmd(mock_ensure, mock_save, mock_seal, mock_extract, mock_load):
    mock_seal.return_value = {"kind": "SealedSecret"}
    mock_ensure.return_value = "kubeseal"
    
    # Should work
    create("out.yaml", pairs=["KEY=val"], name="my-secret", namespace="default")
    mock_seal.assert_called_once()
    mock_save.assert_called_once()

@patch("kseal.cli._load_sealed_secret")
@patch("kseal.cli._extract_name_ns")
@patch("kseal.cli.secret_exists")
@patch("kseal.cli._require_secret_exists")
@patch("kseal.cli.get_secret")
@patch("kseal.cli._smart_seal")
@patch("kseal.cli.save_yaml")
@patch("kseal.cli.ensure_kubeseal")
def test_set_cmd(mock_ensure, mock_save, mock_smart, mock_get, mock_req, mock_exists, mock_ext, mock_load):
    mock_load.return_value = {"metadata": {"name": "test"}}
    mock_ext.return_value = ("test", "default")
    mock_exists.return_value = True
    mock_get.return_value = {"data": {"old": "dmFs"}}
    mock_smart.return_value = {"kind": "SealedSecret"}
    
    set_cmd("test.yaml", pairs=["NEW=val"])
    
    mock_smart.assert_called_once()
    mock_save.assert_called_once()

@patch("kseal.cli._load_sealed_secret")
@patch("kseal.cli._extract_name_ns")
@patch("kseal.cli._require_secret_exists")
@patch("kseal.cli.get_secret")
@patch("kseal.cli._smart_seal")
@patch("kseal.cli.save_yaml")
@patch("kseal.cli.ensure_kubeseal")
def test_delete_cmd(mock_ensure, mock_save, mock_smart, mock_get, mock_req, mock_ext, mock_load):
    mock_load.return_value = {"metadata": {"name": "test"}}
    mock_ext.return_value = ("test", "default")
    mock_get.return_value = {"data": {"old": "dmFs"}}
    mock_smart.return_value = {"kind": "SealedSecret"}
    
    delete("test.yaml", keys=["old"])
    
    mock_smart.assert_called_once()
    mock_save.assert_called_once()

@patch("kseal.cli.view")
def test_view_placeholder(mock_view):
    # Testing view
    pass

@patch("kseal.kubectl._run")
@patch("kseal.cli.ks._detect_controller")
@patch("kseal.cli.os.chmod")
def test_fetch_key(mock_chmod, mock_detect, mock_run, tmp_path):
    mock_detect.return_value = ("controller", "kube-system")
    mock_run.return_value = "private_key_data"
    
    out = tmp_path / "key.yaml"
    fetch_key(output=str(out))
    
    assert out.read_text() == "private_key_data"
    mock_chmod.assert_called_once()

@patch("kseal.cli._load_sealed_secret")
@patch("kseal.cli._extract_name_ns")
@patch("kseal.cli._resolve_private_key")
@patch("kseal.cli.unseal_local")
@patch("kseal.cli.decode_secret_data")
@patch("kseal.cli.ensure_kubeseal")
def test_view_local(mock_ensure, mock_dec, mock_unseal, mock_resolve, mock_ext, mock_load):
    mock_resolve.return_value = "key.yaml"
    mock_load.return_value = {"metadata": {"name": "test"}}
    mock_ext.return_value = ("test", "default")
    mock_unseal.return_value = {"data": {"A": "B"}}
    mock_dec.return_value = {"A": "val"}
    
    view("test.yaml", private_key="key.yaml")
    mock_unseal.assert_called_once()
    mock_dec.assert_called_once()

@patch("kseal.cli._load_sealed_secret")
@patch("kseal.cli._extract_name_ns")
@patch("kseal.cli._resolve_private_key")
@patch("kseal.cli._require_secret_exists")
@patch("kseal.cli.get_secret")
@patch("kseal.cli.decode_secret_data")
@patch("kseal.cli.ensure_kubeseal")
def test_view_cluster(mock_ensure, mock_dec, mock_get, mock_req, mock_resolve, mock_ext, mock_load):
    mock_resolve.return_value = None
    mock_load.return_value = {"metadata": {"name": "test"}}
    mock_ext.return_value = ("test", "default")
    mock_get.return_value = {"data": {"A": "B"}}
    mock_dec.return_value = {"A": "val"}
    
    view("test.yaml")
    mock_get.assert_called_once()
    mock_dec.assert_called_once()

@patch("kseal.cli._load_sealed_secret")
@patch("kseal.cli._extract_name_ns")
@patch("kseal.cli._resolve_private_key")
@patch("kseal.cli.get_secret")
@patch("kseal.cli._require_secret_exists")
@patch("kseal.cli.decode_secret_data")
@patch("kseal.cli.open_editor")
@patch("kseal.cli.yaml.safe_load")
@patch("kseal.cli._smart_seal")
@patch("kseal.cli.save_yaml")
@patch("kseal.cli.ensure_kubeseal")
def test_edit_cluster(
    mock_ensure, mock_save, mock_smart, mock_load_y, mock_editor, mock_dec, mock_req, mock_get, mock_res, mock_ext, mock_load
):
    mock_res.return_value = None
    mock_load.return_value = {"metadata": {"name": "test"}}
    mock_ext.return_value = ("test", "default")
    mock_get.return_value = {"data": {"A": "B"}}
    mock_dec.return_value = {"A": "val"}
    mock_load_y.return_value = {"A": "val2"}
    mock_smart.return_value = {"kind": "SealedSecret"}
    
    from kseal.cli import edit
    edit("test.yaml")
    
    mock_editor.assert_called_once()
    mock_smart.assert_called_once()
    mock_save.assert_called_once()

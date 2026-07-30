import pytest
import os
from unittest.mock import patch, MagicMock

from kseal.installer import (
    is_kubeseal_installed,
    _get_os_arch,
    _get_latest_version,
    _get_install_dir,
    ensure_kubeseal,
)

@patch("kseal.installer.shutil.which")
def test_is_kubeseal_installed(mock_which):
    mock_which.return_value = "/some/path/kubeseal"
    assert is_kubeseal_installed() is True
    
    mock_which.return_value = None
    assert is_kubeseal_installed() is False


@patch("kseal.installer.platform.system")
@patch("kseal.installer.platform.machine")
def test_get_os_arch_darwin(mock_machine, mock_system):
    mock_system.return_value = "Darwin"
    mock_machine.return_value = "arm64"
    assert _get_os_arch() == ("darwin", "arm64")


@patch("kseal.installer.platform.system")
@patch("kseal.installer.platform.machine")
def test_get_os_arch_linux(mock_machine, mock_system):
    mock_system.return_value = "Linux"
    mock_machine.return_value = "x86_64"
    assert _get_os_arch() == ("linux", "amd64")


@patch("kseal.installer.platform.system")
def test_get_os_arch_unsupported_os(mock_system):
    mock_system.return_value = "Windows"
    with pytest.raises(RuntimeError, match="Unsupported OS"):
        _get_os_arch()


@patch("kseal.installer.requests.get")
def test_get_latest_version(mock_get):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"tag_name": "v0.27.1"}
    mock_get.return_value = mock_resp
    assert _get_latest_version() == "0.27.1"


@patch("kseal.installer.Path.home")
def test_get_install_dir(mock_home, tmp_path):
    mock_home.return_value = tmp_path
    res = _get_install_dir()
    assert str(res) == str(tmp_path / ".local" / "bin")
    assert res.is_dir()


@patch("kseal.installer.shutil.which")
def test_ensure_kubeseal_already_installed(mock_which):
    mock_which.return_value = "/usr/local/bin/kubeseal"
    assert ensure_kubeseal() == "/usr/local/bin/kubeseal"


@patch("kseal.installer.shutil.which")
@patch("kseal.installer._get_os_arch")
@patch("kseal.installer._get_latest_version")
@patch("kseal.installer.requests.get")
@patch("kseal.installer.tarfile.open")
@patch("kseal.installer._get_install_dir")
@patch("kseal.installer.shutil.copy2")
@patch("kseal.installer.os.chmod")
def test_ensure_kubeseal_installs(
    mock_chmod,
    mock_copy,
    mock_get_install_dir,
    mock_tar,
    mock_req_get,
    mock_latest,
    mock_os_arch,
    mock_which,
    tmp_path,
):
    mock_which.return_value = None
    mock_os_arch.return_value = ("linux", "amd64")
    mock_latest.return_value = "0.27.1"
    
    mock_resp = MagicMock()
    mock_resp.iter_content.return_value = [b"chunk1", b"chunk2"]
    mock_req_get.return_value = mock_resp
    
    mock_get_install_dir.return_value = tmp_path / "bin"
    
    res = ensure_kubeseal()
    
    mock_copy.assert_called_once()
    mock_chmod.assert_called_once()
    assert res == str(tmp_path / "bin" / "kubeseal")


@patch("kseal.installer.shutil.which")
def test_ensure_kubeseal_fails(mock_which):
    mock_which.return_value = None
    with patch("kseal.installer._get_os_arch", side_effect=Exception("network error")):
        with pytest.raises(RuntimeError, match="Failed to install kubeseal: network error"):
            ensure_kubeseal()

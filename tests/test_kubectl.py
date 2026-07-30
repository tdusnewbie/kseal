import pytest
from unittest.mock import patch, MagicMock
from kseal.kubectl import _run, get_secret, secret_exists

@patch("kseal.kubectl.subprocess.run")
def test_run_success(mock_run):
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "output"
    mock_run.return_value = mock_result

    res = _run(["get", "pods"], context="my-context")
    assert res == "output"
    
    cmd = mock_run.call_args[0][0]
    assert cmd == ["kubectl", "--context", "my-context", "get", "pods"]


@patch("kseal.kubectl.subprocess.run")
def test_run_failure(mock_run):
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "error message"
    mock_run.return_value = mock_result

    with pytest.raises(RuntimeError, match="error message"):
        _run(["get", "pods"])


@patch("kseal.kubectl._run")
def test_get_secret(mock_run):
    mock_run.return_value = "kind: Secret\ndata:\n  key: val"
    res = get_secret("my-secret", "default")
    
    mock_run.assert_called_once_with(["get", "secret", "my-secret", "-n", "default", "-o", "yaml"], context=None)
    assert res["kind"] == "Secret"


@patch("kseal.kubectl._run")
def test_secret_exists_true(mock_run):
    mock_run.return_value = "ok"
    assert secret_exists("my-secret", "default") is True


@patch("kseal.kubectl._run")
def test_secret_exists_false(mock_run):
    mock_run.side_effect = RuntimeError("not found")
    assert secret_exists("my-secret", "default") is False

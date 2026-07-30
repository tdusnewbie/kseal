import pytest
from unittest.mock import patch, MagicMock

from kseal.kubeseal import _detect_controller, seal, unseal_local


def test_detect_controller_success():
    mock_kubectl_output = """
    {
        "items": [
            {
                "metadata": {
                    "name": "sealed-secrets-controller",
                    "namespace": "kube-system"
                }
            }
        ]
    }
    """
    with patch("subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = mock_kubectl_output
        mock_run.return_value = mock_result
        
        name, ns = _detect_controller()
        assert name == "sealed-secrets-controller"
        assert ns == "kube-system"


def test_detect_controller_no_match():
    mock_kubectl_output = """
    {
        "items": [
            {
                "metadata": {
                    "name": "some-other-service",
                    "namespace": "default"
                }
            }
        ]
    }
    """
    with patch("subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = mock_kubectl_output
        mock_run.return_value = mock_result
        
        with pytest.raises(RuntimeError, match="Could not auto-detect"):
            _detect_controller()


@patch("kseal.kubeseal.subprocess.run")
def test_seal_offline_with_cert(mock_run):
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "kind: SealedSecret\n"
    mock_run.return_value = mock_result
    
    secret_manifest = {"apiVersion": "v1", "kind": "Secret"}
    
    # When cert is passed, it should NOT try to detect the controller
    with patch("kseal.kubeseal._detect_controller") as mock_detect:
        result = seal(secret_manifest, cert="public.pem")
        
        mock_detect.assert_not_called()
        cmd = mock_run.call_args[0][0]
        assert "--cert" in cmd
        assert "public.pem" in cmd
        assert "--controller-name" not in cmd


@patch("kseal.kubeseal.subprocess.run")
def test_unseal_local(mock_run, tmp_path):
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "kind: Secret\nmetadata:\n  name: test\n"
    mock_run.return_value = mock_result
    
    sealed_file = tmp_path / "sealed.yaml"
    sealed_file.write_text("kind: SealedSecret\n")
    
    result = unseal_local(str(sealed_file), "private.key")
    
    cmd = mock_run.call_args[0][0]
    assert "--recovery-unseal" in cmd
    assert "--recovery-private-key" in cmd
    assert "private.key" in cmd
    
    assert result["kind"] == "Secret"
    assert result["metadata"]["name"] == "test"

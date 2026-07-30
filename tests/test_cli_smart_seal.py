import pytest
from unittest.mock import patch, MagicMock

from kseal.cli import _smart_seal


def test_smart_seal_no_changes():
    # If no keys change, the encryptedData should remain exactly the same
    old_manifest = {
        "apiVersion": "bitnami.com/v1alpha1",
        "kind": "SealedSecret",
        "metadata": {"name": "test", "namespace": "default"},
        "spec": {
            "encryptedData": {
                "key1": "cipher1",
                "key2": "cipher2"
            }
        }
    }
    
    old_plain = {"key1": "val1", "key2": "val2"}
    new_plain = {"key1": "val1", "key2": "val2"}
    
    # Should not even call ks.seal
    with patch("kseal.cli.ks.seal") as mock_seal:
        new_manifest = _smart_seal(
            old_manifest, old_plain, new_plain,
            "test", "default", "strict", None, None, "kubeseal", None, None
        )
        
        mock_seal.assert_not_called()
        assert new_manifest["spec"]["encryptedData"]["key1"] == "cipher1"
        assert new_manifest["spec"]["encryptedData"]["key2"] == "cipher2"


def test_smart_seal_with_changes():
    old_manifest = {
        "apiVersion": "bitnami.com/v1alpha1",
        "kind": "SealedSecret",
        "metadata": {"name": "test", "namespace": "default"},
        "spec": {
            "encryptedData": {
                "key1": "cipher1",
                "key2": "cipher2"
            }
        }
    }
    
    old_plain = {"key1": "val1", "key2": "val2"}
    # key1 unchanged, key2 changed, key3 added, key4 deleted
    new_plain = {"key1": "val1", "key2": "new_val2", "key3": "val3"}
    
    def fake_ks_seal(plain_secret, **kwargs):
        # Fake kubeseal just returns base64 of the new plaintexts wrapped in a SealedSecret
        sealed = {}
        for k in plain_secret["data"]:
            sealed[k] = f"new_cipher_for_{k}"
            
        return {
            "spec": {
                "encryptedData": sealed
            }
        }
        
    with patch("kseal.cli.ks.seal", side_effect=fake_ks_seal) as mock_seal:
        new_manifest = _smart_seal(
            old_manifest, old_plain, new_plain,
            "test", "default", "strict", None, None, "kubeseal", None, None
        )
        
        # ks.seal should only be called with the changed keys
        args, _ = mock_seal.call_args
        passed_plain_secret = args[0]
        assert "key2" in passed_plain_secret["data"]
        assert "key3" in passed_plain_secret["data"]
        assert "key1" not in passed_plain_secret["data"]
        
        # Verify the final manifest merges correctly
        encrypted = new_manifest["spec"]["encryptedData"]
        
        assert encrypted["key1"] == "cipher1"  # Preserved from old manifest
        assert encrypted["key2"] == "new_cipher_for_key2"  # New cipher
        assert encrypted["key3"] == "new_cipher_for_key3"  # New cipher
        assert "key4" not in encrypted  # Should be dropped

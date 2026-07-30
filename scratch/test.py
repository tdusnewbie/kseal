import subprocess
import yaml
import os

# Create an initial plain secret
secret = {
    "apiVersion": "v1",
    "kind": "Secret",
    "metadata": {"name": "test-secret", "namespace": "default"},
    "data": {"key1": "dmFsMQ==", "key2": "dmFsMg=="} # val1, val2
}
with open("plain.yaml", "w") as f:
    yaml.dump(secret, f)

# Seal it initially
subprocess.run(["kubeseal", "--format", "yaml"], input=open("plain.yaml").read(), text=True, stdout=open("sealed.yaml", "w"))

print("INITIAL SEALED:")
print(open("sealed.yaml").read())

# Modify plain secret: change key1, keep key2, remove key3 (if any), add key3
secret["data"]["key1"] = "bmV3dmFsMQ==" # newval1
secret["data"]["key3"] = "dmFsMw==" # val3
del secret["data"]["key2"]
with open("plain.yaml", "w") as f:
    yaml.dump(secret, f)

# Merge into sealed
subprocess.run(["kubeseal", "--format", "yaml", "--merge-into", "sealed.yaml"], input=open("plain.yaml").read(), text=True)

print("AFTER MERGE:")
print(open("sealed.yaml").read())

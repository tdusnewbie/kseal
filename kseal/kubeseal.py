"""Thin wrapper around the ``kubeseal`` CLI."""
from __future__ import annotations

import json
import subprocess
from typing import Optional

import yaml


def unseal_local(
    sealed_secret_path: str,
    private_key_path: str,
    kubeseal_path: str = "kubeseal",
) -> dict:
    """Decrypt a SealedSecret file locally using a private key — no cluster needed.

    Uses ``kubeseal --recovery-unseal --recovery-private-key`` to produce a
    plain ``v1/Secret`` dict from the encrypted file on disk.

    Parameters
    ----------
    sealed_secret_path:
        Path to the SealedSecret YAML file (the encrypted file).
    private_key_path:
        Path to the private key YAML file fetched via ``kseal fetch-key``.
    kubeseal_path:
        Path to the kubeseal binary.

    Returns
    -------
    dict
        The decrypted ``v1/Secret`` manifest (same shape as ``kubectl get secret -o yaml``).

    Raises
    ------
    RuntimeError
        If kubeseal exits with a non-zero status.
    """
    cmd = [
        kubeseal_path,
        "--recovery-unseal",
        "--recovery-private-key", private_key_path,
        "--format", "yaml",
    ]

    with open(sealed_secret_path, "r") as f:
        sealed_yaml = f.read()

    result = subprocess.run(
        cmd,
        input=sealed_yaml,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"kubeseal --recovery-unseal failed:\n{result.stderr.strip()}"
        )

    return yaml.safe_load(result.stdout)


# ---------------------------------------------------------------------------
# Controller auto-detection
# ---------------------------------------------------------------------------

def _detect_controller(context: Optional[str] = None) -> tuple[str, str]:
    """Scan the cluster for the Sealed Secrets controller service.

    Searches all namespaces for a Service whose name contains
    ``sealed-secret``.  Returns ``(name, namespace)`` for the first match.

    Raises
    ------
    RuntimeError
        If kubectl fails or no matching service is found.
    """
    cmd = ["kubectl", "get", "svc", "--all-namespaces", "-o", "json"]
    if context:
        cmd = ["kubectl", "--context", context, "get", "svc", "--all-namespaces", "-o", "json"]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"kubectl failed while auto-detecting the controller:\n{result.stderr.strip()}"
        )

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Could not parse kubectl output: {exc}") from exc

    for item in data.get("items", []):
        name = item["metadata"]["name"]
        namespace = item["metadata"]["namespace"]
        if "sealed-secret" in name.lower():
            return name, namespace

    raise RuntimeError(
        "Could not auto-detect the Sealed Secrets controller.\n"
        "No Service containing 'sealed-secret' was found in any namespace.\n\n"
        "Run:  kubectl get svc -A | grep sealed\n"
        "Then pass:  --controller-name <name> --controller-namespace <ns>"
    )


# ---------------------------------------------------------------------------
# seal()
# ---------------------------------------------------------------------------

def seal(
    secret_manifest: dict,
    scope: str = "strict",
    cert: Optional[str] = None,
    context: Optional[str] = None,
    kubeseal_path: str = "kubeseal",
    controller_name: Optional[str] = None,
    controller_namespace: Optional[str] = None,
) -> dict:
    """Pipe a plain Kubernetes Secret manifest through kubeseal.

    Returns the parsed SealedSecret dict.

    If ``controller_name`` and ``controller_namespace`` are both ``None``,
    the controller is **auto-detected** by scanning cluster services.  Pass
    explicit values to skip auto-detection.

    Parameters
    ----------
    secret_manifest:
        A plain ``v1/Secret`` manifest as a Python dict.
    scope:
        kubeseal encryption scope — ``strict``, ``namespace-wide``, or
        ``cluster-wide``.  Defaults to ``strict``.
    cert:
        Optional path to the kubeseal public certificate.  Useful in
        air-gapped environments (skips controller lookup entirely).
    context:
        Optional kubectl context to pass to kubeseal.
    kubeseal_path:
        Path to the kubeseal binary (defaults to ``"kubeseal"``).
    controller_name:
        Name of the Sealed Secrets controller Service.  Auto-detected if
        not provided.
    controller_namespace:
        Namespace where the controller lives.  Auto-detected if not
        provided.

    Raises
    ------
    RuntimeError
        If kubeseal exits with a non-zero status or auto-detection fails.
    """
    cmd = [kubeseal_path, "--format", "yaml"]

    if scope and scope != "strict":
        cmd += ["--scope", scope]

    # When a cert file is given we can seal offline — no controller lookup needed.
    if cert:
        cmd += ["--cert", cert]
    else:
        # Auto-detect controller if not explicitly provided
        if not controller_name or not controller_namespace:
            detected_name, detected_ns = _detect_controller(context=context)
            controller_name = controller_name or detected_name
            controller_namespace = controller_namespace or detected_ns

        cmd += ["--controller-name", controller_name]
        cmd += ["--controller-namespace", controller_namespace]

    if context:
        cmd += ["--context", context]

    secret_yaml = yaml.dump(secret_manifest, default_flow_style=False, sort_keys=False)

    result = subprocess.run(
        cmd,
        input=secret_yaml,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(f"kubeseal failed:\n{result.stderr.strip()}")

    return yaml.safe_load(result.stdout)

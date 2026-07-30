"""Thin wrapper around the ``kubectl`` CLI."""
from __future__ import annotations

import subprocess
from typing import Optional

import yaml
from rich.console import Console

console = Console()


def _run(args: list[str], context: Optional[str] = None) -> str:
    """Run a kubectl command and return stdout.

    Raises
    ------
    RuntimeError
        If kubectl exits with a non-zero status.
    """
    cmd = ["kubectl"]
    if context:
        cmd += ["--context", context]
    cmd += args

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout


def get_secret(name: str, namespace: str, context: Optional[str] = None) -> dict:
    """Fetch a Kubernetes Secret and return it as a parsed dict.

    Parameters
    ----------
    name:
        The name of the Secret resource.
    namespace:
        The namespace the Secret lives in.
    context:
        Optional kubectl context override.

    Raises
    ------
    RuntimeError
        If the secret doesn't exist or kubectl fails.
    """
    output = _run(["get", "secret", name, "-n", namespace, "-o", "yaml"], context=context)
    return yaml.safe_load(output)


def secret_exists(name: str, namespace: str, context: Optional[str] = None) -> bool:
    """Return True if the named Secret exists in the cluster."""
    try:
        _run(["get", "secret", name, "-n", namespace], context=context)
        return True
    except RuntimeError:
        return False

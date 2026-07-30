"""Auto-installer for the kubeseal binary."""
from __future__ import annotations

import os
import platform
import shutil
import tarfile
import tempfile
from pathlib import Path

import requests
from rich.console import Console

console = Console()

_GITHUB_API = "https://api.github.com/repos/bitnami-labs/sealed-secrets/releases/latest"


def is_kubeseal_installed() -> bool:
    """Return True if kubeseal is already in PATH."""
    return shutil.which("kubeseal") is not None


def _get_os_arch() -> tuple[str, str]:
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "darwin":
        os_name = "darwin"
    elif system == "linux":
        os_name = "linux"
    else:
        raise RuntimeError(f"Unsupported OS: {system}")

    if machine in ("x86_64", "amd64"):
        arch = "amd64"
    elif machine in ("arm64", "aarch64"):
        arch = "arm64"
    else:
        raise RuntimeError(f"Unsupported architecture: {machine}")

    return os_name, arch


def _get_latest_version() -> str:
    """Fetch the latest kubeseal release tag from GitHub."""
    resp = requests.get(_GITHUB_API, timeout=10)
    resp.raise_for_status()
    tag = resp.json()["tag_name"]  # e.g. "v0.27.1"
    return tag.lstrip("v")


def _get_install_dir() -> Path:
    """Return ~/.local/bin, creating it if needed."""
    local_bin = Path.home() / ".local" / "bin"
    local_bin.mkdir(parents=True, exist_ok=True)
    return local_bin


def ensure_kubeseal() -> str:
    """Ensure kubeseal is installed and return the path to the binary.

    If kubeseal is already in PATH, returns that path immediately.
    Otherwise it downloads the correct release binary for the current OS/arch,
    installs it to ``~/.local/bin``, and returns the new path.

    Raises
    ------
    RuntimeError
        If the download or installation fails.
    """
    path = shutil.which("kubeseal")
    if path:
        return path

    console.print("[yellow]kubeseal not found — auto-installing...[/yellow]")

    try:
        os_name, arch = _get_os_arch()
        version = _get_latest_version()

        filename = f"kubeseal-{version}-{os_name}-{arch}.tar.gz"
        url = (
            f"https://github.com/bitnami-labs/sealed-secrets/releases/download/"
            f"v{version}/{filename}"
        )

        console.print(f"[dim]Downloading kubeseal v{version} ({os_name}/{arch})...[/dim]")

        with tempfile.TemporaryDirectory() as tmpdir:
            tar_path = os.path.join(tmpdir, filename)

            resp = requests.get(url, stream=True, timeout=120)
            resp.raise_for_status()

            with open(tar_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            with tarfile.open(tar_path, "r:gz") as tar:
                tar.extractall(tmpdir)

            binary_src = os.path.join(tmpdir, "kubeseal")
            install_dir = _get_install_dir()
            dest = install_dir / "kubeseal"

            shutil.copy2(binary_src, str(dest))
            os.chmod(dest, 0o755)

        console.print(f"[green]✓ kubeseal installed → {dest}[/green]")
        console.print(f"[dim]Ensure {install_dir} is in your PATH.[/dim]")
        return str(dest)

    except Exception as exc:
        raise RuntimeError(f"Failed to install kubeseal: {exc}") from exc

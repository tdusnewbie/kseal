"""kseal CLI — SOPS-inspired tool for managing SealedSecrets."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Annotated, List, Optional

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from kseal import kubeseal as ks
from kseal.editor import open_editor
from kseal.installer import ensure_kubeseal
from kseal.kubectl import get_secret, secret_exists
from kseal.kubeseal import unseal_local
from kseal.utils import (
    decode_secret_data,
    diff_dicts,
    encode_secret_data,
    load_yaml,
    parse_env_file,
    parse_env_pairs,
    save_yaml,
    yaml_dumps,
)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

console = Console()

app = typer.Typer(
    name="kseal",
    help="A SOPS-inspired CLI tool for managing SealedSecrets in a Kubernetes cluster.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# ---------------------------------------------------------------------------
# Re-usable option type aliases
# ---------------------------------------------------------------------------

ContextOpt = Annotated[
    Optional[str],
    typer.Option("--context", help="kubectl context override"),
]
NamespaceOpt = Annotated[
    Optional[str],
    typer.Option("--namespace", "-n", help="Namespace override"),
]
ScopeOpt = Annotated[
    str,
    typer.Option(
        "--scope",
        help="kubeseal encryption scope: [dim]strict[/dim] | namespace-wide | cluster-wide",
    ),
]
CertOpt = Annotated[
    Optional[str],
    typer.Option("--cert", help="Path to kubeseal public cert (air-gapped environments)"),
]
ControllerNameOpt = Annotated[
    Optional[str],
    typer.Option("--controller-name", help="Sealed Secrets controller name (default: sealed-secrets-controller)"),
]
ControllerNsOpt = Annotated[
    Optional[str],
    typer.Option("--controller-namespace", help="Namespace of the Sealed Secrets controller (default: kube-system)"),
]
PrivateKeyOpt = Annotated[
    Optional[str],
    typer.Option(
        "--private-key",
        help="Path to a local private key file (from 'kseal fetch-key'). "
             "Decrypts the SealedSecret file directly — no cluster connection needed.",
    ),
]
DryRunOpt = Annotated[
    bool,
    typer.Option("--dry-run", help="Print the resulting YAML without writing to disk"),
]

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_sealed_secret(filepath: str) -> dict:
    """Load a YAML file and assert it is a SealedSecret."""
    manifest = load_yaml(filepath)
    if manifest.get("kind") != "SealedSecret":
        raise typer.BadParameter(
            f"[red]{filepath}[/red] is not a SealedSecret manifest "
            f"(got kind: [bold]{manifest.get('kind', '<unknown>')}[/bold])"
        )
    return manifest


def _extract_name_ns(manifest: dict, namespace_override: Optional[str]) -> tuple[str, str]:
    """Return (name, namespace) from a manifest, with optional override."""
    meta = manifest.get("metadata", {})
    name: str = meta.get("name", "")
    if not name:
        raise RuntimeError("Could not determine secret name from manifest metadata.")
    namespace: str = namespace_override or meta.get("namespace", "default")
    return name, namespace


def _build_plain_secret(name: str, namespace: str, data: dict) -> dict:
    """Build a minimal v1/Secret manifest from decoded key-value data."""
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": name, "namespace": namespace},
        "data": encode_secret_data(data),
    }


def _print_diff(old: dict, new: dict) -> None:
    """Pretty-print a diff table between two plaintext secret dicts."""
    added = {k for k in new if k not in old}
    removed = {k for k in old if k not in new}
    changed = {k for k in new if k in old and old[k] != new[k]}

    if not added and not removed and not changed:
        console.print("[dim]No changes detected.[/dim]")
        return

    table = Table(title="Changes", show_header=True, header_style="bold magenta")
    table.add_column("Key", style="cyan", no_wrap=True)
    table.add_column("Action", justify="center")

    for k in sorted(added):
        table.add_row(k, "[green]+ added[/green]")
    for k in sorted(removed):
        table.add_row(k, "[red]- removed[/red]")
    for k in sorted(changed):
        table.add_row(k, "[yellow]~ changed[/yellow]")

    console.print(table)


def _write_sealed_secret(filepath: str, sealed: dict, dry_run: bool) -> None:
    """Either write the SealedSecret to disk or print it (dry-run)."""
    if dry_run:
        console.print(
            Panel(
                yaml_dumps(sealed),
                title="[bold yellow]Dry Run — SealedSecret[/bold yellow]",
                border_style="yellow",
            )
        )
    else:
        save_yaml(filepath, sealed)
        console.print(f"[green]✓ Written to[/green] [bold]{filepath}[/bold]")


def _require_secret_exists(name: str, ns: str, context: Optional[str]) -> None:
    """Exit with an error if the secret is not found in the cluster."""
    if not secret_exists(name, ns, context=context):
        console.print(
            f"[red]Secret [bold]{name}[/bold] not found in namespace "
            f"[bold]{ns}[/bold]. Does it exist in the cluster?[/red]"
        )
        raise typer.Exit(code=1)


def _resolve_private_key(provided_key: Optional[str]) -> Optional[str]:
    """Resolve the private key path to use, if any.
    Order of precedence:
    1. CLI arg (provided_key)
    2. KSEAL_PRIVATE_KEY env var
    3. ~/.kseal/private-key.yaml if it exists
    """
    if provided_key:
        return provided_key
    
    env_key = os.environ.get("KSEAL_PRIVATE_KEY")
    if env_key:
        return env_key
        
    default_key = Path("~/.kseal/private-key.yaml").expanduser()
    if default_key.is_file():
        return str(default_key)
        
    return None


def _smart_seal(
    manifest: dict,
    old_plaintext: dict,
    new_plaintext: dict,
    name: str,
    ns: str,
    scope: str,
    cert: Optional[str],
    context: Optional[str],
    kubeseal_path: str,
    controller_name: Optional[str],
    controller_namespace: Optional[str],
) -> dict:
    """Seal only changed keys and merge them with existing encrypted data.
    
    This prevents kubeseal from generating completely new ciphertexts for
    keys that haven't changed, avoiding huge git diffs.
    """
    changed_keys = {
        k: v for k, v in new_plaintext.items() 
        if k not in old_plaintext or old_plaintext[k] != v
    }
    
    sealed_partial = {}
    if changed_keys:
        plain_secret = _build_plain_secret(name, ns, changed_keys)
        sealed_partial = ks.seal(
            plain_secret,
            scope=scope,
            cert=cert,
            context=context,
            kubeseal_path=kubeseal_path,
            controller_name=controller_name,
            controller_namespace=controller_namespace,
        )
    
    new_manifest = dict(manifest)
    if "spec" not in new_manifest:
        new_manifest["spec"] = {}
    if "encryptedData" not in new_manifest["spec"]:
        new_manifest["spec"]["encryptedData"] = {}
    
    old_encrypted = manifest.get("spec", {}).get("encryptedData", {})
    partial_encrypted = sealed_partial.get("spec", {}).get("encryptedData", {})
    
    merged_encrypted = {}
    for k in new_plaintext:
        if k in changed_keys:
            merged_encrypted[k] = partial_encrypted[k]
        else:
            merged_encrypted[k] = old_encrypted[k]
            
    new_manifest["spec"]["encryptedData"] = merged_encrypted
    
    return new_manifest


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def edit(
    filepath: Annotated[str, typer.Argument(help="Path to the SealedSecret YAML file")],
    context: ContextOpt = None,
    namespace: NamespaceOpt = None,
    scope: ScopeOpt = "strict",
    cert: CertOpt = None,
    controller_name: ControllerNameOpt = None,
    controller_namespace: ControllerNsOpt = None,
    private_key: PrivateKeyOpt = None,
    dry_run: DryRunOpt = False,
) -> None:
    """Decrypt, edit, and re-encrypt a SealedSecret — SOPS style.

    By default, fetches the live plaintext from the cluster.
    Pass [bold]--private-key[/bold] to decrypt the file locally instead — useful when
    you have unapplied edits in the file that haven't reached the cluster yet.
    """
    kubeseal_path = ensure_kubeseal()

    manifest = _load_sealed_secret(filepath)
    name, ns = _extract_name_ns(manifest, namespace)

    # Explain the source of truth upfront so the user is never surprised
    console.print(
        f"\n[bold]Editing[/bold] [cyan]{name}[/cyan]  ·  namespace [cyan]{ns}[/cyan]\n"
    )

    private_key = _resolve_private_key(private_key)

    if private_key:
        # ── LOCAL MODE: decrypt from file using the private key ──────────────
        console.print(
            f"[dim]🔑 Local mode — decrypting file directly with private key.[/dim]\n"
        )
        secret = unseal_local(filepath, private_key, kubeseal_path=kubeseal_path)
        plaintext = decode_secret_data(secret.get("data") or {})
        source_label = f"file: {filepath}  (via private key)"
    else:
        # ── CLUSTER MODE: fetch plaintext from the live Secret ───────────────
        console.print(
            "[dim]ℹ  SealedSecrets use asymmetric encryption — the file contains only\n"
            "   ciphertext that only the cluster's private key can decrypt.\n"
            "   Plaintext values are sourced from the live cluster Secret.\n"
            "   Tip: run [bold]kseal fetch-key[/bold] once to enable local decryption.[/dim]\n"
        )
        _require_secret_exists(name, ns, context)
        console.print(f"[dim]Fetching plaintext from cluster → secret/{name} -n {ns} …[/dim]")
        secret = get_secret(name, ns, context=context)
        plaintext = decode_secret_data(secret.get("data") or {})
        source_label = f"cluster: secret/{name} -n {ns}"

    console.print(
        f"[dim]Found {len(plaintext)} key(s): {', '.join(sorted(plaintext))}[/dim]\n"
    )

    # Write plaintext to a temp file
    fd, tmp_path = tempfile.mkstemp(suffix=".yaml", prefix=f"kseal-{name}-")
    try:
        with os.fdopen(fd, "w") as tmp:
            tmp.write(yaml_dumps(plaintext))

        open_editor(tmp_path)

        with open(tmp_path, "r") as f:
            new_plaintext: dict = yaml.safe_load(f) or {}

    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    _print_diff(plaintext, new_plaintext)

    if new_plaintext == plaintext:
        console.print("[dim]No changes — nothing to do.[/dim]")
        raise typer.Exit(0)

    console.print(f"[dim]Re-sealing → {filepath} …[/dim]")
    sealed = _smart_seal(
        manifest,
        plaintext,
        new_plaintext,
        name,
        ns,
        scope=scope,
        cert=cert,
        context=context,
        kubeseal_path=kubeseal_path,
        controller_name=controller_name,
        controller_namespace=controller_namespace,
    )
    _write_sealed_secret(filepath, sealed, dry_run)



@app.command(name="set")
def set_cmd(
    filepath: Annotated[str, typer.Argument(help="Path to the SealedSecret YAML file")],
    pairs: Annotated[
        Optional[List[str]],
        typer.Argument(help="KEY=value pairs to set"),
    ] = None,
    env_file: Annotated[
        Optional[str],
        typer.Option("--env-file", help="Read KEY=value pairs from a .env file"),
    ] = None,
    from_stdin: Annotated[
        bool,
        typer.Option("--from-stdin", help="Read KEY=value pairs from stdin"),
    ] = False,
    context: ContextOpt = None,
    namespace: NamespaceOpt = None,
    scope: ScopeOpt = "strict",
    cert: CertOpt = None,
    controller_name: ControllerNameOpt = None,
    controller_namespace: ControllerNsOpt = None,
    dry_run: DryRunOpt = False,
) -> None:
    """Set or update keys in a SealedSecret non-interactively.

    Pairs can come from positional [bold]KEY=value[/bold] arguments, an
    [bold]--env-file[/bold], or [bold]--from-stdin[/bold] (all are merged).
    The existing cluster values are fetched first so unchanged keys are
    preserved.
    """
    kubeseal_path = ensure_kubeseal()

    manifest = _load_sealed_secret(filepath)
    name, ns = _extract_name_ns(manifest, namespace)

    # Collect overrides from all sources
    overrides: dict = {}
    if pairs:
        overrides.update(parse_env_pairs(pairs))
    if env_file:
        overrides.update(parse_env_file(env_file))
    if from_stdin:
        raw = sys.stdin.read()
        overrides.update(parse_env_pairs(raw.splitlines()))

    if not overrides:
        console.print("[yellow]No key=value pairs provided — nothing to do.[/yellow]")
        raise typer.Exit(0)

    # Fetch existing values (best-effort; if secret doesn't exist yet, start fresh)
    plaintext: dict = {}
    if secret_exists(name, ns, context=context):
        secret = get_secret(name, ns, context=context)
        plaintext = decode_secret_data(secret.get("data") or {})

    old = dict(plaintext)
    plaintext.update(overrides)

    _print_diff(old, plaintext)

    sealed = _smart_seal(
        manifest,
        old,
        plaintext,
        name,
        ns,
        scope=scope,
        cert=cert,
        context=context,
        kubeseal_path=kubeseal_path,
        controller_name=controller_name,
        controller_namespace=controller_namespace,
    )
    _write_sealed_secret(filepath, sealed, dry_run)


@app.command()
def view(
    filepath: Annotated[str, typer.Argument(help="Path to the SealedSecret YAML file")],
    context: ContextOpt = None,
    namespace: NamespaceOpt = None,
    private_key: PrivateKeyOpt = None,
) -> None:
    """Decrypt and display all secret values.

    By default reads from the cluster. Pass [bold]--private-key[/bold] to
    decrypt the file locally instead.

    [bold yellow]⚠[/bold yellow]  Values are printed to stdout only — nothing is written to disk.
    """
    kubeseal_path = ensure_kubeseal()
    manifest = _load_sealed_secret(filepath)
    name, ns = _extract_name_ns(manifest, namespace)

    private_key = _resolve_private_key(private_key)

    if private_key:
        console.print(f"[dim]🔑 Local mode — decrypting file directly with private key.[/dim]")
        secret = unseal_local(filepath, private_key, kubeseal_path=kubeseal_path)
        plaintext = decode_secret_data(secret.get("data") or {})
    else:
        _require_secret_exists(name, ns, context)
        secret = get_secret(name, ns, context=context)
        plaintext = decode_secret_data(secret.get("data") or {})

    table = Table(
        title=f"[bold cyan]{name}[/bold cyan]  ·  ns: [bold]{ns}[/bold]",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Key", style="cyan", no_wrap=True)
    table.add_column("Value")

    for k, v in sorted(plaintext.items()):
        table.add_row(k, v)

    console.print(table)


@app.command()
def create(
    filepath: Annotated[str, typer.Argument(help="Output path for the new SealedSecret YAML file")],
    pairs: Annotated[
        Optional[List[str]],
        typer.Argument(help="KEY=value pairs"),
    ] = None,
    name: Annotated[
        Optional[str],
        typer.Option("--name", help="Secret name (defaults to the output filename stem)"),
    ] = None,
    env_file: Annotated[
        Optional[str],
        typer.Option("--env-file", help="Read KEY=value pairs from a .env file"),
    ] = None,
    context: ContextOpt = None,
    namespace: NamespaceOpt = None,
    scope: ScopeOpt = "strict",
    cert: CertOpt = None,
    controller_name: ControllerNameOpt = None,
    controller_namespace: ControllerNsOpt = None,
    dry_run: DryRunOpt = False,
) -> None:
    """Create a brand-new SealedSecret YAML from scratch.

    Builds a plain Kubernetes Secret in memory, seals it with kubeseal,
    and writes the result to [bold]filepath[/bold].
    """
    kubeseal_path = ensure_kubeseal()

    secret_name = name or Path(filepath).stem
    ns = namespace or "default"

    data: dict = {}
    if pairs:
        data.update(parse_env_pairs(pairs))
    if env_file:
        data.update(parse_env_file(env_file))

    if not data:
        console.print(
            "[red]No key=value pairs provided. "
            "Pass positional KEY=value args or use --env-file.[/red]"
        )
        raise typer.Exit(1)

    console.print(
        f"Creating SealedSecret [cyan]{secret_name}[/cyan] "
        f"in namespace [cyan]{ns}[/cyan] …"
    )

    plain_secret = _build_plain_secret(secret_name, ns, data)
    sealed = ks.seal(
        plain_secret,
        scope=scope,
        cert=cert,
        context=context,
        kubeseal_path=kubeseal_path,
        controller_name=controller_name,
        controller_namespace=controller_namespace,
    )
    _write_sealed_secret(filepath, sealed, dry_run)

    if not dry_run:
        console.print(
            f"[green]✓ SealedSecret [bold]{secret_name}[/bold] created.[/green]"
        )


@app.command()
def delete(
    filepath: Annotated[str, typer.Argument(help="Path to the SealedSecret YAML file")],
    keys: Annotated[List[str], typer.Argument(help="Keys to remove from the secret")],
    context: ContextOpt = None,
    namespace: NamespaceOpt = None,
    scope: ScopeOpt = "strict",
    cert: CertOpt = None,
    controller_name: ControllerNameOpt = None,
    controller_namespace: ControllerNsOpt = None,
    dry_run: DryRunOpt = False,
) -> None:
    """Remove one or more keys from a SealedSecret.

    Fetches the live plaintext, drops the specified keys, re-seals the
    remaining values, and updates the YAML file in place.
    """
    kubeseal_path = ensure_kubeseal()

    manifest = _load_sealed_secret(filepath)
    name, ns = _extract_name_ns(manifest, namespace)

    _require_secret_exists(name, ns, context)

    secret = get_secret(name, ns, context=context)
    plaintext = decode_secret_data(secret.get("data") or {})

    old = dict(plaintext)
    for key in keys:
        if key not in plaintext:
            console.print(f"[yellow]Key [bold]{key}[/bold] not found — skipping.[/yellow]")
        else:
            del plaintext[key]

    _print_diff(old, plaintext)

    if plaintext == old:
        console.print("[dim]No changes — nothing to do.[/dim]")
        raise typer.Exit(0)

    sealed = _smart_seal(
        manifest,
        old,
        plaintext,
        name,
        ns,
        scope=scope,
        cert=cert,
        context=context,
        kubeseal_path=kubeseal_path,
        controller_name=controller_name,
        controller_namespace=controller_namespace,
    )
    _write_sealed_secret(filepath, sealed, dry_run)


@app.command(name="fetch-key")
def fetch_key(
    output: Annotated[
        str,
        typer.Option(
            "--output", "-o",
            help="Where to save the private key YAML file.",
        ),
    ] = "~/.kseal/private-key.yaml",
    context: ContextOpt = None,
    controller_name: ControllerNameOpt = None,
    controller_namespace: ControllerNsOpt = None,
) -> None:
    """Download the Sealed Secrets private key from the cluster for local decryption.

    Saves the private key to [bold]--output[/bold] (default: [dim]~/.kseal/private-key.yaml[/dim]).
    Once downloaded, pass it to [bold]edit[/bold] and [bold]view[/bold] via [bold]--private-key[/bold]
    to decrypt SealedSecret files locally \u2014 no cluster connection required.

    [bold red]\u26a0  SECURITY:[/bold red] The private key can decrypt ALL your SealedSecrets.
    [bold red]   Never commit it to git. Keep it outside your repository.[/bold red]
    """
    from kseal.kubectl import _run  # noqa: PLC0415

    dest = Path(output).expanduser()
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Auto-detect controller if not specified
    if not controller_name or not controller_namespace:
        console.print("[dim]Auto-detecting Sealed Secrets controller…[/dim]")
        detected_name, detected_ns = ks._detect_controller(context=context)
        controller_name = controller_name or detected_name
        controller_namespace = controller_namespace or detected_ns
        console.print(
            f"[dim]Found controller: [bold]{controller_name}[/bold] "
            f"in namespace [bold]{controller_namespace}[/bold][/dim]"
        )

    console.print(
        f"[dim]Fetching private key from namespace [bold]{controller_namespace}[/bold]…[/dim]"
    )

    # Sealed Secrets stores its key pair(s) as Secrets labelled with this label
    raw = _run(
        [
            "get", "secret",
            "-n", controller_namespace,
            "-l", "sealedsecrets.bitnami.com/sealed-secrets-key",
            "-o", "yaml",
        ],
        context=context,
    )

    dest.write_text(raw)
    console.print(f"[green]\u2713 Private key saved \u2192 {dest}[/green]")
    console.print()
    console.print(
        "[bold yellow]\u26a0  Keep this file secret \u2014 it can decrypt ALL your SealedSecrets.[/bold yellow]\n"
        f"[dim]   Add to .gitignore:  {dest}[/dim]\n"
        "[dim]   Recommended chmod:  chmod 600 " + str(dest) + "[/dim]"
    )
    import os as _os
    _os.chmod(dest, 0o600)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    app()


# kseal — Plan

> A SOPS-inspired CLI tool for managing SealedSecrets in a k3s cluster, without the painful manual encrypt/decrypt cycle.

---

## Problem

Working with `sealed-secrets` in a k3s GitOps repo is painful:
- Adding a new key to an existing SealedSecret requires decrypt → edit → re-encrypt → commit
- There's no easy way to view what's currently sealed
- Creating a new secret from scratch requires multiple `kubectl` and `kubeseal` commands

---

## Goals

- **SOPS-like UX** — `kseal edit myservice.yaml` just works
- **Self-contained** — auto-installs `kubeseal` if not present
- **Git-repo-friendly** — reads and writes local YAML manifest files
- **No plaintext on disk** — decrypted values only live in `/tmp`, cleaned up on exit
- **Single entry point** — one `kseal` command covers all workflows

---

## Prerequisites (auto-handled)

| Tool | How |
|---|---|
| `kubectl` | Must already be in PATH (user's responsibility) |
| `kubeseal` | Auto-detected; auto-installed if missing |
| Python `>=3.8` | Runtime for the tool itself |
| `cryptography`, `PyYAML`, `rich` | pip dependencies, installed via `setup.py` |

---

## Project Structure

```
kseal/
├── kseal/
│   ├── __init__.py
│   ├── cli.py            # argparse / click entry point
│   ├── installer.py      # kubeseal auto-install logic
│   ├── kubeseal.py       # wrapper around kubeseal binary
│   ├── kubectl.py        # wrapper around kubectl
│   ├── editor.py         # open $EDITOR with temp file, watch for save
│   └── utils.py          # YAML helpers, base64, formatting
├── setup.py              # pip install -e .
├── README.md
└── PLAN.md               # this file
```

---

## Commands

### `kseal edit <file.yaml>`
**SOPS-style in-place edit of an existing SealedSecret.**

Flow:
1. Read `file.yaml` — extract `namespace` + `name`
2. `kubectl get secret <name> -n <namespace> -o yaml` → fetch plaintext from cluster
3. Decode base64 values → write to `/tmp/kseal-<name>-XXXX.yaml`
4. Open `$EDITOR` (fallback: `vi`)
5. On save+quit → diff to detect changes
6. `kubeseal` re-encrypts changed/new keys
7. Merge back into `file.yaml` (preserving existing structure)
8. Delete temp file

---

### `kseal set <file.yaml> KEY=value [KEY=value ...]`
**Set or update one or more keys non-interactively.**

Flow:
1. Read `file.yaml` — extract `namespace` + `name`
2. Fetch plaintext from cluster (same as `edit`)
3. Apply `KEY=value` overrides
4. `kubeseal` re-encrypts the full secret
5. Write back to `file.yaml`

Useful for CI/CD pipelines.

---

### `kseal view <file.yaml>`
**Decrypt and display all secret values from the cluster.**

Flow:
1. Read `file.yaml` — extract `namespace` + `name`
2. `kubectl get secret <name> -n <namespace> -o yaml`
3. Decode base64 → pretty-print with `rich`

> ⚠️ Plaintext is printed to stdout only. Nothing is written to disk.

---

### `kseal create <file.yaml> -n <namespace> --name <secret-name> KEY=value [...]`
**Create a brand-new SealedSecret YAML from scratch.**

Flow:
1. Build a plain Kubernetes `Secret` manifest in memory
2. Pipe to `kubeseal` → get encrypted `SealedSecret`
3. Write to `file.yaml`

---

## kubeseal Auto-Installer (`installer.py`)

On every startup, `kseal` checks: `which kubeseal`.

If not found:
1. Detect OS (`darwin`, `linux`) and arch (`amd64`, `arm64`)
2. Fetch latest release tag from GitHub API:
   `https://api.github.com/repos/bitnami-labs/sealed-secrets/releases/latest`
3. Download the appropriate binary:
   `https://github.com/bitnami-labs/sealed-secrets/releases/download/v{version}/kubeseal-{version}-{os}-{arch}.tar.gz`
4. Extract + move to `~/.local/bin/kubeseal` (or `/usr/local/bin` if writable)
5. Confirm installation with a success message

---

## Encryption Scope

`kubeseal` supports three scopes. We'll default to `strict` (tied to secret name + namespace) and allow override via `--scope` flag:

| Scope | Tied to |
|---|---|
| `strict` (default) | name + namespace |
| `namespace-wide` | namespace only |
| `cluster-wide` | anything |

---

## UX Details

- Uses `rich` for colored output, tables, and progress spinners
- Respects `$EDITOR` env var, falls back to `vi` → `nano` → `vim`
- `--dry-run` flag on all write commands (print diff without saving)
- `--context` flag to override `kubectl` context
- `--namespace` / `-n` flag where applicable
- Clear error messages when the secret doesn't exist in the cluster yet

---

## Open Questions

- [ ] Should `kseal edit` work even if the secret doesn't exist in the cluster yet (i.e., create mode as fallback)?
- [ ] Should we support fetching the cert offline (from a file) for air-gapped environments?
- [ ] Do we need a `kseal delete KEY <file.yaml>` to remove a key from a SealedSecret?
- [ ] Should `kseal set` support reading values from stdin or a `.env` file?

---

## Out of Scope (for now)

- Web UI
- Multi-cluster support
- Secret rotation automation
- Vault / external secret backend integration

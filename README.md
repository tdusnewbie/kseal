# kseal

`kseal` is a developer-friendly, SOPS-inspired CLI wrapper for Bitnami's `kubeseal`. It takes the pain out of managing Kubernetes SealedSecrets in GitOps workflows by allowing you to edit, view, and manipulate encrypted secrets as easily as plain YAML.

### ✨ Key Features

* **SOPS-style Editing:** Run `kseal edit my-secret.yaml` to decrypt base64 values, open them in your `$EDITOR` as plain text, and automatically re-seal them on save.
* **Smart Diff Sealing:** `kseal` calculates diffs on save and *only* re-encrypts the keys you actually changed. This prevents `kubeseal`'s default behavior of regenerating every ciphertext, keeping your Git diffs clean and readable!
* **True Offline Mode:** Run `kseal fetch-key` once to grab the controller's private key, then edit and view your secrets completely offline using `--private-key`.
* **Zero-Config Controller Detection:** Automatically scans your cluster to find the `sealed-secrets-controller` namespace and service name so you don't have to pass annoying flags.
* **CLI Key Management:** Add or remove keys instantly with `kseal set` and `kseal delete` without ever opening an editor.
* **Neovim Integration:** Includes `kseal.nvim`, a native Lua plugin that automatically decrypts SealedSecrets when you open them in Neovim and re-seals them when you write the buffer.
* **Auto-Install:** Automatically fetches and installs the correct `kubeseal` binary for your OS/Architecture if it's missing from your system.

---

## Installation

You can install `kseal` globally using `uv`. Since it is published to a custom Forgejo package registry, use the `--index-url` flag:

```bash
# Install from the Forgejo PyPI registry
uv tool install --index-url https://git.local.tdusnewbie.com/api/packages/tdusnewbie/pypi/simple/ kseal
```

*(Note: If your registry is strictly private, you may need to pass credentials in the URL: `https://<user>:<token>@git.local...`)*

Alternatively, you can always install it directly from the Git repository:
```bash
uv tool install git+ssh://git@git.local.tdusnewbie.com:2222/tdusnewbie/kseal.git
```

*The CLI will automatically download the correct `kubeseal` binary for your OS and architecture on first run if it's not already installed.*

---

## The Offline Workflow (Recommended)

By default, `kseal` requires active cluster access to decrypt the secrets. But if you want a fully offline, ultra-fast workflow (perfect for unapplied local edits):

1. **Fetch the key once (needs cluster access):**
   ```bash
   kseal fetch-key
   # Saves to ~/.kseal/private-key.yaml and auto-secures permissions.
   ```
   *(Be sure to add `~/.kseal/private-key.yaml` to your global `.gitignore`)*

2. **Edit and View Offline forever:**
   Once fetched, `kseal edit` and `kseal view` will automatically detect `~/.kseal/private-key.yaml` and decrypt files directly on your machine without touching the cluster!

---

## Usage

### Edit a SealedSecret
Decrypts the current SealedSecret, opens the plaintext in your editor, and re-encrypts only the changed values on save.

```bash
kseal edit my-secret.yaml
```

### View plaintext
View the decrypted values of a SealedSecret securely in your terminal (never written to disk).

```bash
kseal view my-secret.yaml
```

### Set key-value pairs
Update or add keys without opening an editor.

```bash
kseal set my-secret.yaml API_KEY=12345
kseal set my-secret.yaml --env-file .env
```

### Create a new SealedSecret
Create a new encrypted SealedSecret file from scratch.

```bash
kseal create new-secret.yaml -n default --name my-app-secret API_KEY=123
```

### Delete keys
Remove keys from a SealedSecret.

```bash
kseal delete my-secret.yaml API_KEY
```

---

## Global Flags

Available on all commands:
- `--private-key <path>`: Force path to local private key for offline mode (auto-detected if in `~/.kseal/private-key.yaml` or `KSEAL_PRIVATE_KEY` env var)
- `--context <ctx>`: kubectl context override
- `-n, --namespace <ns>`: override namespace
- `--controller-name <name>`: override auto-detected controller service name
- `--controller-namespace <ns>`: override auto-detected controller namespace
- `--scope <strict|namespace-wide|cluster-wide>`: kubeseal scope (default: `strict`)
- `--cert <path>`: path to kubeseal public cert file (for air-gapped environments)
- `--dry-run`: on write commands, print diff but don't save to file

---

## Neovim Integration (`kseal.nvim`)

This repository also includes a native Neovim plugin `kseal.nvim` that allows you to seamlessly read and write SealedSecret files directly inside Neovim buffers.

Because the plugin is housed in a subdirectory of this repository (`kseal.nvim/`), here is how you install it using **lazy.nvim**:

```lua
{
    "tdusnewbie/kseal",
    url = "ssh://git@git.local.tdusnewbie.com:2222/tdusnewbie/kseal.git",
    config = function(plugin)
        -- 1. Add the subdirectory to Neovim's runtimepath
        vim.opt.rtp:append(plugin.dir .. "/kseal.nvim")
        
        -- 2. Setup the plugin
        require("kseal").setup({
            -- Optional: point to your locally fetched private key for offline decryption
            -- private_key_path = vim.fn.expand("~/.kseal/private-key.yaml") 
        })
    end
}
```

When you open a file with `kind: SealedSecret` in Neovim, it will instantly render as decrypted plaintext. When you `:w`, it will smartly re-encrypt your changes back to disk!

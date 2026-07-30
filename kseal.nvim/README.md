# kseal.nvim

A Neovim plugin for managing [SealedSecrets](https://github.com/bitnami-labs/sealed-secrets) via the [`kseal`](../README.md) CLI — SOPS-style, without leaving your editor.

## Requirements

- Neovim ≥ 0.10
- [`kseal`](../README.md) installed and in `PATH` (`uv tool install .`)
- `kubectl` configured and in `PATH`

## Installation

### [lazy.nvim](https://github.com/folke/lazy.nvim)

```lua
{
  -- local path (while developing alongside kseal)
  dir = "~/path/to/kseal/kseal.nvim",
  -- or from GitHub once published:
  -- "your-user/kseal.nvim",
  ft = { "yaml" },
  config = function()
    require("kseal").setup()
  end,
}
```

### [packer.nvim](https://github.com/wbthomason/packer.nvim)

```lua
use {
  "~/path/to/kseal/kseal.nvim",
  config = function()
    require("kseal").setup()
  end,
}
```

## Configuration

All options are optional — the defaults work out of the box.

```lua
require("kseal").setup({
  -- Default flags forwarded to every kseal command
  defaults = {
    scope     = "strict",   -- "strict" | "namespace-wide" | "cluster-wide"
    context   = nil,        -- kubectl context override (string)
    namespace = nil,        -- namespace override (string)
    cert      = nil,        -- path to kubeseal public cert for air-gapped envs
  },

  keymaps = {
    enabled = true,
    prefix  = "<leader>k",  -- change to any prefix you like
  },

  -- Scan YAML buffers on open; auto-attach keymaps when SealedSecret detected
  auto_detect = true,

  -- Show a notification when a SealedSecret file is opened
  notify_on_detect = true,
})
```

## Commands

All commands are available globally. Buffer-local keymaps are also auto-registered when a SealedSecret YAML is opened (if `auto_detect = true`).

| Command        | Keymap         | Description                                              |
|----------------|----------------|----------------------------------------------------------|
| `:KsealView`   | `<leader>kv`   | Decrypt and display all values in a floating terminal    |
| `:KsealEdit`   | `<leader>ke`   | Edit the secret — plaintext opens in *this* nvim session |
| `:KsealSet`    | `<leader>ks`   | Set / update KEY=value pairs (prompts for input)         |
| `:KsealDelete` | `<leader>kd`   | Delete keys (prompts for input)                          |
| `:KsealCreate` | `<leader>kc`   | Create a new SealedSecret (guided prompts)               |

## How `KsealEdit` works

This is the most useful command. The workflow:

1. Press `<leader>ke` on a SealedSecret YAML file.
2. `kseal edit` fetches the live plaintext from the cluster and writes it to a temp file.
3. Because `EDITOR` is set to `nvim --server <socket> --remote-wait`, the temp file opens as a **new buffer in your existing nvim session** — no new terminal, no nested nvim.
4. Edit the values normally. Multiline values (PEM certs, SSH keys) are displayed with YAML `|` block style.
5. When done: `:w` to save, then `:bd` to close the buffer.
6. `kseal` detects the file was saved, re-seals the secret, and writes the new `SealedSecret` back to the original YAML file.
7. The original buffer is automatically reloaded.

> **Note:** For this to work, nvim must be started with a server socket. Most modern setups (e.g. `$NVIM_LISTEN_ADDRESS`, or starting with `nvim --listen`) do this automatically. If not, a terminal split fallback is used.

## Tips

- Use `--dry-run` behaviour via the `defaults` config to preview changes without writing:
  ```lua
  -- Not directly supported via defaults yet; use `:terminal kseal edit --dry-run <file>` for now.
  ```
- Override namespace for a single session:
  ```lua
  require("kseal").config.defaults.namespace = "staging"
  ```
- Works great alongside [telescope.nvim](https://github.com/nvim-telescope/telescope.nvim) for file picking.

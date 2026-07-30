--- kseal.nvim — Public API and setup
--- Call require("kseal").setup({}) in your nvim config.

local M = {}
local commands = require("kseal.commands")

-- ---------------------------------------------------------------------------
-- Default configuration
-- ---------------------------------------------------------------------------

M.config = {
  --- Default flags forwarded to every kseal command.
  defaults = {
    scope     = "strict",   -- "strict" | "namespace-wide" | "cluster-wide"
    context   = nil,        -- kubectl context override
    namespace = nil,        -- namespace override
    cert      = nil,        -- path to kubeseal public cert (air-gapped)
  },

  --- Keymap settings.
  keymaps = {
    enabled = true,
    --- All buffer-local keymaps use this prefix.
    --- Default mappings:
    ---   <prefix>v  →  KsealView
    ---   <prefix>e  →  KsealEdit
    ---   <prefix>s  →  KsealSet
    ---   <prefix>d  →  KsealDelete
    ---   <prefix>c  →  KsealCreate
    prefix = "<leader>k",
  },

  --- When true, automatically scan YAML buffers on open and attach
  --- keymaps/commands when `kind: SealedSecret` is detected.
  auto_detect = true,

  --- When true, show a small notification when a SealedSecret file is opened.
  notify_on_detect = true,
}

-- ---------------------------------------------------------------------------
-- Setup
-- ---------------------------------------------------------------------------

--- Configure and initialise kseal.nvim.
---
--- Example (lazy.nvim):
---   {
---     "your-user/kseal.nvim",
---     ft = { "yaml" },
---     config = function()
---       require("kseal").setup({
---         defaults = { scope = "strict" },
---         keymaps  = { prefix = "<leader>k" },
---       })
---     end,
---   }
---
--- @param user_config table|nil  Partial config — merged with the defaults above.
function M.setup(user_config)
  M.config = vim.tbl_deep_extend("force", M.config, user_config or {})

  -- Global user commands (work from any buffer via :KsealCreate, etc.)
  vim.api.nvim_create_user_command("KsealView", function()
    commands.view(nil, M.config.defaults)
  end, { desc = "kseal: view decrypted SealedSecret values" })

  vim.api.nvim_create_user_command("KsealEdit", function()
    commands.edit(nil, M.config.defaults)
  end, { desc = "kseal: edit SealedSecret (opens plaintext in this nvim instance)" })

  vim.api.nvim_create_user_command("KsealSet", function()
    commands.set_keys(nil, M.config.defaults)
  end, { desc = "kseal: set KEY=value pairs on a SealedSecret" })

  vim.api.nvim_create_user_command("KsealDelete", function()
    commands.delete_keys(nil, M.config.defaults)
  end, { desc = "kseal: delete keys from a SealedSecret" })

  vim.api.nvim_create_user_command("KsealCreate", function()
    commands.create(M.config.defaults)
  end, { desc = "kseal: create a new SealedSecret" })

  -- Auto-detect SealedSecret YAML files
  if M.config.auto_detect then
    local group = vim.api.nvim_create_augroup("kseal_autodetect", { clear = true })

    vim.api.nvim_create_autocmd({ "BufReadPost", "BufNewFile" }, {
      pattern = { "*.yaml", "*.yml" },
      group   = group,
      callback = function(ev)
        local lines   = vim.api.nvim_buf_get_lines(ev.buf, 0, -1, false)
        local content = table.concat(lines, "\n")
        -- Quick scan — avoid full parse overhead
        if content:find("SealedSecret", 1, true) and content:find("kind:", 1, true) then
          M._attach_to_buffer(ev.buf)
        end
      end,
    })
  end
end

-- ---------------------------------------------------------------------------
-- Buffer attachment
-- ---------------------------------------------------------------------------

--- Attach buffer-local keymaps to a detected SealedSecret buffer.
--- Idempotent — safe to call multiple times on the same buffer.
--- @param buf integer  Buffer handle
function M._attach_to_buffer(buf)
  if vim.b[buf].kseal_attached then return end
  vim.b[buf].kseal_attached = true

  if M.config.notify_on_detect then
    vim.notify(
      "[kseal] 🔒 SealedSecret detected  (prefix: " .. M.config.keymaps.prefix .. ")",
      vim.log.levels.INFO
    )
  end

  if not M.config.keymaps.enabled then return end

  local p   = M.config.keymaps.prefix
  local ko  = { buffer = buf, silent = true }
  local d   = M.config.defaults

  local function map(key, fn, description)
    vim.keymap.set("n", p .. key, fn, vim.tbl_extend("force", ko, { desc = "kseal: " .. description }))
  end

  map("v", function() commands.view(nil,        d) end, "view decrypted values")
  map("e", function() commands.edit(nil,        d) end, "edit secret")
  map("s", function() commands.set_keys(nil,    d) end, "set KEY=value")
  map("d", function() commands.delete_keys(nil, d) end, "delete key")
  map("c", function() commands.create(          d) end, "create new SealedSecret")
end

return M

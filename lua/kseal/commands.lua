--- kseal.nvim — Commands implementation
--- All kseal CLI interactions live here.

local M = {}

-- ---------------------------------------------------------------------------
-- Internal helpers
-- ---------------------------------------------------------------------------

--- Return the filepath of the current buffer, or nil + notify on error.
local function current_filepath()
  local path = vim.api.nvim_buf_get_name(0)
  if path == "" then
    vim.notify("[kseal] No file associated with the current buffer.", vim.log.levels.ERROR)
    return nil
  end
  return path
end

--- Build common kseal CLI flags from an opts table.
--- @param opts table
--- @return string
local function build_flags(opts)
  opts = opts or {}
  local flags = {}
  if opts.namespace then
    table.insert(flags, "-n " .. vim.fn.shellescape(opts.namespace))
  end
  if opts.context then
    table.insert(flags, "--context " .. vim.fn.shellescape(opts.context))
  end
  if opts.scope and opts.scope ~= "strict" then
    table.insert(flags, "--scope " .. opts.scope)
  end
  if opts.cert then
    table.insert(flags, "--cert " .. vim.fn.shellescape(opts.cert))
  end
  return table.concat(flags, " ")
end

--- Reload the nvim buffer that corresponds to `filepath` (if it is open).
--- @param filepath string
local function reload_buffer(filepath)
  for _, buf in ipairs(vim.api.nvim_list_bufs()) do
    if vim.api.nvim_buf_is_loaded(buf) and vim.api.nvim_buf_get_name(buf) == filepath then
      vim.api.nvim_buf_call(buf, function()
        vim.cmd("edit!")
      end)
      break
    end
  end
end

--- Open a floating terminal window that runs `cmd`.
--- Keymaps q / <Esc> close the window after the process exits.
--- @param cmd   string  Shell command to run
--- @param title string  Window title shown in the border
local function float_terminal(cmd, title)
  local width  = math.min(120, vim.o.columns - 6)
  local height = math.min(35,  vim.o.lines   - 6)
  local row    = math.floor((vim.o.lines   - height) / 2)
  local col    = math.floor((vim.o.columns - width)  / 2)

  local buf = vim.api.nvim_create_buf(false, true)
  local win = vim.api.nvim_open_win(buf, true, {
    relative   = "editor",
    width      = width,
    height     = height,
    row        = row,
    col        = col,
    style      = "minimal",
    border     = "rounded",
    title      = " " .. title .. " ",
    title_pos  = "center",
  })

  vim.fn.termopen(cmd, {
    on_exit = function(_, _code)
      -- switch to normal mode so the user can scroll / read output
      vim.schedule(function()
        if vim.api.nvim_buf_is_valid(buf) then
          vim.cmd("stopinsert")
          for _, key in ipairs({ "q", "<Esc>" }) do
            vim.keymap.set("n", key, function()
              if vim.api.nvim_win_is_valid(win) then
                vim.api.nvim_win_close(win, true)
              end
            end, { buffer = buf, silent = true })
          end
        end
      end)
    end,
  })

  -- start in normal mode (not insert)
  vim.cmd("stopinsert")
  return buf, win
end

-- ---------------------------------------------------------------------------
-- Public commands
-- ---------------------------------------------------------------------------

--- View decrypted SealedSecret values in a floating terminal.
--- Rich-formatted output is preserved (colours included).
--- @param filepath string|nil  Path to the SealedSecret YAML (default: current file)
--- @param opts     table|nil   Global kseal options
function M.view(filepath, opts)
  filepath = filepath or current_filepath()
  if not filepath then return end

  local cmd = string.format(
    "kseal view %s %s",
    vim.fn.shellescape(filepath),
    build_flags(opts)
  )
  float_terminal(cmd, "🔒 kseal view — q to close")
end

--- Callback invoked by the editor wrapper script when `--remote-expr` is fired.
--- Opens the temporary file and attaches a BufDelete hook that touches the `.done` file.
--- @param filepath string
function M._on_remote_edit(filepath)
  vim.cmd("edit " .. vim.fn.fnameescape(filepath))
  local buf = vim.fn.bufnr(filepath)
  vim.api.nvim_create_autocmd("BufDelete", {
    buffer = buf,
    once = true,
    callback = function()
      os.execute("touch " .. vim.fn.shellescape(filepath .. ".kseal_done"))
    end
  })
  vim.notify(
    "[kseal] Secret opened for editing.\n  :w  — save changes\n  :bd — close buffer and re-seal",
    vim.log.levels.INFO
  )
  return 1 -- satisfy remote-expr
end

--- Edit a SealedSecret by opening its plaintext in *this* nvim instance.
---
--- Uses a dynamically generated wrapper script as EDITOR because Neovim does
--- not natively support `--remote-wait` yet. The wrapper uses `--remote-expr`
--- to tell this Neovim instance to open the file and set up a BufDelete hook,
--- and then it blocks until the `.done` file is touched.
--- @param filepath string|nil
--- @param opts     table|nil
function M.edit(filepath, opts)
  filepath = filepath or current_filepath()
  if not filepath then return end
  opts = opts or {}

  local server = vim.v.servername
  if server == "" then
    -- nvim started without --listen; open kseal edit in a terminal split instead
    vim.notify(
      "[kseal] No nvim server socket detected — opening in a terminal split.\n" ..
      "Tip: start nvim with `nvim --listen /tmp/nvim.sock` or set NVIM_LISTEN_ADDRESS.",
      vim.log.levels.WARN
    )
    vim.cmd("split | terminal kseal edit " .. vim.fn.shellescape(filepath) .. " " .. build_flags(opts))
    return
  end

  -- Create a wrapper shell script that blocks since nvim lacks --remote-wait
  local wrapper_path = vim.fn.stdpath("state") .. "/kseal_editor_wrapper.sh"
  local f = io.open(wrapper_path, "w")
  if f then
    f:write([[#!/bin/sh
SERVER="$1"
FILE="$2"
nvim --server "$SERVER" --remote-expr "luaeval('require(\"kseal.commands\")._on_remote_edit(\"'\"$FILE\"'\")')"
while [ ! -f "$FILE.kseal_done" ]; do sleep 0.5; done
rm -f "$FILE.kseal_done"
]])
    f:close()
    os.execute("chmod +x " .. vim.fn.shellescape(wrapper_path))
  end

  local editor = string.format("%s %s", vim.fn.shellescape(wrapper_path), vim.fn.shellescape(server))
  local cmd = string.format(
    "env EDITOR=%s kseal edit %s %s",
    vim.fn.shellescape(editor),
    vim.fn.shellescape(filepath),
    build_flags(opts)
  )

  vim.fn.jobstart({ "sh", "-c", cmd }, {
    on_exit = function(_, code)
      vim.schedule(function()
        if code == 0 then
          vim.notify("[kseal] ✓ SealedSecret updated!", vim.log.levels.INFO)
          reload_buffer(filepath)
        else
          vim.notify(
            "[kseal] kseal edit exited with code " .. code .. " (no changes applied).",
            vim.log.levels.WARN
          )
        end
      end)
    end,
  })
end

--- Prompt the user for KEY=value pairs and call `kseal set`.
--- @param filepath string|nil
--- @param opts     table|nil
function M.set_keys(filepath, opts)
  filepath = filepath or current_filepath()
  if not filepath then return end

  vim.ui.input(
    { prompt = "KEY=value pairs (space-separated): " },
    function(input)
      if not input or vim.trim(input) == "" then
        vim.notify("[kseal] Cancelled.", vim.log.levels.INFO)
        return
      end

      local cmd = string.format(
        "kseal set %s %s %s",
        vim.fn.shellescape(filepath),
        build_flags(opts),
        input
      )

      vim.fn.jobstart({ "sh", "-c", cmd }, {
        stderr_buffered = true,
        on_stderr = function(_, data)
          if data and #data > 0 and data[1] ~= "" then
            vim.notify("[kseal] " .. table.concat(data, "\n"), vim.log.levels.ERROR)
          end
        end,
        on_exit = function(_, code)
          vim.schedule(function()
            if code == 0 then
              vim.notify("[kseal] ✓ Key(s) updated and re-sealed!", vim.log.levels.INFO)
              reload_buffer(filepath)
            else
              vim.notify("[kseal] kseal set failed (exit " .. code .. ")", vim.log.levels.ERROR)
            end
          end)
        end,
      })
    end
  )
end

--- Prompt the user for key names and call `kseal delete`.
--- @param filepath string|nil
--- @param opts     table|nil
function M.delete_keys(filepath, opts)
  filepath = filepath or current_filepath()
  if not filepath then return end

  vim.ui.input(
    { prompt = "Key(s) to delete (space-separated): " },
    function(input)
      if not input or vim.trim(input) == "" then
        vim.notify("[kseal] Cancelled.", vim.log.levels.INFO)
        return
      end

      local cmd = string.format(
        "kseal delete %s %s %s",
        vim.fn.shellescape(filepath),
        build_flags(opts),
        input
      )

      vim.fn.jobstart({ "sh", "-c", cmd }, {
        stderr_buffered = true,
        on_stderr = function(_, data)
          if data and #data > 0 and data[1] ~= "" then
            vim.notify("[kseal] " .. table.concat(data, "\n"), vim.log.levels.ERROR)
          end
        end,
        on_exit = function(_, code)
          vim.schedule(function()
            if code == 0 then
              vim.notify("[kseal] ✓ Key(s) deleted and secret re-sealed!", vim.log.levels.INFO)
              reload_buffer(filepath)
            else
              vim.notify("[kseal] kseal delete failed (exit " .. code .. ")", vim.log.levels.ERROR)
            end
          end)
        end,
      })
    end
  )
end

--- Guide the user through creating a brand-new SealedSecret via `kseal create`.
--- Uses chained vim.ui.input prompts.
--- @param opts table|nil
function M.create(opts)
  opts = opts or {}

  vim.ui.input({ prompt = "Output file path (.yaml): " }, function(fp)
    if not fp or fp == "" then return end

    vim.ui.input({ prompt = "Secret name (blank = filename stem): " }, function(secret_name)
      vim.ui.input({ prompt = "Namespace: ", default = "default" }, function(ns)
        vim.ui.input({ prompt = "KEY=value pairs (space-separated): " }, function(pairs_str)
          if not pairs_str or vim.trim(pairs_str) == "" then
            vim.notify("[kseal] No key-value pairs provided. Cancelled.", vim.log.levels.WARN)
            return
          end

          local name_arg  = (secret_name and secret_name ~= "")
                            and ("--name " .. vim.fn.shellescape(secret_name))
                            or ""
          local ns_arg    = "-n " .. vim.fn.shellescape(ns or "default")
          local ctx_arg   = opts.context and ("--context " .. vim.fn.shellescape(opts.context)) or ""
          local scope_arg = "--scope " .. (opts.scope or "strict")
          local cert_arg  = opts.cert and ("--cert " .. vim.fn.shellescape(opts.cert)) or ""

          local cmd = string.format(
            "kseal create %s %s %s %s %s %s %s",
            vim.fn.shellescape(fp),
            name_arg, ns_arg, ctx_arg, scope_arg, cert_arg,
            pairs_str
          )

          vim.fn.jobstart({ "sh", "-c", cmd }, {
            on_exit = function(_, code)
              vim.schedule(function()
                if code == 0 then
                  vim.notify("[kseal] ✓ Created: " .. fp, vim.log.levels.INFO)
                  vim.cmd("edit " .. vim.fn.fnameescape(fp))
                else
                  vim.notify("[kseal] kseal create failed (exit " .. code .. ")", vim.log.levels.ERROR)
                end
              end)
            end,
          })
        end)
      end)
    end)
  end)
end

return M

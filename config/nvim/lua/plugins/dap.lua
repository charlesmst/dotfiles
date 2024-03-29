return {
  'mfussenegger/nvim-dap',
  dependencies = {

    'nvim-telescope/telescope.nvim',
    { 'nvim-telescope/telescope-dap.nvim' },
    { 'mfussenegger/nvim-dap-python' },
    { 'leoluz/nvim-dap-go' },
    { "rcarriga/nvim-dap-ui",             dependencies = { "mfussenegger/nvim-dap" } },
  },
  config = function()
    require('telescope').load_extension('dap')
    require('dap-python').setup('python3')
    require('dap-go').setup()

    vim.keymap.set('n', '<f5>', require('dap').continue, { desc = 'DAP continue' })
    vim.keymap.set('n', '<f10>', require('dap').step_over, { desc = 'DAP step over' })
    vim.keymap.set('n', '<f11>', require('dap').step_into, { desc = 'DAP step into' })
    vim.keymap.set('n', '<f12>', require('dap').step_out, { desc = 'DAP step out' })

    vim.keymap.set('n', '<leader>dtb', '<cmd>lua require"dap".toggle_breakpoint()<CR>')
    vim.keymap.set('n', '<leader>dsbr',
      '<cmd>lua require"dap".set_breakpoint(vim.fn.input("Breakpoint condition: "))<CR>')
    vim.keymap.set('n', '<leader>dsbm',
      '<cmd>lua require"dap".set_breakpoint(nil, nil, vim.fn.input("Log point message: "))<CR>')
    vim.keymap.set('n', '<leader>dro', '<cmd>lua require"dap".repl.open()<CR>')
    vim.keymap.set('n', '<leader>drl', '<cmd>lua require"dap".repl.run_last()<CR>')

    -- telescope-dap
    vim.keymap.set('n', '<leader>dcc', '<cmd>lua require"telescope".extensions.dap.commands{}<CR>')
    vim.keymap.set('n', '<leader>dco', '<cmd>lua require"telescope".extensions.dap.configurations{}<CR>')
    vim.keymap.set('n', '<leader>dlb', '<cmd>lua require"telescope".extensions.dap.list_breakpoints{}<CR>')
    vim.keymap.set('n', '<leader>dv', '<cmd>lua require"telescope".extensions.dap.variables{}<CR>')
    vim.keymap.set('n', '<leader>df', '<cmd>lua require"telescope".extensions.dap.frames{}<CR>')

    require("dapui").setup({
      icons = { expanded = "?", collapsed = "?" },
      mappings = {
        -- Use a table to apply multiple mappings
        expand = { "<CR>", "<2-LeftMouse>" },
        open = "o",
        remove = "d",
        edit = "e",
        repl = "r",
        toggle = "t",
      },
      -- Expand lines larger than the window
      -- Requires >= 0.7
      expand_lines = vim.fn.has("nvim-0.7"),
      -- Layouts define sections of the screen to place windows.
      -- The position can be "left", "right", "top" or "bottom".
      -- The size specifies the height/width depending on position. It can be an Int
      -- or a Float. Integer specifies height/width directly (i.e. 20 lines/columns) while
      -- Float value specifies percentage (i.e. 0.3 - 30% of available lines/columns)
      -- Elements are the elements shown in the layout (in order).
      -- Layouts are opened in order so that earlier layouts take priority in window sizing.
      layouts = {
        {
          elements = {
            -- Elements can be strings or table with id and size keys.
            { id = "scopes", size = 0.25 },
            "breakpoints",
            "stacks",
            "watches",
          },
          size = 40, -- 40 columns
          position = "left",
        },
        {
          elements = {
            "repl",
            "console",
          },
          size = 0.25, -- 25% of total lines
          position = "bottom",
        },
      },
      floating = {
        max_height = nil,  -- These can be integers or a float between 0 and 1.
        max_width = nil,   -- Floats will be treated as percentage of your screen.
        border = "single", -- Border style. Can be "single", "double" or "rounded"
        mappings = {
          close = { "q", "<Esc>" },
        },
      },
      windows = { indent = 1 },
      render = {
        max_type_length = nil, -- Can be integer or nil.
        max_value_lines = 100, -- Can be integer or nil.
      }
    })

    local dap, dapui = require("dap"), require("dapui")
    dap.listeners.after.event_initialized["dapui_config"] = function()
      dapui.open()
    end
    dap.listeners.before.event_terminated["dapui_config"] = function()
      dapui.close()
    end
    dap.listeners.before.event_exited["dapui_config"] = function()
      dapui.close()
    end
  end
}

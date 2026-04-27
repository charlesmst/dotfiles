return {
  'nvim-telescope/telescope.nvim',
  dependencies = {
    'nvim-lua/plenary.nvim',
    { 'nvim-telescope/telescope-fzf-native.nvim', build = 'make' }
  },
  config = function()
    -- [[ Configure Telescope ]]
    -- See `:help telescope` and `:help telescope.setup()`
    require('telescope').setup {
      extensions = {
        fzf = {
          fuzzy = true,                    -- false will only do exact matching
          override_generic_sorter = true,  -- override the generic sorter
          override_file_sorter = true,     -- override the file sorter
          case_mode = "smart_case",        -- or "ignore_case" or "respect_case"
                                           -- the default case_mode is "smart_case"
        }
      },
      defaults = {
        mappings = {
          i = {
            ['<C-u>'] = false,
            -- ['<C-d>'] = false,

          ["<c-d>"] = "delete_buffer",
          },
        },
      },
    }

    -- Enable telescope fzf native, if installed
    pcall(require('telescope').load_extension, 'fzf')

    -- See `:help telescope.builtin`
    vim.keymap.set('n', '<leader>?', require('telescope.builtin').oldfiles, { desc = '[?] Find recently opened files' })
    vim.keymap.set('n', '<leader><space>', require('telescope.builtin').buffers, { desc = '[ ] Find existing buffers' })
    vim.keymap.set('n', '<leader>/', function()
      -- You can pass additional configuration to telescope to change theme, layout, etc.
      require('telescope.builtin').current_buffer_fuzzy_find(require('telescope.themes').get_dropdown {
        winblend = 10,
        previewer = false,
      })
    end, { desc = '[/] Fuzzily search in current buffer]' })

    local builtin = require('telescope.builtin')
    vim.keymap.set('n', '<leader>p', builtin.find_files, { desc = '[S]earch [F]iles' })
    vim.keymap.set('n', '<leader>P', builtin.find_files, { desc = '[S]earch [F]iles hidden' })
    vim.keymap.set('n', '<leader>fh', builtin.help_tags, { desc = '[S]earch [H]elp' })
    vim.keymap.set('n', '<leader>fw', builtin.grep_string, { desc = '[S]earch current [W]ord' })
    vim.keymap.set('n', '<leader>fg', builtin.live_grep, { desc = '[S]earch by [G]rep' })
    vim.keymap.set('n', '<leader>fd', builtin.diagnostics, { desc = '[S]earch [D]iagnostics' })

    -- Specialized Switcher function
    local function intellij_switcher()
        builtin.buffers(require('telescope.themes').get_dropdown({
            sort_mru = true,
            ignore_current_buffer = true,
            previewer = false,       -- IntelliJ doesn't usually show a preview in the switcher
            initial_mode = "normal",  -- Start in normal mode to use j/k immediately
            layout_config = {
                width = 0.6,
                prompt_position = "top",
            },
        }))
    end

    vim.keymap.set('n', '<leader>b', intellij_switcher)
  end
}

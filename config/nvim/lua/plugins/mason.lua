return {
  "mason-org/mason.nvim",
  dependencies = {
    "mason-org/mason-lspconfig.nvim",
    "neovim/nvim-lspconfig",
    'hrsh7th/nvim-cmp',
    'hrsh7th/cmp-nvim-lsp',
    'L3MON4D3/LuaSnip',
    'saadparwaiz1/cmp_luasnip',
    "jay-babu/mason-null-ls.nvim",
    "jose-elias-alvarez/null-ls.nvim",
    'folke/neodev.nvim',
  },
  config = function()
    require("neodev").setup()
    local luasnip = require("luasnip")

    local servers = { 'rust_analyzer', 'pyright', 'ts_ls', 'gopls', 'jdtls', 'lua_ls' }

    local on_attach = function(_, bufnr)
      local nmap = function(keys, func, desc)
        if desc then
          desc = 'LSP: ' .. desc
        end

        vim.keymap.set('n', keys, func, { buffer = bufnr, desc = desc })
      end

      nmap('<leader>rn', vim.lsp.buf.rename, '[R]e[n]ame')
      nmap('<leader>s', vim.lsp.buf.code_action, '[S]uggestion')

      nmap('gd', vim.lsp.buf.definition, '[G]oto [D]efinition')
      nmap('<leader>F', vim.lsp.buf.format, 'Format code')

      nmap('gi', vim.lsp.buf.implementation, '[G]oto [I]mplementation')
      nmap('gr', require('telescope.builtin').lsp_references)
      nmap('<leader>ds', require('telescope.builtin').lsp_document_symbols, '[D]ocument [S]ymbols')
      nmap('<leader>ws', require('telescope.builtin').lsp_dynamic_workspace_symbols, '[W]orkspace [S]ymbols')

      nmap('K', vim.lsp.buf.hover, 'Hover Documentation')
      nmap('<C-k>', vim.lsp.buf.signature_help, 'Signature Documentation')

      nmap('gD', vim.lsp.buf.declaration, '[G]oto [D]eclaration')
      nmap('<leader>D', vim.lsp.buf.type_definition, 'Type [D]efinition')
      nmap('<leader>wa', vim.lsp.buf.add_workspace_folder, '[W]orkspace [A]dd Folder')
      nmap('<leader>wr', vim.lsp.buf.remove_workspace_folder, '[W]orkspace [R]emove Folder')
      nmap('<leader>wl', function()
        print(vim.inspect(vim.lsp.buf.list_workspace_folders()))
      end, '[W]orkspace [L]ist Folders')

      vim.api.nvim_buf_create_user_command(bufnr, 'Format', vim.lsp.buf.format or vim.lsp.buf.formatting,
        { desc = 'Format current buffer with LSP' })
    end

    local capabilities = vim.lsp.protocol.make_client_capabilities()
    capabilities = require('cmp_nvim_lsp').default_capabilities(capabilities)

    -- nvim 0.11+ / mason-lspconfig 2.x: extend nvim-lspconfig defaults, no lspconfig.setup() or setup_handlers
    for _, name in ipairs(servers) do
      if name == "lua_ls" then
        vim.lsp.config(name, {
          capabilities = capabilities,
          on_attach = on_attach,
          settings = {
            Lua = {
              workspace = { checkThirdParty = false },
              diagnostics = { globals = { 'vim' } },
            }
          }
        })
      else
        vim.lsp.config(name, {
          capabilities = capabilities,
          on_attach = on_attach,
        })
      end
    end

    require("mason").setup()
    require("mason-lspconfig").setup({
      ensure_installed = servers,
      -- Do not call vim.lsp.enable(); use :LspStart <name> (or <leader>l) when you want a server
      automatic_enable = false,
    })

    require("mason-null-ls").setup({
      ensure_installed = {},
      automatic_installation = false,
      automatic_setup = true,
    })
    require("null-ls").setup({
      sources = {}
    })

    local cmp = require 'cmp'
    cmp.setup {
      snippet = {
        expand = function(args)
          luasnip.lsp_expand(args.body)
        end,
      },
      mapping = cmp.mapping.preset.insert {
        ['<C-d>'] = cmp.mapping.scroll_docs(-4),
        ['<C-f>'] = cmp.mapping.scroll_docs(4),
        ['<C-Space>'] = cmp.mapping.complete(),
        ['<CR>'] = cmp.mapping.confirm {
          behavior = cmp.ConfirmBehavior.Replace,
          select = true,
        },
        ['<Tab>'] = cmp.mapping(function(fallback)
          if cmp.visible() then
            cmp.select_next_item()
          elseif luasnip.expand_or_jumpable() then
            luasnip.expand_or_jump()
          else
            fallback()
          end
        end, { 'i', 's' }),
        ['<S-Tab>'] = cmp.mapping(function(fallback)
          if cmp.visible() then
            cmp.select_prev_item()
          elseif luasnip.jumpable(-1) then
            luasnip.jump(-1)
          else
            fallback()
          end
        end, { 'i', 's' }),
      },
      sources = {
        { name = 'nvim_lsp' },
        { name = 'luasnip' },
      },
    }

    vim.keymap.set("n", "<leader>l", function()
      vim.ui.input({ prompt = "LspStart " }, function(name)
        if not name or not name:match("%S") then
          return
        end
        local ok, err = pcall(vim.cmd, "LspStart " .. name)
        if not ok then
          vim.notify(tostring(err), vim.log.levels.ERROR)
        end
      end)
    end, { desc = "Prompt for :LspStart <server>" })
  end
}

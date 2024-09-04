return {
  "williamboman/mason.nvim",
  dependencies = {
    "williamboman/mason-lspconfig.nvim",
    "neovim/nvim-lspconfig",
    'hrsh7th/nvim-cmp',
    'hrsh7th/cmp-nvim-lsp',
    'hrsh7th/cmp-copilot',
    'L3MON4D3/LuaSnip',
    'saadparwaiz1/cmp_luasnip',

    "jay-babu/mason-null-ls.nvim",
    "jose-elias-alvarez/null-ls.nvim",
    'folke/neodev.nvim',
    "jay-babu/mason-nvim-dap.nvim",
  },
  config = function()
    local servers = { 'clangd', 'rust_analyzer', 'pyright', 'tsserver', 'gopls', 'jdtls','lua_ls' }

    local on_attach = function(_, bufnr)
      -- NOTE: Remember that lua is a real programming language, and as such it is possible
      -- to define small helper and utility functions so you don't have to repeat yourself
      -- many times.
      --
      -- In this case, we create a function that lets us more easily define mappings specific
      -- for LSP related items. It sets the mode, buffer and description for us each time.
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

      -- See `:help K` for why this keymap
      nmap('K', vim.lsp.buf.hover, 'Hover Documentation')
      nmap('<C-k>', vim.lsp.buf.signature_help, 'Signature Documentation')

      -- Lesser used LSP functionality
      nmap('gD', vim.lsp.buf.declaration, '[G]oto [D]eclaration')
      nmap('<leader>D', vim.lsp.buf.type_definition, 'Type [D]efinition')
      nmap('<leader>wa', vim.lsp.buf.add_workspace_folder, '[W]orkspace [A]dd Folder')
      nmap('<leader>wr', vim.lsp.buf.remove_workspace_folder, '[W]orkspace [R]emove Folder')
      nmap('<leader>wl', function()
        print(vim.inspect(vim.lsp.buf.list_workspace_folders()))
      end, '[W]orkspace [L]ist Folders')

      -- Create a command `:Format` local to the LSP buffer
      vim.api.nvim_buf_create_user_command(bufnr, 'Format', vim.lsp.buf.format or vim.lsp.buf.formatting,
        { desc = 'Format current buffer with LSP' })
    end


    local capabilities = vim.lsp.protocol.make_client_capabilities()
    capabilities = require('cmp_nvim_lsp').default_capabilities(capabilities)

    require("mason").setup()
    require("mason-lspconfig").setup {
      ensure_installed = servers,
    }

    require("mason-lspconfig").setup_handlers {
      -- The first entry (without a key) will be the default handler
      -- and will be called for each installed server that doesn't have
      -- a dedicated handler.
      function(server_name) -- default handler (optional)
        require("lspconfig")[server_name].setup {
          on_attach = on_attach,
          autostart = true,
          capabilities = capabilities,
        }
      end,

      -- disable java, too much memory usage by default
      ["jdtls"] = function()
        require("lspconfig")["jdtls"].setup {
          on_attach = on_attach,
          autostart = false,
          capabilities = capabilities,
        }
      end,

      ["groovy-language-server"] = function()
        require("lspconfig")["groovy-language-server"].setup {
          on_attach = on_attach,
          autostart = false,
          capabilities = capabilities,
        }
      end,
      ["lua_ls"] = function()
        require("lspconfig")["lua_ls"].setup {
          on_attach = on_attach,
          autostart = true,
          capabilities = capabilities,
          settings = {
            Lua = {
              diagnostics = { globals = { 'vim' } }
            }
          }
        }
      end,
      ["rust_analyzer"] = function()
        require("lspconfig")["rust_analyzer"].setup {
          on_attach = on_attach,
          autostart = true,
          capabilities = capabilities,
          settings = {
            Lua = {
              diagnostics = { globals = { 'vim' } }
            }
          }
        }
      end,
    }
    -- require('neodev').setup()
    require("mason-null-ls").setup({
      ensure_installed = {
        -- Opt to list sources here, when available in mason.
      },
      automatic_installation = false,
      automatic_setup = true,
    })
    require("null-ls").setup({
      sources = {
      }
    })

    -- require 'mason-null-ls'.setup_handlers()

    require("mason-nvim-dap").setup({
      automatic_setup = true,
    })
    -- require 'mason-nvim-dap'.setup_handlers {}
    -- nvim-cmp setup
    local cmp = require 'cmp'
    local luasnip = require 'luasnip'


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
        { name = 'copilot' }
      },
    }
  end
}

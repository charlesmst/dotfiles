
local servers = { 'clangd', 'rust_analyzer', 'pyright', 'lua_ls', 'tsserver', 'gopls', 'jdtls', 'groovyls'}
require("mason").setup()
require("mason-lspconfig").setup {
    ensure_installed = servers,
}

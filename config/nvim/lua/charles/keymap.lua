
vim.keymap.set('n', '<leader>w', ":w<CR>")
vim.keymap.set('n', '<leader>q', ":q<CR>")
vim.keymap.set({'i', 'v'}, 'kj', "<esc>")

vim.keymap.set('n', '<leader>e', ":NvimTreeFindFileToggle<CR>")

-- Diagnostic keymaps
vim.keymap.set('n', '[d', vim.diagnostic.goto_prev)
vim.keymap.set('n', ']d', vim.diagnostic.goto_next)


vim.keymap.set('n', '<C-d>', "<C-d>zz")
vim.keymap.set('n', '<C-u>', "<C-u>zz")

vim.keymap.set('n', 'n', "nzzzv")
vim.keymap.set('n', 'N', "Nzzzv")

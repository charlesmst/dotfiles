local api = vim.api

require "paq"{
    "savq/paq-nvim";                  
    "neovim/nvim-lspconfig";          
    "hrsh7th/nvim-cmp";
    "nvim-lua/plenary.nvim";
    "nvim-telescope/telescope.nvim";
    "overcache/NeoSolarized";
    "luisiacc/gruvbox-baby";
    "machakann/vim-highlightedyank";
    "preservim/nerdtree";
    "ryanoasis/vim-devicons";
    "tpope/vim-commentary";
    "christoomey/vim-tmux-navigator";

}

vim.o.mouse = "a"
vim.o.ignorecase = true
vim.o.smartcase = true
vim.o.incsearch = true
vim.o.clipboard = "unnamedplus"
vim.o.hidden = true
vim.o.history = 5000
vim.o.tabstop = 4
vim.o.expandtab = true
vim.o.relativenumber = true
vim.o.swapfile = false
vim.o.shiftwidth = vim.o.tabstop
vim.g.mapleader = " "

api.nvim_command [[ colorscheme gruvbox-baby]]
api.nvim_command [[ colorscheme NeoSolarized]]
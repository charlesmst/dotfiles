return {
  'tpope/vim-fugitive',
  'tpope/vim-rhubarb',                                                        
  { 'lewis6991/gitsigns.nvim', dependencies = { 'nvim-lua/plenary.nvim' } },
  'numToStr/Comment.nvim',
  'nvim-treesitter/nvim-treesitter',
  'nvim-treesitter/nvim-treesitter-textobjects',
  {
    "williamboman/mason.nvim",
    "williamboman/mason-lspconfig.nvim",
    "neovim/nvim-lspconfig",
  },
   { 'hrsh7th/nvim-cmp', dependencies = { 'hrsh7th/cmp-nvim-lsp' } },
   { 'L3MON4D3/LuaSnip', dependencies = { 'saadparwaiz1/cmp_luasnip' } },
   'tpope/vim-sleuth',
   { 'nvim-telescope/telescope.nvim', dependencies = { 'nvim-lua/plenary.nvim' } },

  { 'nvim-telescope/telescope-fzf-native.nvim', build = 'make', cond = vim.fn.executable "make" == 1 },

   'lukas-reineke/indent-blankline.nvim',
   { 'kyazdani42/nvim-tree.lua', dependencies = { 'kyazdani42/nvim-web-devicons' } },
   { 'kylechui/nvim-surround' },
   'folke/tokyonight.nvim',
   'christoomey/vim-tmux-navigator',

  -- Debug
   { 'mfussenegger/nvim-dap' },
   { 'nvim-telescope/telescope-dap.nvim' },
   { 'mfussenegger/nvim-dap-python' } ,
   { 'leoluz/nvim-dap-go' },
   { "rcarriga/nvim-dap-ui", dependencies = {"mfussenegger/nvim-dap"} },

   { 'aklt/plantuml-syntax' },
   { "windwp/nvim-autopairs" },
   { 'tpope/vim-obsession'}

  }

return {
  'tpope/vim-fugitive',
  'tpope/vim-rhubarb',                                                        
  {
    "williamboman/mason.nvim",
    "williamboman/mason-lspconfig.nvim",
    "neovim/nvim-lspconfig",
  },
   { 'hrsh7th/nvim-cmp', dependencies = { 'hrsh7th/cmp-nvim-lsp' } },
   { 'L3MON4D3/LuaSnip', dependencies = { 'saadparwaiz1/cmp_luasnip' } },
   'tpope/vim-sleuth',

   'lukas-reineke/indent-blankline.nvim',
   { 'kyazdani42/nvim-tree.lua', dependencies = { 'kyazdani42/nvim-web-devicons' } },
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

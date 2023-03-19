return {
  'kyazdani42/nvim-tree.lua',
  dependencies = { 'kyazdani42/nvim-web-devicons' },
  config = function()
    require("nvim-tree").setup({
      view = {
        adaptive_size = true,
        centralize_selection = true,
      },
      update_focused_file = {
        enable = true,
        update_root = false,
        ignore_list = {},
      },
      renderer = {
        highlight_opened_files = "all",
      }
    })
  end
}

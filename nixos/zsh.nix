
{  pkgs, home, inputs,   ... }:
{
  home.file = {
    ".zshrc" = {
    	source = inputs.dotfiles + "/.zshrc";
    };
    ".config/zsh" = {
    	source = inputs.dotfiles + "/config/zsh";
    };
  }
}

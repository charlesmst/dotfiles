#!/bin/bash

set -e

ln -fs $(pwd)/.zshrc  $HOME/.zshrc
ln -fs $(pwd)/config/zsh $HOME/.config/zsh

ln -fs $(pwd)/.vimrc  $HOME/.vimrc
ln -fs $(pwd)/.ideavimrc  $HOME/.ideavimrc

mkdir -p ~/.config/alacritty
ln -fs $(pwd)/config/alacritty/alacritty.toml $HOME/.config/alacritty/alacritty.toml

if [ -d "$HOME/.config/nvim" ];then
	# ln -fs $(pwd)/config/nvim/init.vim $HOME/.config/nvim/init.vim
	ln -fs $(pwd)/config/nvim/init.lua $HOME/.config/nvim/init.lua
	ln -fs $(pwd)/config/nvim/lua $HOME/.config/nvim/lua
	ln -fs $(pwd)/config/nvim/coc-settings.json $HOME/.config/nvim/coc-settings.json
fi

if [ -d "$HOME/.config/karabiner/assets/complex_modifications/" ]; then
	ln -fs $(pwd)/config/karabiner/assets/complex_modifications/capslock_charles.json  $HOME/.config/karabiner/assets/complex_modifications/capslock_charles.json
	ln -fs $(pwd)/config/karabiner/assets/complex_modifications/ctrl_enchanced.json  $HOME/.config/karabiner/assets/complex_modifications/ctrl_enchanced.json
	ln -fs $(pwd)/config/karabiner/assets/complex_modifications/mouse.json  $HOME/.config/karabiner/assets/complex_modifications/mouse.json

fi


# Requires oh my tmux
ln -fs "$(pwd)/.tmux.conf.local"  "$HOME/.tmux.conf.local"



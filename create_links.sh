#!/bin/bash

set -e

ln -fs $(pwd)/.zshrc  $HOME/.zshrc
ln -fs $(pwd)/.config/zsh/ $HOME/.config/zsh/

ln -fs $(pwd)/.vimrc  $HOME/.vimrc
ln -fs $(pwd)/.ideavimrc  $HOME/.ideavimrc

if [ -d "$HOME/.config/nvim" ];then
	ln -fs $(pwd)/.config/nvim/init.vim $HOME/.config/nvim/init.vim
	ln -fs $(pwd)/.config/nvim/coc-settings.json $HOME/.config/nvim/coc-settings.json
fi

if [ -d "$HOME/.config/karabiner/assets/complex_modifications/" ]; then
	ln -fs $(pwd)/.config/karabiner/assets/complex_modifications/capslock_charles.json  $HOME/.config/karabiner/assets/complex_modifications/capslock_charles.json
	ln -fs $(pwd)/.config/karabiner/assets/complex_modifications/ctrl_enchanced.json  $HOME/.config/karabiner/assets/complex_modifications/ctrl_enchanced.json

fi


# Requires oh my tmux
ln -fs "$(pwd)/.tmux.conf.local"  "$HOME/.tmux.conf.local"


if [[ "$OSTYPE" == "darwin"* ]]; then
	# Specify the preferences directory
	defaults write com.googlecode.iterm2 PrefsCustomFolder -string "$(pwd)/macos/iTerm/settings"
	# Tell iTerm2 to use the custom preferences in the directory
	defaults write com.googlecode.iterm2 LoadPrefsFromCustomFolder -bool true
fi

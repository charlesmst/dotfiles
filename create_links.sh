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

# Claude Code hooks
mkdir -p "$HOME/.claude/hooks"
ln -fs "$(pwd)/config/claude/hooks/worktree-layout.sh" "$HOME/.claude/hooks/worktree-layout.sh"
ln -fs "$(pwd)/config/claude/hooks/worktree-layout-cleanup.sh" "$HOME/.claude/hooks/worktree-layout-cleanup.sh"

# Shared agent (Claude + Cursor CLI) helper scripts. Claude's settings.json
# references them by absolute path inside config/agent-shared/, but we also
# expose them under ~/.claude/hooks/ so terminal-notifier's -execute callback
# can locate focus-agent-pane.sh from the documented hooks directory.
ln -fs "$(pwd)/config/agent-shared/focus-agent-pane.sh" "$HOME/.claude/hooks/focus-agent-pane.sh"
ln -fs "$(pwd)/config/agent-shared/notify-if-unfocused.sh" "$HOME/.claude/hooks/notify-if-unfocused.sh"

# Cursor CLI hooks
mkdir -p "$HOME/.cursor/hooks"
ln -fs "$(pwd)/config/cursor/hooks.json" "$HOME/.cursor/hooks.json"
ln -fs "$(pwd)/config/cursor/hooks/write-session-meta.sh" "$HOME/.cursor/hooks/write-session-meta.sh"
ln -fs "$(pwd)/config/cursor/hooks/clear-session-meta.sh" "$HOME/.cursor/hooks/clear-session-meta.sh"

# Shared state directory used by tmux/agent-attention (markers + picker cache).
mkdir -p "$HOME/.local/state/agent-attention/pending" "$HOME/.local/state/agent-attention/working"



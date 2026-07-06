#!/bin/bash
# Warm the sessionizer cache. Called from tmux focus hooks and notify hooks.
# (The agent picker has no cache — it rebuilds on demand from the process tree.)
MODE="--refresh-cache"
[ "${1:-}" = "--force" ] && MODE="--refresh-now"

bash "$HOME/personal/dotfiles/tmux/tmux-sessionizer.sh" "$MODE" >/dev/null 2>&1 &
disown 2>/dev/null || true
exit 0

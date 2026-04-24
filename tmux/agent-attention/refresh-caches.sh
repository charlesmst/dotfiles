#!/bin/bash
# Refresh both picker caches. Default: skip if cache < 5s old (tmux focus hooks).
# Pass --force to rebuild regardless of age (notify hook, fresh pending marker).
MODE="--refresh-cache"
[ "${1:-}" = "--force" ] && MODE="--refresh-now"

bash "$HOME/personal/dotfiles/tmux/agent-attention/picker.sh" "$MODE" >/dev/null 2>&1 &
bash "$HOME/personal/dotfiles/tmux/tmux-sessionizer.sh" "$MODE" >/dev/null 2>&1 &
disown 2>/dev/null || true
exit 0

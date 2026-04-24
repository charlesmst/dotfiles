#!/bin/bash
# Clear the "working" marker for a tmux pane (Claude finished processing).
# Called from Claude Code's Stop hook (before notify-if-unfocused.sh).
set -u

PANE="${TMUX_PANE:-}"
[ -z "$PANE" ] && exit 0

BASE="${CLAUDE_ATTENTION_DIR:-$HOME/.claude/state}"
SAFE="${PANE//\//_}"
rm -f "$BASE/working/$SAFE"

bash "$HOME/personal/dotfiles/tmux/claude-attention/refresh-caches.sh" --force >/dev/null 2>&1 &
disown 2>/dev/null || true
exit 0

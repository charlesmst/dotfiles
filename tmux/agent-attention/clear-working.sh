#!/bin/bash
# Clear the "working" marker for a tmux pane (an agent finished processing).
# Called from Claude Code's Stop hook and Cursor CLI's stop / sessionEnd hooks
# (before notify-if-unfocused.sh).
set -u

PANE="${TMUX_PANE:-}"
[ -z "$PANE" ] && exit 0

BASE="${AGENT_ATTENTION_DIR:-$HOME/.local/state/agent-attention}"
SAFE="${PANE//\//_}"
rm -f "$BASE/working/$SAFE"

bash "$HOME/personal/dotfiles/tmux/agent-attention/refresh-caches.sh" --force >/dev/null 2>&1 &
disown 2>/dev/null || true
exit 0

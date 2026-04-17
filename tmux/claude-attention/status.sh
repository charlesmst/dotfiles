#!/bin/bash
# Output a status-line indicator for Claude panes pending attention.
# Embed via: #(~/personal/dotfiles/tmux/claude-attention/status.sh)
BASE="${CLAUDE_ATTENTION_DIR:-$HOME/.claude/state}"
count=$(find "$BASE/pending" -maxdepth 1 -type f 2>/dev/null | wc -l | tr -d ' ')
[ "$count" = "0" ] && exit 0
printf '#[fg=yellow,bold]● %s#[default]' "$count"

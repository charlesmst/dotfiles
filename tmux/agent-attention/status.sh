#!/bin/bash
# Output a tmux status-line indicator for agent panes needing attention.
#   ● N  (yellow) — panes with a pending notification
# Embed via: #(~/personal/dotfiles/tmux/agent-attention/status.sh)
BASE="${AGENT_ATTENTION_DIR:-$HOME/.local/state/agent-attention}"

pending=$(find "$BASE/pending" -maxdepth 1 -type f 2>/dev/null | wc -l | tr -d ' ')
if [ "$pending" != "0" ]; then
    printf '#[fg=yellow,bold]● %s#[default]' "$pending"
fi
exit 0

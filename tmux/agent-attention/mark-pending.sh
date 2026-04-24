#!/bin/bash
# Mark a tmux pane as needing attention.
# Usage: mark-pending.sh <pane_id>
set -u

PANE="${1:-${TMUX_PANE:-}}"
[ -z "$PANE" ] && exit 0

BASE="${AGENT_ATTENTION_DIR:-$HOME/.local/state/agent-attention}"
mkdir -p "$BASE/pending"

SAFE="${PANE//\//_}"
touch "$BASE/pending/$SAFE"

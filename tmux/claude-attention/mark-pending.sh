#!/bin/bash
# Mark a tmux pane as needing attention.
# Usage: mark-pending.sh <pane_id>
set -u

PANE="${1:-${TMUX_PANE:-}}"
[ -z "$PANE" ] && exit 0

BASE="${CLAUDE_ATTENTION_DIR:-$HOME/.claude/state}"
mkdir -p "$BASE/pending"

SAFE="${PANE//\//_}"
touch "$BASE/pending/$SAFE"

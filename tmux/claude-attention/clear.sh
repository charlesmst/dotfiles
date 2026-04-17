#!/bin/bash
# Clear the pending marker for a pane.
# Called by tmux pane-focus-in hook: clear.sh #{pane_id}
set -u

PANE="${1:-}"
[ -z "$PANE" ] && exit 0

BASE="${CLAUDE_ATTENTION_DIR:-$HOME/.claude/state}"
SAFE="${PANE//\//_}"
rm -f "$BASE/pending/$SAFE"

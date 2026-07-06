#!/bin/bash
# Clear the pending (attention) marker when the user submits a new prompt.
# Called from Claude Code's UserPromptSubmit hook and Cursor CLI's
# beforeSubmitPrompt hook.
set -u

PANE="${TMUX_PANE:-}"
[ -z "$PANE" ] && exit 0

BASE="${AGENT_ATTENTION_DIR:-$HOME/.local/state/agent-attention}"
SAFE="${PANE//\//_}"
rm -f "$BASE/pending/$SAFE"
exit 0

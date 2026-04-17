#!/bin/bash
# Sync the tmux window name to the current Claude session's `name`.
# Called as a UserPromptSubmit / Stop hook. No-op if:
#   - not running inside tmux
#   - no session_id in hook JSON
#   - no session file / no `name` field
#   - current window name already matches
set -u

[ -z "${TMUX_PANE:-}" ] && exit 0
command -v jq >/dev/null 2>&1 || exit 0

INPUT=$(cat 2>/dev/null || true)
[ -z "$INPUT" ] && exit 0

SID=$(printf '%s' "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
[ -z "$SID" ] && exit 0

SESSION_FILE=$(grep -l "\"sessionId\":\"$SID\"" "$HOME"/.claude/sessions/*.json 2>/dev/null | head -1)
[ -z "$SESSION_FILE" ] && exit 0

NAME=$(jq -r '.name // empty' "$SESSION_FILE" 2>/dev/null)
[ -z "$NAME" ] && exit 0

CURRENT=$(tmux display-message -t "$TMUX_PANE" -p '#{window_name}' 2>/dev/null)
[ "$CURRENT" = "$NAME" ] && exit 0

tmux rename-window -t "$TMUX_PANE" "$NAME" 2>/dev/null

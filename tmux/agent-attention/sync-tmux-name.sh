#!/bin/bash
# Sync the tmux window name to the current agent session's `name`.
# Called as a UserPromptSubmit / Stop hook (Claude) or
# beforeSubmitPrompt / stop hook (Cursor CLI). No-op if:
#   - not running inside tmux
#   - no session id in hook JSON
#   - no session file / no `name` field
#   - current window name already matches
#
# AGENT env var selects the backend:
#   AGENT=claude  -> {session_id} matched against ~/.claude/sessions/*.json
#   AGENT=cursor  -> {conversation_id} matched against ~/.cursor/sessions/*.json
set -u

[ -z "${TMUX_PANE:-}" ] && exit 0
command -v jq >/dev/null 2>&1 || exit 0

AGENT="${AGENT:-claude}"

INPUT=$(cat 2>/dev/null || true)
[ -z "$INPUT" ] && exit 0

case "$AGENT" in
    claude)
        SID=$(printf '%s' "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
        SESSIONS_DIR="$HOME/.claude/sessions"
        ;;
    cursor)
        SID=$(printf '%s' "$INPUT" | jq -r '.conversation_id // empty' 2>/dev/null)
        SESSIONS_DIR="$HOME/.cursor/sessions"
        ;;
    *)
        exit 0
        ;;
esac

[ -z "$SID" ] && exit 0

SESSION_FILE=$(grep -l "\"sessionId\":\"$SID\"" "$SESSIONS_DIR"/*.json 2>/dev/null | head -1)
[ -z "$SESSION_FILE" ] && exit 0

NAME=$(jq -r '.name // empty' "$SESSION_FILE" 2>/dev/null)
[ -z "$NAME" ] && exit 0

CURRENT=$(tmux display-message -t "$TMUX_PANE" -p '#{window_name}' 2>/dev/null)
[ "$CURRENT" = "$NAME" ] && exit 0

tmux rename-window -t "$TMUX_PANE" "$NAME" 2>/dev/null

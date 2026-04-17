#!/bin/bash
# UserPromptSubmit hook: auto-name the session with Haiku after the first prompt.
# Skips if the session already has a name. Runs the API call in the background
# so the user's prompt is not blocked.
set -u

# Recursion guard: the inner `claude -p` call itself triggers UserPromptSubmit.
[ -n "${CLAUDE_AUTO_NAME_IN_PROGRESS:-}" ] && exit 0

INPUT=$(cat 2>/dev/null || true)
[ -z "$INPUT" ] && exit 0
command -v jq >/dev/null 2>&1 || exit 0

SID=$(printf '%s' "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
PROMPT=$(printf '%s' "$INPUT" | jq -r '.prompt // empty' 2>/dev/null)
[ -z "$SID" ] && exit 0
[ -z "$PROMPT" ] && exit 0

SESSION_FILE=$(grep -l "\"sessionId\":\"$SID\"" "$HOME"/.claude/sessions/*.json 2>/dev/null | head -1)
[ -z "$SESSION_FILE" ] && exit 0

HAS_NAME=$(jq -r '.name // empty' "$SESSION_FILE" 2>/dev/null)
[ -n "$HAS_NAME" ] && exit 0

LOG="$HOME/.claude/state/auto-name.log"
mkdir -p "$(dirname "$LOG")"

(
    export CLAUDE_AUTO_NAME_IN_PROGRESS=1
    GEN_PROMPT="Generate a short kebab-case slug (2-5 lowercase words separated by hyphens) that summarizes this task. Output ONLY the slug, nothing else.

Task: $PROMPT"

    NAME=$(printf '%s' "$GEN_PROMPT" | claude -p --model haiku --no-session-persistence 2>/dev/null)
    NAME=$(printf '%s' "$NAME" \
        | tr '[:upper:]' '[:lower:]' \
        | tr -cs 'a-z0-9-' '-' \
        | sed 's/^-*//;s/-*$//' \
        | cut -c1-40)

    if [ -z "$NAME" ]; then
        echo "$(date) sid=$SID name=EMPTY prompt=${PROMPT:0:80}" >> "$LOG"
        exit 0
    fi

    # Re-read in case another process wrote in the meantime.
    CUR=$(jq -r '.name // empty' "$SESSION_FILE" 2>/dev/null)
    if [ -n "$CUR" ]; then
        echo "$(date) sid=$SID name=SKIP-EXISTS($CUR)" >> "$LOG"
        exit 0
    fi

    TMP=$(mktemp)
    if jq --arg n "$NAME" '.name = $n' "$SESSION_FILE" > "$TMP" 2>/dev/null && [ -s "$TMP" ]; then
        mv "$TMP" "$SESSION_FILE"
        echo "$(date) sid=$SID name=$NAME" >> "$LOG"
    else
        rm -f "$TMP"
        echo "$(date) sid=$SID name=FAIL-WRITE" >> "$LOG"
    fi
) </dev/null >/dev/null 2>&1 &
disown 2>/dev/null || true

exit 0

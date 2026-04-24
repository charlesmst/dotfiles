#!/bin/bash
# UserPromptSubmit / beforeSubmitPrompt hook: auto-name the session with a fast
# model after the first prompt. Skips if the session already has a name. Runs
# the API call in the background so the user's prompt is not blocked.
#
# AGENT env var selects the backend:
#   AGENT=claude  -> reads {session_id, prompt}; names ~/.claude/sessions/<pid>.json
#   AGENT=cursor  -> reads {conversation_id, prompt}; names ~/.cursor/sessions/<pid>.json
set -u

AGENT="${AGENT:-claude}"

# Recursion guard: the inner naming `agent -p` call itself triggers the hook.
[ -n "${AGENT_AUTO_NAME_IN_PROGRESS:-}" ] && exit 0

INPUT=$(cat 2>/dev/null || true)
[ -z "$INPUT" ] && exit 0
command -v jq >/dev/null 2>&1 || exit 0

case "$AGENT" in
    claude)
        SID=$(printf '%s' "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
        SESSIONS_DIR="$HOME/.claude/sessions"
        SID_KEY="sessionId"
        ;;
    cursor)
        SID=$(printf '%s' "$INPUT" | jq -r '.conversation_id // empty' 2>/dev/null)
        SESSIONS_DIR="$HOME/.cursor/sessions"
        SID_KEY="sessionId"
        ;;
    *)
        exit 0
        ;;
esac

PROMPT=$(printf '%s' "$INPUT" | jq -r '.prompt // empty' 2>/dev/null)
[ -z "$SID" ] && exit 0
[ -z "$PROMPT" ] && exit 0

SESSION_FILE=$(grep -l "\"$SID_KEY\":\"$SID\"" "$SESSIONS_DIR"/*.json 2>/dev/null | head -1)
[ -z "$SESSION_FILE" ] && exit 0

HAS_NAME=$(jq -r '.name // empty' "$SESSION_FILE" 2>/dev/null)
[ -n "$HAS_NAME" ] && exit 0

LOG="${AGENT_ATTENTION_DIR:-$HOME/.local/state/agent-attention}/auto-name.log"
mkdir -p "$(dirname "$LOG")"

(
    export AGENT_AUTO_NAME_IN_PROGRESS=1
    GEN_PROMPT="Generate a short kebab-case slug (2-5 lowercase words separated by hyphens) that summarizes this task. Output ONLY the slug, nothing else.

Task: $PROMPT"

    case "$AGENT" in
        claude)
            if ! command -v claude >/dev/null 2>&1; then
                echo "$(date) agent=$AGENT sid=$SID name=NO-NAMER-CLI(claude)" >> "$LOG"
                exit 0
            fi
            # Claude reads the prompt from stdin.
            NAME=$(printf '%s' "$GEN_PROMPT" | claude -p --model haiku --no-session-persistence 2>/dev/null)
            ;;
        cursor)
            if ! command -v cursor-agent >/dev/null 2>&1; then
                echo "$(date) agent=$AGENT sid=$SID name=NO-NAMER-CLI(cursor-agent)" >> "$LOG"
                exit 0
            fi
            # cursor-agent takes the prompt as a positional arg, requires
            # --trust in headless mode, and only reaches a non-trusted cwd if
            # we explicitly pass --workspace. We force a known-trusted cwd
            # (the user's home) so naming never blocks on workspace trust.
            NAME=$(cursor-agent -p --trust \
                --output-format text \
                --model composer-2-fast \
                --workspace "$HOME" \
                "$GEN_PROMPT" 2>/dev/null)
            ;;
    esac

    NAME=$(printf '%s' "$NAME" \
        | tr '[:upper:]' '[:lower:]' \
        | tr -cs 'a-z0-9-' '-' \
        | sed 's/^-*//;s/-*$//' \
        | cut -c1-40)

    if [ -z "$NAME" ]; then
        echo "$(date) agent=$AGENT sid=$SID name=EMPTY prompt=${PROMPT:0:80}" >> "$LOG"
        exit 0
    fi

    # Re-read in case another process wrote in the meantime.
    CUR=$(jq -r '.name // empty' "$SESSION_FILE" 2>/dev/null)
    if [ -n "$CUR" ]; then
        echo "$(date) agent=$AGENT sid=$SID name=SKIP-EXISTS($CUR)" >> "$LOG"
        exit 0
    fi

    TMP=$(mktemp)
    # Compact output to keep "sessionId":"<sid>" greppable by sync-tmux-name.sh.
    if jq -c --arg n "$NAME" '.name = $n' "$SESSION_FILE" > "$TMP" 2>/dev/null && [ -s "$TMP" ]; then
        mv "$TMP" "$SESSION_FILE"
        echo "$(date) agent=$AGENT sid=$SID name=$NAME" >> "$LOG"
    else
        rm -f "$TMP"
        echo "$(date) agent=$AGENT sid=$SID name=FAIL-WRITE" >> "$LOG"
    fi
) </dev/null >/dev/null 2>&1 &
disown 2>/dev/null || true

exit 0

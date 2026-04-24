#!/bin/bash
# sessionEnd hook for Cursor CLI.
# Removes the ~/.cursor/sessions/<agent_pid>.json file written by
# write-session-meta.sh. The picker also drops sessions whose pid no longer
# exists, so this is a best-effort cleanup.
set -u

# Skip when invoked as a child of our own auto-name `cursor-agent -p` call —
# we don't want the helper invocation's exit to delete the parent's file.
[ -n "${AGENT_AUTO_NAME_IN_PROGRESS:-}" ] && { printf '{}'; exit 0; }

command -v jq >/dev/null 2>&1 || { printf '{}'; exit 0; }

INPUT=$(cat 2>/dev/null || true)
[ -z "$INPUT" ] && { printf '{}'; exit 0; }

SID=$(printf '%s' "$INPUT" | jq -r '.conversation_id // empty' 2>/dev/null)
[ -z "$SID" ] && { printf '{}'; exit 0; }

SESSIONS_DIR="$HOME/.cursor/sessions"
[ -d "$SESSIONS_DIR" ] || { printf '{}'; exit 0; }

# Remove every session file whose sessionId matches this conversation.
for f in "$SESSIONS_DIR"/*.json; do
    [ -e "$f" ] || continue
    if grep -q "\"sessionId\":\"$SID\"" "$f" 2>/dev/null; then
        rm -f "$f"
    fi
done

printf '{}'
exit 0

#!/bin/bash
# sessionStart hook for Cursor CLI.
# Writes ~/.cursor/sessions/<agent_pid>.json with the same shape Claude Code
# auto-writes for its own sessions, so the agent-attention picker can find
# Cursor sessions and map them to tmux panes.
#
# We discover the agent process PID by walking up from $PPID until we hit a
# process whose command matches the cursor-agent binary; that PID is what
# the picker's PID-to-tmux-pane walk will find as a child of the tmux pane.
set -u

# Skip when invoked as a child of our own auto-name `cursor-agent -p` call —
# we don't want the helper invocation to overwrite the parent session's file.
[ -n "${AGENT_AUTO_NAME_IN_PROGRESS:-}" ] && { printf '{}'; exit 0; }

command -v jq >/dev/null 2>&1 || exit 0

INPUT=$(cat 2>/dev/null || true)
[ -z "$INPUT" ] && exit 0

SID=$(printf '%s' "$INPUT" | jq -r '.conversation_id // empty' 2>/dev/null)
CWD=$(printf '%s' "$INPUT" | jq -r '.workspace_roots[0] // .cwd // empty' 2>/dev/null)
[ -z "$SID" ] && exit 0

# Walk up the process tree to find the topmost cursor-agent ancestor. The
# picker walks PPIDs from this PID until it hits a tmux pane, so we want a
# PID that is a descendant of the tmux pane shell (i.e. anything inside the
# agent process group works).
find_agent_pid() {
    local cur="$PPID" depth=0
    local agent_pid=""
    while [ -n "$cur" ] && [ "$cur" != "1" ] && [ "$cur" != "0" ] && [ "$depth" -lt 12 ]; do
        local cmd
        cmd=$(ps -p "$cur" -o command= 2>/dev/null)
        case "$cmd" in
            */cursor-agent/*|*/.local/bin/agent*|*cursor-agent*)
                agent_pid="$cur"
                ;;
        esac
        cur=$(ps -p "$cur" -o ppid= 2>/dev/null | tr -d ' ')
        depth=$((depth+1))
    done
    printf '%s' "$agent_pid"
}

AGENT_PID=$(find_agent_pid)
# Fallback: if we couldn't identify an agent ancestor, use $PPID. Picker walks
# parents anyway so this still works as long as $PPID is under the tmux pane.
[ -z "$AGENT_PID" ] && AGENT_PID="$PPID"

SESSIONS_DIR="$HOME/.cursor/sessions"
mkdir -p "$SESSIONS_DIR"

NOW=$(date +%s)
PROC_START=$(date '+%a %b %d %H:%M:%S %Y' 2>/dev/null)

# Output compact JSON (no spaces) to match Claude's session file format. Other
# scripts grep for "sessionId":"<sid>" without spaces.
jq -nc \
    --argjson pid "$AGENT_PID" \
    --arg sid "$SID" \
    --arg cwd "$CWD" \
    --argjson started_ms "$(( NOW * 1000 ))" \
    --arg proc_start "$PROC_START" \
    '{
        pid: $pid,
        sessionId: $sid,
        cwd: $cwd,
        startedAt: $started_ms,
        procStart: $proc_start,
        kind: "interactive",
        entrypoint: "cursor-cli"
    }' > "$SESSIONS_DIR/$AGENT_PID.json" 2>/dev/null

# Output an empty JSON object so the hook doesn't fail.
printf '{}'
exit 0

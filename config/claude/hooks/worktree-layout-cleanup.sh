#!/usr/bin/env bash
# Claude Code hook — tears down the tmux panes created by worktree-layout.sh
# when the corresponding worktree is deleted.
#
# Wires up on PostToolUse/Bash (catches `git worktree remove <path>`) and
# PostToolUse/ExitWorktree (Claude's native worktree feature, if exposed).
#
# For every pane in the current tmux window whose cwd is inside the deleted
# worktree, issue `kill-pane`. Claude's own pane is skipped so the session
# keeps running.

set -uo pipefail

command -v tmux >/dev/null 2>&1 || exit 0
[ -n "${TMUX:-}" ] || exit 0

INPUT=""
if [ ! -t 0 ]; then
  INPUT=$(cat)
fi

WTPATH=""
CWD=""
if [ -n "$INPUT" ] && command -v jq >/dev/null 2>&1; then
  CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // empty')
  CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty')

  if [ -n "$CMD" ] && printf '%s' "$CMD" | grep -qE '(^|[^[:alnum:]_-])git[[:space:]]+worktree[[:space:]]+remove([[:space:]]|$)'; then
    # First non-flag positional argument after `remove`.
    WTPATH=$(printf '%s' "$CMD" | awk '
      {
        seen=0
        for (i=1; i<=NF; i++) {
          if (!seen) { if ($i == "remove") seen=1; continue }
          if ($i ~ /^-/) continue
          print $i; exit
        }
      }')
  else
    # Native worktree-exit / remove events — try a few field names.
    WTPATH=$(printf '%s' "$INPUT" | jq -r '
      .tool_input.path
      // .tool_input.worktreePath
      // .tool_response.path
      // .tool_response.worktreePath
      // empty
    ')
  fi
fi

[ -n "$WTPATH" ] || exit 0

# Absolute-ize. The worktree directory may already be gone, so normalize via
# its parent (which still exists) rather than `cd $WTPATH`.
if [[ "$WTPATH" != /* ]]; then
  BASE="${CWD:-$PWD}"
  WTPATH="$BASE/$WTPATH"
fi
PARENT=$(cd "$(dirname "$WTPATH")" 2>/dev/null && pwd -P) || exit 0
WTPATH="$PARENT/$(basename "$WTPATH")"

CLAUDE_PANE=$(tmux display-message -p '#{pane_id}')
WINDOW=$(tmux display-message -p '#{window_id}')

tmux list-panes -t "$WINDOW" -F '#{pane_id} #{pane_current_path}' | \
while read -r PID PPATH; do
  [ "$PID" = "$CLAUDE_PANE" ] && continue
  case "$PPATH" in
    "$WTPATH"|"$WTPATH"/*) tmux kill-pane -t "$PID" 2>/dev/null || true ;;
  esac
done

exit 0

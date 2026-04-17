#!/usr/bin/env bash
# Claude Code hook — builds a tmux layout the first time Claude enters a
# git worktree. Layout:
#
#     +---------+---------------+---------+
#     |         |     nvim      |         |
#     | Claude  +---------------+ lazygit |
#     |         |     shell     |         |
#     +---------+---------------+---------+
#
# Intended to be wired up on any event whose payload carries `.cwd` (e.g.
# CwdChanged, SessionStart) and optionally on PostToolUse/Bash so a
# `git worktree add <path>` command also triggers it.
#
# No-ops unless all of:
#   - running inside tmux
#   - current window has exactly one pane
#   - target path is inside a git worktree (git-dir != git-common-dir)
#   - target worktree has not been laid out before (marker file absent)
#
# Also runs `mise trust` once if a mise/asdf config is present.

set -uo pipefail

command -v tmux >/dev/null 2>&1 || exit 0
[ -n "${TMUX:-}" ] || exit 0

INPUT=""
if [ ! -t 0 ]; then
  INPUT=$(cat)
fi

# --- Resolve candidate worktree path ------------------------------------------
WTPATH=""
CWD=""
if [ -n "$INPUT" ] && command -v jq >/dev/null 2>&1; then
  CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // empty')
  CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty')

  if [ -n "$CMD" ] && printf '%s' "$CMD" | grep -qE '(^|[^[:alnum:]_-])git[[:space:]]+worktree[[:space:]]+add([[:space:]]|$)'; then
    # PostToolUse/Bash: first non-flag positional arg after `add`.
    WTPATH=$(printf '%s' "$CMD" | awk '
      {
        seen=0
        for (i=1; i<=NF; i++) {
          if (!seen) { if ($i == "add") seen=1; continue }
          if ($i ~ /^-/) {
            if ($i == "-b" || $i == "-B") i++
            continue
          }
          print $i; exit
        }
      }')
  else
    # EnterWorktree (or similar) — look in tool_response / tool_input for a path.
    WTPATH=$(printf '%s' "$INPUT" | jq -r '
      .tool_response.worktreePath
      // .tool_response.path
      // .tool_response.worktree_path
      // .tool_input.path
      // .tool_input.worktreePath
      // empty
    ')
  fi
fi

# Fallbacks: payload cwd, then process cwd.
[ -z "$WTPATH" ] && WTPATH="$CWD"
[ -z "$WTPATH" ] && WTPATH="$PWD"

# Make relative paths absolute.
if [[ "$WTPATH" != /* ]]; then
  BASE="${CWD:-$PWD}"
  WTPATH="$BASE/$WTPATH"
fi
WTPATH=$(cd "$WTPATH" 2>/dev/null && pwd -P) || exit 0

# --- Confirm this is a worktree (not main repo, not outside git) --------------
GITDIR=$(cd "$WTPATH" && git rev-parse --git-dir 2>/dev/null) || exit 0
COMMON=$(cd "$WTPATH" && git rev-parse --git-common-dir 2>/dev/null) || exit 0
[[ "$GITDIR" != /* ]] && GITDIR="$WTPATH/$GITDIR"
[[ "$COMMON" != /* ]] && COMMON="$WTPATH/$COMMON"
GITDIR=$(cd "$GITDIR" 2>/dev/null && pwd -P) || exit 0
COMMON=$(cd "$COMMON" 2>/dev/null && pwd -P) || exit 0
[ "$GITDIR" = "$COMMON" ] && exit 0

# --- Idempotency: mark-on-create so re-triggers no-op -------------------------
MARKER="$WTPATH/.claude/.tmux-layout-done"
[ -f "$MARKER" ] && exit 0

# --- tmux: require single-pane window -----------------------------------------
PANES=$(tmux display-message -p '#{window_panes}' 2>/dev/null) || exit 0
[ "$PANES" -eq 1 ] || exit 0

# --- mise trust (best effort) -------------------------------------------------
if command -v mise >/dev/null 2>&1; then
  if [ -f "$WTPATH/.mise.toml" ] || [ -f "$WTPATH/mise.toml" ] || [ -f "$WTPATH/.tool-versions" ]; then
    (cd "$WTPATH" && mise trust >/dev/null 2>&1) || true
  fi
fi

mkdir -p "$(dirname "$MARKER")" 2>/dev/null && : > "$MARKER" 2>/dev/null || true

# --- Build layout -------------------------------------------------------------
CLAUDE_PANE=$(tmux display-message -p '#{pane_id}')
RIGHT=$(tmux split-window -h -c "$WTPATH" -t "$CLAUDE_PANE" -l 67% -P -F '#{pane_id}')
LAZYGIT=$(tmux split-window -h -c "$WTPATH" -t "$RIGHT" -l 50% -P -F '#{pane_id}')
tmux split-window -v -c "$WTPATH" -t "$RIGHT" -l 30% >/dev/null

tmux send-keys -t "$RIGHT"   'nvim'    Enter
tmux send-keys -t "$LAZYGIT" 'lazygit' Enter
tmux select-pane -t "$CLAUDE_PANE"

exit 0

#!/bin/bash
# Mark a tmux pane as currently working (Claude is processing a prompt).
# Called from Claude Code's UserPromptSubmit hook.
# Inherits TMUX_PANE from the pane Claude is running in.
set -u

PANE="${TMUX_PANE:-}"
[ -z "$PANE" ] && exit 0

BASE="${CLAUDE_ATTENTION_DIR:-$HOME/.claude/state}"
mkdir -p "$BASE/working" "$BASE/pending"

SAFE="${PANE//\//_}"
touch "$BASE/working/$SAFE"

rm -f "$BASE/pending/$SAFE"

bash "$HOME/personal/dotfiles/tmux/claude-attention/refresh-caches.sh" --force >/dev/null 2>&1 &
disown 2>/dev/null || true
exit 0

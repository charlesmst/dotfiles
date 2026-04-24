#!/bin/bash
# Focus the tmux pane where the agent (Claude Code or Cursor CLI) is running.
# Called by terminal-notifier when the notification is clicked.
# Usage: focus-agent-pane.sh <session_name> <window_index> <pane_id>

# terminal-notifier launches with a minimal PATH; ensure tmux is reachable.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

SESSION="$1"
WINDOW="$2"
PANE="$3"

tmux select-window -t "${SESSION}:${WINDOW}" 2>/dev/null
tmux select-pane -t "${PANE}" 2>/dev/null
osascript -e 'tell application "Terminal" to activate' 2>/dev/null

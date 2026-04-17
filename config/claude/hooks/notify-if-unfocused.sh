#!/bin/bash
# Notify user if they're not focused on the Claude Code tmux pane.
# Plays "fahhhhhhhhh" sound and shows a clickable macOS notification.
# Clicking the notification focuses the terminal and selects the tmux pane.

CLAUDE_PANE="${TMUX_PANE}"

# If not in tmux, always notify
if [ -z "$CLAUDE_PANE" ]; then
    terminal-notifier \
        -title "Claude Code" \
        -message "Needs your attention" \
        -sound "" \
        &>/dev/null &
    afplay -v 0.2 ~/.claude/sounds/fahhh.mp3 &
    exit 0
fi

# Get pane info for the notification
PANE_INFO=$(tmux display-message -t "$CLAUDE_PANE" -p '#{session_name}:#{window_index}.#{pane_index}' 2>/dev/null)
SESSION_NAME=$(tmux display-message -t "$CLAUDE_PANE" -p '#{session_name}' 2>/dev/null)
WINDOW_INDEX=$(tmux display-message -t "$CLAUDE_PANE" -p '#{window_index}' 2>/dev/null)

# Check if Claude's window and pane are both active
WINDOW_ACTIVE=$(tmux display-message -t "$CLAUDE_PANE" -p '#{window_active}' 2>/dev/null)
PANE_ACTIVE=$(tmux display-message -t "$CLAUDE_PANE" -p '#{pane_active}' 2>/dev/null)

IS_FOCUSED=false

if [ "$WINDOW_ACTIVE" = "1" ] && [ "$PANE_ACTIVE" = "1" ]; then
    # Pane is active in tmux - also check if terminal app is frontmost
    FRONT_APP=$(osascript -e 'tell application "System Events" to get name of first process whose frontmost is true' 2>/dev/null)
    case "$FRONT_APP" in
        *Terminal*|*iTerm*|*Alacritty*|*kitty*|*WezTerm*|*Ghostty*)
            IS_FOCUSED=true
            ;;
    esac
fi

if [ "$IS_FOCUSED" = "false" ]; then
    FOCUS_SCRIPT="${HOME}/.claude/hooks/focus-claude-pane.sh"

    "${HOME}/personal/dotfiles/tmux/claude-attention/mark-pending.sh" "$CLAUDE_PANE" &
    "${HOME}/personal/dotfiles/tmux/claude-attention/refresh-caches.sh" --force &

    terminal-notifier \
        -title "Claude Code" \
        -subtitle "Needs your attention" \
        -message "tmux ${PANE_INFO}" \
        -sound "" \
        -execute "bash '${FOCUS_SCRIPT}' '${SESSION_NAME}' '${WINDOW_INDEX}' '${CLAUDE_PANE}'" \
        &>/dev/null &
    afplay -v 0.2 ~/.claude/sounds/fahhh.mp3 &
fi

exit 0

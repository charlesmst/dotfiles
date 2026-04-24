#!/bin/bash
# Notify the user if they're not focused on the agent's tmux pane.
# Plays a sound and shows a clickable macOS notification. Clicking the
# notification focuses the terminal and selects the tmux pane.
#
# Used by Claude Code (Notification + Stop hooks) and Cursor CLI (stop hook).
# AGENT env var controls the displayed app name and which sound is played.

AGENT="${AGENT:-claude}"

case "$AGENT" in
    claude)
        APP_TITLE="Claude Code"
        SOUND_FILE="$HOME/.claude/sounds/fahhh.mp3"
        ;;
    cursor)
        APP_TITLE="Cursor CLI"
        SOUND_FILE="$HOME/.claude/sounds/fahhh.mp3"
        ;;
    *)
        APP_TITLE="Agent"
        SOUND_FILE="$HOME/.claude/sounds/fahhh.mp3"
        ;;
esac

CLAUDE_PANE="${TMUX_PANE}"

if [ -z "$CLAUDE_PANE" ]; then
    terminal-notifier \
        -title "$APP_TITLE" \
        -message "Needs your attention" \
        -sound "" \
        &>/dev/null &
    [ -r "$SOUND_FILE" ] && afplay -v 0.2 "$SOUND_FILE" &
    exit 0
fi

PANE_INFO=$(tmux display-message -t "$CLAUDE_PANE" -p '#{session_name}:#{window_index}.#{pane_index}' 2>/dev/null)
SESSION_NAME=$(tmux display-message -t "$CLAUDE_PANE" -p '#{session_name}' 2>/dev/null)
WINDOW_INDEX=$(tmux display-message -t "$CLAUDE_PANE" -p '#{window_index}' 2>/dev/null)

WINDOW_ACTIVE=$(tmux display-message -t "$CLAUDE_PANE" -p '#{window_active}' 2>/dev/null)
PANE_ACTIVE=$(tmux display-message -t "$CLAUDE_PANE" -p '#{pane_active}' 2>/dev/null)

IS_FOCUSED=false

if [ "$WINDOW_ACTIVE" = "1" ] && [ "$PANE_ACTIVE" = "1" ]; then
    FRONT_APP=$(osascript -e 'tell application "System Events" to get name of first process whose frontmost is true' 2>/dev/null)
    case "$FRONT_APP" in
        *Terminal*|*iTerm*|*Alacritty*|*kitty*|*WezTerm*|*Ghostty*)
            IS_FOCUSED=true
            ;;
    esac
fi

if [ "$IS_FOCUSED" = "false" ]; then
    FOCUS_SCRIPT="${HOME}/.claude/hooks/focus-agent-pane.sh"
    [ -r "$FOCUS_SCRIPT" ] || FOCUS_SCRIPT="${HOME}/personal/dotfiles/config/agent-shared/focus-agent-pane.sh"

    "${HOME}/personal/dotfiles/tmux/agent-attention/mark-pending.sh" "$CLAUDE_PANE" &
    "${HOME}/personal/dotfiles/tmux/agent-attention/refresh-caches.sh" --force &

    terminal-notifier \
        -title "$APP_TITLE" \
        -subtitle "Needs your attention" \
        -message "tmux ${PANE_INFO}" \
        -sound "" \
        -execute "bash '${FOCUS_SCRIPT}' '${SESSION_NAME}' '${WINDOW_INDEX}' '${CLAUDE_PANE}'" \
        &>/dev/null &
    [ -r "$SOUND_FILE" ] && afplay -v 0.2 "$SOUND_FILE" &
fi

exit 0

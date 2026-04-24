#!/bin/bash
# fzf picker over currently-running agent (Claude + Cursor CLI) sessions
# mapped to their tmux panes.
# Marker states:
#   ●       yellow  = needs attention (pending marker set by Notification/Stop)
#   spinner cyan    = working         (UserPromptSubmit fired, Stop not yet)
#   blank           = idle
# Agent badge:
#   C  cyan    = Claude Code
#   ✦  magenta = Cursor CLI
# Ctrl-D on a row: kill the agent process in that pane and refresh the list.
# Ctrl-R: force refresh. The spinner animates while the picker is open.
# Source of truth:
#   Claude: ~/.claude/sessions/*.json (auto-written by Claude itself)
#   Cursor: ~/.cursor/sessions/*.json (written by our sessionStart hook)
#   Markers: $BASE/{pending,working}/
set -u

BASE="${AGENT_ATTENTION_DIR:-$HOME/.local/state/agent-attention}"
PENDING_DIR="$BASE/pending"
WORKING_DIR="$BASE/working"
CLAUDE_SESSIONS_DIR="$HOME/.claude/sessions"
CURSOR_SESSIONS_DIR="$HOME/.cursor/sessions"
mkdir -p "$PENDING_DIR" "$WORKING_DIR"

W_BADGE=2
W_SWP=24
W_TOPIC=58
W_AGE=6

SPIN_PLACEHOLDER='{SPIN}'
SPIN_FRAMES=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')

C_YELLOW=$'\033[33m'
C_CYAN=$'\033[36m'
C_MAGENTA=$'\033[35m'
C_RESET=$'\033[0m'

# Extract the first user prompt from a Claude transcript jsonl file.
extract_topic_claude() {
    local transcript="$1"
    [ -r "$transcript" ] || return 0
    command -v jq >/dev/null 2>&1 || return 0
    jq -r '
        select(.type == "user") |
        .message.content |
        if type == "string" then .
        else (.. | objects | select(.type? == "text") | .text) // empty
        end
    ' "$transcript" 2>/dev/null \
      | grep -v '^\[Request interrupted' \
      | grep -v '^<command-' \
      | head -1 \
      | tr '\n\t' '  '
}

# Extract the first user prompt from a Cursor agent-transcripts jsonl file.
# Cursor wraps prompts in <timestamp>...</timestamp>\n<user_query>...</user_query>;
# pull out the inner <user_query> text when present, otherwise fall back to
# stripping all tags. Also skip system_reminder / system_notification blocks.
extract_topic_cursor() {
    local transcript="$1"
    [ -r "$transcript" ] || return 0
    command -v jq >/dev/null 2>&1 || return 0
    jq -r '
        select(.role == "user") |
        .message.content |
        if type == "string" then .
        else (.. | objects | select(.type? == "text") | .text) // empty
        end
    ' "$transcript" 2>/dev/null \
      | awk '
          /<user_query>/        { in_q=1; next }
          /<\/user_query>/      { in_q=0; exit }
          in_q                  { print }
        ' \
      | sed 's/<[^>]*>//g' \
      | grep -v '^[[:space:]]*$' \
      | head -1 \
      | tr '\n\t' '  '
}

fit() {
    local s="$1" w="$2"
    if [ "${#s}" -gt "$w" ]; then
        printf '%s…' "${s:0:$((w-1))}"
    else
        printf "%-${w}s" "$s"
    fi
}

find_tmux_pane() {
    local pid="$1" snapshot="$2"
    local depth=0 cur="$pid"
    while [ -n "$cur" ] && [ "$cur" != "1" ] && [ "$cur" != "0" ] && [ "$depth" -lt 12 ]; do
        local match
        match=$(printf '%s\n' "$snapshot" | awk -F'|' -v p="$cur" '$1==p{print; exit}')
        if [ -n "$match" ]; then
            printf '%s' "$match"
            return 0
        fi
        cur=$(ps -p "$cur" -o ppid= 2>/dev/null | tr -d ' ')
        depth=$((depth+1))
    done
    return 1
}

format_age() {
    local age="$1"
    if   [ "$age" -lt 60   ]; then printf '%ss'  "$age"
    elif [ "$age" -lt 3600 ]; then printf '%sm'  "$((age/60))"
    else                            printf '%sh' "$((age/3600))"
    fi
}

# Build a row for one session file.
# Args: <agent> <session_file> <pane_snapshot> <now>
# Sets a global $ROW with the tab-separated row, or returns 1.
build_row_for_session() {
    local agent="$1" sfile="$2" pane_snapshot="$3" now="$4"
    ROW=""

    local agent_pid sid cwd name pane_line pane_id swp tmux_session window_idx
    agent_pid=$(jq -r '.pid // empty' "$sfile" 2>/dev/null)
    sid=$(jq -r '.sessionId // empty' "$sfile" 2>/dev/null)
    cwd=$(jq -r '.cwd // empty' "$sfile" 2>/dev/null)
    name=$(jq -r '.name // empty' "$sfile" 2>/dev/null)
    [ -z "$agent_pid" ] || [ -z "$sid" ] && return 1
    kill -0 "$agent_pid" 2>/dev/null || return 1

    pane_line=$(find_tmux_pane "$agent_pid" "$pane_snapshot") || return 1
    pane_id=$(printf '%s' "$pane_line" | awk -F'|' '{print $2}')
    swp=$(printf '%s' "$pane_line" | awk -F'|' '{print $3}')
    tmux_session=$(printf '%s' "$pane_line" | awk -F'|' '{print $4}')
    window_idx=$(printf '%s' "$pane_line" | awk -F'|' '{print $5}')

    local state mark ago mtime age
    if [ -e "$PENDING_DIR/$pane_id" ]; then
        state=0
        mark="${C_YELLOW}●${C_RESET} "
        mtime=$(stat -f %m "$PENDING_DIR/$pane_id" 2>/dev/null || echo "$now")
        age=$(( now - mtime ))
        ago=$(format_age "$age")
    elif [ -e "$WORKING_DIR/$pane_id" ]; then
        state=1
        mark="${SPIN_PLACEHOLDER} "
        mtime=$(stat -f %m "$WORKING_DIR/$pane_id" 2>/dev/null || echo "$now")
        age=$(( now - mtime ))
        ago=$(format_age "$age")
    else
        state=2
        mark="  "
        ago="-"
    fi

    local badge
    case "$agent" in
        claude) badge="${C_CYAN}C${C_RESET}" ;;
        cursor) badge="${C_MAGENTA}✦${C_RESET}" ;;
        *)      badge="?" ;;
    esac

    local label
    if [ -n "$name" ]; then
        label="★ $name"
    else
        local transcript=""
        case "$agent" in
            claude)
                local encoded_cwd=${cwd//\//-}
                transcript="$HOME/.claude/projects/$encoded_cwd/$sid.jsonl"
                label=$(extract_topic_claude "$transcript")
                ;;
            cursor)
                # Cursor stores transcripts at:
                # ~/.cursor/projects/<cwd-with-slashes-as-dashes>/agent-transcripts/<sid>/<sid>.jsonl
                local encoded_cwd=${cwd//\//-}
                # Strip leading dash from absolute paths.
                encoded_cwd=${encoded_cwd#-}
                transcript="$HOME/.cursor/projects/$encoded_cwd/agent-transcripts/$sid/$sid.jsonl"
                label=$(extract_topic_cursor "$transcript")
                ;;
        esac
        [ -z "$label" ] && label="-"
    fi

    local display
    display=$(printf '%s %s%s  %s  %s' \
        "$badge" \
        "$mark" \
        "$(fit "$swp"   "$W_SWP")" \
        "$(fit "$label" "$W_TOPIC")" \
        "$(fit "$ago"   "$W_AGE")")

    ROW=$(printf '%s\t%s\t%s\t%s\t%s\t%s' \
        "$state" "$display" "$pane_id" "$tmux_session" "$window_idx" "$agent_pid")
    return 0
}

build_rows() {
    local pane_snapshot now rows=""
    pane_snapshot=$(tmux list-panes -a -F '#{pane_pid}|#{pane_id}|#{session_name}:#{window_index}.#{pane_index}|#{session_name}|#{window_index}' 2>/dev/null)
    now=$(date +%s)

    local sfile
    for sfile in "$CLAUDE_SESSIONS_DIR"/*.json; do
        [ -e "$sfile" ] || continue
        if build_row_for_session claude "$sfile" "$pane_snapshot" "$now"; then
            rows+="$ROW"$'\n'
        fi
    done
    for sfile in "$CURSOR_SESSIONS_DIR"/*.json; do
        [ -e "$sfile" ] || continue
        if build_row_for_session cursor "$sfile" "$pane_snapshot" "$now"; then
            rows+="$ROW"$'\n'
        fi
    done

    printf '%s' "$rows" | LC_ALL=C sort -t$'\t' -k1,1n -k2,2 | cut -f2-
}

CACHE="$BASE/picker-cache.txt"
STALE_SECS="${AGENT_ATTENTION_STALE:-5}"

cache_age() {
    [ -f "$CACHE" ] || { echo 999999; return; }
    local mtime now
    mtime=$(stat -f %m "$CACHE" 2>/dev/null || echo 0)
    now=$(date +%s)
    echo $(( now - mtime ))
}

refresh_cache() {
    local tmp
    tmp=$(mktemp "$CACHE.XXXXXX")
    if build_rows > "$tmp"; then
        mv "$tmp" "$CACHE"
    else
        rm -f "$tmp"
    fi
}

render_cache() {
    # Substitute the spinner placeholder with the current animation frame,
    # pulled from $AGENT_SPIN_FRAME (0-9). Defaults to frame 0 if unset.
    [ -f "$CACHE" ] || return 0
    local frame="${AGENT_SPIN_FRAME:-0}"
    case "$frame" in *[!0-9]*) frame=0 ;; esac
    local spin="${SPIN_FRAMES[$(( frame % 10 ))]}"
    local replacement="${C_CYAN}${spin}${C_RESET}"
    sed "s|${SPIN_PLACEHOLDER}|${replacement}|g" "$CACHE"
}

# --list: print rows. Fast path — serves cache immediately, refreshes async if stale.
if [ "${1:-}" = "--list" ]; then
    if [ ! -f "$CACHE" ]; then
        refresh_cache
    elif [ "$(cache_age)" -ge "$STALE_SECS" ]; then
        (refresh_cache >/dev/null 2>&1 &)
    fi
    render_cache
    exit 0
fi

# --refresh-cache: rebuild cache if older than $STALE_SECS. For tmux hooks.
if [ "${1:-}" = "--refresh-cache" ]; then
    if [ "$(cache_age)" -ge "$STALE_SECS" ]; then
        refresh_cache
    fi
    exit 0
fi

# --refresh-now: rebuild cache regardless of age. For notify / working hooks.
if [ "${1:-}" = "--refresh-now" ]; then
    refresh_cache
    exit 0
fi

# Interactive mode: ensure cache is warm, then launch fzf with a background
# animator that reloads every ~250ms to advance the spinner frame.
if [ ! -f "$CACHE" ]; then
    refresh_cache
fi
(bash "${BASH_SOURCE[0]:-$0}" --refresh-cache >/dev/null 2>&1 &)

# Prune stale markers for panes no longer in the active agent list.
live_panes=$(cut -f2 "$CACHE" 2>/dev/null)
for dir in "$PENDING_DIR" "$WORKING_DIR"; do
    for p in "$dir"/*; do
        [ -e "$p" ] || continue
        pid=$(basename "$p")
        printf '%s\n' "$live_panes" | grep -qx "$pid" || rm -f "$p"
    done
done

if [ ! -s "$CACHE" ]; then
    tmux display-message "No live agent sessions"
    exit 0
fi

header=$(printf '%-*s %s  %s  %s' \
    "$W_BADGE" "ag" \
    "$(printf "%-${W_SWP}s"   "session:w.p")" \
    "$(printf "%-${W_TOPIC}s" "topic")" \
    "$(printf "%-${W_AGE}s"   "age")")

SELF="${BASH_SOURCE[0]:-$0}"

# Animator: while this file exists, fzf is alive. Each tick POSTs a reload to
# fzf's listen port with an incrementing AGENT_SPIN_FRAME env var.
PORT_FILE=$(mktemp -t agent-picker-port.XXXXXX)
trap 'rm -f "$PORT_FILE"' EXIT

(
    frame=0
    while [ -f "$PORT_FILE" ]; do
        sleep 0.25
        port=$(cat "$PORT_FILE" 2>/dev/null)
        [ -z "$port" ] && continue
        curl -sS -m 0.2 -X POST "http://localhost:${port}" \
            -d "reload(AGENT_SPIN_FRAME=${frame} bash '$SELF' --list)" \
            >/dev/null 2>&1 || true
        frame=$(( (frame + 1) % 10 ))
    done
) >/dev/null 2>&1 &

selected=$(AGENT_SPIN_FRAME=0 bash "$SELF" --list | fzf \
    --listen \
    --delimiter=$'\t' \
    --with-nth=1 \
    --nth=1 \
    --prompt='agent> ' \
    --header="$header  [ctrl-d: kill | ctrl-r: refresh]" \
    --header-first \
    --preview='tmux capture-pane -ep -t {2} 2>/dev/null | tail -40' \
    --preview-window='down:65%:wrap' \
    --no-sort \
    --ansi \
    --bind "start:execute-silent(printf '%s' \$FZF_PORT > '$PORT_FILE')" \
    --bind "ctrl-d:execute-silent(kill {5} 2>/dev/null; sleep 0.4; bash '$SELF' --refresh-now)+reload(bash '$SELF' --list)" \
    --bind "ctrl-r:execute-silent(bash '$SELF' --refresh-now)+reload(bash '$SELF' --list)")

rm -f "$PORT_FILE"

[ -z "$selected" ] && exit 0

pane_id=$(printf '%s' "$selected" | awk -F'\t' '{print $2}')
tmux_session=$(printf '%s' "$selected" | awk -F'\t' '{print $3}')
window_idx=$(printf '%s' "$selected" | awk -F'\t' '{print $4}')

tmux switch-client -t "$tmux_session" \; select-window -t "$tmux_session:$window_idx" \; select-pane -t "$pane_id"

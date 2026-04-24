#!/bin/bash
# fzf picker over currently-running Claude sessions mapped to their tmux panes.
# States:
#   ●       yellow  = needs attention (pending marker set by Notification/Stop)
#   spinner cyan    = working         (UserPromptSubmit fired, Stop not yet)
#   blank           = idle
# Ctrl-D on a row: kill Claude process in that pane and refresh the list.
# Ctrl-R: force refresh. The spinner animates while the picker is open.
# Source of truth: ~/.claude/sessions/*.json + $BASE/{pending,working}/.
set -u

BASE="${CLAUDE_ATTENTION_DIR:-$HOME/.claude/state}"
PENDING_DIR="$BASE/pending"
WORKING_DIR="$BASE/working"
SESSIONS_DIR="$HOME/.claude/sessions"
mkdir -p "$PENDING_DIR" "$WORKING_DIR"

W_SWP=28
W_TOPIC=60
W_AGE=6

SPIN_PLACEHOLDER='{SPIN}'
SPIN_FRAMES=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')

C_YELLOW=$'\033[33m'
C_CYAN=$'\033[36m'
C_RESET=$'\033[0m'

extract_topic() {
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

build_rows() {
    local pane_snapshot now rows=""
    pane_snapshot=$(tmux list-panes -a -F '#{pane_pid}|#{pane_id}|#{session_name}:#{window_index}.#{pane_index}|#{session_name}|#{window_index}' 2>/dev/null)
    now=$(date +%s)

    for sfile in "$SESSIONS_DIR"/*.json; do
        [ -e "$sfile" ] || continue
        local claude_pid sid cwd name pane_line pane_id swp tmux_session window_idx
        claude_pid=$(jq -r '.pid // empty' "$sfile" 2>/dev/null)
        sid=$(jq -r '.sessionId // empty' "$sfile" 2>/dev/null)
        cwd=$(jq -r '.cwd // empty' "$sfile" 2>/dev/null)
        name=$(jq -r '.name // empty' "$sfile" 2>/dev/null)
        [ -z "$claude_pid" ] || [ -z "$sid" ] && continue
        kill -0 "$claude_pid" 2>/dev/null || continue

        pane_line=$(find_tmux_pane "$claude_pid" "$pane_snapshot") || continue
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

        local label
        if [ -n "$name" ]; then
            label="★ $name"
        else
            local encoded_cwd transcript
            encoded_cwd=${cwd//\//-}
            transcript="$HOME/.claude/projects/$encoded_cwd/$sid.jsonl"
            label=$(extract_topic "$transcript")
            [ -z "$label" ] && label="-"
        fi

        local display
        display=$(printf '%s%s  %s  %s' \
            "$mark" \
            "$(fit "$swp"   "$W_SWP")" \
            "$(fit "$label" "$W_TOPIC")" \
            "$(fit "$ago"   "$W_AGE")")

        rows+="$state	$display	$pane_id	$tmux_session	$window_idx	$claude_pid"$'\n'
    done

    printf '%s' "$rows" | LC_ALL=C sort -t$'\t' -k1,1n -k2,2 | cut -f2-
}

CACHE="$BASE/picker-cache.txt"
STALE_SECS="${CLAUDE_ATTENTION_STALE:-5}"

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
    # pulled from $CLAUDE_SPIN_FRAME (0-9). Defaults to frame 0 if unset.
    [ -f "$CACHE" ] || return 0
    local frame="${CLAUDE_SPIN_FRAME:-0}"
    case "$frame" in *[!0-9]*) frame=0 ;; esac
    local spin="${SPIN_FRAMES[$(( frame % 10 ))]}"
    local replacement="${C_CYAN}${spin}${C_RESET}"
    # sed-escape the placeholder (no regex chars besides {}) — use | as delimiter
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

# Prune stale markers for panes no longer in the active Claude list.
live_panes=$(cut -f2 "$CACHE" 2>/dev/null)
for dir in "$PENDING_DIR" "$WORKING_DIR"; do
    for p in "$dir"/*; do
        [ -e "$p" ] || continue
        pid=$(basename "$p")
        printf '%s\n' "$live_panes" | grep -qx "$pid" || rm -f "$p"
    done
done

if [ ! -s "$CACHE" ]; then
    tmux display-message "No live Claude sessions"
    exit 0
fi

header=$(printf '%s  %s  %s' \
    "$(printf "%-${W_SWP}s"   "session:w.p")" \
    "$(printf "%-${W_TOPIC}s" "topic")" \
    "$(printf "%-${W_AGE}s"   "age")")

SELF="${BASH_SOURCE[0]:-$0}"

# Animator: while this file exists, fzf is alive. Each tick POSTs a reload to
# fzf's listen port with an incrementing CLAUDE_SPIN_FRAME env var.
PORT_FILE=$(mktemp -t claude-picker-port.XXXXXX)
trap 'rm -f "$PORT_FILE"' EXIT

(
    frame=0
    while [ -f "$PORT_FILE" ]; do
        sleep 0.25
        port=$(cat "$PORT_FILE" 2>/dev/null)
        [ -z "$port" ] && continue
        curl -sS -m 0.2 -X POST "http://localhost:${port}" \
            -d "reload(CLAUDE_SPIN_FRAME=${frame} bash '$SELF' --list)" \
            >/dev/null 2>&1 || true
        frame=$(( (frame + 1) % 10 ))
    done
) >/dev/null 2>&1 &

selected=$(CLAUDE_SPIN_FRAME=0 bash "$SELF" --list | fzf \
    --listen \
    --delimiter=$'\t' \
    --with-nth=1 \
    --nth=1 \
    --prompt='claude> ' \
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

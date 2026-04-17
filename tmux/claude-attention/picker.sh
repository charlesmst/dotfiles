#!/bin/bash
# fzf picker over currently-running Claude sessions mapped to their tmux panes.
# Ctrl-D on a row: kill Claude process in that pane and refresh the list.
# Source of truth: ~/.claude/sessions/*.json.
set -u

BASE="${CLAUDE_ATTENTION_DIR:-$HOME/.claude/state}"
PENDING_DIR="$BASE/pending"
SESSIONS_DIR="$HOME/.claude/sessions"
mkdir -p "$PENDING_DIR"

W_MARK=2
W_SWP=28
W_TOPIC=60
W_AGE=6

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

        local mark ago mtime age
        if [ -e "$PENDING_DIR/$pane_id" ]; then
            mark="● "
            mtime=$(stat -f %m "$PENDING_DIR/$pane_id" 2>/dev/null || echo "$now")
            age=$(( now - mtime ))
            if   [ "$age" -lt 60   ]; then ago="${age}s"
            elif [ "$age" -lt 3600 ]; then ago="$((age/60))m"
            else                            ago="$((age/3600))h"
            fi
        else
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
        display=$(printf '%s %s  %s  %s' \
            "$mark" \
            "$(fit "$swp"   "$W_SWP")" \
            "$(fit "$label" "$W_TOPIC")" \
            "$(fit "$ago"   "$W_AGE")")

        rows+="$display	$pane_id	$tmux_session	$window_idx	$claude_pid"$'\n'
    done

    printf '%s' "$rows" | awk -F'\t' 'BEGIN{OFS="\t"} NF>0 {key = ($1 ~ /^●/) ? "0" : "1"; print key, $0}' \
        | LC_ALL=C sort -t$'\t' -k1,1 -k2,2 \
        | cut -f2-
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

# --list: print current rows (cache if fresh, else rebuild). Used by fzf reload.
if [ "${1:-}" = "--list" ]; then
    if [ "$(cache_age)" -lt "$STALE_SECS" ]; then
        cat "$CACHE"
    else
        build_rows | tee "$CACHE"
    fi
    exit 0
fi

# --refresh-cache: rebuild cache if older than $STALE_SECS. For tmux hooks.
if [ "${1:-}" = "--refresh-cache" ]; then
    if [ "$(cache_age)" -ge "$STALE_SECS" ]; then
        refresh_cache
    fi
    exit 0
fi

# --refresh-now: rebuild cache regardless of age. For notify hook (new pending marker).
if [ "${1:-}" = "--refresh-now" ]; then
    refresh_cache
    exit 0
fi

# Interactive mode: read cache immediately, then trigger background refresh.
if [ -f "$CACHE" ]; then
    rows=$(cat "$CACHE")
else
    rows=$(build_rows)
    printf '%s' "$rows" > "$CACHE"
fi
(bash "${BASH_SOURCE[0]:-$0}" --refresh-cache >/dev/null 2>&1 &)

# Prune pending markers for panes that are no longer in the active Claude list.
live_panes=$(printf '%s' "$rows" | awk -F'\t' '{print $2}')
for p in "$PENDING_DIR"/*; do
    [ -e "$p" ] || continue
    pid=$(basename "$p")
    printf '%s\n' "$live_panes" | grep -qx "$pid" || rm -f "$p"
done

if [ -z "$rows" ]; then
    tmux display-message "No live Claude sessions"
    exit 0
fi

header=$(printf '%s %s  %s  %s' \
    "$(printf "%-${W_MARK}s" " ")" \
    "$(printf "%-${W_SWP}s"   "session:w.p")" \
    "$(printf "%-${W_TOPIC}s" "topic")" \
    "$(printf "%-${W_AGE}s"   "age")")

SELF="${BASH_SOURCE[0]:-$0}"

selected=$(printf '%s' "$rows" | fzf \
    --delimiter=$'\t' \
    --with-nth=1 \
    --nth=1 \
    --prompt='claude> ' \
    --header="$header  [ctrl-d: kill]" \
    --header-first \
    --preview='tmux capture-pane -ep -t {2} 2>/dev/null | tail -40' \
    --preview-window='down:65%:wrap' \
    --no-sort \
    --ansi \
    --bind "ctrl-d:execute-silent(kill {5} 2>/dev/null; sleep 0.4; bash '$SELF' --refresh-now)+reload(bash '$SELF' --list)")

[ -z "$selected" ] && exit 0

pane_id=$(printf '%s' "$selected" | awk -F'\t' '{print $2}')
tmux_session=$(printf '%s' "$selected" | awk -F'\t' '{print $3}')
window_idx=$(printf '%s' "$selected" | awk -F'\t' '{print $4}')

tmux switch-client -t "$tmux_session" \; select-window -t "$tmux_session:$window_idx" \; select-pane -t "$pane_id"

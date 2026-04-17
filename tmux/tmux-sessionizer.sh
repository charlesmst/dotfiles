#!/usr/bin/env bash
# Picker over ~/projects and ~/personal directories.
# Dirs with an existing tmux session sort first and are marked with ●.
# Ctrl-D kills the tmux session for the highlighted row and refreshes the list.
set -u

SEARCH_ROOTS=(~/projects ~/personal)

build_rows() {
    local sessions
    sessions=$(tmux list-sessions -F '#{session_name}' 2>/dev/null)
    local row dir name mark
    while IFS= read -r dir; do
        [ -z "$dir" ] && continue
        name=$(basename "$dir" | tr . _)
        if printf '%s\n' "$sessions" | grep -qxF "$name"; then
            mark="● "
        else
            mark="  "
        fi
        row=$(printf '%s %s' "$mark" "$dir")
        printf '%s\t%s\t%s\n' "$row" "$dir" "$name"
    done < <(find "${SEARCH_ROOTS[@]}" -mindepth 1 -maxdepth 1 -type d 2>/dev/null)
}

sort_rows() {
    awk -F'\t' 'BEGIN{OFS="\t"} {key = ($1 ~ /^●/) ? "0" : "1"; print key, $0}' \
        | LC_ALL=C sort -t$'\t' -k1,1 -k2,2 \
        | cut -f2-
}

CACHE="${HOME}/.claude/state/sessionizer-cache.txt"
STALE_SECS="${SESSIONIZER_STALE:-5}"

cache_age() {
    [ -f "$CACHE" ] || { echo 999999; return; }
    local mtime now
    mtime=$(stat -f %m "$CACHE" 2>/dev/null || echo 0)
    now=$(date +%s)
    echo $(( now - mtime ))
}

refresh_cache() {
    mkdir -p "$(dirname "$CACHE")"
    local tmp
    tmp=$(mktemp "$CACHE.XXXXXX")
    if build_rows | sort_rows > "$tmp"; then
        mv "$tmp" "$CACHE"
    else
        rm -f "$tmp"
    fi
}

if [ "${1:-}" = "--list" ]; then
    if [ "$(cache_age)" -lt "$STALE_SECS" ]; then
        cat "$CACHE"
    else
        build_rows | sort_rows | tee "$CACHE"
    fi
    exit 0
fi

if [ "${1:-}" = "--refresh-cache" ]; then
    if [ "$(cache_age)" -ge "$STALE_SECS" ]; then
        refresh_cache
    fi
    exit 0
fi

if [ "${1:-}" = "--refresh-now" ]; then
    refresh_cache
    exit 0
fi

# Explicit path argument: legacy one-shot mode.
if [ $# -eq 1 ] && [ -d "$1" ]; then
    selected_dir="$1"
    selected_name=$(basename "$selected_dir" | tr . _)
else
    SELF="${BASH_SOURCE[0]:-$0}"

    # Read cache immediately so fzf displays without blocking on find/tmux.
    if [ -f "$CACHE" ]; then
        rows=$(cat "$CACHE")
    else
        rows=$(build_rows | sort_rows)
        mkdir -p "$(dirname "$CACHE")"
        printf '%s' "$rows" > "$CACHE"
    fi
    (bash "$SELF" --refresh-cache >/dev/null 2>&1 &)

    selection=$(printf '%s' "$rows" | fzf \
        --delimiter=$'\t' \
        --with-nth=1 \
        --nth=1 \
        --prompt='session> ' \
        --header='[ctrl-d: kill session]' \
        --header-first \
        --no-sort \
        --ansi \
        --bind "ctrl-d:execute-silent(tmux kill-session -t {3} 2>/dev/null; bash '$SELF' --refresh-now)+reload(bash '$SELF' --list)")
    [ -z "$selection" ] && exit 0
    selected_dir=$(printf '%s' "$selection" | awk -F'\t' '{print $2}')
    selected_name=$(printf '%s' "$selection" | awk -F'\t' '{print $3}')
fi

tmux_running=$(pgrep tmux)

if [ -z "${TMUX:-}" ] && [ -z "$tmux_running" ]; then
    tmux new-session -s "$selected_name" -c "$selected_dir"
    exit 0
fi

if ! tmux has-session -t="$selected_name" 2>/dev/null; then
    tmux new-session -ds "$selected_name" -c "$selected_dir"
    tmux new-window -t "$selected_name:1" -n 'nvim' -c "$selected_dir"
    tmux new-window -t "$selected_name:2" -n 'lg' -c "$selected_dir"
    tmux send-keys -t "$selected_name:2" 'lg' Enter
    tmux new-window -t "$selected_name:3" -n 'cmd' -c "$selected_dir"
    tmux send-keys -t "$selected_name:1" 'nvim .' Enter
fi

tmux switch-client -t "$selected_name"

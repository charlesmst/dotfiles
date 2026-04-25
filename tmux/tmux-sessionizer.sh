#!/usr/bin/env bash
# Picker over ~/projects and ~/personal directories (shown as projects/... and personal/...).
# Dirs with an existing tmux session sort first and are marked with ●.
# Ctrl-D kills the tmux session for the highlighted row and refreshes the list.
# Ctrl-A prompts for a session name and creates/attaches (no project folder).
# Sessions not under ~/projects|~/personal (ad-hoc names) are listed as ● ◇ NAME.
set -u
_SESSIONIZER_SH="${BASH_SOURCE[0]:-$0}"

SEARCH_ROOTS=(~/projects ~/personal)

# List display only: drop $HOME/ so you see projects/... or personal/... (col2 stays absolute).
path_display() {
    case "$1" in
        "${HOME}/"*) printf '%s' "${1#"${HOME}/"}" ;;
        *) printf '%s' "$1" ;;
    esac
}

# Writes tab lines: col1=display, col2=start directory, col3=session name
build_rows() {
    local sessions row dir name mark s start_dir disp
    local dir_names
    dir_names=$(mktemp)
    sessions=$(tmux list-sessions -F '#{session_name}' 2>/dev/null || true)

    while IFS= read -r dir; do
        [ -z "$dir" ] && continue
        name=$(basename "$dir" | tr . _)
        printf '%s\n' "$name" >> "$dir_names"
    done < <(find "${SEARCH_ROOTS[@]}" -mindepth 1 -maxdepth 1 -type d 2>/dev/null)

    while IFS= read -r dir; do
        [ -z "$dir" ] && continue
        name=$(basename "$dir" | tr . _)
        if printf '%s\n' "$sessions" | grep -qxF "$name"; then
            mark="● "
        else
            mark="  "
        fi
        disp=$(path_display "$dir")
        row=$(printf '%s %s' "$mark" "$disp")
        printf '%s\t%s\t%s\n' "$row" "$dir" "$name"
    done < <(find "${SEARCH_ROOTS[@]}" -mindepth 1 -maxdepth 1 -type d 2>/dev/null)

    # Tmux sessions that are not derived from a top-level project/personal directory
    while IFS= read -r s; do
        [ -z "$s" ] && continue
        if [ -f "$dir_names" ] && grep -qxF "$s" "$dir_names" 2>/dev/null; then
            continue
        fi
        start_dir=$(tmux display -p -F '#{pane_current_path}' -t "$s:0.0" 2>/dev/null || true)
        [ -n "$start_dir" ] && [ -d "$start_dir" ] || start_dir="${HOME:-/}"
        row="● ◇ $s"
        printf '%s\t%s\t%s\n' "$row" "$start_dir" "$s"
    done < <(printf '%s\n' "$sessions")
    rm -f "$dir_names"
}

sort_rows() {
    awk -F'\t' 'BEGIN{OFS="\t"} {key = ($1 ~ /^●/) ? "0" : "1"; print key, $0}' \
        | LC_ALL=C sort -t$'\t' -k1,1 -k2,2 \
        | cut -f2-
}

# New session with an arbitrary name (not tied to ~/projects|personal folders).
# Uses the current tmux pane's working directory (or $PWD / $HOME when not in tmux).
new_named_session() {
    local name start_dir
    IFS= read -r -p "New session name: " name </dev/tty || true
    name="${name#"${name%%[![:space:]]*}"}"
    name="${name%"${name##*[![:space:]]}"}"
    if [ -z "$name" ]; then
        return 0
    fi
    name=${name// /_}
    if [[ ! "$name" =~ ^[A-Za-z0-9._-]+$ ]]; then
        echo "Session name: use letters, numbers, and ._-" >&2
        return 1
    fi

    if [ -n "${TMUX:-}" ]; then
        start_dir=$(tmux display -p -F '#{pane_current_path}' 2>/dev/null) || start_dir="${HOME:-/}"
    else
        start_dir="${PWD:-$HOME}"
    fi
    [ -d "$start_dir" ] || start_dir="${HOME:-/}"

    local tmux_running
    tmux_running=$(pgrep tmux 2>/dev/null || true)

    if [ -z "${TMUX:-}" ] && [ -z "$tmux_running" ]; then
        exec tmux new-session -s "$name" -c "$start_dir"
    fi

    if ! tmux has-session -t="$name" 2>/dev/null; then
        tmux new-session -ds "$name" -c "$start_dir"
    fi
    tmux switch-client -t "$name"
    # Fzf list is cached; new ad-hoc sessions only appear after a rebuild
    bash "$_SESSIONIZER_SH" --refresh-now >/dev/null 2>&1
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

if [ "${1:-}" = "--new-named-session" ]; then
    new_named_session
    exit 0
fi

# Explicit path argument: legacy one-shot mode.
if [ $# -eq 1 ] && [ -d "$1" ]; then
    selected_dir="$1"
    selected_name=$(basename "$selected_dir" | tr . _)
else
    SELF="${BASH_SOURCE[0]:-$0}"
    SELF_q=$(printf '%q' "$SELF")

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
        --header='[enter: open | ctrl-a: new named session | ctrl-d: kill | ctrl-r: refresh]' \
        --header-first \
        --no-sort \
        --ansi \
        --bind "ctrl-d:execute-silent(tmux kill-session -t {3} 2>/dev/null; bash $SELF_q --refresh-now)+reload(bash $SELF_q --list)" \
        --bind "ctrl-r:execute-silent(bash $SELF_q --refresh-now)+reload(bash $SELF_q --list)" \
        --bind "ctrl-a:execute(bash $SELF_q --new-named-session)+abort")
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

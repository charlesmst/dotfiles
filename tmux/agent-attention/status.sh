#!/bin/bash
# Output a status-line indicator for agent (Claude / Cursor CLI) panes.
#   ● N  (yellow) — panes needing attention
#   ⠿ N  (cyan)   — panes currently working
# Embed via: #(~/personal/dotfiles/tmux/agent-attention/status.sh)
BASE="${AGENT_ATTENTION_DIR:-$HOME/.local/state/agent-attention}"

count_dir() {
    find "$1" -maxdepth 1 -type f 2>/dev/null | wc -l | tr -d ' '
}

pending=$(count_dir "$BASE/pending")
working=$(count_dir "$BASE/working")

out=""
if [ "$working" != "0" ]; then
    out="#[fg=cyan,bold]⠿ ${working}#[default]"
fi
if [ "$pending" != "0" ]; then
    [ -n "$out" ] && out="$out "
    out="${out}#[fg=yellow,bold]● ${pending}#[default]"
fi
[ -n "$out" ] && printf '%s' "$out"
exit 0

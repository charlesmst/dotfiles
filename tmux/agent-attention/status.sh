#!/bin/bash
# Output a tmux status-line indicator for agent panes needing attention.
#   ● N  (yellow)  — panes with a pending notification
#   ⇢ N  (magenta) — ACTIVE remote (cloud) sessions started with `claude --environment`
#                    (unknown / running / idle / needs-input; finished and failed
#                    sessions drop off, as do forgotten and >7-day-old records)
# Embed via: #(~/personal/dotfiles/tmux/agent-attention/status.sh)
BASE="${AGENT_ATTENTION_DIR:-$HOME/.local/state/agent-attention}"

pending=$(find "$BASE/pending" -maxdepth 1 -type f 2>/dev/null | wc -l | tr -d ' ')
# Same retention as agent-view (AGENT_VIEW_REMOTE_DAYS, default 7); skip `remote forget` tombstones.
remote=$(find "$BASE/remote" -maxdepth 1 -type f -name 'session_*' -mtime "-${AGENT_VIEW_REMOTE_DAYS:-7}" \
    -exec grep -L -e '"dismissed": true' -e '"status": "finished"' -e '"status": "failed"' {} + 2>/dev/null \
    | wc -l | tr -d ' ')
out=""
if [ "$pending" != "0" ]; then
    out="#[fg=yellow,bold]● $pending#[default]"
fi
if [ "$remote" != "0" ]; then
    out="${out:+$out }#[fg=magenta,bold]⇢ $remote#[default]"
fi
printf '%s' "$out"
exit 0

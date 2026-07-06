#!/usr/bin/env bash
# Codex CLI notify hook — wired via `notify = [".../notify.sh"]` in
# ~/.codex/config.toml (agent-view install does this). Codex passes one JSON
# argument, e.g. {"type":"agent-turn-complete","last-assistant-message":...}.
# Codex runs this from the agent's process so $TMUX_PANE identifies the pane.
exec "$HOME/.local/bin/agent-view" event pending \
    --agent codex --unless-focused --payload "${1:-}"

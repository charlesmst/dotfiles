# agent-view

Exposé-style tmux TUI for coding-agent panes (Claude Code, Codex CLI,
Cursor CLI). Bound to `prefix + a`: a grid of live pane previews, one tile
per agent, with pending/working/idle/stale states, fuzzy filtering, and
kill shortcuts. Inspired by [tmux.expose](https://github.com/cesarferreira/tmux.expose),
but pure Python — no compiled binary, no daemon.

```
┌ C ● stocks:4.1 fix-tests ──┐┌ ✦ ⠿ dotfiles:1.2 tui ──────┐
│ $ pytest tests/            ││ > Rewriting picker in      │
│ ..F.. 2 failed             ││   Python...                │
└─ ● Waiting for permission ─┘└─ working ──────────────────┘
┌ C   bff:3.2 datadog ───────┐┌ X ✖ api:1.1 ───────────────┐
│ ✻ thinking...              ││ $ codex                    │
└─ idle 12m ─────────────────┘└─ stale 6h — ^k to kill ────┘
 filter> _         4/4 agents · ● 1 · ✖ 1 stale
```

## Install

```bash
uv run --project ~/personal/dotfiles/agent-view agent-view install
```

This installs the `agent-view` CLI into `~/.local/bin` (via
`uv tool install --editable`) and wires the hooks:

| Agent | Mechanism | What gets wired |
|---|---|---|
| Claude Code | local plugin (`plugins/claude`) | `Notification`/`Stop` → mark pending, `UserPromptSubmit` → clear |
| Cursor CLI | merged into `~/.cursor/hooks.json` | `stop` → mark pending, `beforeSubmitPrompt` → clear |
| Codex CLI | `notify = [...]` in `~/.codex/config.toml` | turn-complete → mark pending |

All hook sources live in this repo under `plugins/`; the installer is
idempotent and re-run by `create_links.sh`.

## Keys

| Key | Action |
|---|---|
| type | fuzzy-filter tiles (session/window/kind) |
| arrows / tab | move selection |
| enter / click | jump to the agent's pane |
| ctrl-d | kill the agent process (confirm) |
| ctrl-k | kill the whole tmux session (confirm) |
| ctrl-r | refresh now (auto-refreshes every 1s) |
| esc | clear filter, then quit |

## States

- **● pending** (yellow) — a hook reported the agent needs you; the reason
  is shown in the tile footer. Cleared when you focus the pane, submit a
  prompt, or jump from the TUI.
- **⠿ working** (blue) — pane produced output in the last 20s (agents
  stream output while processing; no hooks needed).
- **· idle** — quiet but recent.
- **✖ stale** (red) — no output for 5+ hours; sorted last and flagged so
  you remember to kill it.

Only "pending" needs hooks; everything else derives live from
`tmux list-panes` + one `ps` snapshot. State on disk is a single marker
file per pending pane in `~/.local/state/agent-attention/pending/`.

## CLI

```
agent-view                  # the TUI (run from a tmux popup)
agent-view event pending    # hook entrypoint: mark $TMUX_PANE pending
agent-view event clear      # hook entrypoint: clear the marker
agent-view status           # status-line fragment: "● N" pending count
agent-view doctor           # print the discovery snapshot (debugging)
agent-view install [--dry-run]
```

## Tests

```bash
uv run --project ~/personal/dotfiles/agent-view pytest
```

Integration tests spawn a disposable tmux server (`-L agent-view-test`)
with fake agent processes; TUI tests drive the app headless via Textual's
pilot. See `CLAUDE.md` for architecture notes.

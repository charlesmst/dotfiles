# agent-view — notes for agents working on this package

Exposé-style tmux TUI over live coding-agent panes (Claude Code, Codex,
Cursor CLI). Bound to tmux `prefix + a` via `display-popup`. Read
`README.md` first for the user-facing behavior; this file covers
architecture, invariants, and gotchas.

## Commands

```bash
uv run pytest                                # everything (~5s)
uv run pytest --ignore=tests/integration    # unit only (<1s)
uv run agent-view doctor                     # discovery snapshot on the real server
uv run agent-view install --dry-run          # what install would touch
```

Integration tests spawn real tmux servers on private sockets
(`-L agent-view-test-<uuid>` via `AGENT_VIEW_TMUX_ARGS`) and fake agents
(symlinks of `sleep` named `claude`/`codex`/`cursor-agent`, so `ps`
classification is exercised for real). They never touch the user's tmux
server or state dir (`AGENT_ATTENTION_DIR` is redirected per-test).

## Architecture

```
cli.py        argparse entrypoint; hook subcommands lazy-import and NEVER
              raise (a failing hook must not break the calling agent)
model.py      AgentPane dataclass + state machine (pending/working/idle/stale)
discovery.py  tmux list-panes + ONE ps snapshot → BFS pane pid → agent pid
state.py      pending markers: the only persistent state
tmux.py       all tmux subprocess calls; honors AGENT_VIEW_TMUX_ARGS
fuzzy.py      dependency-free fzf-ish subsequence scorer
installer.py  wires hook configs into claude/cursor/codex (idempotent)
tui/app.py    Textual app: grid of AgentTile + filter + confirm modal
```

Design invariants — do not break these:

- **No daemon, no cache.** Everything is derived on demand from
  `tmux list-panes`, one `ps -A` snapshot, and `capture-pane`. The TUI
  refreshes via a 1s thread worker posting `SnapshotReady` messages.
- **Minimal state.** Only pending markers persist: one file per pane in
  `~/.local/state/agent-attention/pending/`, filename = pane id with `/`→`_`,
  body = optional JSON `{"message":..., "agent":...}`. **Empty files are
  valid** — the legacy shell hooks (`tmux/agent-attention/*.sh`, still used
  on other machines) `touch` them. Keep both directions compatible.
- **States are hook-free except pending.** working/idle/stale come from
  tmux's `window_activity` (working = output <20s ago; stale = quiet for
  `AGENT_VIEW_STALE_HOURS`, default 5h). Pending comes only from agent
  hooks calling `agent-view event pending`.
- **Startup must stay fast** (popup opens on a keystroke). Keep heavy
  imports (textual) out of `cli.py` module level; hook subcommands must not
  import textual at all.

## Hook wiring (the "plugin" story)

All hook *sources* live in `plugins/` in this repo; `agent-view install`
copies/merges/registers them (also run by `create_links.sh`):

- **Claude**: `plugins/` is a local plugin marketplace
  (`.claude-plugin/marketplace.json` → `plugins/claude/`). Installed with
  `claude plugin marketplace add` + `claude plugin install
  agent-view@agent-view`. Hooks: Notification/Stop → `event pending
  --unless-focused`, UserPromptSubmit → `event clear`.
- **Cursor**: `plugins/cursor/hooks.json` is merged into
  `~/.cursor/hooks.json` by exact command-string comparison. NOTE: on
  dotfiles machines `~/.cursor/hooks.json` is a symlink to
  `config/cursor/hooks.json` (which already contains the same commands —
  keep those strings in sync or the merge will duplicate).
- **Codex**: no hook system; `notify = ["plugins/codex/notify.sh"]` is
  prepended to `~/.codex/config.toml`. Root-level TOML keys must appear
  BEFORE any `[table]`, hence prepend, and it's done textually because
  Python 3.10 has no toml writer.

Hooks call `$HOME/.local/bin/agent-view` — a `uv tool install --editable`
shim, so repo edits are live without reinstalling. The tmux side
(binding + `pane-focus-in` clear hook) lives in `.tmux.conf.local`
(search "agent-view").

## Gotchas learned the hard way

- Textual `App.visible` / `Widget.visible` are DOM properties — never name
  an attribute `visible` (we use `filtered_agents`).
- `Grid.remove_children()` / `mount()` are deferred; `_rebuild_view` is
  async and awaits them, otherwise `query()` sees stale children.
- Rich `Text("\n").join(lines)` drops `no_wrap`; set `no_wrap`/`overflow`
  on the *joined* Text in `AgentTile.render` (previews must crop, not
  wrap — pane content is already wrapped at source width).
- Textual CSS rejects Rich color names like `grey37`; use hex.
- `event pending` must not read stdin when `--message` is given (pytest
  and some hook runners have no readable stdin; Claude pipes JSON, Codex
  passes JSON as argv via `--payload`).
- Workers: refresh runs in a thread and posts a `SnapshotReady` message —
  the thread must never touch widgets directly.
- `App.query_one` searches the **active** screen. While the ctrl-d/ctrl-k
  `ConfirmScreen` is up, the 1s refresh still ticks, so `_rebuild_view`
  must query `self.screen_stack[0]` (where `#grid`/`#statusbar` live) or
  it dies with NoMatches. Regression test:
  `test_kill_agent_survives_refresh_ticks_while_confirm_open`.

## Relationship to tmux/agent-attention

`tmux/agent-attention/` is the older shell system. agent-view replaced its
picker (`picker.sh`) and marker scripts, but auto-naming
(`auto-name.sh`, `sync-tmux-name.sh`), macOS notifications
(`notify-if-unfocused.sh`) and the status bar (`status.sh`, reads the same
pending dir) are still in use. Don't delete those without checking
`.tmux.conf.local` and `config/cursor/hooks.json` references.

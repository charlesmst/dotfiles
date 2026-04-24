# agent-attention

Unified tmux integration for tracking **Claude Code** and **Cursor CLI** sessions across all your tmux panes:

- `prefix + a` opens an fzf picker over every live agent session, mapped to its tmux pane
- Status bar shows `⠿ N` (working) and `● N` (needs attention) counts
- macOS notification + sound when any agent finishes its turn while you're focused elsewhere — clicking the notification jumps to the pane
- Auto-names each session with a kebab-case slug from the first prompt and renames the tmux window to match

```
+-------------------------------------------------------+
|  ag  state  session:w.p              topic       age  |
+-------------------------------------------------------+
|  C   ●      stocks:4.1               ★ fix-tests  3m  |
|  ✦   ⠿      dotfiles:1.2             ★ unified-…  -   |
|  C          bff-services:3.2         ★ datadog-…  -   |
+-------------------------------------------------------+
```

`C` cyan = Claude. `✦` magenta = Cursor CLI.

## How it works

Both agents support hooks. We register the same set of events on each side and they all share one tiny shell script library + one shared state directory.

| Concept | Claude | Cursor CLI |
|---|---|---|
| User submits prompt | `UserPromptSubmit` hook | `beforeSubmitPrompt` hook |
| Agent finishes turn | `Stop` hook | `stop` hook |
| Needs user input mid-task | `Notification` hook | *(no equivalent — Cursor product gap)* |
| Per-session metadata file | Auto-written: `~/.claude/sessions/<pid>.json` | We write it ourselves on `sessionStart` |
| First-prompt transcript | `~/.claude/projects/<encoded-cwd>/<sid>.jsonl` | `~/.cursor/projects/<encoded-cwd>/agent-transcripts/<sid>/<sid>.jsonl` |
| Naming model | `claude -p --model haiku` | `cursor-agent -p --model composer-2-fast` |

Pane state markers (`pending`, `working`) live in `~/.local/state/agent-attention/` keyed by tmux `pane_id`. The picker walks each agent process's PID up to its tmux pane via `ps -o ppid=`.

## File layout

```
tmux/agent-attention/
├── picker.sh              # fzf popup; bound to prefix+a
├── status.sh              # tmux status-line indicator
├── mark-working.sh        # called from <agent>SubmitPrompt
├── clear-working.sh       # called from <agent>Stop / sessionEnd
├── mark-pending.sh        # called from notify hook
├── clear.sh               # called from tmux pane-focus-in
├── auto-name.sh           # AGENT={claude,cursor}; backgrounds CLI naming
├── sync-tmux-name.sh      # AGENT={claude,cursor}; renames tmux window
└── refresh-caches.sh

config/agent-shared/
├── notify-if-unfocused.sh # AGENT={claude,cursor}; macOS notification + sound
└── focus-agent-pane.sh    # called by terminal-notifier on click

config/cursor/
├── hooks.json             # symlinked to ~/.cursor/hooks.json
└── hooks/
    ├── write-session-meta.sh   # sessionStart -> writes ~/.cursor/sessions/<pid>.json
    └── clear-session-meta.sh   # sessionEnd -> removes it
```

## Post-install setup checklist

Run `bash create_links.sh` (it symlinks everything into `~/.claude/hooks/`, `~/.cursor/hooks.json`, `~/.cursor/hooks/`, and creates `~/.local/state/agent-attention/`). Then **manually** edit your settings files — they're not in this repo because they contain personal config:

### 1. `~/.claude/settings.json`

Add or merge these hooks. Existing hooks (worktree-layout, etc.) stay as-is. The `AGENT=claude` env prefix is required so the shared scripts know which agent they're acting on.

```json
{
  "hooks": {
    "Notification": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "AGENT=claude bash ~/personal/dotfiles/config/agent-shared/notify-if-unfocused.sh",
            "timeout": 10,
            "async": true
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          { "type": "command", "command": "bash ~/personal/dotfiles/tmux/agent-attention/clear-working.sh", "timeout": 3, "async": true },
          { "type": "command", "command": "AGENT=claude bash ~/personal/dotfiles/config/agent-shared/notify-if-unfocused.sh", "timeout": 10, "async": true },
          { "type": "command", "command": "AGENT=claude bash ~/personal/dotfiles/tmux/agent-attention/sync-tmux-name.sh", "timeout": 3, "async": true }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          { "type": "command", "command": "bash ~/personal/dotfiles/tmux/agent-attention/mark-working.sh", "timeout": 3, "async": true },
          { "type": "command", "command": "AGENT=claude bash ~/personal/dotfiles/tmux/agent-attention/auto-name.sh", "timeout": 5, "async": true },
          { "type": "command", "command": "AGENT=claude bash ~/personal/dotfiles/tmux/agent-attention/sync-tmux-name.sh", "timeout": 3, "async": true }
        ]
      }
    ]
  }
}
```

### 2. `~/.cursor/hooks.json`

`create_links.sh` symlinks this from `config/cursor/hooks.json` automatically. Nothing manual to do — but if for some reason you have a personal `~/.cursor/hooks.json` already, merge in the contents of `config/cursor/hooks.json`.

### 3. `.tmux.conf.local`

Already wired in this repo. The relevant lines (search for `agent-attention`):

```tmux
# status-right embeds the indicator
tmux_conf_theme_status_right=" #(~/personal/dotfiles/tmux/agent-attention/status.sh) ..."

# pane-focus-in clears the pending marker + warms picker cache
set -g focus-events on
set-hook -g pane-focus-in 'run-shell "~/personal/dotfiles/tmux/agent-attention/clear.sh #{pane_id}"'
set-hook -ga pane-focus-in 'run-shell -b "~/personal/dotfiles/tmux/agent-attention/refresh-caches.sh"'
set-hook -g client-attached 'run-shell -b "~/personal/dotfiles/tmux/agent-attention/refresh-caches.sh"'

# prefix + a opens the picker
bind-key a display-popup -E -w 80% -h 70% "~/personal/dotfiles/tmux/agent-attention/picker.sh"
```

### 4. Required CLI tools

- `jq` — all hook scripts parse JSON via jq
- `fzf` — picker UI
- `terminal-notifier` (macOS) — clickable notifications
- `afplay` (macOS, built-in) — alert sound at `~/.claude/sounds/fahhh.mp3`
- `claude` (Anthropic Claude Code CLI) — for auto-naming Claude sessions
- `cursor-agent` (Cursor CLI) — for auto-naming Cursor sessions

## Picker UX

| Key | Action |
|---|---|
| `prefix + a` | Open the picker (tmux popup) |
| `Enter` | Jump to the selected agent's pane |
| `Ctrl-D` | Kill the agent process in that pane |
| `Ctrl-R` | Force-refresh the cache |
| `Esc` / `Ctrl-C` | Close without action |

The cyan spinner is animated by an fzf `--listen` reload loop. The picker reads `~/.claude/sessions/*.json` and `~/.cursor/sessions/*.json` (both compact JSON), confirms each PID is alive, walks parent PIDs to find the matching tmux pane, then sorts pending → working → idle.

## Behavioral details

- **Auto-naming runs async.** The hook returns immediately; a background subshell calls the naming CLI (~3-30s). The first prompt's tmux window keeps its old name — by the time the **next** prompt fires (or `Stop`), the name is written and `sync-tmux-name.sh` renames the window.
- **Recursion guard.** When `auto-name.sh` shells out to `claude -p` or `cursor-agent -p`, that inner invocation also fires the hook. The env var `AGENT_AUTO_NAME_IN_PROGRESS=1` is set in the backgrounded subshell so the inner call no-ops on naming. The same guard short-circuits Cursor's `write-session-meta.sh` / `clear-session-meta.sh` so the inner invocation doesn't overwrite or delete the parent's session file.
- **Cursor `--workspace $HOME`.** Cursor refuses to run headlessly in a non-trusted workspace. Naming forces `--workspace $HOME` (always trusted) so it never blocks waiting for permission.
- **Compact JSON.** Both `write-session-meta.sh` and `auto-name.sh` write session files via `jq -nc` / `jq -c`. Other scripts grep for the literal `"sessionId":"<sid>"` pattern (no spaces) — pretty-printed JSON would silently break the lookup.
- **Marker cleanup.** Stale pane markers (for panes that no longer have a live agent) are pruned when the picker opens.
- **Cursor session bootstrap.** A Cursor session started **before** `~/.cursor/hooks.json` existed will not have a session-meta file and won't appear in the picker. Either restart that `cursor-agent` invocation, or manually run:

  ```bash
  echo '{"conversation_id":"<sid>","cwd":"<cwd>"}' | bash ~/.cursor/hooks/write-session-meta.sh
  ```

## State directory

```
~/.local/state/agent-attention/
├── pending/         # one empty file per pane needing attention (mtime = age)
├── working/         # one empty file per pane currently processing
├── picker-cache.txt # rendered rows; refreshed by tmux focus hooks
└── auto-name.log    # debug log from auto-name.sh
```

Wipe with `rm -rf ~/.local/state/agent-attention/*` if anything gets stuck.

## Known limits

- macOS only (uses `terminal-notifier`, `afplay`, `osascript`, `stat -f %m`).
- Cursor has no `Notification` event, so Cursor only notifies on `stop`. If Cursor pops a permission dialog mid-task, you won't get an alert.
- Cursor `auto-name.sh` invocations take 15-30s per first prompt (composer-2-fast cold start). Backgrounded so it doesn't block, but the rename arrives one prompt late.

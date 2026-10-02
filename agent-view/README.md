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
| Claude Code | local plugin (`plugins/claude`) | `Notification`/`Stop` → mark pending, `UserPromptSubmit` → clear, `PostToolUse`(Bash) → record PR |
| Cursor CLI | merged into `~/.cursor/hooks.json` | `stop` → mark pending, `beforeSubmitPrompt` → clear, `afterShellExecution` → record PR |
| Codex CLI | `notify = [...]` in `~/.codex/config.toml` | turn-complete → mark pending (no per-tool hook → PRs are branch-derived) |

All hook sources live in this repo under `plugins/`; the installer is
idempotent and re-run by `create_links.sh`.

## Keys

| Key | Action |
|---|---|
| type | fuzzy-filter agents (session/window/kind) |
| arrows / tab | move selection |
| enter / double-click | jump to the agent's pane |
| ctrl-o | open the agent's PR in the browser (if any) |
| ctrl-l | toggle grid ⇄ list view (persists) |
| pgup / pgdn | scroll the preview (list view; includes scrollback) |
| ctrl-d | kill the agent process (confirm) |
| ctrl-k | kill the whole tmux session (confirm) |
| ctrl-x | remove the selected ☁ remote tile from agent-view (confirm; local only, the cloud session is untouched) |
| ctrl-r | refresh now (auto-refreshes every 1s) |
| esc | clear filter, then quit |

Two views, toggled with `ctrl-l` (the choice is remembered):

- **grid** — Exposé wall of live tiles, one per agent.
- **list** — compact rows on the left (like the old fzf picker), one large
  scrollable preview on the right that captures 300 lines of scrollback
  and follows new output unless you scroll up.

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
agent-view listen [PATH]     # bind the notify socket, print datagrams (one JSON/line)
agent-view doctor           # print the discovery snapshot (debugging)
agent-view install [--dry-run]
```

### Push notifications (`event` always pushes)

After its marker logic, `event {pending,clear,pr}` **always** does a best-effort,
fire-and-forget send of **one JSON datagram** (`AF_UNIX` / `SOCK_DGRAM` /
`sendto` — no connect/accept) to a well-known socket, so a listener is pushed
the instant an agent finishes, blocks, or opens a PR — no polling, no caller
opt-in. The datagram carries `pane_id`, `location` (resolved tmux
`session:window.pane`, or null), `agent`, `event` (`pending`/`clear`/`pr`),
`message` (the reason, or PR url for `pr`), and `ts` (unix time).

It never raises, never blocks the hook, and silently no-ops when nothing is
bound (short internal send timeout) — so it costs nothing when no one listens.
The destination is `$AGENT_VIEW_NOTIFY_SOCK`, else `<state>/events.sock`
(`~/.local/state/agent-attention/events.sock`); `--notify PATH` overrides it per
invocation. Nothing to enable — the installed hooks already emit these.

An orchestrator just binds that path and reads (`recvfrom`):

```python
import socket, json
s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
s.bind("/Users/you/.local/state/agent-attention/events.sock")  # the default path
while True:
    event = json.loads(s.recvfrom(65536)[0])    # {"pane_id":..., "event":"pending", ...}
    print(event["location"], event["event"], event["message"])
```

Or use the built-in reader (generic bind + print, no filtering — pipe it into
your own consumer):

```bash
agent-view listen                 # binds the default socket, prints one JSON/line
agent-view listen /tmp/fleet.sock # bind a specific path
```

```bash
# override the destination for a one-off invocation:
agent-view event pending --agent claude --event stop \
  --message "Turn finished" --notify /tmp/fleet.sock
```

### AI-friendly layer (`ls` / `show` / `transcript` / `wait`)

A small, render-once, `--json`-capable surface an assistant (or a script)
can drive to navigate the fleet. Every command takes an **id** — a tmux
location like `stocks:4.1`, a `session:window` prefix like `stocks:4`, a raw
pane id like `%42`, or any unique substring of the location / window name.
Transcripts and last-messages are read straight from each agent's own files
(**no new state**); status rides the hook markers, not pane scraping.

```
agent-view ls [--json] [-m] [--pr]   # list agents + status (one shot)
agent-view show <id> [--json] [--no-pr]   # status + last message + PR + metadata
agent-view transcript <id> [--json] [--tail N] [--role user|assistant|tool|system] [--no-pane-fallback]
agent-view wait <id> [--json] [-m] [--timeout S] [--interval S] [--startup S]
```

`wait` blocks **only while the agent is `working`** (producing output). The
moment it's doing nothing — `done`/`blocked` (a hook fired), `idle`/`stale`
(quiet), or the process is gone (`exited`) — it returns immediately with that
status. So waiting on an already-idle agent returns at once; waiting on a busy
one returns as soon as it stops. `--startup S` (default 0) guards the
launch race for "trigger then wait": for the first S seconds an agent not yet
seen working isn't counted as finished.

Status vocabulary (small on purpose, so you can branch on it):

| status | meaning |
|---|---|
| `working` | producing output right now — leave it alone |
| `idle` | quiet but recent; no completion signal yet |
| `done` | finished a turn (Stop / turn-complete hook); awaiting input |
| `blocked` | proactively asked for you — permission or a question (`Notification` hook). This is "needs an answer". |
| `stale` | no output for hours; probably abandoned |
| `exited` | (`wait` only) the agent process is gone |

`done` / `blocked` come from the hook-driven pending markers, so `wait` gets
the precise signal the instant it fires. Where a completion hook can't fire
(e.g. the pane is focused, as with `--unless-focused`), `wait` still returns
as soon as output stops — it reports `idle` rather than inventing a `done`.

One trap this avoids: an agent's TUI can keep the pane "active" long after the
turn is logically finished — Claude's per-second `✻ …` spinner and the
backgrounded-agent indicator repaint every second, so a marker-less focused
pane would look `working` forever. So when a Claude pane looks `working` but
has no marker, `wait` reads the transcript's end-of-turn state
(`stop_reason == "end_turn"`) and returns `done` regardless of the repaints.

Transcript sources per agent: Claude → `~/.claude/projects/.../*.jsonl`;
Cursor → `~/.cursor/chats/*/<sessionId>/store.db` (via the pid→session map in
`~/.cursor/sessions/<pid>.json`); Codex → `~/.codex/sessions/**/rollout-*.jsonl`
(best-effort). If none is found, `transcript` falls back to live pane text and
labels the source `pane`.

Example (an assistant polling a delegated agent):

```bash
agent-view wait stocks:4.1 --json -m     # → {"status":"blocked","reason":"...","last_message":"..."}
```

### Remote (cloud) sessions

`claude --environment <ccpool_id>` starts a cloud session on a self-hosted runner and the
local `claude` exits, so the pane looks like a bare shell. agent-view keeps those visible:

```bash
agent-view ls                 # remote sessions are listed after the local panes
agent-view ls --json          # …as rows with "kind": "remote"  (--no-remote to omit)
agent-view remote             # just the remote ones: id, URL, launch pane, repo/branch, prompt
agent-view remote open [id]   # open the URL (newest by default)
agent-view remote forget <id> # remove one from agent-view (same as ctrl-x in the overview)
agent-view show <id|fragment> # details
# launch-time registry — output passes through unchanged, the session is recorded:
claude -p "$P" --environment ccpool_… --output-format json | agent-view remote record --prompt "$P"
```

A pane whose `claude` exited after creating a cloud session reads `-> remote <url>` (not
dead/idle). Sessions are found via `remote record`, or by scanning shell panes' scrollback
for the `Created cloud session` block / the JSON result, and are kept for
`AGENT_VIEW_REMOTE_DAYS` (default 7). **Status** (running / idle / needs-input / finished / failed) comes from a read-only,
GET-only lookup of the cloud session with your existing login (`cloudstatus.py`; the token is
never printed or logged); on any error it reads "unknown, open URL". `agent-view remote show
<id> --last` prints the session's last message (redacted), `--tail N` its recent events, and
a background monitor appends the attention events (see **Cloud-session events** below). In the live overview (`prefix + a`) a remote session is a normal tile with a `☁ REMOTE` badge,
state colours like local agents, and a live peek at its latest assistant text and tool activity
(refreshed ~every 12 s, read-only); `enter`/`^o` opens its claude.ai page. The status bar adds a
`☁ N remote` count, and `tmux/agent-attention/status.sh` adds `⇢ N` to the tmux
status line. Each new session appends a `remote-created` line to `agent-events.log`.

**Cloud-session events.** Every recorded session announces each attention state **once** in
`~/.local/state/agent-attention/agent-events.log`, with no overview open: `remote-needs-input`,
`remote-finished`, `remote-failed`, `remote-gone` (claude.ai no longer knows the session: killed,
deleted or expired) and `remote-idle-expired` (running/idle but silent for `AGENT_VIEW_REMOTE_IDLE_HOURS`,
default 6). Each line carries `session_id`, `url`, `title`, `repo`, `branch`, `status_detail` and the
session's `last_message` (redacted, ≤500 chars). One shared poller does it, `agent-view remote monitor`:
a lock file allows a single copy, `remote record` / the scan / the overview start it when none runs, and it
exits after `AGENT_VIEW_MONITOR_IDLE_MINUTES` (15) with nothing left to watch (`remote monitor --status`,
`--stop`, `--once`). It reads the same cached status and per-session backoff as the overview, so the two
share polls. Whoever sees a state first claims it under the record's lock; a removed (`ctrl-x`) session
emits nothing. Lines have `pane_id: null` — the launching pane is `launch_pane_id` — because the
orchestrator's `event-filter.pl` drops any line whose `pane_id` is its own pane, and it launches its
runner sessions from that pane.

**Remotes load lazily.** The overview draws the local panes first; remote tiles come straight from
the records on disk (the cache) with a `loading…` hint on the status bar, and one background pass then
looks for new launches (scrollback scan, at most every 5 s), polls status (~15 s per session) and fetches
the peeks (~12 s), publishing each as it lands. Passes are spaced `AGENT_VIEW_REMOTE_TICK` seconds apart
(default 3), never overlap, share the refresh's single `tmux list-panes`, and back off on errors, so an
unreachable claude.ai only delays the ☁ tiles. Keypresses and redraws run no remote work, the keychain
token is read once per process, and `status.sh` only reads the cached files (no network, no Python).
`AGENT_VIEW_NO_STATUS=1` turns the lookups off entirely.

**Removing a remote tile.** Press `ctrl-x` on a ☁ tile (or `agent-view remote forget <id>`) and
confirm with `y`. That only edits agent-view's own record (`~/.local/state/agent-attention/remote/<id>`,
one small JSON file per session): the cloud session is not stopped, deleted or touched, and nothing
is sent to claude.ai. The record is scrubbed down to a tombstone (id, URL, times; the title, prompt
and last message are dropped), so the launch block still in a pane's scrollback does not bring the
session back on the next refresh. The tombstone is forgotten after 30 days. Piping the launch
output into `agent-view remote record` again brings the session back.

### Pull requests

When an agent creates a PR, agent-view **records** it against that session and
shows it with **live status** from `gh`. A session can open **several** PRs
(multiple repos/worktrees, stacked branches) — all of them are tracked, deduped
in creation order.

- **Recording** is hook-driven: Claude's `PostToolUse` (Bash) and Cursor's
  `afterShellExecution` see the `gh pr create` command + its output and append
  the PR URL to the pane's list (`agent-view event pr`). Only URLs are stored,
  never the mutable PR state. Codex has no per-tool hook, so its PRs (and any
  opened in the browser) are picked up by the branch-derive fallback instead.
- **Status** is fetched on demand via `gh pr view <url>` (open/merged/closed +
  CI check counts), cached 60s in-process so the 1s TUI refresh never hammers
  the network.

```bash
agent-view ls --pr            # each agent + one "PR #482 OPEN · ✓5/6 checks" line per PR
agent-view show stocks:4.1    # lists every PR (pr[1], pr[2], …) + urls
```

Under `--json`, each agent carries a `prs` array (one object per PR).

In the **TUI**, agents with PRs show status on the tile / list row (a `⇥×N`
marker when there's more than one), and **`ctrl-o`** opens the selected agent's
PR(s) in the browser (`gh pr view --web`).

## Tests

```bash
uv run --project ~/personal/dotfiles/agent-view pytest
```

Integration tests spawn a disposable tmux server (`-L agent-view-test`)
with fake agent processes; TUI tests drive the app headless via Textual's
pilot. See `CLAUDE.md` for architecture notes.

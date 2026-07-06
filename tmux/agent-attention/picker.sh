#!/usr/bin/env python3
"""
fzf picker over tmux panes running Claude or Cursor CLI agents.
Source of truth: tmux list-panes + a single ps snapshot — no session JSON files.

States:
  ●  yellow = pending (Notification hook fired; needs attention)
  blank     = running or idle
Agent badge: C cyan = Claude Code, ✦ magenta = Cursor CLI.
Ctrl-D: kill the agent process.  Ctrl-R: refresh.
"""
import os
import subprocess
import sys

AGENT_ATTENTION_DIR = os.environ.get(
    'AGENT_ATTENTION_DIR',
    os.path.expanduser('~/.local/state/agent-attention'),
)
PENDING_DIR = os.path.join(AGENT_ATTENTION_DIR, 'pending')

C_YELLOW  = '\033[33m'
C_CYAN    = '\033[36m'
C_MAGENTA = '\033[35m'
C_RESET   = '\033[0m'

# basename of the executable → (display-kind, badge-string)
AGENT_NAMES = {
    'claude':       ('claude', f'{C_CYAN}C{C_RESET}'),
    'cursor-agent': ('cursor', f'{C_MAGENTA}✦{C_RESET}'),
}


def fit(s: str, w: int) -> str:
    if len(s) > w:
        return s[:w - 1] + '…'
    return s.ljust(w)


def get_panes() -> list[dict]:
    fmt = '#{pane_id}|#{pane_pid}|#{session_name}|#{window_index}|#{pane_index}|#{window_name}'
    out = subprocess.run(
        ['tmux', 'list-panes', '-a', '-F', fmt],
        capture_output=True, text=True,
    ).stdout
    panes = []
    for line in out.splitlines():
        parts = line.split('|', 5)
        if len(parts) >= 6:
            panes.append({
                'pane_id':  parts[0],
                'pane_pid': int(parts[1]),
                'session':  parts[2],
                'win_idx':  parts[3],
                'pane_idx': parts[4],
                'win_name': parts[5],
            })
    return panes


def get_process_tree() -> tuple[dict, dict]:
    """Returns (children: pid→[pid], comm_of: pid→agent-basename-or-name).

    Uses the full command line so we can detect cursor-agent, which is a bash
    script and shows up as 'bash' in the short comm field.
    """
    out = subprocess.run(
        ['ps', '-A', '-o', 'pid=,ppid=,command='],
        capture_output=True, text=True,
    ).stdout
    children: dict[int, list[int]] = {}
    comm_of:  dict[int, str]       = {}
    for line in out.splitlines():
        parts = line.split(None, 2)
        if len(parts) < 2:
            continue
        pid, ppid = int(parts[0]), int(parts[1])
        cmd = parts[2] if len(parts) > 2 else ''
        exe = cmd.split()[0] if cmd else ''
        name = os.path.basename(exe)
        # cursor-agent runs as a wrapper script (bash/sh) or as the bundled
        # "agent" binary (~/.local/bin/agent .../cursor-agent/versions/...).
        # Neither basename matches "cursor-agent" — detect via full cmdline.
        if name in ('bash', 'sh', 'zsh', 'agent') and 'cursor-agent' in cmd:
            name = 'cursor-agent'
        comm_of[pid] = name
        children.setdefault(ppid, []).append(pid)
    return children, comm_of


def find_agent(root: int, children: dict, comm_of: dict):
    """BFS from root; return (agent_pid, agent_basename) or None."""
    queue, seen = [root], set()
    while queue:
        pid = queue.pop(0)
        if pid in seen:
            continue
        seen.add(pid)
        name = comm_of.get(pid, '')
        if name in AGENT_NAMES:
            return pid, name
        queue.extend(children.get(pid, []))
    return None


def get_pending() -> set[str]:
    try:
        return set(os.listdir(PENDING_DIR))
    except FileNotFoundError:
        return set()


def build_rows() -> list[str]:
    """Return tab-separated rows: display\\tpane_id\\tsession\\twin_idx\\tagent_pid"""
    os.makedirs(PENDING_DIR, exist_ok=True)
    panes             = get_panes()
    children, comm_of = get_process_tree()
    pending           = get_pending()
    rows = []
    for p in panes:
        hit = find_agent(p['pane_pid'], children, comm_of)
        if hit is None:
            continue
        agent_pid, agent_name = hit
        _, badge   = AGENT_NAMES[agent_name]
        safe       = p['pane_id'].replace('/', '_')
        is_pending = safe in pending
        mark       = f'{C_YELLOW}●{C_RESET}' if is_pending else ' '
        state      = 0                        if is_pending else 1
        loc        = f"{p['win_idx']}.{p['pane_idx']}"
        wn         = p['win_name']
        label      = wn if wn and wn not in ('zsh', 'bash', 'sh') else '-'
        display    = f"{badge} {mark} {fit(p['session'], 22)}  {fit(loc, 5)}  {fit(label, 18)}"
        rows.append((state, display, p['pane_id'], p['session'], p['win_idx'], str(agent_pid)))
    rows.sort(key=lambda r: (r[0], r[1]))
    return ['\t'.join(str(x) for x in r[1:]) for r in rows]


def main() -> None:
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == '--rows':
            for row in build_rows():
                print(row)
        # Legacy cache-refresh subcommands — no-op; no cache in the new design.
        # (refresh-caches.sh still calls these; ignore gracefully.)
        return

    rows = build_rows()
    if not rows:
        subprocess.run(['tmux', 'display-message', 'No live agent panes'])
        return

    self_path = os.path.abspath(__file__)
    header    = "ag ●  session                   w.p    window  [ctrl-d: kill | ctrl-r: refresh]"

    proc = subprocess.run(
        [
            'fzf',
            '--delimiter=\t',
            '--with-nth=1',
            '--nth=1',
            '--prompt=agent> ',
            f'--header={header}',
            '--header-first',
            '--preview=tmux capture-pane -ep -t {2} 2>/dev/null | tail -40',
            '--preview-window=down:65%:wrap',
            '--no-sort',
            '--ansi',
            f"--bind=ctrl-d:execute-silent(kill {{5}} 2>/dev/null; sleep 0.3)+reload(python3 '{self_path}' --rows)",
            f"--bind=ctrl-r:reload(python3 '{self_path}' --rows)",
        ],
        input='\n'.join(rows) + '\n',
        stdout=subprocess.PIPE,
        text=True,
    )

    selected = proc.stdout.strip()
    if not selected:
        return

    parts = selected.split('\t')
    if len(parts) < 5:
        return

    # cols: display, pane_id, session, win_idx, agent_pid
    _, pane_id, session, win_idx, _ = parts[:5]

    safe = pane_id.replace('/', '_')
    try:
        os.remove(os.path.join(PENDING_DIR, safe))
    except FileNotFoundError:
        pass

    subprocess.run(['tmux', 'switch-client',  '-t', session])
    subprocess.run(['tmux', 'select-window',  '-t', f'{session}:{win_idx}'])
    subprocess.run(['tmux', 'select-pane',    '-t', pane_id])


if __name__ == '__main__':
    main()

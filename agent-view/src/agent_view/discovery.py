"""Discover live agent processes inside tmux panes.

Source of truth is ``tmux list-panes`` plus a single ``ps`` snapshot — no
session files, no daemon. Each pane's process tree is walked breadth-first
looking for a known agent CLI.
"""
from __future__ import annotations

import os
import shlex
import subprocess
from collections import deque

from . import state, tmux
from .model import AgentKind, AgentPane

# executable basename → agent kind
AGENT_BASENAMES = {
    "claude": AgentKind.CLAUDE,
    "cursor-agent": AgentKind.CURSOR,
    "codex": AgentKind.CODEX,
}


def _split_cmd(cmd: str) -> list[str]:
    try:
        return shlex.split(cmd)
    except ValueError:
        return cmd.split()


def classify_command(cmd: str) -> AgentKind | None:
    """Map a full command line to an agent kind, or None."""
    args = _split_cmd(cmd)
    exe = args[0] if args else ""
    name = os.path.basename(exe)

    if name in AGENT_BASENAMES:
        return AGENT_BASENAMES[name]

    # cursor-agent runs as a wrapper script (bash/sh) or as the bundled
    # "agent" binary; neither basename matches "cursor-agent".
    if name in ("bash", "sh", "zsh", "agent") and "cursor-agent" in cmd:
        return AgentKind.CURSOR

    # npm-installed Codex CLI appears as a Node wrapper: node .../bin/codex
    if name == "node" and len(args) > 1:
        script = args[1]
        if os.path.basename(script) == "codex" or "@openai/codex" in script:
            return AgentKind.CODEX

    return None


def process_snapshot() -> tuple[dict[int, list[int]], dict[int, AgentKind]]:
    """One ps pass → (children: pid→[child pids], agents: pid→kind)."""
    out = subprocess.run(
        ["ps", "-A", "-o", "pid=,ppid=,args="],
        capture_output=True,
        text=True,
    ).stdout
    children: dict[int, list[int]] = {}
    agents: dict[int, AgentKind] = {}
    for line in out.splitlines():
        parts = line.split(None, 2)
        if len(parts) < 2:
            continue
        try:
            pid, ppid = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        cmd = parts[2] if len(parts) > 2 else ""
        kind = classify_command(cmd)
        if kind is not None:
            agents[pid] = kind
        children.setdefault(ppid, []).append(pid)
    return children, agents


def find_agent(
    root_pid: int,
    children: dict[int, list[int]],
    agents: dict[int, AgentKind],
) -> tuple[int, AgentKind] | None:
    """BFS from the pane's root process; return (agent_pid, kind)."""
    queue: deque[int] = deque([root_pid])
    seen: set[int] = set()
    while queue:
        pid = queue.popleft()
        if pid in seen:
            continue
        seen.add(pid)
        if pid in agents:
            return pid, agents[pid]
        queue.extend(children.get(pid, []))
    return None


def discover() -> list[AgentPane]:
    """All agent panes, sorted pending → working → idle → stale."""
    panes = tmux.list_panes()
    children, agents = process_snapshot()
    markers = state.load_pending()

    found: list[AgentPane] = []
    live_pane_ids: set[str] = set()
    for pane in panes:
        hit = find_agent(pane["pane_pid"], children, agents)
        if hit is None:
            continue
        agent_pid, kind = hit
        live_pane_ids.add(pane["pane_id"])
        marker = markers.get(pane["pane_id"])
        found.append(
            AgentPane(
                pane_id=pane["pane_id"],
                pane_pid=pane["pane_pid"],
                agent_pid=agent_pid,
                kind=kind,
                session=pane["session"],
                window_index=pane["window_index"],
                pane_index=pane["pane_index"],
                window_name=pane["window_name"],
                last_activity=pane["last_activity"],
                pending_message=marker.message if marker else None,
                pending_since=marker.since if marker else None,
            )
        )

    state.prune_pending(live_pane_ids)
    found.sort(key=AgentPane.sort_key)
    return found

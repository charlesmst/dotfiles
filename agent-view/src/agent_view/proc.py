"""Small process-tree helpers used to link a pane to its agent's files.

Kept separate from ``discovery`` so the AI-friendly / transcript layer can
reuse the same ``ps`` snapshot without importing the TUI-facing discovery
flow. Everything here is derived on demand — no state, no caching.
"""
from __future__ import annotations

import subprocess
from collections import deque


def subtree_pids(root_pid: int, children: dict[int, list[int]]) -> list[int]:
    """All pids in ``root_pid``'s process subtree (root first, BFS order)."""
    order: list[int] = []
    seen: set[int] = set()
    queue: deque[int] = deque([root_pid])
    while queue:
        pid = queue.popleft()
        if pid in seen:
            continue
        seen.add(pid)
        order.append(pid)
        queue.extend(children.get(pid, []))
    return order


def process_cwd(pid: int) -> str | None:
    """Current working directory of ``pid`` via ``lsof`` (macOS/BSD & Linux).

    Returns None if it can't be determined (process gone, permission, etc.).
    """
    try:
        out = subprocess.run(
            ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except Exception:
        return None
    for line in out.splitlines():
        if line.startswith("n"):
            return line[1:]
    return None


def first_cwd(pids: list[int]) -> str | None:
    """The cwd of the first pid in ``pids`` that reports one."""
    for pid in pids:
        cwd = process_cwd(pid)
        if cwd:
            return cwd
    return None

"""Pending markers — the only persistent state.

One file per pane under ``$AGENT_ATTENTION_DIR/pending/`` (default
``~/.local/state/agent-attention/pending/``), named after the tmux pane id
with ``/`` replaced by ``_``. File body is optional JSON
``{"message": ..., "agent": ...}``; empty files (written by the legacy
shell hooks) are valid and mean "pending, no message".

The directory is shared with the older agent-attention shell scripts so
both systems stay in sync during migration.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass


def base_dir() -> str:
    return os.environ.get(
        "AGENT_ATTENTION_DIR",
        os.path.expanduser("~/.local/state/agent-attention"),
    )


def pending_dir() -> str:
    return os.path.join(base_dir(), "pending")


def _safe(pane_id: str) -> str:
    return pane_id.replace("/", "_")


def _unsafe(name: str) -> str:
    return name.replace("_", "/")


@dataclass
class PendingMarker:
    pane_id: str
    message: str | None
    since: float


def mark_pending(pane_id: str, message: str | None = None, agent: str | None = None) -> None:
    os.makedirs(pending_dir(), exist_ok=True)
    path = os.path.join(pending_dir(), _safe(pane_id))
    body = ""
    if message or agent:
        body = json.dumps({"message": message, "agent": agent})
    with open(path, "w") as f:
        f.write(body)


def clear_pending(pane_id: str) -> None:
    try:
        os.remove(os.path.join(pending_dir(), _safe(pane_id)))
    except FileNotFoundError:
        pass


def load_pending() -> dict[str, PendingMarker]:
    """pane_id → marker for every pending file."""
    markers: dict[str, PendingMarker] = {}
    try:
        names = os.listdir(pending_dir())
    except FileNotFoundError:
        return markers
    for name in names:
        path = os.path.join(pending_dir(), name)
        try:
            stat = os.stat(path)
            with open(path) as f:
                body = f.read().strip()
        except OSError:
            continue
        message = None
        if body:
            try:
                message = json.loads(body).get("message")
            except (json.JSONDecodeError, AttributeError):
                message = None
        pane_id = _unsafe(name)
        markers[pane_id] = PendingMarker(
            pane_id=pane_id,
            message=message or "needs attention",
            since=stat.st_mtime,
        )
    return markers


def prune_pending(live_pane_ids: set[str]) -> None:
    """Drop markers whose pane no longer hosts a live agent."""
    for pane_id in list(load_pending()):
        if pane_id not in live_pane_ids:
            clear_pending(pane_id)


def count_pending() -> int:
    try:
        return len(os.listdir(pending_dir()))
    except FileNotFoundError:
        return 0


VIEW_MODES = ("grid", "list")


def load_view_mode(default: str = "grid") -> str:
    """Last TUI view mode ('grid' or 'list'); persisted across opens."""
    try:
        with open(os.path.join(base_dir(), "view-mode")) as f:
            mode = f.read().strip()
        return mode if mode in VIEW_MODES else default
    except OSError:
        return default


def save_view_mode(mode: str) -> None:
    if mode not in VIEW_MODES:
        return
    try:
        os.makedirs(base_dir(), exist_ok=True)
        with open(os.path.join(base_dir(), "view-mode"), "w") as f:
            f.write(mode)
    except OSError:
        pass  # a failed save must never break the TUI

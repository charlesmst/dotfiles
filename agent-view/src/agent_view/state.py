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


def pr_dir() -> str:
    return os.path.join(base_dir(), "prs")


def notify_sock() -> str:
    """Well-known push-notify socket path.

    ``event`` always fires a best-effort datagram here (silent no-op if nothing
    is bound), so a listener just binds this path — no caller opt-in. Override
    with ``AGENT_VIEW_NOTIFY_SOCK`` or the ``--notify`` flag.
    """
    return os.environ.get("AGENT_VIEW_NOTIFY_SOCK") or os.path.join(
        base_dir(), "events.sock"
    )


def _safe(pane_id: str) -> str:
    return pane_id.replace("/", "_")


def _unsafe(name: str) -> str:
    return name.replace("_", "/")


@dataclass
class PendingMarker:
    pane_id: str
    message: str | None
    since: float
    # Which hook fired: "stop"/"turn-complete" mean the agent finished a turn;
    # "notification" means it is blocked waiting on you (permission / a
    # question). None = a legacy/empty marker with no recorded event.
    event: str | None = None
    agent: str | None = None


def mark_pending(
    pane_id: str,
    message: str | None = None,
    agent: str | None = None,
    event: str | None = None,
) -> None:
    os.makedirs(pending_dir(), exist_ok=True)
    path = os.path.join(pending_dir(), _safe(pane_id))
    body = ""
    if message or agent or event:
        body = json.dumps({"message": message, "agent": agent, "event": event})
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
        event = None
        agent = None
        if body:
            try:
                parsed = json.loads(body)
                message = parsed.get("message")
                event = parsed.get("event")
                agent = parsed.get("agent")
            except (json.JSONDecodeError, AttributeError):
                message = None
        pane_id = _unsafe(name)
        markers[pane_id] = PendingMarker(
            pane_id=pane_id,
            message=message or "needs attention",
            since=stat.st_mtime,
            event=event,
            agent=agent,
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


# --- PR markers -------------------------------------------------------------
# When an agent creates a pull request we record its identity (URL) for the
# pane, so the viewer can show "this session has a PR" and fetch live status
# on demand. A session can open several PRs (multiple repos/worktrees, stacked
# branches), so the marker holds a *list*, deduped by URL in creation order.
# Only the identity is stored — never the (mutable) PR state.


@dataclass
class PRRef:
    url: str
    repo: str | None = None  # "owner/name"
    number: int | None = None
    recorded_at: float = 0.0


@dataclass
class PRMarker:
    pane_id: str
    prs: list[PRRef]

    @property
    def urls(self) -> list[str]:
        return [p.url for p in self.prs]


def _read_pr_refs(path: str) -> list[PRRef]:
    """Parse a PR marker file, tolerating the legacy single-PR shape."""
    try:
        with open(path) as f:
            data = json.loads(f.read() or "{}")
    except (OSError, json.JSONDecodeError):
        return []
    raw = data.get("prs")
    if raw is None and data.get("url"):  # legacy single-PR file
        raw = [data]
    refs: list[PRRef] = []
    for item in raw or []:
        if isinstance(item, dict) and item.get("url"):
            refs.append(PRRef(
                url=item["url"], repo=item.get("repo"),
                number=item.get("number"), recorded_at=item.get("recorded_at", 0.0),
            ))
    return refs


def record_pr(
    pane_id: str,
    url: str,
    repo: str | None = None,
    number: int | None = None,
) -> None:
    """Append a PR to the pane's marker (no-op if that URL is already recorded)."""
    import time

    os.makedirs(pr_dir(), exist_ok=True)
    path = os.path.join(pr_dir(), _safe(pane_id))
    refs = _read_pr_refs(path)
    if any(r.url == url for r in refs):
        return  # already recorded — keep original order/timestamp
    refs.append(PRRef(url=url, repo=repo, number=number, recorded_at=time.time()))
    body = json.dumps({"prs": [r.__dict__ for r in refs]})
    with open(path, "w") as f:
        f.write(body)


def clear_pr(pane_id: str) -> None:
    try:
        os.remove(os.path.join(pr_dir(), _safe(pane_id)))
    except FileNotFoundError:
        pass


def load_prs() -> dict[str, PRMarker]:
    """pane_id → PR marker (list of recorded PRs) for every pane with any."""
    out: dict[str, PRMarker] = {}
    try:
        names = os.listdir(pr_dir())
    except FileNotFoundError:
        return out
    for name in names:
        refs = _read_pr_refs(os.path.join(pr_dir(), name))
        if not refs:
            continue
        pane_id = _unsafe(name)
        out[pane_id] = PRMarker(pane_id=pane_id, prs=refs)
    return out


def prune_prs(live_pane_ids: set[str]) -> None:
    """Drop PR markers whose pane no longer hosts a live agent."""
    for pane_id in list(load_prs()):
        if pane_id not in live_pane_ids:
            clear_pr(pane_id)


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

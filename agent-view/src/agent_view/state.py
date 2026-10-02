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
import re
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


# --- Remote (cloud) session records -----------------------------------------
# `claude --environment <ccpool_id>` creates a cloud session and then the local
# `claude` exits, so the only place its id ever appears is the launching pane's
# scrollback — which dies with the pane. We therefore persist the identity the
# first time we see it, one file per session id (not per pane: the pane is
# usually gone by the time anyone asks). Only identity + launch context is
# stored — never status, because no local source exposes it.

_REMOTE_ID_RE = re.compile(r"^session_[A-Za-z0-9]+$")


def remote_dir() -> str:
    return os.path.join(base_dir(), "remote")


@dataclass
class RemoteRef:
    session_id: str  # "session_01BB…" — also the record's filename stem
    url: str  # canonical https://claude.ai/code/session_… (query stripped)
    title: str | None = None  # the cloud session title the CLI printed
    environment: str | None = None  # ccpool_… from the launch line, if visible
    pane_id: str | None = None  # tmux pane the launch happened in
    location: str | None = None  # session:window.pane when first seen
    created_at: float = 0.0  # launch time (delegator sidecar) else first seen
    created_source: str = "first-seen"  # "registry" (recorded at launch) | "delegator" | "first-seen"
    recorded_at: float = 0.0
    prompt: str | None = None  # prompt summary (delegator sidecar)
    repo: str | None = None  # launch dir's repo — NOT verified against the runner
    branch: str | None = None  # launch dir's branch — likewise
    worktree: str | None = None
    project_dir: str | None = None
    delegator_key: str | None = None  # sidecar session key, when matched
    # `remote forget` / ctrl-x in the TUI: the user removed it from agent-view. A scrubbed
    # tombstone stays, so the block still sitting in the pane's scrollback isn't re-recorded
    # by the next scan; only an explicit `remote record` brings it back. Pruned after
    # TOMBSTONE_SECONDS. Never touches the cloud session itself.
    dismissed: bool = False
    # Last observed cloud status (see cloudstatus.py). None = never observed → "unknown".
    status: str | None = None  # running | idle | needs-input | finished | failed
    status_detail: str | None = None
    status_checked_at: float = 0.0
    status_changed_at: float = 0.0
    remote_branch: str | None = None  # the runner's branch (claude/<slug>), when reported
    last_event_at: str | None = None
    last_message: str | None = None  # redacted ≤500-char excerpt of the last assistant message
    pool_name: str | None = None  # the self-hosted runner pool's name ("main"), when reported


def valid_remote_id(session_id: str) -> bool:
    return bool(_REMOTE_ID_RE.match(session_id or ""))


def record_remote(ref: RemoteRef, revive: bool = False) -> bool:
    """Persist a remote session. Returns True if new; existing ids are kept as-is.

    ``revive=True`` is for an *explicit* record (``remote record`` at launch): it also
    brings back a session the user removed, replacing the scrubbed tombstone with the fresh
    record. The scrollback scan never revives, or a removed session would return on the
    next refresh while its launch block is still in the pane.
    """
    import time

    if not valid_remote_id(ref.session_id):
        return False
    path = os.path.join(remote_dir(), ref.session_id)
    if os.path.exists(path):
        if not (revive and _is_dismissed(path)):
            return False  # keep the original record (first sight has the best context)
    os.makedirs(remote_dir(), exist_ok=True)
    ref.dismissed = False
    ref.recorded_at = ref.recorded_at or time.time()
    ref.created_at = ref.created_at or ref.recorded_at
    with open(path, "w") as f:
        f.write(json.dumps(ref.__dict__))
    return True


def is_dismissed(session_id: str) -> bool:
    """True if the user removed this session (its tombstone is on disk)."""
    return valid_remote_id(session_id) and _is_dismissed(os.path.join(remote_dir(), session_id))


def _is_dismissed(path: str) -> bool:
    try:
        with open(path) as f:
            return bool((json.loads(f.read() or "{}") or {}).get("dismissed"))
    except (OSError, json.JSONDecodeError, AttributeError):
        return False


def load_remote() -> dict[str, RemoteRef]:
    """session_id → record for every persisted remote session."""
    out: dict[str, RemoteRef] = {}
    try:
        names = os.listdir(remote_dir())
    except FileNotFoundError:
        return out
    fields = RemoteRef.__dataclass_fields__
    for name in names:
        if not valid_remote_id(name):
            continue
        try:
            with open(os.path.join(remote_dir(), name)) as f:
                data = json.loads(f.read() or "{}")
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or not data.get("url"):
            continue
        out[name] = RemoteRef(**{k: v for k, v in data.items() if k in fields} | {"session_id": name})
    return out


def dismiss_remote(session_id: str) -> bool:
    """Remove a session from agent-view: local state only, the cloud session is not touched.

    Rewrites the record as a tombstone that keeps just the identity (id, url, times) and
    drops the stored text (title, prompt, last message, repo…). It takes the same lock as
    ``update_remote_status``, so a status poll already in flight can't write the old record
    back over it. Returns False for an unknown id.
    """
    import fcntl

    if not valid_remote_id(session_id):
        return False
    try:
        with open(os.path.join(remote_dir(), session_id), "r+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            data = json.loads(f.read() or "{}")
            if not isinstance(data, dict) or not data.get("url"):
                return False
            tomb = RemoteRef(
                session_id=session_id,
                url=data["url"],
                created_at=data.get("created_at") or 0.0,
                recorded_at=data.get("recorded_at") or 0.0,
                created_source=data.get("created_source") or "first-seen",
                dismissed=True,
            )
            f.seek(0)
            f.truncate()
            f.write(json.dumps(tomb.__dict__))
            return True
    except (OSError, json.JSONDecodeError):
        return False


def update_remote_status(
    session_id: str,
    status: str,
    detail: str | None = None,
    remote_branch: str | None = None,
    last_event_at: str | None = None,
    last_message: str | None = None,
    pool_name: str | None = None,
) -> tuple[str | None, bool, RemoteRef | None]:
    """Record an observed status under an exclusive lock → (previous, changed, ref).

    The lock makes check-then-write atomic across processes (the TUI worker, a
    ``remote watch`` and ``ls`` can all poll), so each transition is reported by
    exactly one of them — which is the one that emits the event.
    """
    import fcntl
    import time

    if not valid_remote_id(session_id):
        return None, False, None
    path = os.path.join(remote_dir(), session_id)
    try:
        with open(path, "r+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            data = json.loads(f.read() or "{}")
            fields = RemoteRef.__dataclass_fields__
            ref = RemoteRef(**{k: v for k, v in data.items() if k in fields} | {"session_id": session_id})
            if ref.dismissed:
                return None, False, None  # removed while the lookup was in flight: leave the tombstone alone
            prev, now = ref.status, time.time()
            changed = prev != status
            ref.status, ref.status_checked_at = status, now
            if detail is not None:
                ref.status_detail = detail
            ref.remote_branch = remote_branch or ref.remote_branch
            ref.last_event_at = last_event_at or ref.last_event_at
            ref.last_message = last_message or ref.last_message
            ref.pool_name = pool_name or ref.pool_name
            if changed:
                ref.status_changed_at = now
            f.seek(0)
            f.truncate()
            f.write(json.dumps(ref.__dict__))
            return prev, changed, ref
    except (OSError, json.JSONDecodeError, TypeError):
        return None, False, None


def count_remote(max_age_seconds: float | None = None) -> int:
    """Active remote sessions (not forgotten/aged out/finished/failed) — records only, no tmux."""
    import os as _os
    import time

    if max_age_seconds is None:
        max_age_seconds = float(_os.environ.get("AGENT_VIEW_REMOTE_DAYS", "7")) * 86400
    cutoff = time.time() - max_age_seconds
    return sum(
        1 for r in load_remote().values()
        if not r.dismissed and r.status not in ("finished", "failed")
        and (r.recorded_at or r.created_at) >= cutoff
    )


def clear_remote(session_id: str) -> bool:
    if not valid_remote_id(session_id):
        return False
    try:
        os.remove(os.path.join(remote_dir(), session_id))
        return True
    except FileNotFoundError:
        return False


TOMBSTONE_SECONDS = 30 * 86400  # how long a removal is remembered (from the removal, not the launch)


def prune_remote(max_age_seconds: float) -> None:
    """Drop old records (status is unknowable offline, so age is the only GC).

    Live records age out ``max_age_seconds`` after they were recorded; a removal's tombstone
    lives ``TOMBSTONE_SECONDS`` from when it was removed, so a session removed late in its
    life doesn't lose the tombstone (and reappear from scrollback) a day later.
    """
    import time

    now = time.time()
    for sid, ref in load_remote().items():
        if ref.dismissed:
            try:
                removed_at = os.path.getmtime(os.path.join(remote_dir(), sid))
            except OSError:
                continue
            if now - removed_at > TOMBSTONE_SECONDS:
                clear_remote(sid)
        elif (ref.recorded_at or ref.created_at) < now - max_age_seconds:
            clear_remote(sid)


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

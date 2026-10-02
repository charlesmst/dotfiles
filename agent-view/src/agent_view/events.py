"""Append events to the fleet event log (``agent-events.log``).

The orchestrator reacts to ``~/.local/state/agent-attention/agent-events.log``,
a plain ``>>`` append log written by the agent-fleet aggregator
(``staff-support/.claude/skills/agent-fleet/scripts/event-aggregator.ts``) and
tailed through ``event-filter.pl``. Local agents reach it via agent-view's
datagram push → ``fleet-listen.py`` → aggregator. That listener forwards **only**
``pending``/``pr`` events, so a new kind can't ride the socket; remote-session
events are appended to the log directly instead, in the same one-JSON-object-
per-line shape as the ``fleet`` stream (``pane_id``/``location``/``agent``/
``event``/``message``/``ts``) plus ``stream``/``kind`` = ``remote`` and
``session_id``/``url``.

One ``O_APPEND`` write of one short line is atomic against the aggregator's own
appends. Best-effort: emitting must never break a command.
"""
from __future__ import annotations

import json
import os
import time

from . import state


def log_path() -> str:
    """Same location the aggregator writes (it honours ``AGENT_ATTENTION_DIR`` too)."""
    return os.environ.get("AGENT_VIEW_EVENTS_LOG") or os.path.join(
        state.base_dir(), "agent-events.log"
    )


def emit(event: dict) -> bool:
    """Append ``event`` as one JSONL line. Returns False (never raises) on failure."""
    try:
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
        fd = os.open(log_path(), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)
        return True
    except Exception:
        return False


def remote_created(ref: state.RemoteRef) -> dict:
    """``remote-created``: a cloud session now exists. Status is unknown by design."""
    return {
        "stream": "remote",
        "kind": "remote",
        "pane_id": ref.pane_id,
        "location": ref.location,
        "agent": "claude",
        "event": "remote-created",
        "message": f"{ref.title or ref.session_id} — {ref.url}",
        "ts": time.time(),
        "session_id": ref.session_id,
        "url": ref.url,
        "title": ref.title,
        "environment": ref.environment,
        "status": "unknown",
        "repo": ref.repo,
        "branch": ref.branch,
        "worktree": ref.worktree,
        "prompt": ref.prompt,
        "created_source": ref.created_source,
    }


# status → event name. Only these are announced: a terminal state or a request for
# input. running/idle are visible state (overview, `ls`) but would only be noise here.
STATUS_EVENTS = {
    "finished": "remote-finished",
    "failed": "remote-failed",
    "needs-input": "remote-needs-input",
}


def remote_status(ref: state.RemoteRef, previous: str | None) -> dict | None:
    """The event for a session that just changed to a notable status, else None."""
    name = STATUS_EVENTS.get(ref.status or "")
    if not name:
        return None
    ev = remote_created(ref)
    ev.update({
        "event": name,
        # the session's own last words (redacted, ≤500 chars) so the orchestrator can
        # react without opening the browser
        "message": f"{ref.title or ref.session_id}: {ref.status}"
                   + (f" — {ref.status_detail}" if ref.status_detail else "")
                   + f" — {ref.url}"
                   + (f" — last message: {ref.last_message}" if ref.last_message else ""),
        "last_message": ref.last_message,
        "status": ref.status,
        "status_detail": ref.status_detail,
        "previous_status": previous or "unknown",
        "remote_branch": ref.remote_branch,
        "last_event_at": ref.last_event_at,
        "ts": time.time(),
    })
    return ev

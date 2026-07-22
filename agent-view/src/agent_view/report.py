"""AI-friendly abstraction over a discovered agent.

One small surface an assistant can drive from the CLI: given an *id* (a tmux
location like ``stocks:3.1`` or a raw pane id like ``%42``), resolve the live
agent and report its **status**, **last message**, and (on demand) its
**transcript** — read from the agent's own files, never from new state.

Status vocabulary (deliberately small so an assistant can branch on it):

* ``working``  — actively producing output; leave it alone.
* ``idle``     — quiet but recent; no completion signal yet.
* ``done``     — finished a turn (Stop / turn-complete hook); awaiting input.
* ``blocked``  — proactively asked for you (permission / a question); a
                 ``Notification`` hook fired. This is the "needs an answer".
* ``stale``    — no output for hours; probably abandoned.

``done``/``blocked`` ride the hook-driven pending markers (reliable), so they
do not depend on scraping the pane. ``working``/``idle``/``stale`` derive from
tmux activity, exactly as the TUI does.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from . import discovery, transcript as transcript_mod
from .model import AgentPane, AgentState, format_age


class AgentStatus(str, Enum):
    WORKING = "working"
    IDLE = "idle"
    DONE = "done"
    BLOCKED = "blocked"
    STALE = "stale"


# Legacy markers carry no event kind; classify blocked-ness from the text.
_BLOCKED_RE = re.compile(
    r"permission|approve|allow|authoriz|confirm|waiting for your input|\?\s*$",
    re.IGNORECASE,
)

_TERMINAL_EVENTS = {"stop", "turn-complete", "agent-turn-complete"}


def status_of(pane: AgentPane) -> tuple[AgentStatus, str | None]:
    """(status, reason) for a pane, from hook markers + tmux activity."""
    if pane.pending_message is not None:
        event = (pane.pending_event or "").lower()
        if event == "notification":
            return AgentStatus.BLOCKED, pane.pending_message
        if event in _TERMINAL_EVENTS:
            return AgentStatus.DONE, pane.pending_message
        # No recorded event (legacy/empty marker): fall back to the message.
        if _BLOCKED_RE.search(pane.pending_message):
            return AgentStatus.BLOCKED, pane.pending_message
        return AgentStatus.DONE, pane.pending_message

    mapping = {
        AgentState.WORKING: AgentStatus.WORKING,
        AgentState.IDLE: AgentStatus.IDLE,
        AgentState.STALE: AgentStatus.STALE,
    }
    return mapping.get(pane.state, AgentStatus.IDLE), None


@dataclass
class AgentReport:
    pane: AgentPane
    status: AgentStatus
    reason: str | None

    @property
    def id(self) -> str:
        return self.pane.location

    @property
    def blocked(self) -> bool:
        return self.status is AgentStatus.BLOCKED

    @property
    def finished(self) -> bool:
        """The agent has yielded control (finished or waiting on you)."""
        return self.status in (AgentStatus.DONE, AgentStatus.BLOCKED)

    def to_dict(self) -> dict:
        p = self.pane
        return {
            "id": self.id,
            "pane_id": p.pane_id,
            "kind": p.kind.value,
            "session": p.session,
            "window": p.window_name,
            "title": p.title,
            "status": self.status.value,
            "blocked": self.blocked,
            "reason": self.reason,
            "idle_seconds": round(p.idle_seconds),
            "idle": format_age(p.idle_seconds),
            "agent_pid": p.agent_pid,
        }


def report_for(pane: AgentPane) -> AgentReport:
    status, reason = status_of(pane)
    return AgentReport(pane=pane, status=status, reason=reason)


def all_reports(agents: list[AgentPane] | None = None) -> list[AgentReport]:
    agents = discovery.discover() if agents is None else agents
    return [report_for(a) for a in agents]


# --- id resolution ----------------------------------------------------------


@dataclass
class Resolution:
    pane: AgentPane | None
    error: str | None = None
    candidates: list[AgentPane] | None = None


def _norm(s: str) -> str:
    return s.strip().lower()


def resolve(agents: list[AgentPane], ident: str) -> Resolution:
    """Resolve an id to a single agent.

    Match order: exact pane id (``%42``) → exact location (``sess:3.1``) →
    ``session:window`` prefix → unique case-insensitive substring across
    location / session / window name. Ambiguous matches return candidates.
    """
    ident = ident.strip()
    if not ident:
        return Resolution(None, error="empty id")

    for a in agents:
        if a.pane_id == ident:
            return Resolution(a)
    for a in agents:
        if a.location == ident:
            return Resolution(a)

    # `session:window` (no pane index) — common as a delegator tmux_target.
    prefix = [a for a in agents if a.location.startswith(ident + ".") or
              f"{a.session}:{a.window_index}" == ident]
    if len(prefix) == 1:
        return Resolution(prefix[0])
    if len(prefix) > 1:
        return Resolution(None, error=f"'{ident}' is ambiguous", candidates=prefix)

    needle = _norm(ident)
    subs = [
        a for a in agents
        if needle in _norm(a.location)
        or needle in _norm(a.session)
        or needle in _norm(a.window_name)
    ]
    if len(subs) == 1:
        return Resolution(subs[0])
    if len(subs) > 1:
        return Resolution(None, error=f"'{ident}' is ambiguous", candidates=subs)
    return Resolution(None, error=f"no agent matches '{ident}'")


# --- transcript convenience -------------------------------------------------


def transcript_for(
    pane: AgentPane,
    children: dict[int, list[int]] | None = None,
    allow_pane_fallback: bool = True,
) -> transcript_mod.Transcript:
    """On-disk transcript for a pane, falling back to live pane text."""
    if children is None:
        children, _ = discovery.process_snapshot()
    t = transcript_mod.resolve(pane, children)
    if not t and allow_pane_fallback:
        return transcript_mod.pane_transcript(pane)
    return t


def last_message(pane: AgentPane, children: dict[int, list[int]] | None = None) -> tuple[str, str]:
    """(text, source) of the agent's most recent assistant/pane message."""
    t = transcript_for(pane, children)
    turn = t.last_assistant() or t.last()
    return (turn.text if turn else ""), t.source

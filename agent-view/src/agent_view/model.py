"""Data model for agent panes."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from enum import Enum


class AgentKind(str, Enum):
    CLAUDE = "claude"
    CURSOR = "cursor"
    CODEX = "codex"


class AgentState(str, Enum):
    """Sort order: pending first, then working, idle, stale last."""

    PENDING = "pending"
    WORKING = "working"
    IDLE = "idle"
    STALE = "stale"


STATE_ORDER = {
    AgentState.PENDING: 0,
    AgentState.WORKING: 1,
    AgentState.IDLE: 2,
    AgentState.STALE: 3,
}

# Output within this window counts as "working" (agents emit constant
# spinner/progress output while processing).
WORKING_WINDOW_SECONDS = 20
# No output for this long marks the pane as stale (kill candidate).
STALE_AFTER_SECONDS = float(os.environ.get("AGENT_VIEW_STALE_HOURS", "5")) * 3600


@dataclass
class AgentPane:
    pane_id: str  # tmux pane id, e.g. "%42"
    pane_pid: int  # pid of the pane's root process
    agent_pid: int  # pid of the agent CLI process
    kind: AgentKind
    session: str
    window_index: str
    pane_index: str
    window_name: str
    last_activity: float  # epoch seconds of last pane output
    pending_message: str | None = None  # set when a pending marker exists
    pending_since: float | None = None
    now: float = field(default_factory=time.time)

    @property
    def location(self) -> str:
        return f"{self.session}:{self.window_index}.{self.pane_index}"

    @property
    def idle_seconds(self) -> float:
        return max(0.0, self.now - self.last_activity)

    @property
    def state(self) -> AgentState:
        if self.pending_message is not None:
            return AgentState.PENDING
        if self.idle_seconds >= STALE_AFTER_SECONDS:
            return AgentState.STALE
        if self.idle_seconds <= WORKING_WINDOW_SECONDS:
            return AgentState.WORKING
        return AgentState.IDLE

    @property
    def title(self) -> str:
        name = self.window_name
        if not name or name in ("zsh", "bash", "sh", "fish"):
            return ""
        return name

    def sort_key(self) -> tuple:
        return (STATE_ORDER[self.state], -self.last_activity, self.session)

    def filter_haystack(self) -> str:
        """Text the fuzzy filter matches against."""
        return f"{self.kind.value} {self.session} {self.window_name} {self.location}"


def format_age(seconds: float) -> str:
    """Compact human age: 45s, 12m, 3h, 2d."""
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"

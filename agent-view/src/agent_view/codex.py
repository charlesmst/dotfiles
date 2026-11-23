"""Read-only view of the Codex store — the Codex CLI and the ChatGPT desktop app share it.

Both write to ``$CODEX_HOME`` (default ``~/.codex``):

* ``state_5.sqlite`` table ``threads`` — one row per session: id, title (``name``),
  ``cwd``, ``model``, ``rollout_path``, ``updated_at``, ``originator`` (``Codex Desktop``
  for the app), ``daybreak_enabled``. Opened **read-only**; never written.
* ``sessions/YYYY/MM/DD/rollout-<ts>-<id>.jsonl`` — the transcript. Lines are
  ``{"timestamp", "type", "payload"}``: ``response_item`` (``message`` with role
  user/assistant/developer, ``function_call``/``custom_tool_call`` + ``*_output``) and
  ``event_msg`` (``task_started`` / ``task_complete`` carry the turn lifecycle).

Nothing here writes, caches, or touches ``auth.json``. Status is derived from the
rollout's last ``task_started``/``task_complete`` — a file-based signal, so a desktop
session (no tmux pane, no hook) still reports ``working`` / ``done``.
"""
from __future__ import annotations

import glob
import json
import os
import sqlite3
import time
from dataclasses import dataclass, field

# Only the tail of a rollout is read for status: rollouts reach many MB.
_TAIL_BYTES = 256 * 1024
_MAX_TOOL_TEXT = 400

# A session whose latest turn started this recently and never completed is "working".
WORKING_WINDOW_S = 120


def home() -> str:
    return os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")


@dataclass
class CodexThread:
    id: str
    title: str
    cwd: str
    model: str | None
    rollout_path: str
    updated_at: float
    originator: str | None = None
    daybreak: bool = False
    archived: bool = False
    git_branch: str | None = None

    @property
    def desktop(self) -> bool:
        return (self.originator or "").lower() == "codex desktop"

    def to_dict(self) -> dict:
        return {
            "id": self.id, "title": self.title, "cwd": self.cwd, "model": self.model,
            "rollout": self.rollout_path, "updated_at": self.updated_at,
            "originator": self.originator, "daybreak": self.daybreak,
        }


def _db_path() -> str:
    return os.path.join(home(), "state_5.sqlite")


def _connect() -> sqlite3.Connection | None:
    """Open the thread DB read-only. ``mode=ro`` honours the WAL; ``immutable`` is the fallback
    for a locked/odd file (stale but safe). ``None`` when there is no DB."""
    path = _db_path()
    if not os.path.exists(path):
        return None
    for flags in ("mode=ro", "mode=ro&immutable=1"):
        try:
            con = sqlite3.connect(f"file:{path}?{flags}", uri=True, timeout=1.0)
            con.execute("select 1 from threads limit 1")
            return con
        except sqlite3.Error:
            continue
    return None


def _scalar(row: dict, key: str, default=None):
    v = row.get(key)
    return default if v is None else v


def threads(since: float | None = None, include_archived: bool = False) -> list[CodexThread]:
    """Threads newest-first. ``since`` (epoch seconds) keeps only those updated after it."""
    con = _connect()
    if con is None:
        return []
    try:
        con.row_factory = sqlite3.Row
        have = {r[1] for r in con.execute("pragma table_info(threads)")}
        cols = [c for c in ("id", "name", "title", "cwd", "model", "rollout_path", "updated_at",
                            "originator", "daybreak_enabled", "archived", "git_branch") if c in have]
        rows = con.execute(f"select {', '.join(cols)} from threads order by updated_at desc").fetchall()
    except sqlite3.Error:
        return []
    finally:
        con.close()
    out: list[CodexThread] = []
    for r in rows:
        d = dict(r)
        if d.get("archived") and not include_archived:
            continue
        updated = float(_scalar(d, "updated_at", 0))
        if since is not None and updated < since:
            continue
        out.append(CodexThread(
            id=str(d["id"]),
            title=(d.get("name") or d.get("title") or "").strip(),
            cwd=_scalar(d, "cwd", ""),
            model=d.get("model"),
            rollout_path=_scalar(d, "rollout_path", ""),
            updated_at=updated,
            originator=d.get("originator"),
            daybreak=bool(d.get("daybreak_enabled")),
            archived=bool(d.get("archived")),
            git_branch=d.get("git_branch"),
        ))
    return out


# --- rollout parsing ---------------------------------------------------------


@dataclass
class RolloutTurn:
    role: str  # user | assistant | tool
    text: str
    ts: float | None = None


@dataclass
class Rollout:
    turns: list[RolloutTurn] = field(default_factory=list)
    state: str = "unknown"  # working | done | unknown
    last_event_at: float | None = None
    last_agent_message: str | None = None


def _iso(ts: str | None) -> float | None:
    if not ts:
        return None
    from datetime import datetime

    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    parts = [b.get("text", "") for b in content or []
             if isinstance(b, dict) and b.get("type") in ("input_text", "output_text", "text")]
    return "\n".join(p for p in parts if p)


def _is_injected(text: str) -> bool:
    """Context Codex adds to a user turn itself (environment block, AGENTS.md, …), not typed by the user."""
    t = text.lstrip()
    return t.startswith(("<environment_context>", "<user_instructions>", "<permissions", "# AGENTS.md",
                         "<INSTRUCTIONS>", "<collaboration_mode>"))


def _tool_output_text(out) -> str:
    text = _text_of(out) if isinstance(out, list) else str(out or "")
    return text.strip()[:_MAX_TOOL_TEXT]


def _apply(ro: Rollout, rec: dict) -> None:
    kind, p = rec.get("type"), rec.get("payload")
    if not isinstance(p, dict):
        return
    ts = _iso(rec.get("timestamp"))
    ptype = p.get("type")
    if kind == "event_msg":
        if ptype == "task_started":
            ro.state, ro.last_event_at = "working", ts
        elif ptype in ("task_complete", "turn_aborted"):
            ro.state, ro.last_event_at = "done", ts
            msg = p.get("last_agent_message")
            if isinstance(msg, str) and msg.strip():
                ro.last_agent_message = msg
        return
    if kind != "response_item":
        return
    if ro.last_event_at is None or (ts and ts > ro.last_event_at):
        ro.last_event_at = ts or ro.last_event_at
    if ptype == "message":
        role = p.get("role")
        if role not in ("user", "assistant"):
            return  # developer = Codex's own system prompt
        text = _text_of(p.get("content")).strip()
        if not text or (role == "user" and _is_injected(text)):
            return
        ro.turns.append(RolloutTurn(role, text, ts))
    elif ptype in ("function_call", "custom_tool_call"):
        ro.turns.append(RolloutTurn("tool", f"[tool: {p.get('name', 'tool')}]", ts))
    elif ptype in ("function_call_output", "custom_tool_call_output"):
        text = _tool_output_text(p.get("output"))
        if text:
            ro.turns.append(RolloutTurn("tool", f"[tool result] {text}", ts))


def read_rollout(path: str) -> Rollout | None:
    """Whole rollout → turns + lifecycle state. ``None`` if unreadable."""
    ro = Rollout()
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(rec, dict):
                    _apply(ro, rec)
    except OSError:
        return None
    return ro


def read_rollout_tail(path: str) -> Rollout | None:
    """Last ``_TAIL_BYTES`` of a rollout: enough for state + last message without parsing MBs."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            f.seek(max(0, size - _TAIL_BYTES))
            data = f.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    lines = data.splitlines()
    if size > _TAIL_BYTES:
        lines = lines[1:]  # first line is cut mid-record
    ro = Rollout()
    for line in lines:
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict):
            _apply(ro, rec)
    return ro


# --- status / listing ---------------------------------------------------------


@dataclass
class CodexSession:
    thread: CodexThread
    status: str  # working | done | idle | unknown
    last_message: str
    last_event_at: float | None

    @property
    def idle_seconds(self) -> float:
        return max(0.0, time.time() - (self.last_event_at or self.thread.updated_at))

    def to_dict(self) -> dict:
        t = self.thread
        return {
            "id": f"codex:{t.id[:8]}", "kind": "codex-desktop" if t.desktop else "codex",
            "thread_id": t.id, "title": t.title, "cwd": t.cwd, "model": t.model,
            "daybreak": t.daybreak, "status": self.status, "idle_seconds": round(self.idle_seconds),
            "last_message": self.last_message, "rollout": t.rollout_path,
        }


def status_of(ro: Rollout | None) -> str:
    if ro is None or ro.state == "unknown":
        return "unknown"
    if ro.state == "working":
        # A started-but-never-completed turn in a file nobody has touched for a while is a dead
        # session, not a working one.
        fresh = ro.last_event_at and time.time() - ro.last_event_at < WORKING_WINDOW_S
        return "working" if fresh else "idle"
    return "done"


def session_for(thread: CodexThread) -> CodexSession:
    ro = read_rollout_tail(thread.rollout_path) if thread.rollout_path else None
    last = ro.last_agent_message if ro and ro.last_agent_message else ""
    if not last and ro:
        a = [t for t in ro.turns if t.role == "assistant"]
        last = a[-1].text if a else ""
    return CodexSession(thread, status_of(ro), last, ro.last_event_at if ro else None)


def recent_hours() -> float:
    try:
        return float(os.environ.get("AGENT_VIEW_CODEX_HOURS", "24"))
    except ValueError:
        return 24.0


def discover(hours: float | None = None, desktop_only: bool = True) -> list[CodexSession]:
    """Codex sessions updated within ``hours``, newest first.

    ``desktop_only`` (default) keeps the ChatGPT desktop app's threads: a CLI session already
    shows as a tmux pane, so listing it here too would double-count it.
    """
    h = recent_hours() if hours is None else hours
    return [session_for(t) for t in threads(since=time.time() - h * 3600)
            if t.desktop or not desktop_only]


def find_thread(cwd: str | None, pids_open: set[str] | None = None) -> CodexThread | None:
    """Thread a tmux pane's Codex process is running: the open rollout if known, else the
    newest thread whose ``cwd`` equals the pane's."""
    ts = threads()
    if pids_open:
        for t in ts:
            if t.rollout_path in pids_open:
                return t
    if cwd:
        for t in ts:  # newest first
            if t.cwd == cwd:
                return t
    return None


@dataclass
class Resolution:
    session: CodexSession | None
    error: str | None = None
    candidates: list[CodexSession] | None = None


def resolve(sessions: list[CodexSession], ident: str) -> Resolution:
    """``codex:<id-prefix>``, a bare id prefix (≥6 chars), or a unique title substring."""
    want = ident.strip()
    key = want[6:] if want.lower().startswith("codex:") else want
    low = key.lower()
    if not low:
        return Resolution(None, f"no codex session matches {ident!r}")
    hit = [s for s in sessions if s.thread.id.lower().startswith(low)] if len(low) >= 4 else []
    if not hit and not want.lower().startswith("codex:"):
        hit = [s for s in sessions if low in s.thread.title.lower()] if len(low) >= 3 else []
    if len(hit) == 1:
        return Resolution(hit[0])
    if len(hit) > 1:
        return Resolution(None, f"{ident!r} matches {len(hit)} codex sessions", hit)
    return Resolution(None, f"no codex session matches {ident!r}")


def rollout_files() -> list[str]:
    base = os.path.join(home(), "sessions")
    return glob.glob(os.path.join(base, "**", "rollout-*.jsonl"), recursive=True)

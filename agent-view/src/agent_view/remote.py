"""Remote (cloud) Claude Code sessions: ``claude --environment <ccpool_id>``.

Such a launch creates a cloud session on a self-hosted runner and the local
``claude`` exits straight back to the shell, so the tmux pane shows a bare
prompt and the agent vanishes from discovery. There are two launch shapes.

Interactive — the CLI prints this block into the pane's scrollback::

    Created cloud session: Environment diagnostics check
    Session ID: session_01VpjMyefcP66wrGW91FtrDY
    View: https://claude.ai/code/session_01VpjMyefcP66wrGW91FtrDY?from=cli&m=0
    Resume with: claude --teleport session_01VpjMyefcP66wrGW91FtrDY

Documented — ``claude -p "<prompt>" --environment <ccpool_id> --output-format
json`` is fire-and-forget (~5s) and prints one JSON object::

    {"ok":true,"session_id":"session_01…","title":"…","url":"https://claude.ai/code/session_01…?from=cli&m=0","pool_id":"ccpool_…"}

Sources (nothing here talks to the network):

* **launch-time registry** — ``agent-view remote record`` filters that output
  (pass-through) and writes the record the moment the session is created, with
  the exact launch time. This is the reliable path for scripted launches,
  whose JSON is usually captured by ``$(…)`` and never reaches a pane.
* **pane scrollback** — either shape above, scanned for shell panes (no agent
  process) and persisted on first sight via ``state.record_remote`` because the
  pane usually dies before anyone asks. Fallback for launches that bypassed
  the registry.
* **delegator sidecar** — ``~/.local/share/local-tmux-agent-delegator/sessions``
  (``$TMUX_AGENT_STATE_DIR``): prompt, worktree, repo and launch time, matched
  through the ``…/prompts/<key>.txt`` path in the launch line, else by pane id.
* **git** in the launch directory — branch. This describes where the session
  was *launched from*; the runner's checkout is not observable.

Each newly recorded session emits one ``remote-created`` line to the fleet event
log (``events.py``).

Status (running/idle/finished) is **not** exposed by any local source or by
the CLI (``logs``/``agents`` only see local background jobs; ``--cloud <id>``
attach is disabled for the account), so it is always ``unknown`` — open the URL.
``status_of`` is the single seam where a real source would plug in.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from . import cloudstatus, events, state, tmux
from .model import AgentPane, format_age

# How far back to look in a pane. The block is printed right after launch; this
# only has to survive until the next scan (a record is persisted on first sight).
SCAN_LINES = 1000
SHELLS = {"zsh", "bash", "sh", "fish", "dash", "ksh", "tcsh"}
KEEP_SECONDS = float(os.environ.get("AGENT_VIEW_REMOTE_DAYS", "7")) * 86400

# Anchored at line start and requires the three-line shape, so prose that merely
# mentions "Created cloud session" (docs, this very feature's prompts) never matches.
_CREATED_RE = re.compile(
    r"^Created cloud session(?::[ \t]*(?P<title>[^\n]*?))?[ \t]*\n"
    r"Session ID:[ \t]*(?P<sid>session_[A-Za-z0-9]+)[ \t]*\n"
    r"View:[ \t]*(?P<url>https?://\S+)",
    re.MULTILINE,
)
_ENV_RE = re.compile(r"--environment[ =]+(ccpool_[A-Za-z0-9]+)")
# `claude -p "<prompt>"` / `-p '<prompt>'` on the launch line (not `-p "$P"` / `$(cat …)`).
_PROMPT_ARG_RE = re.compile(r"""\s-p\s+(?:"(?P<d>[^"$`]+)"|'(?P<s>[^']+)')""")
_PROMPT_KEY_RE = re.compile(r"local-tmux-agent-delegator/sessions/prompts/([\w.-]+)\.txt")


@dataclass
class Created:
    """One ``Created cloud session`` block parsed out of text."""

    session_id: str
    url: str
    title: str | None
    environment: str | None
    delegator_key: str | None
    prompt: str | None = None  # the -p "<prompt>" argument, when literally on the launch line


def canonical_url(url: str) -> str:
    """Drop the ``?from=cli&m=0`` tracking query; the path is the session."""
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path, "", ""))


def _json_blocks(text: str) -> list[tuple[int, dict]]:
    """(offset, object) for each ``--output-format json`` launch result in ``text``."""
    out = []
    if '"session_id"' not in text:
        return out
    dec = json.JSONDecoder()
    i = text.find("{")
    while i != -1:
        try:
            obj, end = dec.raw_decode(text, i)
        except ValueError:
            i = text.find("{", i + 1)
            continue
        if isinstance(obj, dict) and obj.get("ok") is not False and state.valid_remote_id(
            str(obj.get("session_id", ""))
        ) and isinstance(obj.get("url"), str):
            out.append((i, obj))
        i = text.find("{", end)
    return out


def parse_created(text: str) -> list[Created]:
    """Every cloud-session launch result in ``text``, oldest first, deduped by id.

    Understands the interactive ``Created cloud session`` block and the
    ``-p … --output-format json`` object. The launch line (``--environment
    ccpool_…``, the delegator prompt-file path, a literal ``-p "<prompt>"``)
    is read from the text *before* each result, nearest preceding occurrence.
    """
    hits: list[tuple[int, str, str, str | None, str | None]] = []  # pos, sid, url, title, env
    for m in _CREATED_RE.finditer(text):
        hits.append((m.start(), m.group("sid"), m.group("url"),
                     (m.group("title") or "").strip() or None, None))
    for pos, obj in _json_blocks(text):
        hits.append((pos, obj["session_id"], obj["url"],
                     (obj.get("title") or "").strip() or None, obj.get("pool_id")))
    found: dict[str, Created] = {}
    for pos, sid, url, title, pool in sorted(hits):
        if sid in found:
            continue  # re-printed result: the first one sits under the right launch line
        before = text[:pos]
        env = _ENV_RE.findall(before)
        key = _PROMPT_KEY_RE.findall(before)
        arg = _PROMPT_ARG_RE.findall(before)
        found[sid] = Created(
            session_id=sid,
            url=canonical_url(url),
            title=title,
            environment=pool or (env[-1] if env else None),
            delegator_key=key[-1] if key else None,
            prompt=(arg[-1][0] or arg[-1][1]) if arg else None,
        )
    return list(found.values())


# --- delegator sidecar ------------------------------------------------------


def delegator_dir() -> str:
    return os.environ.get(
        "TMUX_AGENT_STATE_DIR",
        os.path.expanduser("~/.local/share/local-tmux-agent-delegator/sessions"),
    )


def _read_sidecar(path: str) -> dict | None:
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def find_sidecar(key: str | None, pane_id: str | None, since: float | None) -> dict | None:
    """Delegator record for a launch: by session key, else newest for the pane id.

    Pane ids restart at ``%0`` with the tmux server, so the by-pane fallback
    only considers sidecars written after the current server started.
    """
    d = delegator_dir()
    if key:
        hit = _read_sidecar(os.path.join(d, f"{key}.json"))
        if hit:
            return hit
    if not pane_id:
        return None
    try:
        names = [n for n in os.listdir(d) if n.endswith(".json")]
    except OSError:
        return None
    best: dict | None = None
    for name in names:
        path = os.path.join(d, name)
        try:
            if since is not None and os.stat(path).st_mtime < since:
                continue
        except OSError:
            continue
        data = _read_sidecar(path)
        if not data or data.get("tmux_target") != pane_id:
            continue
        if best is None or str(data.get("started_at", "")) > str(best.get("started_at", "")):
            best = data
    return best


def _epoch(iso: str | None) -> float | None:
    if not iso:
        return None
    from datetime import datetime

    try:
        return datetime.fromisoformat(iso).timestamp()
    except ValueError:
        return None


def summarize(text: str | None, limit: int = 140) -> str | None:
    """One-line gist of a (possibly huge, multi-paragraph) prompt."""
    if not text:
        return None
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _git(path: str, *args: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", path, *args], capture_output=True, text=True, timeout=2,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def git_info(path: str | None) -> tuple[str | None, str | None]:
    """(repo name, branch) of ``path``; (None, None) when the dir is gone / not a repo.

    Repo is the origin URL's basename. A detached HEAD (a clean ``origin/main``
    checkout) reads ``detached@<sha>``, not the unhelpful ``HEAD``.
    """
    if not path or not os.path.isdir(path):
        return None, None
    branch = _git(path, "rev-parse", "--abbrev-ref", "HEAD") or None
    if branch == "HEAD":
        sha = _git(path, "rev-parse", "--short", "HEAD")
        branch = f"detached@{sha}" if sha else None
    url = _git(path, "remote", "get-url", "origin")
    repo = os.path.basename(url.rstrip("/")).removesuffix(".git") if url else None
    return repo or None, branch


def _build_ref(c: Created, pane: dict | None, pane_id: str | None, location: str | None,
               server_start: float | None, launched_now: bool = False,
               prompt: str | None = None) -> state.RemoteRef:
    """Record for a launch result. ``launched_now``: the registry saw it happen."""
    side = find_sidecar(c.delegator_key, pane_id, server_start)
    project_dir = (side or {}).get("project_dir") or (pane or {}).get("path") or None
    launched = time.time() if launched_now else _epoch((side or {}).get("started_at"))
    git_repo, git_branch = git_info(project_dir)
    return state.RemoteRef(
        session_id=c.session_id,
        url=c.url,
        title=c.title,
        environment=c.environment,
        pane_id=pane_id,
        location=location,
        created_at=launched or 0.0,
        created_source=("registry" if launched_now else "delegator") if launched else "first-seen",
        prompt=summarize(prompt or (side or {}).get("prompt") or c.prompt),
        repo=(side or {}).get("repo") or git_repo,
        branch=git_branch,
        worktree=(side or {}).get("worktree"),
        project_dir=project_dir,
        delegator_key=(side or {}).get("session_key") or c.delegator_key,
    )


# --- discovery --------------------------------------------------------------

# (pane_id, last_activity) → already scanned. A bare shell that hasn't printed
# anything since the last scan can't have grown a new block, so the 1s TUI
# refresh stays at one list-panes call instead of a capture per shell pane.
_scanned: dict[str, float] = {}


def register(ref: state.RemoteRef) -> bool:
    """Persist a new remote session and announce it (``remote-created``) exactly once."""
    if not state.record_remote(ref):
        return False
    events.emit(events.remote_created(ref))
    return True


def scan_panes(panes: list[dict], agent_pane_ids: set[str]) -> int:
    """Record cloud sessions found in shell panes' scrollback. Returns #new."""
    new = 0
    server_start: float | None = None
    looked_up = False
    for pane in panes:
        pid = pane["pane_id"]
        if pid in agent_pane_ids:
            continue  # a live local agent owns this pane
        if pane.get("command") and pane["command"] not in SHELLS:
            continue  # nvim, lazygit, make… — not a bare prompt
        if _scanned.get(pid) == pane["last_activity"]:
            continue
        _scanned[pid] = pane["last_activity"]
        text = tmux.capture_scrollback(pid, SCAN_LINES)
        if "Created cloud session" not in text and '"session_id"' not in text:
            continue
        known = state.load_remote()
        for c in parse_created(text):
            if c.session_id in known:
                continue
            if not looked_up:
                server_start, looked_up = tmux.server_start_time(), True
            location = f"{pane['session']}:{pane['window_index']}.{pane['pane_index']}"
            if register(_build_ref(c, pane, pid, location, server_start)):
                new += 1
    return new


def record_from_output(text: str, pane_id: str | None = None, prompt: str | None = None,
                       environment: str | None = None) -> list[state.RemoteRef]:
    """Registry entry point: record every launch result in ``text`` as of *now*.

    Fed the stdout of ``claude -p … --output-format json`` (or the interactive
    block). Returns the newly recorded refs. Pure local I/O, never networks.
    """
    created = parse_created(text)
    if not created:
        return []
    location = tmux.pane_location(pane_id) if pane_id else None
    server_start = tmux.server_start_time() if pane_id else None
    out = []
    for c in created:
        c.environment = c.environment or environment
        ref = _build_ref(c, {"path": os.getcwd()}, pane_id, location, server_start,
                         launched_now=True, prompt=prompt)
        if register(ref):
            out.append(ref)
    return out


@dataclass
class RemoteSession:
    """A persisted record joined with live tmux state."""

    ref: state.RemoteRef
    pane_alive: bool = False  # the launching pane still exists
    pane_has_agent: bool = False  # …and a local agent runs in it now
    live_location: str | None = None
    now: float = 0.0
    lookup: cloudstatus.CloudStatus | None = None  # this run's status lookup, if one was made

    @property
    def session_id(self) -> str:
        return self.ref.session_id

    @property
    def url(self) -> str:
        return self.ref.url

    @property
    def location(self) -> str | None:
        """Where it was launched from: live location if the pane exists."""
        return self.live_location or self.ref.location

    @property
    def awaiting_flag(self) -> bool:
        """Pane is a bare shell whose claude exited after creating this session."""
        return self.pane_alive and not self.pane_has_agent

    @property
    def flag(self) -> str:
        """The marker shown on the launching pane: '-> remote <url>'."""
        return f"-> remote {self.url}"

    @property
    def status(self) -> str:
        return status_of(self)[0]

    @property
    def status_text(self) -> str:
        status, hint = status_of(self)
        return f"{status}, {hint}" if status == "unknown" else f"{status} — {hint}"

    @property
    def age(self) -> str:
        return format_age((self.now or time.time()) - self.ref.created_at)

    def filter_haystack(self) -> str:
        r = self.ref
        return " ".join(filter(None, [
            "remote", r.session_id, r.title, r.repo, r.branch, r.worktree, self.location,
        ]))

    def to_dict(self) -> dict:
        r = self.ref
        return {
            # Same leading keys as a local `ls --json` row, so consumers can branch on `kind`.
            "id": r.session_id,
            # Only a live pane is addressable; a gone pane's id may be reused after a tmux
            # restart, so the recorded one stays under `launched_from` only.
            "pane_id": r.pane_id if self.pane_alive else None,
            "kind": "remote",
            "session": (self.location or "").split(":", 1)[0] or None,
            "window": r.worktree,
            "title": r.title,
            "status": self.status,
            "blocked": False,
            "reason": None,
            # Remote-specific.
            "session_id": r.session_id,
            "url": r.url,
            "status_hint": status_of(self)[1],
            "status_detail": r.status_detail,
            "status_checked_at": r.status_checked_at or None,
            "status_source": cloudstatus.SOURCE if r.status else None,
            "status_reason": self.lookup.reason if self.lookup and not self.lookup.known else None,
            "remote_branch": r.remote_branch,  # the runner's own branch (claude/<slug>)
            "last_message": r.last_message,  # redacted ≤500-char excerpt, when one was fetched
            "last_event_at": r.last_event_at,
            "environment": r.environment,
            "launched_from": {
                "pane_id": r.pane_id,
                "location": self.location,
                "pane_alive": self.pane_alive,
                "pane_has_agent": self.pane_has_agent,
                "flag": self.flag if self.awaiting_flag else None,
            },
            "repo": r.repo,
            "branch": r.branch,
            "branch_note": "launch directory's branch, not verified against the runner",
            "worktree": r.worktree,
            "project_dir": r.project_dir,
            "created_at": r.created_at,
            "created_source": r.created_source,
            "age": self.age,
            "prompt": r.prompt,
            "delegator_key": r.delegator_key,
        }


# An active state (running/idle/needs-input) is only trustworthy while fresh; a
# finished/failed one stays true until the session is resumed.
ACTIVE_FRESH_SECONDS = 300.0
POLL_ACTIVE_SECONDS = 15.0
POLL_TERMINAL_SECONDS = 600.0
MAX_POLLED = 12  # newest sessions only; never fan out unboundedly


def status_of(session: RemoteSession) -> tuple[str, str]:
    """(status, hint) from the last observed cloud status, else ``unknown, open URL``.

    Source: ``cloudstatus`` — a read-only GET of the session, the same call the CLI
    makes. A lookup that failed *this run* reads unknown with its reason; an active
    state that hasn't been refreshed lately is unknown too, not a stale "running".
    """
    r = session.ref
    if session.lookup is not None and not session.lookup.known and not r.status:
        why = session.lookup.reason
        return "unknown", f"{why}, open URL" if why else "open URL"
    if not r.status:
        return "unknown", "open URL"
    age = (session.now or time.time()) - (r.status_checked_at or 0)
    ago = format_age(age)
    if session.lookup is not None and not session.lookup.known:
        return "unknown", f"lookup failed ({session.lookup.reason}); last seen {r.status} {ago} ago, open URL"
    if r.status in cloudstatus.ACTIVE and age > ACTIVE_FRESH_SECONDS:
        return "unknown", f"last seen {r.status} {ago} ago, open URL"
    detail = f"{r.status_detail} · " if r.status_detail else ""
    return r.status, f"{detail}checked {ago} ago"


def _due(ref: state.RemoteRef, now: float) -> bool:
    age = now - (ref.status_checked_at or 0)
    return age >= (POLL_TERMINAL_SECONDS if ref.status in cloudstatus.TERMINAL else POLL_ACTIVE_SECONDS)


_refresh_lock = threading.Lock()  # the TUI ticks every second; never stack lookups
# Backoff for failing lookups: session_id → (consecutive failures, don't retry before). The
# TUI ticks every second, so without this an error would be retried every second.
BACKOFF_MAX_SECONDS = 120.0
_status_backoff: dict[str, tuple[int, float]] = {}


def _backoff_delay(fails: int, base: float) -> float:
    return min(BACKOFF_MAX_SECONDS, base * (2 ** max(0, fails - 1)))


def refresh_status(sessions: list[RemoteSession], force: bool = False) -> list[dict]:
    """Look up due sessions (read-only GETs, in parallel) and announce transitions.

    Persists each observed status under a lock; the process that sees a change into
    ``finished`` / ``failed`` / ``needs-input`` appends the matching event to the log.
    A failed lookup records nothing (the session just reads unknown this run).
    Returns the events emitted. Never raises.
    """
    from concurrent.futures import ThreadPoolExecutor

    emitted: list[dict] = []
    if os.environ.get("AGENT_VIEW_NO_STATUS"):
        return emitted  # opted out: no lookups, nothing to explain
    if not _refresh_lock.acquire(blocking=False):
        return emitted  # a lookup is already in flight in this process
    try:
        now = time.time()
        todo = [
            s for s in sessions[:MAX_POLLED]
            if force or (_due(s.ref, now) and _status_backoff.get(s.session_id, (0, 0.0))[1] <= now)
        ]
        if not todo:
            return emitted
        with ThreadPoolExecutor(max_workers=min(6, len(todo))) as ex:
            results = list(ex.map(lambda s: cloudstatus.fetch(s.session_id), todo))
        for s, res in zip(todo, results):
            s.lookup = res
            if not res.known:
                fails = _status_backoff.get(s.session_id, (0, 0.0))[0] + 1
                _status_backoff[s.session_id] = (fails, now + _backoff_delay(fails, POLL_ACTIVE_SECONDS))
                continue
            _status_backoff.pop(s.session_id, None)
            excerpt = None
            if res.state in events.STATUS_EVENTS and (s.ref.status != res.state or not s.ref.last_message):
                # announcing (or backfilling a notable state with no excerpt yet): fetch the
                # session's last words — one more read-only GET; no event unless status changed
                lm = cloudstatus.fetch_last_message(s.session_id)
                excerpt = lm.excerpt() if lm.ok else None
            prev, changed, ref = state.update_remote_status(
                s.session_id, res.state, res.detail, res.remote_branch, res.last_event_at, excerpt,
                res.pool_name,
            )
            if ref is None:
                continue
            s.ref = ref
            ev = events.remote_status(ref, prev) if changed else None
            if ev and events.emit(ev):
                emitted.append(ev)
    except Exception:
        pass
    finally:
        _refresh_lock.release()
    return emitted


def discover(
    agents: list[AgentPane] | None = None,
    panes: list[dict] | None = None,
    scan: bool = True,
    refresh: bool = False,
) -> list[RemoteSession]:
    """All known remote sessions, newest first. Never raises (best-effort).

    ``scan=False`` skips the scrollback pass and reads persisted records only
    (milliseconds) — the TUI's first frame uses it and scans in a worker.
    ``refresh=True`` also looks up each due session's cloud status (network, parallel,
    ~1s) and emits transition events; CLI commands pass it, the TUI does it in a worker.
    """
    try:
        if panes is None:
            panes = tmux.list_panes()
        if agents is None:
            from . import discovery

            agents = discovery.discover()
        agent_ids = {a.pane_id for a in agents}
        if scan:
            scan_panes(panes, agent_ids)
            state.prune_remote(KEEP_SECONDS)
        by_id = {p["pane_id"]: p for p in panes}
        now = time.time()
        out = []
        for ref in state.load_remote().values():
            if ref.dismissed:
                continue
            pane = by_id.get(ref.pane_id or "")
            out.append(RemoteSession(
                ref=ref,
                pane_alive=pane is not None,
                pane_has_agent=ref.pane_id in agent_ids,
                live_location=(
                    f"{pane['session']}:{pane['window_index']}.{pane['pane_index']}"
                    if pane else None
                ),
                now=now,
            ))
        out.sort(key=lambda s: -s.ref.created_at)
        if refresh:
            refresh_status(out)
        return out
    except Exception:
        return []  # remote awareness must never break the local listing


def change_key(sessions: list[RemoteSession]) -> list[tuple]:
    """What a viewer would see change — lets a refresh skip redundant rebuilds."""
    return [(s.session_id, s.pane_alive, s.pane_has_agent, s.location, s.status) for s in sessions]


# --- live peek (tile body) --------------------------------------------------------
# What the session is doing, from the read-only events GET, refreshed on a timer:
# ~12s while it is active, every 5 min once finished, exponential backoff on errors.

PEEK_SECONDS = float(os.environ.get("AGENT_VIEW_PEEK_SECONDS", "12"))
PEEK_TERMINAL_SECONDS = 300.0
MAX_PEEKED = 8


@dataclass
class PeekState:
    peek: cloudstatus.Peek
    next_due: float = 0.0
    fails: int = 0
    version: int = 0  # bumps when the content changed (lets the UI skip redundant redraws)


_peeks: dict[str, PeekState] = {}
_peek_lock = threading.Lock()


def peeks_enabled() -> bool:
    return not os.environ.get("AGENT_VIEW_NO_STATUS")


def peek_of(session_id: str) -> PeekState | None:
    return _peeks.get(session_id)


def refresh_peeks(sessions: list[RemoteSession], force: bool = False) -> bool:
    """Fetch due peeks (read-only GETs, parallel). Returns True if any content changed."""
    from concurrent.futures import ThreadPoolExecutor

    if not peeks_enabled() or not _peek_lock.acquire(blocking=False):
        return False
    changed = False
    try:
        now = time.time()
        todo = [
            s for s in sessions[:MAX_PEEKED]
            if force or (st := _peeks.get(s.session_id)) is None or st.next_due <= now
        ]
        if not todo:
            return False
        with ThreadPoolExecutor(max_workers=min(4, len(todo))) as ex:
            results = list(ex.map(lambda s: cloudstatus.fetch_peek(s.session_id), todo))
        for s, peek in zip(todo, results):
            old = _peeks.get(s.session_id)
            if peek.reason:  # error: keep the last good content, back off
                fails = (old.fails if old else 0) + 1
                keep = old.peek if old else peek
                _peeks[s.session_id] = PeekState(
                    keep, now + _backoff_delay(fails, PEEK_SECONDS), fails, old.version if old else 0
                )
                changed = changed or old is None
                continue
            terminal = s.ref.status in cloudstatus.TERMINAL
            sig = [(i.kind, i.at, i.lines) for i in peek.items]
            same = old is not None and [(i.kind, i.at, i.lines) for i in old.peek.items] == sig
            _peeks[s.session_id] = PeekState(
                peek, now + (PEEK_TERMINAL_SECONDS if terminal else PEEK_SECONDS), 0,
                (old.version if old else 0) + (0 if same else 1),
            )
            changed = changed or not same
    except Exception:
        pass
    finally:
        _peek_lock.release()
    return changed


# --- a remote session as a normal agent tile -----------------------------------------

import re as _re  # noqa: E402

from .model import STALE_AFTER_SECONDS, AgentKind, AgentPane, AgentState  # noqa: E402

TILE_HOURS = float(os.environ.get("AGENT_VIEW_REMOTE_TILE_HOURS", "24"))
_ANSI = {"assistant": "\x1b[35m✎\x1b[0m ", "tool_use": "\x1b[36m▸\x1b[0m \x1b[36m", "tool_result": "\x1b[90m◂ ",
         "user": "\x1b[90m› "}


def _epoch(iso: str | None) -> float | None:  # shadows the earlier helper on purpose: same behaviour
    if not iso:
        return None
    from datetime import datetime

    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


@dataclass
class RemoteAgent(AgentPane):
    """An ``AgentPane`` look-alike for a cloud session, so the overview can draw it as a tile.

    Everything the TUI reads from an agent (state, sort key, filter text, title, idle time) is
    derived from the session's record + last observed status. There is no pane and no process:
    selecting it opens the claude.ai URL, and nothing can be killed or jumped to.
    """

    session_obj: RemoteSession | None = None
    is_remote = True

    @classmethod
    def from_session(cls, s: RemoteSession) -> "RemoteAgent":
        r = s.ref
        activity = _epoch(r.last_event_at) or r.status_changed_at or r.created_at
        if s.status in ("running", "needs-input"):  # alive and observed just now
            activity = max(activity, r.status_checked_at or 0)
        return cls(
            pane_id=f"r-{r.session_id}",  # valid as a Textual widget id (no %, no :)
            pane_pid=0, agent_pid=0, kind=AgentKind.REMOTE,
            session="remote", window_index="-", pane_index="-",
            window_name=r.title or r.session_id,
            last_activity=activity,
            now=s.now or time.time(),
            session_obj=s,
        )

    # -- identity --------------------------------------------------------------------
    @property
    def remote(self) -> RemoteSession:
        assert self.session_obj is not None
        return self.session_obj

    @property
    def url(self) -> str:
        return self.remote.url

    @property
    def location(self) -> str:  # shown where a local tile shows pane coordinates
        return f"remote {short_id(self.remote.session_id, 12)}"

    @property
    def pool(self) -> str | None:
        r = self.remote.ref
        return r.pool_name or (r.environment[:12] + "…" if r.environment else None)

    @property
    def remote_status(self) -> str:
        return self.remote.status

    # -- state: map the cloud status onto the markers local tiles use -----------------
    @property
    def state(self) -> AgentState:
        st = self.remote.status
        if st == "needs-input":
            return AgentState.PENDING  # yellow, sorts first
        if st == "running":
            return AgentState.WORKING  # blue
        if st == "failed" or self.idle_seconds >= STALE_AFTER_SECONDS:
            return AgentState.STALE  # red: failed, or quiet for hours like a forgotten pane
        return AgentState.IDLE  # finished / idle / unknown

    @property
    def pending_message(self) -> str | None:  # type: ignore[override]
        if self.remote.status == "needs-input":
            return self.remote.ref.status_detail or "needs your input"
        return None

    @pending_message.setter
    def pending_message(self, _v) -> None:  # dataclass init assigns it; remote derives it
        pass

    @property
    def pending_since(self) -> float | None:  # type: ignore[override]
        return self.remote.ref.status_changed_at or None

    @pending_since.setter
    def pending_since(self, _v) -> None:
        pass

    @property
    def show_tile(self) -> bool:
        """Show active sessions always; finished/failed ones for TILE_HOURS after their last event."""
        st = self.remote.status
        return st not in cloudstatus.TERMINAL or self.idle_seconds < TILE_HOURS * 3600

    def filter_haystack(self) -> str:
        r = self.remote.ref
        return " ".join(filter(None, [
            "remote cloud", r.session_id, r.title, self.pool, r.repo, r.branch, r.remote_branch, self.remote.status,
        ]))

    # -- the live peek ------------------------------------------------------------------
    def peek_ansi(self, max_lines: int = 60) -> str:
        """Tile body: recent assistant text / tool activity as ANSI (what a pane capture is for local)."""
        st = peek_of(self.remote.session_id)
        lines: list[str] = []
        if st and st.peek.items:
            for item in st.peek.items:
                pre = _ANSI.get(item.kind, "")
                post = "\x1b[0m" if item.kind in ("tool_use", "tool_result", "user") else ""
                for n, text in enumerate(item.lines):
                    lines.append((pre if n == 0 else "  ") + text + post)
        else:  # nothing fetched yet (first frame, no credential, error): what the record knows
            r = self.remote.ref
            if r.prompt:
                lines.append("\x1b[90m› \x1b[0m" + r.prompt)
            if r.last_message:
                lines.append("\x1b[35m✎\x1b[0m " + r.last_message)
            if not lines:
                lines.append("\x1b[90m(waiting for the first update…)\x1b[0m")
            if st and st.peek.reason:
                lines.append(f"\x1b[90m(live view unavailable: {st.peek.reason})\x1b[0m")
        return "\n".join(lines[-max_lines:])


def remote_agents(sessions: list[RemoteSession]) -> list[RemoteAgent]:
    """Tiles for the overview: one per visible session (see ``RemoteAgent.show_tile``)."""
    return [a for a in (RemoteAgent.from_session(s) for s in sessions) if a.show_tile]


def peek_key(sessions: list[RemoteSession]) -> list[tuple]:
    """Change token for a redraw decision: per-session peek version + status."""
    return [(s.session_id, (peek_of(s.session_id).version if peek_of(s.session_id) else -1)) for s in sessions]


# --- id resolution ----------------------------------------------------------


@dataclass
class Resolution:
    session: RemoteSession | None
    error: str | None = None
    candidates: list[RemoteSession] | None = None


def resolve(sessions: list[RemoteSession], ident: str) -> Resolution:
    """session id (exact or unique substring) · URL · pane id · pane location."""
    ident = ident.strip()
    if not ident:
        return Resolution(None, error="empty id")
    for s in sessions:
        if ident in (s.session_id, s.url, s.ref.pane_id, s.location):
            return Resolution(s)
    needle = ident.lower()
    subs = [s for s in sessions if needle in s.session_id.lower() or needle in s.url.lower()]
    if len(subs) == 1:
        return Resolution(subs[0])
    if len(subs) > 1:
        return Resolution(None, error=f"'{ident}' is ambiguous", candidates=subs)
    return Resolution(None, error=f"no remote session matches '{ident}'")


# --- rendering --------------------------------------------------------------


def short_id(session_id: str, n: int = 14) -> str:
    return session_id if len(session_id) <= n + 1 else session_id[:n] + "…"


def row_lines(s: RemoteSession, width_prompt: int = 90) -> list[str]:
    """Text rows for ``ls``: a headline, then context lines."""
    r = s.ref
    where = s.location or r.pane_id or "?"
    if not s.pane_alive:
        where += " (gone)"
    head = f"{where:16} remote  {s.status:8} {r.session_id}  {s.flag if s.awaiting_flag else s.url}"
    ctx = []
    if r.title:
        ctx.append(r.title)
    repo = "/".join(filter(None, [r.repo, r.worktree])) if r.repo or r.worktree else None
    if repo:
        ctx.append(repo + (f"@{r.branch}" if r.branch else ""))
    elif r.branch:
        ctx.append(f"@{r.branch}")
    ctx.append(f"launched {s.age} ago" + ("" if r.created_source != "first-seen" else " (first seen)"))
    lines = [head, f"                 {' · '.join(ctx)}"]
    if s.pane_alive and s.pane_has_agent:
        lines.append("                 (pane now runs a local agent; this session is still remote)")
    if r.prompt:
        text = r.prompt if len(r.prompt) <= width_prompt else r.prompt[: width_prompt - 1] + "…"
        lines.append(f"                 prompt: {text}")
    if r.remote_branch:
        lines.append(f"                 runner branch: {r.remote_branch}")
    if r.last_message:
        text = r.last_message if len(r.last_message) <= 110 else r.last_message[:109] + "…"
        lines.append(f"                 last message: {text}")
    lines.append(f"                 status: {s.status_text}")
    return lines

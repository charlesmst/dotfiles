"""Read-only status of a remote (cloud) session, from the endpoint the ``claude`` CLI uses.

Authorized by Charles (2026-10-01, "Yes, read-only"). Conditions, enforced here:

* **GET only.** One request type, ``GET {base}/v1/code/sessions/{id}`` — the same call
  the CLI makes when it fetches a cloud session. Nothing is ever sent *into* a
  session (no POST/PUT, no events, no messages), and redirects are refused so the
  bearer can never be forwarded to another host.
* **The token never leaves this module.** It is resolved in memory, put in one
  ``Authorization`` header, and is never printed, logged, stored, or included in an
  error string. Failures return a short fixed reason, never exception text.
* **Any error → unknown.** No credential, expired token, HTTP error, timeout, bad
  JSON, unrecognised shape: ``fetch`` returns ``CloudStatus(state="unknown", reason=…)``.
  Never raises.

Credential sources, in order: ``CLAUDE_CODE_OAUTH_TOKEN`` (the CLI's documented
long-lived-token variable) then, on macOS, the CLI's own keychain entry. An expired
token is *not* refreshed (that would be a POST): it reads as unknown until the CLI
refreshes it itself.

State derivation is deliberately conservative — it only maps values that were
observed in real responses or are used by the CLI itself; everything else is
``unknown``:

======================  =====================================================
state                   when
======================  =====================================================
``needs-input``         ``worker_status == "requires_action"``, a non-empty
                        ``requires_action_details_list``, or a non-empty
                        ``post_turn_summary.needs_action``
``running``             ``worker_status == "running"``
``finished``            ``worker_status == "idle"`` and the turn is complete
                        (``status_bucket`` / ``post_turn_summary.status_category``
                        == ``"completed"``), or the session is archived
``idle``                ``worker_status == "idle"``, turn not complete
``failed``              ``status == "failed"``
``unknown``             anything else / any error
======================  =====================================================
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from .redact import excerpt, redact

BASE_URL = os.environ.get("AGENT_VIEW_CLAUDE_API", "https://api.anthropic.com")
KEYCHAIN_SERVICE = "Claude Code-credentials"
TIMEOUT = 8.0
SOURCE = "claude.ai cloud session (GET /v1/code/sessions)"

ACTIVE = {"unknown", "running", "idle", "needs-input"}
TERMINAL = {"finished", "failed"}


@dataclass
class CloudStatus:
    state: str = "unknown"
    detail: str | None = None  # the session's own short post-turn summary
    reason: str | None = None  # why unknown (fixed strings; never exception text)
    remote_branch: str | None = None  # the runner's branch (claude/<slug>), if reported
    last_event_at: str | None = None
    pool_name: str | None = None  # self_hosted_runner_state.pool_name ("main")
    checked_at: float = 0.0

    @property
    def known(self) -> bool:
        return self.state != "unknown"


# --- credential (in memory only) --------------------------------------------


def _token() -> tuple[str | None, str | None]:
    """(token, None) or (None, reason). The token is never returned to a caller that logs."""
    env = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip()
    if env:
        return env, None
    if sys.platform != "darwin":
        return None, "no credential"
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode != 0:
            return None, "no credential"
        oauth = (json.loads(out.stdout) or {}).get("claudeAiOauth") or {}
        token = oauth.get("accessToken")
        expires = oauth.get("expiresAt")  # ms epoch
        if not token:
            return None, "no credential"
        if isinstance(expires, (int, float)) and expires / 1000 < time.time():
            return None, "token expired"
        return token, None
    except Exception:
        return None, "no credential"


# --- request (GET only, no redirects) ---------------------------------------


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # never forward the bearer elsewhere
        return None


def _get(path: str, token: str) -> tuple[int, bytes]:
    """The only HTTP call in this module, and it is a GET. ``path`` is under /v1/code/sessions."""
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        method="GET",
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
            "User-Agent": "agent-view-status/0.1",
        },
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=TIMEOUT) as r:
            return r.status, r.read(4_000_000)
    except urllib.error.HTTPError as e:
        return e.code, b""


# --- derivation (pure) -------------------------------------------------------


def _short(s: object, n: int = 140) -> str | None:
    if not isinstance(s, str) or not s.strip():
        return None
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def derive(data: dict) -> CloudStatus:
    """Map a ``/v1/code/sessions/{id}`` body to a state. Conservative; see module doc."""
    d = data.get("response_shape", data) if isinstance(data, dict) else None
    if not isinstance(d, dict):
        return CloudStatus(reason="unrecognised response")
    pts = d.get("post_turn_summary") if isinstance(d.get("post_turn_summary"), dict) else {}
    ws, st = d.get("worker_status"), d.get("status")
    completed = d.get("status_bucket") == "completed" or pts.get("status_category") == "completed"
    needs = bool(d.get("requires_action_details_list")) or bool(_short(pts.get("needs_action")))
    branches = (d.get("external_metadata") or {}).get("current_branches")
    branch = next((b for b in branches.values() if isinstance(b, str)), None) \
        if isinstance(branches, dict) else None

    if st == "failed":
        state = "failed"
    elif st in ("archived", "deleted") or d.get("archived_at"):
        state = "finished"
    elif ws == "requires_action" or needs:
        state = "needs-input"
    elif ws == "running":
        state = "running"
    elif ws == "idle":
        state = "finished" if completed else "idle"
    else:
        return CloudStatus(reason="unrecognised state", remote_branch=branch)
    runner = d.get("self_hosted_runner_state")
    pool = runner.get("pool_name") if isinstance(runner, dict) else None
    detail = _short(pts.get("status_detail")) or _short(pts.get("recent_action"))
    return CloudStatus(
        state=state,
        detail=redact(detail) if detail else None,  # session-authored text: same rule as everything else
        pool_name=pool if isinstance(pool, str) else None,
        remote_branch=branch,
        last_event_at=d.get("last_event_at") if isinstance(d.get("last_event_at"), str) else None,
    )


def fetch(session_id: str) -> CloudStatus:
    """Status of one cloud session. Never raises; any problem → ``unknown`` + a fixed reason."""
    now = time.time()
    if os.environ.get("AGENT_VIEW_NO_STATUS"):
        return CloudStatus(reason="status lookup disabled", checked_at=now)
    try:
        token, why = _token()
        if not token:
            return CloudStatus(reason=why, checked_at=now)
        code, body = _get(f"/v1/code/sessions/{session_id}", token)
        token = None  # drop the reference as soon as the request is done
        if code == 404:
            return CloudStatus(reason="session not found", checked_at=now)
        if code in (401, 403):
            return CloudStatus(reason="not authorized", checked_at=now)
        if code != 200:
            return CloudStatus(reason=f"http {code}", checked_at=now)
        st = derive(json.loads(body))
        st.checked_at = now
        return st
    except Exception:
        return CloudStatus(reason="lookup failed", checked_at=now)


# --- last message / event tail (read-only GET of the session's events) -----------
#
# ``GET /v1/code/sessions/{id}/events`` returns ``{"data": [event…], "resume_cursor"}``,
# newest first (``sequence_num`` descending). Events seen: ``assistant`` (message.content
# blocks, ``text``/``tool_use``), ``user`` (the prompt from the client; tool results from
# the worker), ``result`` (subtype ``success``, ``result`` = the final text), ``system``
# (``status``, hooks, init) and runner noise (``env_manager_log``…), which is skipped.
# Everything returned is run through ``redact`` — a session may echo secrets.

EXCERPT_CHARS = 500


@dataclass
class LastMessage:
    text: str = ""  # redacted, full (callers cap it)
    kind: str | None = None  # "assistant" | "result"
    at: str | None = None  # created_at of the event
    reason: str | None = None  # why there is no text (fixed strings)

    @property
    def ok(self) -> bool:
        return bool(self.text)

    def excerpt(self, limit: int = EXCERPT_CHARS) -> str:
        return excerpt(self.text, limit)


@dataclass
class TailEntry:
    at: str
    kind: str  # assistant | tool_use | tool_result | user | result | status
    text: str  # redacted, one line, short


@dataclass
class Tail:
    entries: list[TailEntry] = field(default_factory=list)
    reason: str | None = None


def _events(session_id: str):
    """(events newest-first | None, reason, scrub). ``scrub`` redacts and knows the token."""
    if os.environ.get("AGENT_VIEW_NO_STATUS"):
        return None, "status lookup disabled", redact
    token, why = _token()
    if not token:
        return None, why, redact
    scrub = lambda t: redact(t, [token])  # noqa: E731 - holds the token, never returns it
    try:
        code, body = _get(f"/v1/code/sessions/{session_id}/events", token)
        if code == 404:
            return None, "session not found", scrub
        if code in (401, 403):
            return None, "not authorized", scrub
        if code != 200:
            return None, f"http {code}", scrub
        data = json.loads(body).get("data")
        if not isinstance(data, list):
            return None, "unrecognised response", scrub
        evs = [e for e in data if isinstance(e, dict) and isinstance(e.get("payload"), dict)]

        def seq(e):
            try:
                return int(e.get("sequence_num"))
            except (TypeError, ValueError):
                return 0

        evs.sort(key=seq, reverse=True)
        return evs, None, scrub
    except Exception:
        return None, "lookup failed", scrub


def _blocks(payload: dict) -> list[dict]:
    msg = payload.get("message")
    content = msg.get("content") if isinstance(msg, dict) else None
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return [b for b in content or [] if isinstance(b, dict)]


def _text(payload: dict) -> str:
    return "\n".join(
        b["text"].strip() for b in _blocks(payload)
        if b.get("type") == "text" and isinstance(b.get("text"), str) and b["text"].strip()
    )


def fetch_last_message(session_id: str) -> LastMessage:
    """The session's last assistant message (else its final ``result`` text). Never raises."""
    evs, why, scrub = _events(session_id)
    if evs is None:
        return LastMessage(reason=why)
    try:
        for e in evs:
            if e.get("event_type") == "assistant" or e["payload"].get("type") == "assistant":
                text = _text(e["payload"])
                if text:
                    return LastMessage(scrub(text), "assistant", e.get("created_at"))
        for e in evs:
            res = e["payload"].get("result")
            if (e.get("event_type") == "result" or e["payload"].get("type") == "result") and isinstance(res, str) and res.strip():
                return LastMessage(scrub(res.strip()), "result", e.get("created_at"))
    except Exception:
        return LastMessage(reason="lookup failed")
    return LastMessage(reason="no assistant message yet")


def _tool_result_text(payload: dict) -> str:
    out = []
    for b in _blocks(payload):
        c = b.get("content")
        if isinstance(c, str):
            out.append(c)
        elif isinstance(c, list):
            out.extend(x.get("text", "") for x in c if isinstance(x, dict))
    return " ".join(out)


def fetch_tail(session_id: str, n: int = 10, width: int = 160) -> Tail:
    """Last ``n`` meaningful events, oldest first, each one redacted line. Never raises."""
    evs, why, scrub = _events(session_id)
    if evs is None:
        return Tail(reason=why)
    groups: list[list[TailEntry]] = []  # one group per event, newest event first
    try:
        for e in evs:
            p, at = e["payload"], e.get("created_at") or ""
            t, g = p.get("type"), []
            if t == "assistant":
                text = _text(p)
                if text:
                    g.append(TailEntry(at, "assistant", excerpt(scrub(text), width)))
                for b in _blocks(p):
                    if b.get("type") == "tool_use":
                        arg = json.dumps(b.get("input"), ensure_ascii=False)
                        g.append(TailEntry(at, "tool_use", excerpt(scrub(f"{b.get('name')} {arg}"), width)))
            elif t == "user":
                if any(b.get("type") == "tool_result" for b in _blocks(p)):
                    g.append(TailEntry(at, "tool_result", excerpt(scrub(_tool_result_text(p)), width)))
                else:
                    g.append(TailEntry(at, "user", excerpt(scrub(_text(p)), width)))
            elif t == "result":
                g.append(TailEntry(at, "result", f"{p.get('subtype') or '?'}"
                                   + (" (error)" if p.get("is_error") else "")))
            elif t == "system" and p.get("subtype") == "status":
                g.append(TailEntry(at, "status", str(p.get("status"))[:40]))
            if g:
                groups.append(g)
            if sum(len(x) for x in groups) >= n:
                break
    except Exception:
        return Tail(reason="lookup failed")
    flat = [entry for g in reversed(groups) for entry in g]  # oldest event first, in-event order kept
    return Tail(entries=flat[-n:])


# --- live peek: what the session is doing right now ------------------------------
#
# The same read-only events GET, shaped for a tile body: the recent assistant text
# and tool activity, oldest first, each line redacted and width-capped. One request.


@dataclass
class PeekItem:
    kind: str  # assistant | tool_use | tool_result | user
    at: str
    lines: list[str]


@dataclass
class Peek:
    items: list[PeekItem] = field(default_factory=list)
    reason: str | None = None  # fixed string when there is nothing (errors)
    fetched_at: float = 0.0


def _tool_summary(block: dict) -> str:
    inp = block.get("input") if isinstance(block.get("input"), dict) else {}
    for key in ("command", "description", "file_path", "path", "pattern", "url", "query", "prompt"):
        v = inp.get(key)
        if isinstance(v, str) and v.strip():
            return f"{block.get('name', 'tool')}: {' '.join(v.split())}"
    return f"{block.get('name', 'tool')}: {json.dumps(inp, ensure_ascii=False)[:200]}" if inp else str(block.get("name", "tool"))


def _cap_lines(text: str, scrub, max_lines: int, width: int) -> list[str]:
    out = []
    for raw in scrub(text).splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        out.append(line if len(line) <= width else line[: width - 1] + "…")
        if len(out) >= max_lines:
            break
    return out


def fetch_peek(session_id: str, max_events: int = 12, width: int = 240) -> Peek:
    """Recent assistant text / tool activity of a session. Never raises; GET only; redacted."""
    now = time.time()
    evs, why, scrub = _events(session_id)
    if evs is None:
        return Peek(reason=why, fetched_at=now)
    items: list[PeekItem] = []
    try:
        for e in evs:  # newest first
            p, at = e["payload"], e.get("created_at") or ""
            t = p.get("type")
            group: list[PeekItem] = []
            if t == "assistant":
                text = _text(p)
                if text:
                    group.append(PeekItem("assistant", at, _cap_lines(text, scrub, 24, width)))
                for b in _blocks(p):
                    if b.get("type") == "tool_use":
                        group.append(PeekItem("tool_use", at, _cap_lines(_tool_summary(b), scrub, 2, width)))
            elif t == "user":
                if any(b.get("type") == "tool_result" for b in _blocks(p)):
                    group.append(PeekItem("tool_result", at, _cap_lines(_tool_result_text(p), scrub, 6, width)))
                else:
                    group.append(PeekItem("user", at, _cap_lines(_text(p), scrub, 3, width)))
            group = [g for g in group if g.lines]
            if group:
                items[:0] = group  # prepend: keep chronological order inside the event
            if len(items) >= max_events:
                break
        # `items` was built by prepending whole events newest→oldest, so it is oldest first.
    except Exception:
        return Peek(reason="lookup failed", fetched_at=now)
    return Peek(items=items[-max_events:], fetched_at=now)

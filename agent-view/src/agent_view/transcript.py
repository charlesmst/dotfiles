"""Read agent transcripts straight from the files each CLI already writes.

No new state is created here — we only *read* what Claude Code, Cursor CLI
and Codex persist on their own:

* **Claude Code** — JSONL at ``~/.claude/projects/<enc-cwd>/<session>.jsonl``.
  The active session is the newest-modified ``*.jsonl`` in the project dir
  for the agent's cwd. Claude has no "print transcript" command, so we parse
  the JSONL directly.
* **Cursor CLI** — the agent pid maps to ``~/.cursor/sessions/<pid>.json``
  (written by the sessionStart hook) which gives the ``sessionId`` + ``cwd``.
  The conversation lives in ``~/.cursor/chats/*/<sessionId>/store.db``, a
  SQLite blob store: message blobs are plain JSON ``{"role","content"}`` and
  binary index blobs form a DAG headed by ``meta.latestRootBlobId``.
* **Codex CLI** — rollout JSONL under ``~/.codex/sessions/**/rollout-*.jsonl``
  (best-effort; format is tolerated rather than assumed).

Everything degrades gracefully: if no on-disk source is found the caller can
fall back to a live ``tmux capture-pane`` (see ``pane_transcript``).
"""
from __future__ import annotations

import glob
import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime

from . import proc, tmux
from .model import AgentKind, AgentPane

# --- normalized model -------------------------------------------------------


@dataclass
class Turn:
    role: str  # user | assistant | tool | system
    text: str
    ts: float | None = None


@dataclass
class Transcript:
    # Where the turns came from, for the caller to surface honestly.
    source: str  # claude-jsonl | cursor-sqlite | codex-jsonl | pane | none
    path: str | None
    turns: list[Turn] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.turns)

    def last(self, roles: tuple[str, ...] | None = None) -> Turn | None:
        for turn in reversed(self.turns):
            if roles is None or turn.role in roles:
                if turn.text.strip():
                    return turn
        return None

    def last_assistant(self) -> Turn | None:
        return self.last(roles=("assistant",))


def _iso_to_epoch(value) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


# --- text extraction shared across formats ---------------------------------


def _blocks_to_text(content) -> tuple[str, str | None]:
    """Flatten a message ``content`` (str or list of typed parts) to text.

    Returns ``(text, role_override)``. ``role_override`` becomes "tool" when
    the content is purely a tool result, so tool output is labeled distinctly.
    """
    if isinstance(content, str):
        return content, None
    if not isinstance(content, list):
        return str(content), None

    parts: list[str] = []
    only_tool = True
    for block in content:
        if not isinstance(block, dict):
            parts.append(str(block))
            only_tool = False
            continue
        btype = block.get("type")
        if btype in ("text", None) and isinstance(block.get("text"), str):
            parts.append(block["text"])
            only_tool = False
        elif btype == "tool_use":
            name = block.get("name", "tool")
            parts.append(f"[tool: {name}]")
            only_tool = False
        elif btype in ("tool_result", "tool-result"):
            out = block.get("content") or block.get("output") or ""
            if isinstance(out, list):
                out, _ = _blocks_to_text(out)
            parts.append(f"[tool result] {str(out)[:400]}")
        elif btype in ("tool-call", "tool_call"):
            parts.append(f"[tool: {block.get('toolName') or block.get('name', 'tool')}]")
            only_tool = False
        elif btype in ("thinking", "reasoning", "redacted-reasoning"):
            # Reasoning is noise for a transcript summary; drop it.
            continue
        else:
            only_tool = False
    text = "\n".join(p for p in parts if p)
    return text, ("tool" if only_tool and parts else None)


# --- Claude Code ------------------------------------------------------------


def _claude_dir() -> str:
    return os.path.expanduser("~/.claude/projects")


def _encode_cwd(cwd: str) -> str:
    # Claude Code encodes the cwd into the project-dir name by replacing
    # path separators and dots with '-'.
    return re.sub(r"[/.]", "-", cwd)


def _claude_project_dir(cwd: str) -> str | None:
    encoded = os.path.join(_claude_dir(), _encode_cwd(cwd))
    if os.path.isdir(encoded):
        return encoded
    # Fallback: match by the `cwd` field recorded inside each project's
    # transcripts (guards against encoding drift).
    root = _claude_dir()
    if not os.path.isdir(root):
        return None
    for name in os.listdir(root):
        d = os.path.join(root, name)
        jsonls = glob.glob(os.path.join(d, "*.jsonl"))
        if not jsonls:
            continue
        try:
            with open(jsonls[0]) as f:
                first = json.loads(f.readline() or "{}")
            if first.get("cwd") == cwd:
                return d
        except (OSError, json.JSONDecodeError):
            continue
    return None


def _newest_jsonl(project_dir: str) -> str | None:
    jsonls = glob.glob(os.path.join(project_dir, "*.jsonl"))
    if not jsonls:
        return None
    return max(jsonls, key=lambda p: os.path.getmtime(p))


def read_claude(path: str) -> Transcript:
    turns: list[Turn] = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("isSidechain"):
                    continue  # subagent side-transcript, not the main thread
                rtype = rec.get("type")
                if rtype not in ("user", "assistant"):
                    continue
                msg = rec.get("message")
                if not isinstance(msg, dict):
                    continue
                text, role_override = _blocks_to_text(msg.get("content", ""))
                if not text.strip():
                    continue
                role = role_override or rtype
                turns.append(Turn(role=role, text=text, ts=_iso_to_epoch(rec.get("timestamp"))))
    except OSError:
        return Transcript(source="none", path=None)
    return Transcript(source="claude-jsonl", path=path, turns=turns)


def _claude(pids: list[int]) -> Transcript:
    cwd = proc.first_cwd(pids)
    if not cwd:
        return Transcript(source="none", path=None)
    project_dir = _claude_project_dir(cwd)
    if not project_dir:
        return Transcript(source="none", path=None)
    path = _newest_jsonl(project_dir)
    if not path:
        return Transcript(source="none", path=None)
    return read_claude(path)


# --- Cursor CLI -------------------------------------------------------------


def _cursor_session_for(pids: list[int]) -> dict | None:
    sessions_dir = os.path.expanduser("~/.cursor/sessions")
    for pid in pids:
        f = os.path.join(sessions_dir, f"{pid}.json")
        try:
            with open(f) as fh:
                data = json.load(fh)
            if data.get("sessionId"):
                return data
        except (OSError, json.JSONDecodeError):
            continue
    return None


def _cursor_store_db(session_id: str) -> str | None:
    matches = glob.glob(
        os.path.expanduser(f"~/.cursor/chats/*/{session_id}/store.db")
    )
    return matches[0] if matches else None


def _cursor_refs(data: bytes) -> list[str]:
    """Pull 32-byte blob-id references out of a binary index blob.

    Index blobs are protobuf-ish: a length-delimited field (tag ``0x0a``)
    with length ``0x20`` (32) followed by the referenced blob id.
    """
    out: list[str] = []
    i = 0
    n = len(data)
    while i + 34 <= n:
        if data[i] == 0x0A and data[i + 1] == 0x20:
            out.append(data[i + 2 : i + 34].hex())
            i += 34
        else:
            i += 1
    return out


def _cursor_blob_message(data: bytes) -> dict | None:
    if data[:1] != b"{":
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(data.decode("utf-8", "replace"))
    except (json.JSONDecodeError, ValueError):
        return None
    return obj if isinstance(obj, dict) and "role" in obj else None


def _open_ro(path: str) -> sqlite3.Connection:
    try:
        return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
    except sqlite3.OperationalError:
        # WAL recovery may need the sidecar files; immutable skips locking.
        return sqlite3.connect(f"file:{path}?immutable=1", uri=True, timeout=2)


def read_cursor(path: str) -> Transcript:
    try:
        con = _open_ro(path)
    except sqlite3.Error:
        return Transcript(source="none", path=None)
    try:
        con.row_factory = sqlite3.Row
        meta_row = con.execute("select value from meta").fetchone()
        blobs = {r["id"]: r["data"] for r in con.execute("select id, data from blobs")}
    except sqlite3.Error:
        return Transcript(source="none", path=None)
    finally:
        con.close()

    head = None
    if meta_row is not None:
        raw = meta_row[0]
        try:
            raw_bytes = bytes.fromhex(raw) if isinstance(raw, str) else raw
            meta, _ = json.JSONDecoder().raw_decode(raw_bytes.decode("utf-8", "replace"))
            head = meta.get("latestRootBlobId")
        except (ValueError, json.JSONDecodeError):
            head = None

    turns: list[Turn] = []

    def emit(obj: dict) -> None:
        text, role_override = _blocks_to_text(obj.get("content", ""))
        if not text.strip():
            return
        turns.append(Turn(role=role_override or obj.get("role", "assistant"), text=text))

    if head and head in blobs:
        seen: set[str] = set()
        stack = [head]
        # Iterative DFS following index-blob references; message blobs are
        # emitted in the order the DAG chains them (oldest → newest observed).
        while stack:
            bid = stack.pop(0)
            if bid in seen or bid not in blobs:
                continue
            seen.add(bid)
            data = blobs[bid]
            msg = _cursor_blob_message(data)
            if msg is not None:
                emit(msg)
            else:
                stack[:0] = _cursor_refs(data)

    if not turns:
        # DAG walk found nothing usable — salvage every message blob we can,
        # order unknown but content preserved.
        for data in blobs.values():
            msg = _cursor_blob_message(data)
            if msg is not None:
                emit(msg)

    if not turns:
        return Transcript(source="none", path=None)
    return Transcript(source="cursor-sqlite", path=path, turns=turns)


def _cursor(pids: list[int]) -> Transcript:
    session = _cursor_session_for(pids)
    if not session:
        return Transcript(source="none", path=None)
    db = _cursor_store_db(session["sessionId"])
    if not db:
        return Transcript(source="none", path=None)
    return read_cursor(db)


# --- Codex CLI (best-effort) ------------------------------------------------


def _codex_rollouts() -> list[str]:
    base = os.path.expanduser("~/.codex/sessions")
    files = glob.glob(os.path.join(base, "**", "rollout-*.jsonl"), recursive=True)
    files += glob.glob(os.path.join(base, "*.jsonl"))
    return files


def read_codex(path: str) -> Transcript:
    turns: list[Turn] = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # Rollout lines vary; accept anything carrying role + content,
                # or a payload/message envelope around one.
                obj = rec
                for key in ("payload", "message", "msg"):
                    inner = rec.get(key) if isinstance(rec, dict) else None
                    if isinstance(inner, dict) and "role" in inner:
                        obj = inner
                        break
                if not isinstance(obj, dict) or "role" not in obj:
                    continue
                text, role_override = _blocks_to_text(obj.get("content", ""))
                if not text.strip():
                    continue
                turns.append(
                    Turn(
                        role=role_override or obj.get("role", "assistant"),
                        text=text,
                        ts=_iso_to_epoch(rec.get("timestamp") or rec.get("ts")),
                    )
                )
    except OSError:
        return Transcript(source="none", path=None)
    if not turns:
        return Transcript(source="none", path=None)
    return Transcript(source="codex-jsonl", path=path, turns=turns)


def _codex(pids: list[int]) -> Transcript:
    files = _codex_rollouts()
    if not files:
        return Transcript(source="none", path=None)
    cwd = proc.first_cwd(pids)
    candidates = files
    if cwd:
        matched = []
        for path in files:
            try:
                with open(path) as f:
                    head = f.read(4096)
                if f'"{cwd}"' in head or cwd in head:
                    matched.append(path)
            except OSError:
                continue
        if matched:
            candidates = matched
    newest = max(candidates, key=lambda p: os.path.getmtime(p))
    return read_codex(newest)


# --- pane fallback ----------------------------------------------------------


def pane_transcript(pane: AgentPane, lines: int = 200) -> Transcript:
    """Last-resort view: the live pane text, when no file source exists."""
    text = tmux.capture_pane(pane.pane_id, lines=lines, include_history=True)
    if not text.strip():
        return Transcript(source="none", path=None)
    return Transcript(source="pane", path=None, turns=[Turn(role="pane", text=text)])


# --- entry point ------------------------------------------------------------


def resolve(pane: AgentPane, children: dict[int, list[int]]) -> Transcript:
    """Best on-disk transcript for ``pane``; ``source == 'none'`` if unfound.

    Callers that want a guaranteed non-empty result fall back to
    ``pane_transcript`` themselves (the report layer does this).
    """
    pids = proc.subtree_pids(pane.pane_pid, children)
    if pane.kind == AgentKind.CLAUDE:
        return _claude(pids)
    if pane.kind == AgentKind.CURSOR:
        return _cursor(pids)
    if pane.kind == AgentKind.CODEX:
        return _codex(pids)
    return Transcript(source="none", path=None)

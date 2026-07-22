"""Transcript readers parse each agent's own on-disk format."""
import json
import sqlite3

from agent_view import transcript as T


# --- shared block flattening ------------------------------------------------


def test_blocks_to_text_string():
    text, role = T._blocks_to_text("hello")
    assert text == "hello" and role is None


def test_blocks_to_text_mixed_blocks():
    content = [
        {"type": "text", "text": "doing it"},
        {"type": "tool_use", "name": "Bash"},
        {"type": "thinking", "thinking": "secret"},
    ]
    text, role = T._blocks_to_text(content)
    assert "doing it" in text and "[tool: Bash]" in text
    assert "secret" not in text  # reasoning dropped
    assert role is None


def test_blocks_to_text_pure_tool_result_is_tool_role():
    content = [{"type": "tool_result", "content": "exit 0"}]
    text, role = T._blocks_to_text(content)
    assert role == "tool" and "exit 0" in text


# --- Claude JSONL -----------------------------------------------------------


def _write_claude(path):
    rows = [
        {"type": "user", "isSidechain": False, "timestamp": "2026-07-22T10:00:00.000Z",
         "message": {"role": "user", "content": "fix the bug"}},
        {"type": "assistant", "isSidechain": False, "timestamp": "2026-07-22T10:00:05.000Z",
         "message": {"role": "assistant", "content": [{"type": "text", "text": "on it"}]}},
        {"type": "assistant", "isSidechain": True,  # subagent — must be skipped
         "message": {"role": "assistant", "content": [{"type": "text", "text": "SIDE"}]}},
        {"type": "user", "isSidechain": False,
         "message": {"role": "user", "content": [{"type": "tool_result", "content": "ok"}]}},
        {"type": "assistant", "isSidechain": False, "timestamp": "2026-07-22T10:00:09.000Z",
         "message": {"role": "assistant", "content": [{"type": "text", "text": "done fixing"}]}},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def test_read_claude(tmp_path):
    f = tmp_path / "session.jsonl"
    _write_claude(f)
    t = T.read_claude(str(f))
    assert t.source == "claude-jsonl"
    roles = [turn.role for turn in t.turns]
    assert roles == ["user", "assistant", "tool", "assistant"]  # sidechain gone
    assert t.last_assistant().text == "done fixing"
    assert t.turns[0].ts is not None


def test_encode_cwd():
    assert T._encode_cwd("/Users/x/personal/dotfiles") == "-Users-x-personal-dotfiles"
    assert "." not in T._encode_cwd("/tmp/a.b/c")


# --- Cursor SQLite blob-DAG -------------------------------------------------


def _blob_id(n: int) -> str:
    return f"{n:064x}"  # 32-byte id as 64 hex chars


def _make_cursor_db(path, messages):
    """Build a store.db: message blobs + one index blob chaining them, and a
    meta row pointing at the index (value stored hex-encoded, as Cursor does)."""
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE blobs (id TEXT PRIMARY KEY, data BLOB)")
    con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    ids = []
    for i, m in enumerate(messages, start=1):
        bid = _blob_id(i)
        ids.append(bid)
        con.execute("INSERT INTO blobs VALUES (?, ?)", (bid, json.dumps(m).encode()))
    # index blob: 0x0a 0x20 <32 raw bytes> per referenced message, in order
    index = b"".join(b"\x0a\x20" + bytes.fromhex(bid) for bid in ids)
    index_id = _blob_id(999)
    con.execute("INSERT INTO blobs VALUES (?, ?)", (index_id, index))
    meta = json.dumps({"latestRootBlobId": index_id, "name": "T"}).encode().hex()
    con.execute("INSERT INTO meta VALUES ('0', ?)", (meta,))
    con.commit()
    con.close()


def test_read_cursor_orders_via_dag(tmp_path):
    db = tmp_path / "store.db"
    _make_cursor_db(db, [
        {"role": "system", "content": "you are an agent"},
        {"role": "user", "content": "reset main"},
        {"role": "assistant", "content": [{"type": "text", "text": "resetting"}]},
        {"role": "tool", "content": [{"type": "tool-result", "content": "done"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "Fixed."}]},
    ])
    t = T.read_cursor(str(db))
    assert t.source == "cursor-sqlite"
    assert [turn.role for turn in t.turns] == ["system", "user", "assistant", "tool", "assistant"]
    assert t.last_assistant().text == "Fixed."


def test_read_cursor_salvages_without_index(tmp_path):
    """If the DAG head is missing, still recover message content."""
    db = tmp_path / "store.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE blobs (id TEXT PRIMARY KEY, data BLOB)")
    con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO blobs VALUES (?, ?)",
                (_blob_id(1), json.dumps({"role": "assistant", "content": "hi"}).encode()))
    con.execute("INSERT INTO meta VALUES ('0', ?)",
                (json.dumps({"latestRootBlobId": _blob_id(500)}).encode().hex(),))
    con.commit(); con.close()
    t = T.read_cursor(str(db))
    assert t.source == "cursor-sqlite"
    assert t.last_assistant().text == "hi"


def test_cursor_refs_extraction():
    ids = [_blob_id(1), _blob_id(2)]
    data = b"".join(b"\x0a\x20" + bytes.fromhex(b) for b in ids)
    assert T._cursor_refs(data) == ids


# --- Codex rollout JSONL (best-effort) --------------------------------------


def test_read_codex_tolerant(tmp_path):
    f = tmp_path / "rollout-x.jsonl"
    rows = [
        {"type": "session_meta", "cwd": "/repo"},
        {"type": "message", "role": "user", "content": "hi"},
        {"payload": {"role": "assistant", "content": [{"type": "text", "text": "hello back"}]}},
    ]
    f.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    t = T.read_codex(str(f))
    assert t.source == "codex-jsonl"
    assert t.last_assistant().text == "hello back"
    assert [turn.role for turn in t.turns] == ["user", "assistant"]


# --- empty transcript sentinel ----------------------------------------------


def test_transcript_falsey_when_empty():
    assert not T.Transcript(source="none", path=None)
    assert T.Transcript(source="claude-jsonl", path="x", turns=[T.Turn("user", "hi")])

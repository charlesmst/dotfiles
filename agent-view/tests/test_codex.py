"""Codex store reader: the ChatGPT-desktop thread DB + rollout JSONL (real record shapes)."""
import json
import sqlite3
import time
from datetime import datetime, timezone

import pytest

from agent_view import codex, transcript as T
from agent_view.cli import main


def _ts(offset: float = 0.0) -> str:
    return datetime.fromtimestamp(time.time() + offset, timezone.utc).isoformat().replace("+00:00", "Z")


def _msg(role, text, kind="output_text", ts=None):
    return {"timestamp": ts or _ts(), "type": "response_item",
            "payload": {"type": "message", "role": role, "content": [{"type": kind, "text": text}]}}


def _ev(kind, ts=None, **extra):
    return {"timestamp": ts or _ts(), "type": "event_msg", "payload": {"type": kind, **extra}}


def _write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return str(path)


def _store(home, rollout, *, tid="01a1f0c0-4043-7073-a474-c6b85b9a3cee", name="Triage thing",
           originator="Codex Desktop", daybreak=1, cwd="/work/new-chat", updated=None):
    con = sqlite3.connect(home / "state_5.sqlite")
    con.execute("create table threads (id text primary key, rollout_path text, updated_at integer, "
                "cwd text, name text, title text, model text, originator text, "
                "daybreak_enabled boolean, archived integer default 0, git_branch text)")
    con.execute("insert into threads values (?,?,?,?,?,?,?,?,?,0,null)",
                (tid, rollout, int(updated or time.time()), cwd, name, "", "gpt-6-sol", originator, daybreak))
    con.commit()
    con.close()


@pytest.fixture
def home(tmp_path):
    return tmp_path / "codex-home-empty"  # CODEX_HOME, set by conftest


def _finished_rollout(home):
    return _write(home / "sessions/2026/11/18/rollout-x.jsonl", [
        {"timestamp": _ts(-60), "type": "session_meta", "payload": {"cwd": "/work/new-chat"}},
        _ev("task_started", _ts(-50)),
        _msg("developer", "SYSTEM PROMPT DO NOT SHOW", "input_text"),
        _msg("user", "<environment_context>\n  <cwd>/work</cwd>\n</environment_context>", "input_text"),
        _msg("user", "run it end to end", "input_text", _ts(-45)),
        {"timestamp": _ts(-40), "type": "response_item",
         "payload": {"type": "custom_tool_call", "name": "exec", "input": "ls"}},
        {"timestamp": _ts(-39), "type": "response_item",
         "payload": {"type": "custom_tool_call_output", "output": [{"type": "input_text", "text": "a.txt"}]}},
        _msg("assistant", "all done", ts=_ts(-30)),
        _ev("task_complete", _ts(-29), last_agent_message="all done"),
        _ev("thread_settings_applied", _ts(-1)),  # later, non-turn event: must not flip state
    ])


def test_rollout_turns_skip_system_prompt_and_injected_context(home):
    ro = codex.read_rollout(_finished_rollout(home))
    assert [(t.role, t.text) for t in ro.turns] == [
        ("user", "run it end to end"), ("tool", "[tool: exec]"), ("tool", "[tool result] a.txt"),
        ("assistant", "all done")]
    assert ro.state == "done" and ro.last_agent_message == "all done"


def test_started_but_not_completed_is_working_only_while_fresh(home):
    path = _write(home / "r.jsonl", [_ev("task_started", _ts(-5)), _msg("assistant", "thinking...")])
    assert codex.status_of(codex.read_rollout_tail(path)) == "working"
    stale = _write(home / "r2.jsonl", [_ev("task_started", _ts(-3600))])
    assert codex.status_of(codex.read_rollout_tail(stale)) == "idle"  # an abandoned turn is not "working"


def test_threads_read_only_and_listed(home):
    _store(home, _finished_rollout(home))
    before = (home / "state_5.sqlite").read_bytes()
    [s] = codex.discover()
    assert (s.thread.title, s.thread.daybreak, s.status, s.last_message) == ("Triage thing", True, "done", "all done")
    assert (home / "state_5.sqlite").read_bytes() == before  # opened read-only, untouched


def test_cli_session_is_not_double_listed_with_its_pane(home):
    _store(home, _finished_rollout(home), originator="codex_cli_rs")
    assert codex.discover() == []  # a CLI thread already shows as a tmux pane
    assert len(codex.discover(desktop_only=False)) == 1


def test_negative_no_codex_home_means_no_sessions(home, monkeypatch, tmp_path):
    _store(home, _finished_rollout(home))
    assert len(codex.discover()) == 1
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "nowhere"))  # the one thing the reader keys on
    assert codex.discover() == []


def test_old_threads_fall_outside_the_window(home):
    _store(home, _finished_rollout(home), updated=time.time() - 3 * 86400)
    assert codex.discover(hours=24) == []
    assert len(codex.discover(hours=24 * 7)) == 1


def test_resolve_by_prefix_and_title(home):
    _store(home, _finished_rollout(home))
    ss = codex.discover()
    assert codex.resolve(ss, "codex:01a1f0c0").session is ss[0]
    assert codex.resolve(ss, "triage").session is ss[0]
    assert codex.resolve(ss, "codex:ffffffff").session is None


def test_transcript_reads_real_shape_and_legacy_shape(home, tmp_path):
    t = T.read_codex(_finished_rollout(home))
    assert t.source == "codex-jsonl" and t.last_assistant().text == "all done"
    assert all("SYSTEM PROMPT" not in turn.text for turn in t.turns)
    legacy = _write(tmp_path / "old.jsonl", [{"type": "message", "role": "user", "content": "hi"}])
    assert T.read_codex(legacy).turns[0].text == "hi"


def test_pane_finds_its_thread_by_exact_cwd(home):
    _store(home, _finished_rollout(home), cwd="/work/new-chat")
    assert codex.find_thread("/work/new-chat").title == "Triage thing"
    assert codex.find_thread("/work/other") is None  # no cwd match → no guessing at another session


def test_ls_show_transcript_cli(home, capsys, monkeypatch):
    monkeypatch.setattr("agent_view.discovery.discover", lambda *a, **k: [])
    _store(home, _finished_rollout(home))
    assert main(["ls", "--no-remote"]) == 0
    out = capsys.readouterr().out
    assert "codex:01a1f0c0" in out and "done" in out and "daybreak" in out
    assert main(["ls", "--no-remote", "--no-codex"]) == 0
    assert "codex:" not in capsys.readouterr().out
    assert main(["show", "codex:01a1f0c0"]) == 0
    assert "kind     : codex-desktop" in capsys.readouterr().out
    assert main(["transcript", "codex:01a1f0c0", "--json", "--role", "assistant"]) == 0
    assert json.loads(capsys.readouterr().out)["turns"][0]["text"] == "all done"

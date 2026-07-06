import io
import json

import pytest

from agent_view import state
from agent_view.cli import main


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ATTENTION_DIR", str(tmp_path))
    monkeypatch.setenv("TMUX_PANE", "%9")
    # No stdin payload unless a test provides one.
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    return tmp_path


def test_event_pending_marks_the_calling_pane(env):
    assert main(["event", "pending", "--message", "look at me"]) == 0
    assert state.load_pending()["%9"].message == "look at me"


def test_event_pending_reads_claude_stdin_payload(env, monkeypatch):
    payload = json.dumps({"message": "Claude needs permission to run Bash"})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    assert main(["event", "pending"]) == 0
    assert state.load_pending()["%9"].message == "Claude needs permission to run Bash"


def test_event_pending_reads_codex_payload_argument(env):
    payload = json.dumps(
        {"type": "agent-turn-complete", "last-assistant-message": "done: 3 files"}
    )
    assert main(["event", "pending", "--payload", payload]) == 0
    assert state.load_pending()["%9"].message == "done: 3 files"


def test_event_pending_ignores_other_codex_event_types(env):
    payload = json.dumps({"type": "something-else"})
    assert main(["event", "pending", "--payload", payload]) == 0
    assert state.load_pending() == {}


def test_event_pending_explicit_pane_flag(env):
    assert main(["event", "pending", "--pane", "%33"]) == 0
    assert set(state.load_pending()) == {"%33"}


def test_event_clear(env):
    main(["event", "pending"])
    assert main(["event", "clear"]) == 0
    assert state.load_pending() == {}


def test_event_without_pane_is_a_noop(env, monkeypatch):
    monkeypatch.delenv("TMUX_PANE")
    assert main(["event", "pending"]) == 0
    assert state.load_pending() == {}


def test_event_never_raises_even_on_bad_state_dir(env, monkeypatch):
    monkeypatch.setenv("AGENT_ATTENTION_DIR", "/proc/definitely/not/writable")
    assert main(["event", "pending"]) == 0


def test_status_prints_pending_count(env, capsys):
    state.mark_pending("%1")
    state.mark_pending("%2")
    assert main(["status"]) == 0
    assert "● 2" in capsys.readouterr().out


def test_status_prints_nothing_when_quiet(env, capsys):
    assert main(["status"]) == 0
    assert capsys.readouterr().out == ""

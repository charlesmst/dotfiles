"""Opt-in push-notify over an AF_UNIX SOCK_DGRAM socket (agent-view event --notify)."""
import json
import socket

import pytest

from agent_view import notify, state
from agent_view.cli import main


@pytest.fixture
def dgram_socket(tmp_path, monkeypatch):
    """A bound AF_UNIX datagram socket at a short relative path (macOS sun_path
    is capped ~104 bytes; long pytest tmp paths overflow it)."""
    monkeypatch.chdir(tmp_path)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    sock.bind("n.sock")
    sock.settimeout(2)
    yield sock, "n.sock"
    sock.close()


# --- notify.send unit behavior ----------------------------------------------


def test_send_delivers_datagram(dgram_socket):
    sock, path = dgram_socket
    assert notify.send(path, {"hello": "world"}) is True
    data, _ = sock.recvfrom(65536)
    assert json.loads(data) == {"hello": "world"}


def test_send_missing_path_is_silent_noop(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert notify.send("does-not-exist.sock", {"a": 1}) is False  # no raise


def test_send_dead_path_is_silent_noop(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "regular-file").write_text("not a socket")
    assert notify.send("regular-file", {"a": 1}) is False  # no raise


def test_send_empty_path_is_noop():
    assert notify.send("", {"a": 1}) is False
    assert notify.send(None, {"a": 1}) is False


# --- event --notify integration ---------------------------------------------


def test_pending_notify_sends_wellformed_datagram(dgram_socket, tmp_path, monkeypatch):
    sock, path = dgram_socket
    monkeypatch.setenv("AGENT_ATTENTION_DIR", str(tmp_path))
    monkeypatch.setattr("agent_view.tmux.pane_location", lambda pane, timeout=0.3: "staff-support:4.1")

    rc = main(["event", "pending", "--pane", "%7", "--agent", "claude",
               "--event", "stop", "--message", "Turn finished", "--notify", path])
    assert rc == 0

    data, _ = sock.recvfrom(65536)
    msg = json.loads(data)
    assert msg["pane_id"] == "%7"
    assert msg["location"] == "staff-support:4.1"
    assert msg["agent"] == "claude"
    assert msg["event"] == "pending"
    assert msg["message"] == "Turn finished"
    assert isinstance(msg["ts"], (int, float)) and msg["ts"] > 0
    # marker still written as before
    assert state.load_pending()["%7"].event == "stop"


def test_pr_notify_carries_url(dgram_socket, tmp_path, monkeypatch):
    sock, path = dgram_socket
    monkeypatch.setenv("AGENT_ATTENTION_DIR", str(tmp_path))
    monkeypatch.setattr("agent_view.tmux.pane_location", lambda pane, timeout=0.3: None)

    payload = ('{"tool_input":{"command":"gh pr create"},'
               '"tool_response":{"stdout":"https://github.com/o/n/pull/9"}}')
    rc = main(["event", "pr", "--pane", "%7", "--agent", "cursor",
               "--payload", payload, "--notify", path])
    assert rc == 0
    msg = json.loads(sock.recvfrom(65536)[0])
    assert msg["event"] == "pr" and msg["message"] == "https://github.com/o/n/pull/9"
    assert msg["location"] is None  # unresolved is fine


def test_clear_notify_sends(dgram_socket, tmp_path, monkeypatch):
    sock, path = dgram_socket
    monkeypatch.setenv("AGENT_ATTENTION_DIR", str(tmp_path))
    monkeypatch.setattr("agent_view.tmux.pane_location", lambda pane, timeout=0.3: "s:1.1")
    rc = main(["event", "clear", "--pane", "%7", "--notify", path])
    assert rc == 0
    msg = json.loads(sock.recvfrom(65536)[0])
    assert msg["event"] == "clear" and msg["message"] is None


def test_notify_to_missing_socket_is_silent_and_marker_still_written(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGENT_ATTENTION_DIR", str(tmp_path))
    rc = main(["event", "pending", "--pane", "%7", "--agent", "claude",
               "--message", "hi", "--notify", "nobody-home.sock"])
    assert rc == 0  # no raise despite dead socket
    assert state.load_pending()["%7"].message == "hi"  # existing behavior intact


def test_marker_still_written_when_default_socket_unbound(tmp_path, monkeypatch):
    # No --notify and nothing bound at the default path → still a silent no-op.
    monkeypatch.setenv("AGENT_ATTENTION_DIR", str(tmp_path))
    rc = main(["event", "pending", "--pane", "%7", "--message", "hi"])
    assert rc == 0
    assert state.load_pending()["%7"].message == "hi"


def test_always_sends_to_default_socket_without_notify(tmp_path, monkeypatch):
    # No --notify: the push still fires to the well-known default socket.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGENT_ATTENTION_DIR", str(tmp_path))
    monkeypatch.setenv("AGENT_VIEW_NOTIFY_SOCK", "default.sock")  # short (macOS sun_path)
    monkeypatch.setattr("agent_view.tmux.pane_location", lambda pane, timeout=0.3: "s:2.1")
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    sock.bind("default.sock")
    sock.settimeout(2)
    try:
        rc = main(["event", "pending", "--pane", "%7", "--agent", "claude", "--message", "hi"])
        assert rc == 0
        msg = json.loads(sock.recvfrom(65536)[0])
        assert msg["event"] == "pending" and msg["pane_id"] == "%7" and msg["message"] == "hi"
    finally:
        sock.close()


def test_notify_flag_overrides_default(dgram_socket, tmp_path, monkeypatch):
    sock, path = dgram_socket
    monkeypatch.setenv("AGENT_ATTENTION_DIR", str(tmp_path))
    monkeypatch.setenv("AGENT_VIEW_NOTIFY_SOCK", "unused-default.sock")  # not bound
    monkeypatch.setattr("agent_view.tmux.pane_location", lambda pane, timeout=0.3: None)
    rc = main(["event", "clear", "--pane", "%7", "--notify", path])  # explicit wins
    assert rc == 0
    assert json.loads(sock.recvfrom(65536)[0])["event"] == "clear"


def test_listen_bind_roundtrip(tmp_path, monkeypatch):
    from agent_view.cli import _bind_listen_socket

    monkeypatch.chdir(tmp_path)
    sock = _bind_listen_socket("listen.sock")
    sock.settimeout(2)
    try:
        assert notify.send("listen.sock", {"event": "pending"}) is True
        assert json.loads(sock.recvfrom(65536)[0]) == {"event": "pending"}
    finally:
        sock.close()


def test_listen_clears_stale_socket(tmp_path, monkeypatch):
    from agent_view.cli import _bind_listen_socket

    monkeypatch.chdir(tmp_path)
    first = _bind_listen_socket("listen.sock")
    first.close()  # leaves the socket file behind (stale)
    second = _bind_listen_socket("listen.sock")  # must unlink + rebind, not raise
    try:
        assert notify.send("listen.sock", {"ok": 1}) is True
        second.settimeout(2)
        assert json.loads(second.recvfrom(65536)[0]) == {"ok": 1}
    finally:
        second.close()


def test_listen_refuses_non_socket_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "regular").write_text("i am a file")
    rc = main(["listen", "regular"])  # returns 1 fast, never enters the loop
    assert rc == 1
    assert (tmp_path / "regular").exists()  # not deleted


def test_notify_sock_resolution(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ATTENTION_DIR", str(tmp_path))
    monkeypatch.delenv("AGENT_VIEW_NOTIFY_SOCK", raising=False)
    assert state.notify_sock() == str(tmp_path / "events.sock")
    monkeypatch.setenv("AGENT_VIEW_NOTIFY_SOCK", "/tmp/custom.sock")
    assert state.notify_sock() == "/tmp/custom.sock"

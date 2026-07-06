"""Discovery + state against a real tmux server (no mocks)."""
import os
import signal
import time

import pytest

from agent_view import discovery, state, tmux
from agent_view.cli import main
from agent_view.model import AgentKind, AgentState

pytestmark = pytest.mark.integration


def test_discovers_agents_and_ignores_plain_panes(tmux_server):
    claude_pane = tmux_server.start_agent_session("proj-a", "claude")
    codex_pane = tmux_server.start_agent_session("proj-b", "codex")
    tmux_server.start_plain_session("no-agent")

    agents = {a.pane_id: a for a in discovery.discover()}
    assert set(agents) == {claude_pane, codex_pane}
    assert agents[claude_pane].kind == AgentKind.CLAUDE
    assert agents[claude_pane].session == "proj-a"
    assert agents[codex_pane].kind == AgentKind.CODEX


def test_pending_event_via_cli_shows_up_in_discovery(tmux_server, monkeypatch):
    pane = tmux_server.start_agent_session("proj", "claude")
    monkeypatch.setenv("TMUX_PANE", pane)

    assert main(["event", "pending", "--message", "review the diff"]) == 0
    (agent,) = discovery.discover()
    assert agent.state == AgentState.PENDING
    assert agent.pending_message == "review the diff"

    assert main(["event", "clear"]) == 0
    (agent,) = discovery.discover()
    assert agent.state != AgentState.PENDING


def test_pending_marker_pruned_when_agent_dies(tmux_server):
    pane = tmux_server.start_agent_session("proj", "claude")
    state.mark_pending(pane, message="stale marker")

    (agent,) = discovery.discover()
    os.kill(agent.agent_pid, signal.SIGKILL)
    _wait_until(lambda: discovery.discover() == [])
    assert state.load_pending() == {}


def test_kill_session_removes_agent(tmux_server):
    tmux_server.start_agent_session("doomed", "claude")
    tmux.kill_session("doomed")
    _wait_until(lambda: discovery.discover() == [])


def test_capture_pane_returns_content(tmux_server):
    pane = tmux_server.start_agent_session("proj", "claude")
    tmux.run("send-keys", "-t", pane, "hello-from-test", check=False)
    out = tmux.capture_pane(pane, 10)
    assert isinstance(out, str)


def test_pane_not_focused_on_detached_server(tmux_server):
    pane = tmux_server.start_agent_session("proj", "claude")
    assert tmux.pane_is_focused(pane) is False


def _wait_until(cond, timeout: float = 5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return
        time.sleep(0.05)
    raise AssertionError("condition never became true")

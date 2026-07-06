"""End-to-end proof that the shipped hook configs flip panes to pending.

These tests execute the *exact command strings* from the plugin configs in
``plugins/`` (not hand-typed flags), so they fail if the JSON drifts out of
sync with the CLI.

They also document the failure mode Charles observed: an agent that has
finished its turn keeps showing WORKING (recent pane output) until the
Stop hook fires. Sessions started *before* the Claude plugin was installed
never fire it — Claude Code snapshots hooks at session start — so they
show the working icon even when done. Restarting those sessions fixes it.
"""
from __future__ import annotations

import io
import json
import shlex
from pathlib import Path

import pytest

from agent_view import discovery
from agent_view.cli import main
from agent_view.model import AgentState

pytestmark = pytest.mark.integration

PLUGINS = Path(__file__).resolve().parents[2] / "plugins"


def claude_hook_args(event: str) -> list[str]:
    """CLI argv from the real Claude plugin hooks.json for an event."""
    hooks = json.loads((PLUGINS / "claude" / "hooks" / "hooks.json").read_text())
    command = hooks["hooks"][event][0]["hooks"][0]["command"]
    argv = shlex.split(command)
    assert argv[0].endswith("agent-view"), f"unexpected executable: {argv[0]}"
    return argv[1:]


def cursor_hook_args(event: str) -> list[str]:
    hooks = json.loads((PLUGINS / "cursor" / "hooks.json").read_text())
    command = hooks["hooks"][event][0]["command"]
    argv = shlex.split(command)
    assert argv[0].endswith("agent-view"), f"unexpected executable: {argv[0]}"
    return argv[1:]


def test_finished_agent_shows_working_until_stop_hook_fires(
    tmux_server, monkeypatch
):
    """The bug as observed: done agent + no hook event = working icon."""
    pane = tmux_server.start_agent_session("proj", "claude")
    monkeypatch.setenv("TMUX_PANE", pane)

    # Pane had output seconds ago and there is no marker: discovery can
    # only say WORKING — it cannot know the turn is finished without the
    # hook. This is exactly what a pre-plugin session looks like.
    (agent,) = discovery.discover()
    assert agent.state == AgentState.WORKING
    assert agent.pending_message is None

    # Now the turn "finishes": run the real Stop hook command, with a
    # Stop-shaped stdin payload like Claude Code pipes to hooks.
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"hook_event_name": "Stop", "session_id": "s1"})),
    )
    assert main(claude_hook_args("Stop")) == 0

    (agent,) = discovery.discover()
    assert agent.state == AgentState.PENDING
    assert agent.pending_message == "Turn finished — awaiting your input"


def test_notification_hook_surfaces_the_notification_message(
    tmux_server, monkeypatch
):
    pane = tmux_server.start_agent_session("proj", "claude")
    monkeypatch.setenv("TMUX_PANE", pane)
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            json.dumps(
                {
                    "hook_event_name": "Notification",
                    "message": "Claude needs your permission to use Bash",
                }
            )
        ),
    )

    assert main(claude_hook_args("Notification")) == 0

    (agent,) = discovery.discover()
    assert agent.state == AgentState.PENDING
    assert agent.pending_message == "Claude needs your permission to use Bash"


def test_user_prompt_submit_hook_clears_pending(tmux_server, monkeypatch):
    pane = tmux_server.start_agent_session("proj", "claude")
    monkeypatch.setenv("TMUX_PANE", pane)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))

    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"hook_event_name": "Stop", "session_id": "s1"})),
    )
    assert main(claude_hook_args("Stop")) == 0
    (agent,) = discovery.discover()
    assert agent.state == AgentState.PENDING

    # User submits the next prompt → the agent is working again.
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    assert main(claude_hook_args("UserPromptSubmit")) == 0
    (agent,) = discovery.discover()
    assert agent.state == AgentState.WORKING
    assert agent.pending_message is None


def test_cursor_hook_commands_stay_in_sync_with_the_cli(
    tmux_server, monkeypatch
):
    """The cursor hooks.json command strings must parse and behave."""
    pane = tmux_server.start_agent_session("proj", "cursor-agent")
    monkeypatch.setenv("TMUX_PANE", pane)
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))

    assert main(cursor_hook_args("stop")) == 0
    (agent,) = discovery.discover()
    assert agent.state == AgentState.PENDING
    assert agent.pending_message == "Turn finished — awaiting your input"

    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    assert main(cursor_hook_args("beforeSubmitPrompt")) == 0
    (agent,) = discovery.discover()
    assert agent.state != AgentState.PENDING

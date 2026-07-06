"""TUI driven headless via Textual's pilot, against a real tmux server."""
import os
import time

import pytest

from agent_view import state, tmux
from agent_view.model import AgentState
from agent_view.tui.app import AgentTile, AgentViewApp, ConfirmScreen

pytestmark = pytest.mark.integration


async def _settle(pilot, app: AgentViewApp, min_tiles: int = 0):
    """Wait for the refresh worker to populate the grid."""
    deadline = time.time() + 5
    while time.time() < deadline:
        await pilot.pause(0.1)
        if len(app.filtered_agents) >= min_tiles and app._tile_order is not None:
            return
    raise AssertionError("TUI never settled")


async def test_tiles_render_for_each_agent(tmux_server):
    tmux_server.start_agent_session("alpha", "claude")
    tmux_server.start_agent_session("beta", "codex")

    app = AgentViewApp()
    async with app.run_test(size=(140, 40)) as pilot:
        await _settle(pilot, app, min_tiles=2)
        tiles = list(app.query(AgentTile))
        assert len(tiles) == 2
        sessions = {t.agent.session for t in tiles}
        assert sessions == {"alpha", "beta"}


async def test_filter_narrows_tiles(tmux_server):
    tmux_server.start_agent_session("alpha", "claude")
    tmux_server.start_agent_session("beta", "codex")

    app = AgentViewApp()
    async with app.run_test(size=(140, 40)) as pilot:
        await _settle(pilot, app, min_tiles=2)
        await pilot.press("b", "e", "t")
        assert [a.session for a in app.filtered_agents] == ["beta"]
        assert len(list(app.query(AgentTile))) == 1

        await pilot.press("escape")  # clear filter, not quit
        assert app.filter_query == ""
        assert len(app.filtered_agents) == 2
        assert app._exit is False


async def test_pending_agent_sorts_first_and_shows_message(tmux_server):
    tmux_server.start_agent_session("alpha", "claude")
    pending_pane = tmux_server.start_agent_session("beta", "codex")
    state.mark_pending(pending_pane, message="needs review")

    app = AgentViewApp()
    async with app.run_test(size=(140, 40)) as pilot:
        await _settle(pilot, app, min_tiles=2)
        first = app.filtered_agents[0]
        assert first.pane_id == pending_pane
        assert first.state == AgentState.PENDING
        assert first.pending_message == "needs review"


async def test_kill_agent_with_confirm(tmux_server):
    tmux_server.start_agent_session("doomed", "claude")

    app = AgentViewApp()
    async with app.run_test(size=(140, 40)) as pilot:
        await _settle(pilot, app, min_tiles=1)
        pid = app.filtered_agents[0].agent_pid

        await pilot.press("ctrl+d")
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("y")

        deadline = time.time() + 5
        while time.time() < deadline:
            await pilot.pause(0.1)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
        else:
            raise AssertionError("agent process still alive")


async def test_kill_agent_survives_refresh_ticks_while_confirm_open(tmux_server):
    """Regression: leaving the ctrl-d confirm dialog open for >1s crashed.

    The 1s refresh tick kept firing while the modal was up, and
    _rebuild_view queried #grid via App.query_one — which searches the
    *active* screen (the ConfirmScreen), raising NoMatches.
    """
    tmux_server.start_agent_session("alpha", "claude")
    tmux_server.start_agent_session("beta", "codex")

    app = AgentViewApp()
    async with app.run_test(size=(140, 40)) as pilot:
        await _settle(pilot, app, min_tiles=2)
        await pilot.press("right")
        target = app.filtered_agents[1]
        survivor = app.filtered_agents[0]

        await pilot.press("ctrl+d")
        assert isinstance(app.screen, ConfirmScreen)

        # Sit in the dialog across at least one refresh tick.
        await pilot.pause(1.5)
        assert app._exit is False
        assert isinstance(app.screen, ConfirmScreen)

        await pilot.press("y")

        deadline = time.time() + 5
        while time.time() < deadline:
            await pilot.pause(0.1)
            try:
                os.kill(target.agent_pid, 0)
            except ProcessLookupError:
                break
        else:
            raise AssertionError("selected agent still alive")

        os.kill(survivor.agent_pid, 0)  # the other agent must survive
        assert app._exit is False


async def test_kill_confirm_can_be_cancelled(tmux_server):
    tmux_server.start_agent_session("safe", "claude")

    app = AgentViewApp()
    async with app.run_test(size=(140, 40)) as pilot:
        await _settle(pilot, app, min_tiles=1)
        pid = app.filtered_agents[0].agent_pid

        await pilot.press("ctrl+k")
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("n")
        await pilot.pause(0.2)

        os.kill(pid, 0)  # still alive
        assert "safe" in tmux.run("list-sessions", "-F", "#{session_name}").stdout


async def test_kill_session_with_confirm(tmux_server):
    tmux_server.start_agent_session("doomed", "claude")

    app = AgentViewApp()
    async with app.run_test(size=(140, 40)) as pilot:
        await _settle(pilot, app, min_tiles=1)
        await pilot.press("ctrl+k")
        await pilot.press("y")

        deadline = time.time() + 5
        while time.time() < deadline:
            await pilot.pause(0.1)
            sessions = tmux.run("list-sessions", "-F", "#{session_name}").stdout
            if "doomed" not in sessions:
                break
        else:
            raise AssertionError("tmux session still alive")


async def test_jump_selects_pane_and_exits(tmux_server):
    pane = tmux_server.start_agent_session("target", "claude")
    state.mark_pending(pane, message="waiting")

    app = AgentViewApp()
    async with app.run_test(size=(140, 40)) as pilot:
        await _settle(pilot, app, min_tiles=1)
        await pilot.press("enter")
        await pilot.pause(0.2)

    # Jump clears the pending marker and selects the pane's window.
    assert state.load_pending() == {}
    active = tmux.run(
        "display-message", "-p", "-t", "target", "#{pane_id}"
    ).stdout.strip()
    assert active == pane


async def test_navigation_moves_selection(tmux_server):
    tmux_server.start_agent_session("alpha", "claude")
    tmux_server.start_agent_session("beta", "codex")

    app = AgentViewApp()
    async with app.run_test(size=(140, 40)) as pilot:
        await _settle(pilot, app, min_tiles=2)
        assert app.selected == 0
        await pilot.press("right")
        assert app.selected == 1
        await pilot.press("left")
        assert app.selected == 0
        await pilot.press("right", "right", "right")
        assert app.selected == 1  # clamped


async def test_empty_view_shows_message_and_esc_quits(tmux_server):
    app = AgentViewApp()
    async with app.run_test(size=(140, 40)) as pilot:
        await _settle(pilot, app, min_tiles=0)
        assert app.query("#empty")
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert app._exit is True

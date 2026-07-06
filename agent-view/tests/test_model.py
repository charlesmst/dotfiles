import time

from agent_view.model import (
    STALE_AFTER_SECONDS,
    AgentKind,
    AgentPane,
    AgentState,
    format_age,
)
from agent_view.tui.app import grid_dimensions


def make_pane(**overrides) -> AgentPane:
    now = time.time()
    defaults = dict(
        pane_id="%1",
        pane_pid=100,
        agent_pid=200,
        kind=AgentKind.CLAUDE,
        session="proj",
        window_index="1",
        pane_index="0",
        window_name="fix-tests",
        last_activity=now,
        now=now,
    )
    defaults.update(overrides)
    return AgentPane(**defaults)


def test_recent_output_is_working():
    assert make_pane().state == AgentState.WORKING


def test_quiet_pane_is_idle():
    pane = make_pane(last_activity=time.time() - 600)
    assert pane.state == AgentState.IDLE


def test_old_pane_is_stale():
    pane = make_pane(last_activity=time.time() - STALE_AFTER_SECONDS - 1)
    assert pane.state == AgentState.STALE


def test_pending_beats_everything():
    pane = make_pane(
        last_activity=time.time() - STALE_AFTER_SECONDS - 1,
        pending_message="needs you",
    )
    assert pane.state == AgentState.PENDING


def test_sort_order_pending_first_stale_last():
    now = time.time()
    pending = make_pane(pane_id="%1", pending_message="hi")
    working = make_pane(pane_id="%2")
    idle = make_pane(pane_id="%3", last_activity=now - 600)
    stale = make_pane(pane_id="%4", last_activity=now - STALE_AFTER_SECONDS - 1)
    ordered = sorted([stale, idle, working, pending], key=AgentPane.sort_key)
    assert [p.pane_id for p in ordered] == ["%1", "%2", "%3", "%4"]


def test_shell_window_names_hidden_from_title():
    assert make_pane(window_name="zsh").title == ""
    assert make_pane(window_name="fix-tests").title == "fix-tests"


def test_format_age():
    assert format_age(45) == "45s"
    assert format_age(120) == "2m"
    assert format_age(7200) == "2h"
    assert format_age(200000) == "2d"


def test_grid_dimensions():
    assert grid_dimensions(1) == (1, 1)
    assert grid_dimensions(2) == (2, 1)
    assert grid_dimensions(3) == (2, 2)
    assert grid_dimensions(4) == (2, 2)
    assert grid_dimensions(5) == (3, 2)
    assert grid_dimensions(9) == (3, 3)
    assert grid_dimensions(10) == (4, 3)

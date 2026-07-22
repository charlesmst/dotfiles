"""Status classification and id resolution for the AI-friendly layer."""
from agent_view import report
from agent_view.model import AgentKind, AgentPane
from agent_view.report import AgentStatus


def _pane(pane_id="%1", session="repo", win_index="1", pane_index="1",
          window_name="w", idle=0.0, message=None, event=None):
    now = 1_000_000.0
    return AgentPane(
        pane_id=pane_id, pane_pid=1, agent_pid=2, kind=AgentKind.CLAUDE,
        session=session, window_index=win_index, pane_index=pane_index,
        window_name=window_name, last_activity=now - idle,
        pending_message=message, pending_event=event, now=now,
    )


# --- status_of --------------------------------------------------------------


def test_notification_event_is_blocked():
    s, r = report.status_of(_pane(message="Claude needs your permission", event="notification"))
    assert s is AgentStatus.BLOCKED and "permission" in r


def test_stop_event_is_done():
    s, _ = report.status_of(_pane(message="Turn finished", event="stop"))
    assert s is AgentStatus.DONE


def test_turn_complete_event_is_done():
    s, _ = report.status_of(_pane(message="done", event="turn-complete"))
    assert s is AgentStatus.DONE


def test_legacy_marker_permission_text_is_blocked():
    # No event recorded (old shell hook) → classify from the message text.
    s, _ = report.status_of(_pane(message="needs your permission to run Bash", event=None))
    assert s is AgentStatus.BLOCKED


def test_legacy_marker_generic_text_is_done():
    s, _ = report.status_of(_pane(message="needs attention", event=None))
    assert s is AgentStatus.DONE


def test_no_marker_recent_is_working():
    s, r = report.status_of(_pane(idle=1.0))
    assert s is AgentStatus.WORKING and r is None


def test_no_marker_quiet_is_idle():
    s, _ = report.status_of(_pane(idle=120.0))
    assert s is AgentStatus.IDLE


def test_no_marker_ancient_is_stale():
    s, _ = report.status_of(_pane(idle=6 * 3600))
    assert s is AgentStatus.STALE


def test_report_finished_and_blocked_flags():
    rep = report.report_for(_pane(message="x", event="notification"))
    assert rep.blocked and rep.finished
    rep2 = report.report_for(_pane(idle=1.0))
    assert not rep2.blocked and not rep2.finished


def test_to_dict_shape():
    d = report.report_for(_pane(message="Turn finished", event="stop")).to_dict()
    assert d["status"] == "done" and d["kind"] == "claude" and d["blocked"] is False
    assert d["id"] == "repo:1.1"


# --- resolve ----------------------------------------------------------------


def _fleet():
    return [
        _pane(pane_id="%10", session="stocks", win_index="4", window_name="stocks-fix"),
        _pane(pane_id="%11", session="bff", win_index="3", window_name="bff-audit"),
        _pane(pane_id="%12", session="bff", win_index="5", window_name="bff-tests"),
    ]


def test_resolve_exact_pane_id():
    assert report.resolve(_fleet(), "%11").pane.pane_id == "%11"


def test_resolve_exact_location():
    assert report.resolve(_fleet(), "stocks:4.1").pane.pane_id == "%10"


def test_resolve_session_window_prefix():
    assert report.resolve(_fleet(), "stocks:4").pane.pane_id == "%10"


def test_resolve_unique_substring():
    assert report.resolve(_fleet(), "audit").pane.pane_id == "%11"


def test_resolve_ambiguous_returns_candidates():
    res = report.resolve(_fleet(), "bff")
    assert res.pane is None and res.error and len(res.candidates) == 2


def test_resolve_no_match():
    res = report.resolve(_fleet(), "nope")
    assert res.pane is None and "no agent" in res.error

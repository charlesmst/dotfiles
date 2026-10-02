"""A remote session as a normal overview tile: state mapping, ordering, visibility, peek, backoff."""
import re
import time

import pytest

from agent_view import cloudstatus, remote, state
from agent_view.model import AgentKind, AgentState

SID = "session_01AAAAAAAAAAAAAAAAAAAAAA"


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ATTENTION_DIR", str(tmp_path / "state"))
    remote._peeks.clear()
    remote._status_backoff.clear()


def session(status=None, sid=SID, age_s=60, checked=None, **ref_kw):
    now = time.time()
    ref = state.RemoteRef(
        session_id=sid, url=f"https://claude.ai/code/{sid}", title="Read-only diagnostic output",
        created_at=now - age_s, recorded_at=now - age_s, status=status,
        status_checked_at=checked if checked is not None else now - 5,
        status_changed_at=now - age_s, last_event_at=None, **ref_kw,
    )
    return remote.RemoteSession(ref=ref, now=now)


def agent(*a, **k):
    return remote.RemoteAgent.from_session(session(*a, **k))


# --- looks like a normal agent ------------------------------------------------


@pytest.mark.parametrize("status,expected", [
    ("needs-input", AgentState.PENDING),   # yellow, sorts first
    ("running", AgentState.WORKING),       # blue
    ("idle", AgentState.IDLE),
    ("finished", AgentState.IDLE),
    (None, AgentState.IDLE),               # unknown
    ("failed", AgentState.STALE),          # red
])
def test_status_maps_onto_the_local_tile_states(status, expected):
    assert agent(status).state is expected


def test_finished_for_hours_turns_stale_like_a_forgotten_pane():
    assert agent("finished", age_s=6 * 3600).state is AgentState.STALE


def test_identity_is_not_pane_coordinates():
    a = agent("running", pool_name="main")
    assert a.kind is AgentKind.REMOTE and a.is_remote
    assert a.pane_id == f"r-{SID}" and a.pool == "main"
    assert re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", f"tile-{a.pane_id}")  # a valid Textual widget id
    assert a.location == "remote session_01AA…"
    assert a.url == f"https://claude.ai/code/{SID}"


def test_pool_falls_back_to_the_environment_id():
    assert agent("running", environment="ccpool_FAKEFAKEFAKEFAKEFAKEFAKE").pool == "ccpool_FAKEF…"
    assert agent("running").pool is None


def test_needs_input_exposes_a_pending_message():
    a = agent("needs-input", status_detail="Approve the deploy?")
    assert a.pending_message == "Approve the deploy?" and a.pending_since
    assert agent("running").pending_message is None


def test_sorts_with_local_agents_by_the_same_state_order():
    items = [agent("finished", sid="session_01B"), agent("running", sid="session_01C"),
             agent("needs-input", sid="session_01A")]
    items.sort(key=lambda a: a.sort_key())
    assert [a.remote.status for a in items] == ["needs-input", "running", "finished"]


def test_filter_text_answers_to_remote_and_cloud():
    h = agent("running", repo="bitso-web", pool_name="main").filter_haystack()
    assert "remote" in h and "cloud" in h and "bitso-web" in h and "main" in h


def test_tiles_show_active_sessions_always_and_finished_ones_for_a_day():
    sessions = [session("running", sid="session_01A", age_s=3 * 86400),
                session("finished", sid="session_01B", age_s=3600),
                session("finished", sid="session_01C", age_s=3 * 86400),
                session("failed", sid="session_01D", age_s=3 * 86400)]
    for s in sessions:
        s.ref.last_event_at = None
    shown = {a.remote.session_id for a in remote.remote_agents(sessions)}
    assert shown == {"session_01A", "session_01B"}


# --- the peek ------------------------------------------------------------------


def _put_peek(sid, items, version=1):
    remote._peeks[sid] = remote.PeekState(cloudstatus.Peek(items=items), 0.0, 0, version)


def test_peek_ansi_renders_recent_activity_oldest_first_like_a_pane():
    _put_peek(SID, [
        cloudstatus.PeekItem("tool_use", "t", ["Bash: ls"]),
        cloudstatus.PeekItem("tool_result", "t", ["alpha", "hubble"]),
        cloudstatus.PeekItem("assistant", "t", ["Found two apps.", "Reading README."]),
    ])
    text = agent("running").peek_ansi()
    plain = re.sub(r"\x1b\[[0-9;]*m", "", text).splitlines()
    assert plain == ["▸ Bash: ls", "◂ alpha", "  hubble", "✎ Found two apps.", "  Reading README."]


def test_peek_before_the_first_fetch_uses_what_the_record_knows():
    a = remote.RemoteAgent.from_session(session("finished", prompt="Explore the repo", last_message="All done."))
    plain = re.sub(r"\x1b\[[0-9;]*m", "", a.peek_ansi())
    assert "Explore the repo" in plain and "All done." in plain
    assert "waiting for the first update" in re.sub(r"\x1b\[[0-9;]*m", "", agent("running").peek_ansi())


def test_peek_is_capped_to_the_tile_height():
    _put_peek(SID, [cloudstatus.PeekItem("assistant", "t", [f"line {i}" for i in range(50)])])
    assert len(agent("running").peek_ansi(max_lines=10).splitlines()) == 10


# --- refresh cadence and backoff -------------------------------------------------


@pytest.fixture
def fetches(monkeypatch):
    calls = []
    results = []

    def fake(sid, **k):
        calls.append(sid)
        return results.pop(0) if results else cloudstatus.Peek(items=[cloudstatus.PeekItem("assistant", "t", ["hi"])])

    monkeypatch.setattr(remote, "peeks_enabled", lambda: True)
    monkeypatch.setattr(cloudstatus, "fetch_peek", fake)
    fake.calls, fake.results = calls, results
    return fake


def test_active_sessions_are_peeked_on_an_interval_not_every_tick(fetches):
    s = session("running")
    assert remote.refresh_peeks([s]) is True and len(fetches.calls) == 1
    assert remote.refresh_peeks([s]) is False and len(fetches.calls) == 1  # not due yet
    remote._peeks[SID].next_due = time.time() - 1
    remote.refresh_peeks([s])
    assert len(fetches.calls) == 2
    assert 10 <= remote._peeks[SID].next_due - time.time() <= remote.PEEK_SECONDS + 1


def test_finished_sessions_are_peeked_rarely(fetches):
    remote.refresh_peeks([session("finished")])
    assert remote._peeks[SID].next_due - time.time() > 200


def test_errors_back_off_exponentially_and_keep_the_last_good_peek(fetches):
    s = session("running")
    remote.refresh_peeks([s])
    good = remote._peeks[SID].peek
    delays = []
    for _ in range(6):
        fetches.results.append(cloudstatus.Peek(reason="http 500"))
        remote._peeks[SID].next_due = 0
        remote.refresh_peeks([s])
        delays.append(round(remote._peeks[SID].next_due - time.time()))
    assert delays[:4] == [12, 24, 48, 96] and delays[4:] == [120, 120]  # doubles, capped at 120s
    assert remote._peeks[SID].peek is good                               # content survives errors
    remote._peeks[SID].next_due = 0
    remote.refresh_peeks([s])                                            # recovers
    assert remote._peeks[SID].fails == 0


def test_unchanged_content_does_not_bump_the_version(fetches):
    s = session("running")
    remote.refresh_peeks([s])
    v = remote._peeks[SID].version
    remote._peeks[SID].next_due = 0
    assert remote.refresh_peeks([s]) is False
    assert remote._peeks[SID].version == v


def test_peeks_are_off_when_status_lookups_are_disabled(monkeypatch):
    monkeypatch.setenv("AGENT_VIEW_NO_STATUS", "1")
    assert remote.refresh_peeks([session("running")]) is False and remote._peeks == {}


def test_failing_status_lookups_are_not_retried_every_second(monkeypatch):
    calls = []
    monkeypatch.delenv("AGENT_VIEW_NO_STATUS", raising=False)
    monkeypatch.setattr(cloudstatus, "fetch", lambda sid: calls.append(sid) or cloudstatus.CloudStatus(reason="http 500"))
    state.record_remote(state.RemoteRef(session_id=SID, url="https://x"))
    for _ in range(5):
        remote.refresh_status(remote.discover(agents=[], panes=[], scan=False))
    assert len(calls) == 1                      # backoff held the other four ticks
    fails, not_before = remote._status_backoff[SID]
    assert fails == 1 and not_before > time.time() + 10

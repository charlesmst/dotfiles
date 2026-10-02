"""Cloud-session events: one line per attention state, with no TUI open, nothing for removed sessions.

The orchestrator reacts to ~/.local/state/agent-attention/agent-events.log. A recorded session
that needs input / finishes / fails / vanishes / goes quiet must put exactly one line there,
whoever notices first (the monitor, an open overview, `ls`) and however many times it is polled.
"""
import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest

from agent_view import cloudstatus, events, remote, state, tmux

SID = "session_01AAAAAAAAAAAAAAAAAAAAAA"
SID2 = "session_01BBBBBBBBBBBBBBBBBBBBBB"
PANE = "%41"


class Cloud:
    """A fake claude.ai: per-session worker state (or 404), counting every GET."""

    BODIES = {
        "running": {"worker_status": "running"},
        "needs-input": {"worker_status": "requires_action", "post_turn_summary": {"status_detail": "blocked on a token"}},
        "finished": {"worker_status": "idle", "status_bucket": "completed"},
        "failed": {"status": "failed"},
    }

    def __init__(self):
        self.state = {}  # sid -> key of BODIES | "404"
        self.gets = []
        self.on_get = None
        self.last_words = "Which branch do you want me to use?"

    def get(self, path, token):
        self.gets.append(path)
        if self.on_get:
            self.on_get(path)
        sid = path.split("/")[4]
        st = self.state.get(sid, "running")
        if st == "404":
            return 404, b""
        if path.endswith("/events"):
            ev = {"event_type": "assistant", "sequence_num": "2", "created_at": "2026-10-02T10:00:00Z",
                  "payload": {"type": "assistant", "message": {"content": [{"type": "text", "text": self.last_words}]}}}
            return 200, json.dumps({"data": [ev]}).encode()
        return 200, json.dumps({"response_shape": self.BODIES[st]}).encode()


@pytest.fixture
def cloud(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ATTENTION_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("AGENT_VIEW_NO_STATUS", raising=False)
    remote._peeks.clear()
    remote._status_backoff.clear()
    remote._gone_seen.clear()
    c = Cloud()
    monkeypatch.setattr(cloudstatus, "_token", lambda: ("test-token", None))
    monkeypatch.setattr(cloudstatus, "_get", c.get)
    monkeypatch.setattr(remote, "IDLE_EXPIRE_SECONDS", 6 * 3600.0)
    return c


def record(sid=SID, **kw):
    now = time.time()
    fields = dict(
        session_id=sid, url=f"https://claude.ai/code/{sid}", title="PR 5149 conflict resolution",
        pane_id=PANE, location="staff-support:3.2", repo="bitso-web", branch="feat/x",
        created_at=now - 600, recorded_at=now - 600,
    )
    fields.update(kw)
    ref = state.RemoteRef(**fields)
    assert state.record_remote(ref)
    return ref


def sessions():
    return remote.discover(agents=[], panes=[], scan=False)


def poll(force=True):
    return remote.refresh_status(sessions(), force=force)


def lines():
    path = events.log_path()
    if not os.path.exists(path):
        return []
    return [json.loads(l) for l in open(path) if l.strip()]


def names():
    return [e["event"] for e in lines()]


# --- one event per state, however often it is polled ------------------------------------------


@pytest.mark.parametrize("cloud_state,event", [
    ("needs-input", "remote-needs-input"), ("finished", "remote-finished"), ("failed", "remote-failed"),
])
def test_each_attention_state_is_written_once_however_many_polls(cloud, cloud_state, event):
    record()
    cloud.state[SID] = cloud_state
    for _ in range(5):
        poll()
    assert names() == [event]
    (ev,) = lines()
    assert (ev["session_id"], ev["title"], ev["repo"]) == (SID, "PR 5149 conflict resolution", "bitso-web")
    assert ev["url"] == f"https://claude.ai/code/{SID}" and ev["status"] == cloud_state
    assert ev["last_message"] == cloud.last_words and cloud.last_words in ev["message"]


def test_running_and_idle_are_not_announced(cloud):
    record()
    cloud.state[SID] = "running"
    poll()
    poll()
    assert names() == []


def test_needing_input_again_after_running_is_a_new_event(cloud):
    record()
    for st in ["needs-input", "needs-input", "running", "needs-input", "needs-input"]:
        cloud.state[SID] = st
        poll()
    assert names() == ["remote-needs-input", "remote-needs-input"]


def test_two_pollers_at_once_write_one_line(cloud):
    """The monitor and an open overview race on the same state: the record's lock admits one."""
    record()
    cloud.state[SID] = "needs-input"
    claims = []
    barrier = threading.Barrier(8)

    def go():
        barrier.wait()
        claims.append(state.claim_notification(SID, "needs-input"))

    ts = [threading.Thread(target=go) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sum(c is not None for c in claims) == 1


def test_a_second_process_view_of_the_same_state_does_not_repeat_it(cloud):
    record()
    cloud.state[SID] = "finished"
    stale_view = sessions()  # what a second process loaded before the first announced
    poll()
    remote.refresh_status(stale_view, force=True)  # …then polls with its stale copy
    assert names() == ["remote-finished"]


def test_the_status_is_still_announced_when_the_poll_that_saw_it_did_not_write(cloud, monkeypatch):
    """A crash (or a failed append) between recording a state and announcing it must not lose it."""
    record()
    cloud.state[SID] = "failed"
    real_emit = events.emit
    calls = []

    def flaky(ev):
        calls.append(ev["event"])
        return False if len(calls) == 1 else real_emit(ev)

    monkeypatch.setattr(events, "emit", flaky)
    poll()
    assert names() == [] and state.load_remote()[SID].notified is None  # claim given back
    poll(force=False)  # the next pass (even a not-due one) retries from the cached state
    assert names() == ["remote-failed"]
    poll()
    assert names() == ["remote-failed"]


# --- removed sessions emit nothing ------------------------------------------------------------


def test_a_removed_session_emits_nothing(cloud):
    record()
    cloud.state[SID] = "needs-input"
    state.dismiss_remote(SID)
    poll()
    assert names() == [] and cloud.gets == []  # not even looked up


def test_removing_while_the_lookup_is_in_flight_emits_nothing(cloud):
    record()
    cloud.state[SID] = "needs-input"
    cloud.on_get = lambda path: state.dismiss_remote(SID)
    poll()
    assert names() == []
    assert state.load_remote()[SID].dismissed and state.load_remote()[SID].notified is None


def test_a_claim_on_a_removed_session_is_refused(cloud):
    record()
    state.dismiss_remote(SID)
    assert state.claim_notification(SID, "finished") is None


# --- gone (killed / deleted / expired on the server) -----------------------------------------


def test_a_session_claude_ai_no_longer_knows_is_announced_once_after_two_404s(cloud):
    record(status="running", status_checked_at=time.time() - 60, status_changed_at=time.time() - 60)
    cloud.state[SID] = "404"
    poll()
    assert names() == []  # one 404 is not a verdict
    poll()
    assert names() == ["remote-gone"]
    for _ in range(3):
        poll()
    assert names() == ["remote-gone"]
    assert state.load_remote()[SID].status == "gone"
    assert "no longer on claude.ai" in lines()[0]["message"]


def test_a_404_for_a_session_never_seen_is_not_a_kill(cloud):
    """No status yet (e.g. a credential for another account) → 404 proves nothing."""
    record()
    cloud.state[SID] = "404"
    for _ in range(4):
        poll()
    assert names() == []


def test_one_stray_404_between_good_answers_resets_the_count(cloud):
    record(status="running", status_checked_at=time.time() - 60, status_changed_at=time.time() - 60)
    for st in ["404", "running", "404", "running"]:
        cloud.state[SID] = st
        poll()
    assert names() == []


# --- idle-expired -------------------------------------------------------------------------


def iso(ago):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - ago))


def test_a_session_quiet_for_hours_is_announced_once(cloud):
    record(status="idle", status_checked_at=time.time() - 60, status_changed_at=time.time() - 8 * 3600,
           last_event_at=iso(7 * 3600))
    cloud.state[SID] = "running"  # still "running" per the cloud, but nothing has happened for 7h
    poll()
    poll()
    assert names() == ["remote-idle-expired"]
    assert "no activity for 6h" in lines()[0]["message"]


def test_activity_resets_idle_expiry_and_recent_or_finished_sessions_are_left_alone(cloud):
    record(status="idle", status_checked_at=time.time() - 60, status_changed_at=time.time() - 3600,
           last_event_at=iso(600))
    record(SID2, status="finished", status_checked_at=time.time() - 60, status_changed_at=time.time() - 9 * 3600,
           last_event_at=iso(9 * 3600), notified="finished")
    cloud.state[SID] = cloud.state[SID2] = "finished"
    poll()
    assert "remote-idle-expired" not in names()
    ref = state.load_remote()[SID]
    ref.notified = "idle-expired"
    state.update_remote_status(SID, "idle", last_event_at=iso(60))  # woke up…
    assert state.load_remote()[SID].notified is None  # …so a later quiet spell can be announced again


# --- records from before announcements were tracked --------------------------------------------


def test_a_session_waiting_for_input_with_no_announcement_on_file_is_announced_without_a_lookup(cloud):
    record(status="needs-input", status_detail="blocked", status_checked_at=time.time(),
           status_changed_at=time.time() - 3 * 86400, last_message="Which one?")
    remote.refresh_status(sessions())  # not due: only the cached state is looked at
    remote.refresh_status(sessions())
    assert names() == ["remote-needs-input"] and cloud.gets == []


def test_an_old_terminal_record_is_marked_not_re_announced(cloud):
    record(status="finished", status_checked_at=time.time(), status_changed_at=time.time() - 3 * 86400)
    record(SID2, status="finished", status_checked_at=time.time(), status_changed_at=time.time() - 600)
    remote.refresh_status(sessions())
    assert [e["session_id"] for e in lines()] == [SID2]  # the recent one is news, the 3-day-old one is history
    assert state.load_remote()[SID].notified == "finished"


# --- the line the orchestrator's filter sees ----------------------------------------------------

FILTER = Path(os.environ.get(
    "AGENT_FLEET_FILTER",
    "/Users/charlesstein/projects/staff-support/.claude/skills/agent-fleet/scripts/event-filter.pl",
))


def test_events_do_not_carry_the_launch_pane_as_pane_id(cloud):
    """event-filter.pl job 5 drops any line whose "pane_id" is the orchestrator's own pane."""
    record()
    cloud.state[SID] = "needs-input"
    poll()
    (ev,) = lines()
    assert ev["pane_id"] is None and ev["launch_pane_id"] == PANE and ev["launch_location"] == "staff-support:3.2"
    raw = open(events.log_path()).read()
    assert not re.search(r'"pane_id"\s*:\s*"[^"]+"', raw)  # job 5's own pattern finds nothing to match
    assert events.remote_created(state.RemoteRef(session_id=SID, url="u", pane_id=PANE))["pane_id"] is None


@pytest.mark.skipif(not FILTER.exists() or not shutil.which("perl"), reason="staff-support event-filter.pl not present")
def test_the_orchestrators_filter_keeps_these_lines_even_when_it_runs_in_the_launch_pane(cloud):
    record()
    cloud.state[SID] = "needs-input"
    poll()
    log = open(events.log_path()).read()
    kept = subprocess.run(["perl", str(FILTER)], input=log, capture_output=True, text=True,
                          env={**os.environ, "TMUX_PANE": PANE}).stdout  # the orchestrator launched it
    got = [json.loads(l)["event"] for l in kept.splitlines()]
    assert got == ["remote-needs-input"]


# --- the monitor: one background poller, no TUI -------------------------------------------------


def test_the_monitor_announces_with_no_tui_open(cloud):
    record()
    cloud.state[SID] = "needs-input"
    assert remote.monitor(once=True, scan=False) == 0
    assert names() == ["remote-needs-input"]
    remote.monitor(once=True, scan=False)
    assert names() == ["remote-needs-input"]


def test_a_session_parked_at_needs_input_is_polled_slowly(cloud):
    record(status="needs-input", status_checked_at=time.time() - 30, status_changed_at=time.time() - 3600,
           notified="needs-input")
    poll(force=False)
    assert cloud.gets == []  # 30s since the last look: parked sessions wait for 60s
    state.update_remote_status(SID, "needs-input")
    ref = state.load_remote()[SID]
    ref.status_checked_at = time.time() - 61
    open(os.path.join(state.remote_dir(), SID), "w").write(json.dumps(ref.__dict__))
    poll(force=False)
    assert cloud.gets  # past 60s it looks again


def test_the_monitor_watches_until_the_session_finishes_then_goes_quiet(cloud):
    record()
    clock = {"t": 1000.0}
    script = iter(["running", "running", "needs-input", "needs-input", "finished", "finished", "finished", "finished"])

    def sleep(s):
        clock["t"] += s
        st = next(script, "finished")
        cloud.state[SID] = st
        # the persisted poll time is wall-clock based: make the next pass due
        ref = state.load_remote()[SID]
        ref.status_checked_at = 0.0
        open(os.path.join(state.remote_dir(), SID), "w").write(json.dumps(ref.__dict__))

    cloud.state[SID] = "running"
    assert remote.monitor(interval=15, idle_exit=40, scan=False, clock=lambda: clock["t"], sleep=sleep) == 0
    assert names() == ["remote-needs-input", "remote-finished"]
    assert clock["t"] < 1000 + 15 * 20  # and it stopped by itself once the session was done and announced


def test_the_monitor_backs_off_while_everything_is_parked(cloud):
    record(status="needs-input", status_checked_at=time.time(), status_changed_at=time.time(), notified="needs-input")
    waits = []

    class Stop(Exception):
        pass

    def sleep(s):
        waits.append(s)
        if len(waits) == 2:
            raise Stop  # a parked session keeps the monitor alive by design; stop the test's loop

    cloud.state[SID] = "needs-input"
    with pytest.raises(Stop):
        remote.monitor(interval=15, idle_exit=100, scan=False, sleep=sleep)
    assert waits == [60.0, 60.0]  # not every 15s while nothing is moving
    assert remote.monitor_pid() is None  # and the lock was released on the way out


def test_only_one_monitor_runs(cloud, tmp_path):
    record()
    import fcntl

    os.makedirs(state.base_dir(), exist_ok=True)
    fd = os.open(remote._monitor_lock_path(), os.O_RDWR | os.O_CREAT)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.pwrite(fd, b"4242", 0)
    try:
        assert remote.monitor_pid() == 4242
        cloud.state[SID] = "needs-input"
        assert remote.monitor(once=True, scan=False) == 0  # a second one steps aside…
        assert names() == [] and cloud.gets == []  # …without polling anything
    finally:
        os.close(fd)
    assert remote.monitor_pid() is None
    assert remote.monitor(once=True, scan=False) == 0
    assert names() == ["remote-needs-input"]
    assert remote.monitor_pid() is None  # the lock is released on exit


def test_the_monitor_and_the_overview_loader_announce_a_state_once_between_them(cloud, monkeypatch):
    record()
    cloud.state[SID] = "needs-input"
    monkeypatch.setattr(tmux, "list_panes", lambda: [])
    loader = remote.Loader(tick=0)
    monkeypatch.setattr(remote, "ensure_monitor", lambda *a, **k: False)
    loader.run([], [], lambda *a: None)
    remote.monitor(once=True, scan=False)
    loader.run([], [], lambda *a: None)
    assert names() == ["remote-needs-input"]


def test_the_monitor_does_not_ask_again_while_the_overview_has_just_asked(cloud):
    """Both go through the same persisted due time, so an open overview and the monitor share polls."""
    record()
    cloud.state[SID] = "running"
    poll(force=True)
    before = len(cloud.gets)
    remote.monitor(once=True, scan=False)
    assert len(cloud.gets) == before


# --- starting it ---------------------------------------------------------------------------------


@pytest.fixture
def spawned(monkeypatch, cloud):
    monkeypatch.delenv("AGENT_VIEW_NO_WATCH", raising=False)
    monkeypatch.setattr(remote, "_monitor_checked", 0.0)
    calls = []
    monkeypatch.setattr(remote.subprocess, "Popen", lambda cmd, **k: calls.append((cmd, k)))
    return calls


def test_recording_a_session_starts_one_monitor_not_a_watcher_per_session(spawned, cloud):
    now = time.time()
    for sid in (SID, SID2):
        assert remote.register(state.RemoteRef(session_id=sid, url=f"https://claude.ai/code/{sid}", created_at=now))
    assert len(spawned) == 1  # the second record found it already being started (checked once a minute)
    cmd, kw = spawned[0]
    assert cmd[-4:] == ["-m", "agent_view.cli", "remote", "monitor"]
    assert kw["start_new_session"] is True and "watch" not in cmd


def test_it_is_not_started_when_one_runs_or_when_opted_out(spawned, cloud, monkeypatch):
    import fcntl

    os.makedirs(state.base_dir(), exist_ok=True)
    fd = os.open(remote._monitor_lock_path(), os.O_RDWR | os.O_CREAT)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        assert remote.ensure_monitor(force=True) is False
    finally:
        os.close(fd)
    monkeypatch.setenv("AGENT_VIEW_NO_WATCH", "1")
    assert remote.ensure_monitor(force=True) is False
    monkeypatch.delenv("AGENT_VIEW_NO_WATCH")
    monkeypatch.setenv("AGENT_VIEW_NO_STATUS", "1")
    assert remote.ensure_monitor(force=True) is False
    assert spawned == []


def test_the_overview_starts_the_monitor_only_for_a_session_still_going(spawned, cloud, monkeypatch):
    started = []
    monkeypatch.setattr(remote, "ensure_monitor", lambda *a, **k: started.append(1))
    record(status="finished", status_changed_at=time.time(), status_checked_at=time.time(), notified="finished")
    remote.Loader(tick=0).run([], [], lambda *a: None)
    assert started == []
    record(SID2, status="running", status_checked_at=time.time())
    remote.Loader(tick=0).run([], [], lambda *a: None)
    assert started == [1]


def test_monitor_status_and_stop_commands(cloud, capsys):
    from agent_view.cli import main

    assert main(["remote", "monitor", "--status"]) == 0
    assert "not running" in capsys.readouterr().out
    assert main(["remote", "monitor", "--stop"]) == 0
    assert "not running" in capsys.readouterr().out


def test_the_real_monitor_entrypoint_announces_once_across_separate_processes(tmp_path, monkeypatch):
    """`agent-view remote monitor --once` as its own process against a local stand-in for claude.ai."""
    import sys
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path.endswith("/events"):
                body = json.dumps({"data": [{"event_type": "assistant", "sequence_num": "1", "payload": {
                    "type": "assistant", "message": {"content": [{"type": "text", "text": "Need a decision."}]}}}]})
            else:
                body = json.dumps({"response_shape": {"worker_status": "requires_action"}})
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body.encode())

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = tmp_path / "state"
    monkeypatch.setenv("AGENT_ATTENTION_DIR", str(base))
    record()
    env = {**os.environ, "AGENT_ATTENTION_DIR": str(base), "AGENT_VIEW_CLAUDE_API": f"http://127.0.0.1:{srv.server_port}",
           "CLAUDE_CODE_OAUTH_TOKEN": "test-token", "AGENT_VIEW_NO_WATCH": "1"}
    env.pop("AGENT_VIEW_NO_STATUS", None)
    try:
        for _ in range(3):
            out = subprocess.run([sys.executable, "-m", "agent_view.cli", "remote", "monitor", "--once", "--no-scan"],
                                 capture_output=True, text=True, env=env, timeout=60)
            assert out.returncode == 0, out.stderr
    finally:
        srv.shutdown()
    (ev,) = lines()
    assert ev["event"] == "remote-needs-input" and ev["session_id"] == SID and ev["last_message"] == "Need a decision."
    assert "test-token" not in open(events.log_path()).read()


def test_a_gone_session_leaves_the_tmux_count_and_reads_stale_on_its_tile(cloud):
    from agent_view.model import AgentState

    record(status="gone", status_checked_at=time.time(), status_changed_at=time.time(), notified="gone")
    assert state.count_remote() == 0
    (s,) = sessions()
    assert remote.RemoteAgent.from_session(s).state is AgentState.STALE
    assert remote.status_of(s)[0] == "gone"

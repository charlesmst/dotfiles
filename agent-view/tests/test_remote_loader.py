"""remote.Loader: the lazy, throttled background pass the TUI runs for remote sessions.

The contract (Charles: "lazy load the remotes, it is impacting performance too much"):
a pass never stacks, is spaced out, scans/prunes at a slower cadence than it ticks, does no
network when nothing is due, reuses the caller's tmux listing, and publishes in stages so a
slow claude.ai call can't hold back what is already known.
"""
import subprocess
import sys
import threading
import time

import pytest

from agent_view import cloudstatus, remote, state, tmux

SID = "session_01AAAAAAAAAAAAAAAAAAAAAA"


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ATTENTION_DIR", str(tmp_path / "state"))
    remote._peeks.clear()
    remote._status_backoff.clear()
    # a pass must work from the listing it is given: any tmux call of its own is a bug
    monkeypatch.setattr(tmux, "list_panes", lambda: pytest.fail("the loader listed tmux panes itself"))
    monkeypatch.setattr(tmux, "capture_scrollback", lambda *a, **k: "")


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


def record(sid=SID):
    now = time.time()
    state.record_remote(state.RemoteRef(
        session_id=sid, url=f"https://claude.ai/code/{sid}", created_at=now - 60, recorded_at=now - 60,
    ))


def make(tick=3.0):
    clock = Clock()
    return remote.Loader(tick=tick, clock=clock), clock


def spy(monkeypatch, name, ret=0):
    calls = []
    monkeypatch.setattr(remote, name, lambda *a, **k: calls.append(a) or ret)
    return calls


def test_a_pass_is_spaced_out_by_the_tick():
    loader, clock = make(tick=3.0)
    assert loader.ready() and not loader.settled
    assert loader.run([], [], lambda *a: None) is True
    assert loader.settled and not loader.ready()  # just ran
    clock.t += 2.9
    assert not loader.ready()
    clock.t += 0.2
    assert loader.ready()


def test_passes_never_stack(monkeypatch):
    record()
    loader, _ = make()
    entered, release = threading.Event(), threading.Event()

    def slow_peeks(sessions, force=False):
        entered.set()
        release.wait(5)
        return False

    monkeypatch.setattr(remote, "refresh_peeks", slow_peeks)
    t = threading.Thread(target=loader.run, args=([], [], lambda *a: None))
    t.start()
    assert entered.wait(5)
    assert not loader.ready()  # busy: the UI tick won't even start a worker
    published = []
    assert loader.run([], [], lambda *a: published.append(a)) is False  # …and a direct call does nothing
    assert published == []
    release.set()
    t.join(5)
    assert loader.settled


def test_scan_and_prune_run_less_often_than_passes(monkeypatch):
    scans = spy(monkeypatch, "scan_panes")
    prunes = []
    monkeypatch.setattr(state, "prune_remote", lambda *a: prunes.append(a))
    loader, clock = make(tick=1.0)
    for _ in range(4):  # four passes, 1s apart: inside SCAN_SECONDS
        loader.run([], [], lambda *a: None)
        clock.t += 1.0
    assert len(scans) == 1 and len(prunes) == 1
    clock.t += remote.SCAN_SECONDS
    loader.run([], [], lambda *a: None)
    assert len(scans) == 2 and len(prunes) == 1  # scanning again does not mean pruning again
    clock.t += remote.PRUNE_SECONDS
    loader.run([], [], lambda *a: None)
    assert len(prunes) == 2


def test_the_scan_uses_the_listing_it_was_given(monkeypatch):
    seen = []
    monkeypatch.setattr(remote, "scan_panes", lambda panes, ids: seen.append((panes, ids)) or 0)
    panes = [{"pane_id": "%1"}]

    class A:
        pane_id = "%9"

    loader, _ = make()
    loader.run([A()], panes, lambda *a: None)
    assert seen == [(panes, {"%9"})]


def test_publishes_in_stages_and_the_last_one_is_settled(monkeypatch):
    record()
    loader, _ = make()
    out = []
    loader.run([], [], lambda sessions, settled: out.append((len(sessions), settled)))
    assert out[-1] == (1, True)
    assert [s for _, s in out].count(True) == 1 and len(out) >= 2  # peeks and status land separately


def test_published_sessions_are_snapshots(monkeypatch):
    record()
    loader, _ = make()
    got = []

    def late_status(sessions, force=False):
        time.sleep(0.05)
        for s in sessions:
            s.ref = state.RemoteRef(session_id=s.session_id, url=s.ref.url, status="finished")
        return []

    monkeypatch.setattr(remote, "refresh_peeks", lambda *a, **k: False)
    monkeypatch.setattr(remote, "refresh_status", late_status)
    loader.run([], [], lambda sessions, settled: got.append((sessions, settled)))
    first, last = got[0][0][0], got[-1][0][0]
    assert first.ref.status is None  # what the UI was handed earlier isn't mutated under it
    assert last.ref.status == "finished"


def test_a_slow_status_lookup_does_not_hold_back_the_peeks(monkeypatch):
    record()
    loader, _ = make()
    release = threading.Event()
    monkeypatch.setattr(remote, "refresh_status", lambda s, force=False: release.wait(5) and [])
    monkeypatch.setattr(remote, "refresh_peeks", lambda s, force=False: True)
    first_publish = threading.Event()
    stages = []

    def publish(sessions, settled):
        stages.append(settled)
        first_publish.set()

    t = threading.Thread(target=loader.run, args=([], [], publish))
    t.start()
    assert first_publish.wait(5), "peeks were not published while the status GET was still pending"
    assert stages == [False] and not loader.ready()
    release.set()
    t.join(5)
    assert stages[-1] is True


def test_a_failing_pass_still_settles_and_frees_the_loader(monkeypatch):
    record()
    loader, clock = make()
    monkeypatch.setattr(remote, "refresh_peeks", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    out = []
    assert loader.run([], [], lambda s, settled: out.append(settled)) is True
    assert out[-1] is True and loader.settled
    clock.t += 10
    assert loader.ready()


def test_nothing_due_means_no_network_and_no_token_lookup(monkeypatch):
    """After the first pass, passes between due times only read files."""
    record()
    monkeypatch.delenv("AGENT_VIEW_NO_STATUS", raising=False)
    gets, tokens = [], []
    monkeypatch.setattr(cloudstatus, "_token", lambda: tokens.append(1) or ("tok", None))
    monkeypatch.setattr(cloudstatus, "_get", lambda path, token: gets.append(path) or (500, b""))
    loader, clock = make(tick=3.0)
    loader.run([], [], lambda *a: None)
    first = len(gets)
    assert first >= 1  # it did look the first time (status + events)
    for _ in range(3):  # 3s ticks, well inside the 15s/12s polls and the failure backoff
        clock.t += 3.0
        loader.run([], [], lambda *a: None)
    assert len(gets) == first and len(tokens) == first


def test_successful_lookups_are_not_repeated_until_their_poll_interval(monkeypatch):
    record()
    monkeypatch.delenv("AGENT_VIEW_NO_STATUS", raising=False)
    monkeypatch.setattr(cloudstatus, "_token", lambda: ("tok", None))
    gets = []

    def get(path, token):
        gets.append(path)
        if path.endswith("/events"):
            return 200, b'{"data": []}'
        return 200, b'{"response_shape": {"worker_status": "running"}}'

    monkeypatch.setattr(cloudstatus, "_get", get)
    loader, clock = make(tick=3.0)
    loader.run([], [], lambda *a: None)
    first = len(gets)
    assert first == 2 and state.load_remote()[SID].status == "running"
    t0 = time.time()
    monkeypatch.setattr(time, "time", lambda: t0 + 5)  # three more passes inside 15s (status) / 12s (peek)
    for _ in range(3):
        clock.t += 3.0
        loader.run([], [], lambda *a: None)
    assert len(gets) == first
    monkeypatch.setattr(time, "time", lambda: t0 + 20)  # past both intervals: now it looks again
    clock.t += 3.0
    loader.run([], [], lambda *a: None)
    assert len(gets) == first + 2


def test_no_session_means_no_threads_or_lookups(monkeypatch):
    status, peeks = spy(monkeypatch, "refresh_status"), spy(monkeypatch, "refresh_peeks")
    loader, _ = make()
    out = []
    loader.run([], [], lambda s, settled: out.append((s, settled)))
    assert status == [] and peeks == [] and out == [([], True)]


# --- startup: the network stack is not paid for until a lookup happens --------------------


@pytest.mark.parametrize("module", ["agent_view.cloudstatus", "agent_view.remote"])
def test_importing_remote_support_does_not_load_urllib_or_ssl(module):
    code = f"import {module}, sys; bad = [m for m in ('urllib.request', 'ssl', 'http.client') if m in sys.modules]; sys.exit(','.join(bad) or 0)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 0, f"eagerly imported: {out.stderr or out.stdout}"

"""Remote (cloud) sessions against a real tmux server and the real CLI.

A pane replays what `claude --environment ccpool_…` leaves behind — the long,
soft-wrapped launch line plus the four-line "Created cloud session" block —
and then sits at a shell prompt, exactly like the delegator pane whose
``claude`` exited. The tmux server is private; nothing touches the user's.
"""
import json
import os
import shutil
import threading

import pytest

from agent_view import cloudstatus, remote, state, tmux
from agent_view.cli import main
from agent_view.tui.app import AgentTile, AgentViewApp, ConfirmScreen, RemoteReady

pytestmark = pytest.mark.integration

async def _settle(pilot, app, min_tiles: int = 0):
    """Wait until one refresh cycle has rendered enough agents."""
    import time

    deadline = time.time() + 10
    while time.time() < deadline:
        await pilot.pause(0.1)
        if app.snapshots_applied > 0 and len(app.filtered_agents) >= min_tiles:
            return
    raise AssertionError("TUI never settled")


SID = "session_01BBBBBBBBBBBBBBBBBBBBBB"
URL = f"https://claude.ai/code/{SID}"
KEY = "demo-repo-11-1700000000"

SCROLLBACK = (
    "$ claude --permission-mode auto --model claude-sonnet-5-5 --effort high "
    "--environment ccpool_FAKEFAKEFAKEFAKEFAKEFAKE --settings '{\"x\":true}' "
    f"\"$(cat '/home/u/.local/share/local-tmux-agent-delegator/sessions/prompts/{KEY}.txt')\"\n"
    "Created cloud session: Environment diagnostics check\n"
    f"Session ID: {SID}\n"
    f"View: {URL}?from=cli&m=0\n"
    f"Resume with: claude --teleport {SID}\n"
)


@pytest.fixture
def launched(tmux_server, tmp_path, monkeypatch):
    """A shell pane that replays a remote launch; a delegator sidecar for it."""
    d = tmp_path / "delegator"
    d.mkdir()
    monkeypatch.setenv("TMUX_AGENT_STATE_DIR", str(d))
    (d / f"{KEY}.json").write_text(json.dumps({
        "session_key": KEY, "repo": "bitso-web", "worktree": "runner-env-probe",
        "tmux_target": "%999", "project_dir": str(tmp_path),
        "started_at": "2026-10-01T15:35:22.681730+00:00",
        "prompt": "Read-only check, no changes: print hostname, pwd.",
    }))
    script = tmp_path / "scrollback.txt"
    script.write_text(SCROLLBACK)
    remote._scanned.clear()
    # width 60 forces the launch line (and the sidecar path in it) to soft-wrap
    proc = tmux.run(
        "new-session", "-d", "-s", "bitso-web", "-x", "60", "-y", "30", "-P", "-F", "#{pane_id}",
        f"sh -c 'cat {script}; exec sh'", check=True,
    )
    pane = proc.stdout.strip()
    _wait_for_prompt(pane)
    return pane


def _wait_for_prompt(pane, timeout=5.0):
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        if "Resume with" in tmux.capture_scrollback(pane, 50):
            return
        time.sleep(0.05)
    raise AssertionError("scrollback never printed")


def test_bare_pane_after_remote_launch_is_flagged_and_enriched(launched, capsys):
    (s,) = remote.discover(agents=[])
    assert s.session_id == SID and s.url == URL
    assert s.awaiting_flag and s.flag == f"-> remote {URL}"
    r = s.ref
    assert r.title == "Environment diagnostics check"
    assert r.environment == "ccpool_FAKEFAKEFAKEFAKEFAKEFAKE"
    # joined across soft-wraps -> matched the delegator sidecar by prompt-file key
    assert r.delegator_key == KEY and r.worktree == "runner-env-probe" and r.repo == "bitso-web"
    assert r.created_source == "delegator" and r.prompt.startswith("Read-only check")

    assert main(["ls"]) == 0
    out = capsys.readouterr().out
    assert "remote sessions · 1" in out
    assert f"-> remote {URL}" in out
    assert "status: unknown, open URL" in out
    assert "no live agent panes found" in out


def test_session_survives_the_launching_pane(launched, capsys):
    remote.discover(agents=[])  # first sight persists it
    tmux.run("kill-session", "-t", "bitso-web")
    (s,) = remote.discover(agents=[])
    assert not s.pane_alive and not s.awaiting_flag
    assert main(["ls", "--json"]) == 0
    (row,) = json.loads(capsys.readouterr().out)
    assert row["kind"] == "remote" and row["session_id"] == SID
    assert row["pane_id"] is None and row["launched_from"]["pane_alive"] is False
    assert row["status"] == "unknown"


def test_local_agents_and_remote_are_listed_together(launched, tmux_server, capsys):
    agent_pane = tmux_server.start_agent_session("alpha", "claude")
    assert main(["ls", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert [(r["kind"], r.get("pane_id")) for r in rows] == [
        ("claude", agent_pane), ("remote", launched),
    ]
    assert main(["ls", "--no-remote", "--json"]) == 0
    assert [r["kind"] for r in json.loads(capsys.readouterr().out)] == ["claude"]
    assert main(["doctor"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("claude") and lines[1].startswith("remote")
    assert f"-> remote {URL}" in lines[1]


def test_prose_mentioning_the_phrase_is_not_a_session(tmux_server, tmp_path):
    prose = tmp_path / "prose.txt"
    prose.write_text("It prints `Created cloud session` and a URL; Session ID: and View: follow.\n")
    remote._scanned.clear()
    proc = tmux.run("new-session", "-d", "-s", "docs", "-P", "-F", "#{pane_id}",
                    f"sh -c 'cat {prose}; exec sh'", check=True)
    _wait_for_prompt_text(proc.stdout.strip(), "follow.")
    assert remote.discover(agents=[]) == []
    assert not os.path.isdir(state.remote_dir())  # nothing recorded, nothing written


def _wait_for_prompt_text(pane, text, timeout=5.0):
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        if text in tmux.capture_scrollback(pane, 50):
            return
        time.sleep(0.05)
    raise AssertionError("never printed")


def test_remote_forget_and_show(launched, capsys):
    assert main(["show", "01BBBBBBB"]) == 0
    out = capsys.readouterr().out
    assert "kind     : remote" in out and "unknown, open URL" in out and URL in out
    assert main(["remote", "forget", SID]) == 0
    capsys.readouterr()
    assert main(["remote"]) == 0
    assert "no remote sessions known" in capsys.readouterr().out
    assert main(["show", SID]) == 1  # forgotten: not resolvable any more


def test_remote_open_uses_the_browser(launched, monkeypatch, capsys):
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda u: opened.append(u) or True)
    assert main(["remote", "open"]) == 0  # defaults to the newest
    assert opened == [URL]


PEEK = cloudstatus.Peek(items=[
    cloudstatus.PeekItem("user", "17:19:32", ["Explore the repo, read-only."]),
    cloudstatus.PeekItem("tool_use", "17:20:08", ["Bash: ls apps/"]),
    cloudstatus.PeekItem("tool_result", "17:20:09", ["alpha", "hubble"]),
    cloudstatus.PeekItem("assistant", "17:20:23", ["Found two apps: alpha and hubble.", "Reading the README next."]),
])


@pytest.fixture
def remote_tile(launched, monkeypatch):
    """A recorded, finished remote session whose peek comes from a canned read-only fetch."""
    remote.discover(agents=[])  # first sight records it
    state.update_remote_status(SID, "running", "exploring", pool_name="main")
    monkeypatch.setattr(remote, "peeks_enabled", lambda: True)
    monkeypatch.setattr(cloudstatus, "fetch_peek", lambda sid, **k: PEEK)
    remote._peeks.clear()
    return launched


async def _remote_settled(pilot, app):
    for _ in range(80):  # status/peek arrive from their own worker, after the first frame
        if app.remotes and remote.peek_of(SID):
            break
        await pilot.pause(0.1)
    await pilot.pause(0.4)


@pytest.mark.parametrize("mode", ["grid", "list"])
async def test_remote_session_is_a_normal_tile_with_a_live_peek(remote_tile, tmux_server, mode):
    """The overview (prefix+a popup) draws a remote session like any agent: badge, state, live body."""
    tmux_server.start_agent_session("alpha", "claude")
    state.save_view_mode(mode)
    app = AgentViewApp()
    async with app.run_test(size=(150, 45)) as pilot:
        await _settle(pilot, app, min_tiles=1)
        await _remote_settled(pilot, app)
        assert len(app.query("#remote-strip")) == 0  # the separate bottom section is gone
        kinds = sorted(a.kind.value for a in app.filtered_agents)
        assert kinds == ["claude", "remote"]
        remote_agent = next(a for a in app.filtered_agents if getattr(a, "is_remote", False))
        assert remote_agent.state.value == "working"  # running → the same marker local tiles use
        if mode == "grid":
            tile = next(t for t in app.query(AgentTile) if getattr(t.agent, "is_remote", False))
            assert tile.has_class("-remote") and tile.has_class("-working")
            assert "REMOTE" in tile.border_title and "pool main" in tile.border_title
            assert "running" in tile.border_subtitle and "open in claude.ai" in tile.border_subtitle
            body = "\n".join(line.plain for line in tile._lines)
            assert "Bash: ls apps/" in body and "Found two apps" in body  # the live peek
        else:
            panel = str(app.query_one("#agent-list").render())
            assert "☁" in panel and "remote session_01BB" in panel
            # both tiles are "working", so which sorts first (and is auto-selected) depends on
            # timing: select the remote one explicitly before reading the preview
            app.select_pane(remote_agent.pane_id)
            assert "REMOTE" in app.query_one("#preview").border_title
        bar = str(app.query_one("#statusbar").render())
        assert "1/1 agents" in bar and "☁ 1 remote" in bar


async def test_enter_and_ctrl_o_open_the_session_url_without_leaving(remote_tile, monkeypatch):
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda u: opened.append(u) or True)
    app = AgentViewApp()
    async with app.run_test(size=(150, 45)) as pilot:
        await _remote_settled(pilot, app)
        assert app.current is not None and app.current.is_remote
        await pilot.press("enter")
        await pilot.pause(0.5)
        await pilot.press("ctrl+o")
        await pilot.pause(0.5)
        assert opened == [URL, URL]
        assert app._exit is False  # stays open so the tile keeps updating


async def test_kill_keys_do_not_apply_to_a_remote_tile(remote_tile):
    app = AgentViewApp()
    async with app.run_test(size=(150, 45)) as pilot:
        await _remote_settled(pilot, app)
        await pilot.press("ctrl+d")
        await pilot.pause(0.2)
        assert type(app.screen).__name__ != "ConfirmScreen"  # no kill dialog
        await pilot.press("ctrl+k")
        await pilot.pause(0.2)
        assert type(app.screen).__name__ != "ConfirmScreen"


async def test_remote_filter_matches_the_session(remote_tile, tmux_server):
    tmux_server.start_agent_session("alpha", "claude")
    app = AgentViewApp()
    async with app.run_test(size=(150, 45)) as pilot:
        await _remote_settled(pilot, app)
        await pilot.press(*"cloud")  # remote tiles answer to "cloud"/"remote"
        assert [a.kind.value for a in app.filtered_agents] == ["remote"]


async def test_tui_without_remote_sessions_has_no_remote_tile_or_count(tmux_server):
    tmux_server.start_agent_session("alpha", "claude")
    app = AgentViewApp()
    async with app.run_test(size=(140, 40)) as pilot:
        await _settle(pilot, app, min_tiles=1)
        assert [a.kind.value for a in app.filtered_agents] == ["claude"]
        assert "remote" not in str(app.query_one("#statusbar").render())


def test_discovery_announces_a_new_session_once(launched, tmp_path):
    log = tmp_path / "state" / "agent-events.log"
    remote.discover(agents=[])
    remote.discover(agents=[])
    remote._scanned.clear()
    remote.discover(agents=[])  # rescanned, already recorded: no second event
    lines = [json.loads(line) for line in log.read_text().splitlines()]
    assert [e["event"] for e in lines] == ["remote-created"]
    e = lines[0]
    assert (e["stream"], e["kind"], e["session_id"], e["url"]) == ("remote", "remote", SID, URL)
    assert e["status"] == "unknown" and e["title"] == "Environment diagnostics check"


# --- removing a remote tile (ctrl-x) ------------------------------------------------------

async def _cycles(pilot, app, n=3, timeout=15.0):
    """Let ``n`` more refresh cycles (and the remote worker behind each) complete."""
    import time

    target = app.snapshots_applied + n
    deadline = time.time() + timeout
    while time.time() < deadline and app.snapshots_applied < target:
        await pilot.pause(0.1)
    await pilot.pause(0.6)


def _remote_ids(app):
    return [a.remote.session_id for a in app.filtered_agents if getattr(a, "is_remote", False)]


async def test_ctrl_x_asks_first_and_cancel_keeps_the_tile(remote_tile):
    app = AgentViewApp()
    async with app.run_test(size=(150, 45)) as pilot:
        await _remote_settled(pilot, app)
        await pilot.press("ctrl+x")
        await pilot.pause(0.3)
        assert isinstance(app.screen, ConfirmScreen)
        assert "cloud session is not stopped" in str(app.screen.query_one("Label").render())
        await pilot.press("n")
        await pilot.pause(0.3)
        assert not isinstance(app.screen, ConfirmScreen)
        assert _remote_ids(app) == [SID] and not state.is_dismissed(SID)


@pytest.mark.parametrize("mode", ["grid", "list"])
async def test_ctrl_x_removes_the_tile_and_it_stays_removed(remote_tile, tmux_server, mode):
    """Removed once, gone for good — even though the launch block is still in the pane."""
    tmux_server.start_agent_session("alpha", "claude")
    state.save_view_mode(mode)
    app = AgentViewApp()
    async with app.run_test(size=(150, 45)) as pilot:
        await _settle(pilot, app, min_tiles=1)
        await _remote_settled(pilot, app)
        assert _remote_ids(app) == [SID]
        app.select_pane(next(a.pane_id for a in app.filtered_agents if getattr(a, "is_remote", False)))
        bar = str(app.query_one("#statusbar").render())
        assert "^x" in bar and "remove" in bar  # the hint shows while a remote tile is selected

        await pilot.press("ctrl+x")
        await pilot.pause(0.3)
        await pilot.press("y")
        await pilot.pause(0.5)

        assert _remote_ids(app) == [] and state.is_dismissed(SID)
        assert [a.kind.value for a in app.filtered_agents] == ["claude"]  # the local agent is untouched
        bar = str(app.query_one("#statusbar").render())
        assert "☁" not in bar and "^x" not in bar
        if mode == "grid":
            assert not any(getattr(t.agent, "is_remote", False) for t in app.query(AgentTile))

        remote._scanned.clear()  # force the scrollback scan to look at the pane again
        await _cycles(pilot, app, n=3)
        assert _remote_ids(app) == [] and state.is_dismissed(SID)


async def test_a_refresh_already_in_flight_cannot_put_a_removed_tile_back(remote_tile):
    app = AgentViewApp()
    async with app.run_test(size=(150, 45)) as pilot:
        await _remote_settled(pilot, app)
        stale = list(app.remotes)  # what a worker started before the removal would deliver
        state.dismiss_remote(SID)
        await app.on_remote_ready(RemoteReady(stale))
        assert app.remotes == [] and _remote_ids(app) == []


async def test_removed_session_returns_after_an_explicit_record(remote_tile):
    app = AgentViewApp()
    async with app.run_test(size=(150, 45)) as pilot:
        await _remote_settled(pilot, app)
        await pilot.press("ctrl+x")
        await pilot.pause(0.3)
        await pilot.press("y")
        await pilot.pause(0.5)
        assert _remote_ids(app) == []

        assert [r.session_id for r in remote.record_from_output(SCROLLBACK)] == [SID]
        await _cycles(pilot, app, n=3)
        assert _remote_ids(app) == [SID] and not state.is_dismissed(SID)


async def test_ctrl_x_on_a_local_agent_removes_nothing(remote_tile, tmux_server):
    pane = tmux_server.start_agent_session("alpha", "claude")
    app = AgentViewApp()
    async with app.run_test(size=(150, 45)) as pilot:
        await _settle(pilot, app, min_tiles=1)
        await _remote_settled(pilot, app)
        app.select_pane(pane)
        await pilot.press("ctrl+x")
        await pilot.pause(0.3)
        assert not isinstance(app.screen, ConfirmScreen)  # no dialog: nothing to remove
        assert sorted(a.kind.value for a in app.filtered_agents) == ["claude", "remote"]
        assert not state.is_dismissed(SID)


async def test_removing_keeps_the_selection_in_place(remote_tile, tmux_server):
    tmux_server.start_agent_session("alpha", "claude")
    tmux_server.start_agent_session("beta", "claude")
    app = AgentViewApp()
    async with app.run_test(size=(150, 45)) as pilot:
        await _settle(pilot, app, min_tiles=2)
        await _remote_settled(pilot, app)
        rid = next(a.pane_id for a in app.filtered_agents if getattr(a, "is_remote", False))
        app.select_pane(rid)
        before = app.selected
        await pilot.press("ctrl+x")
        await pilot.pause(0.3)
        await pilot.press("y")
        await pilot.pause(0.5)
        assert app.current is not None and not getattr(app.current, "is_remote", False)
        assert app.selected == min(before, len(app.filtered_agents) - 1)


# --- lazy loading: remotes must never get in front of the local overview ----------------------


@pytest.fixture
def hung_claude_ai(monkeypatch):
    """Every remote pass blocks (as if claude.ai never answered) until the test lets it go."""
    gate, entered = threading.Event(), []
    real = remote.Loader.run

    def stuck(self, agents, panes, publish):
        entered.append(1)
        with self._lock:  # a pass in progress: ready() stays False like a real slow one
            gate.wait(20)
        return real(self, agents, panes, publish)

    monkeypatch.setattr(remote.Loader, "run", stuck)
    yield gate
    gate.set()


async def test_local_and_cached_remote_tiles_render_while_the_remote_pass_hangs(
    remote_tile, tmux_server, hung_claude_ai
):
    tmux_server.start_agent_session("alpha", "claude")
    app = AgentViewApp()
    async with app.run_test(size=(150, 45)) as pilot:
        await _settle(pilot, app, min_tiles=2)  # the local agent AND the remote tile, with the pass stuck
        assert sorted(a.kind.value for a in app.filtered_agents) == ["claude", "remote"]
        bar = str(app.query_one("#statusbar").render())
        assert "☁ 1 remote" in bar and "loading…" in bar  # placeholder until the first pass settles
        tile = next(t for t in app.query(AgentTile) if getattr(t.agent, "is_remote", False))
        assert "Read-only check" in "\n".join(line.plain for line in tile._lines)  # the cached record, not a blank

        await pilot.press(*"alp")  # the UI is live: a keypress is handled while the pass is stuck
        assert [a.kind.value for a in app.filtered_agents] == ["claude"]
        await pilot.press("backspace", "backspace", "backspace")

        hung_claude_ai.set()
        await _remote_settled(pilot, app)
        assert "loading…" not in str(app.query_one("#statusbar").render())
        assert remote.peek_of(SID)  # …and the live peek filled in afterwards


async def test_remote_passes_are_spaced_out_not_run_every_tick(remote_tile, monkeypatch):
    monkeypatch.setattr(remote, "TICK_SECONDS", 60.0)
    runs = []
    real = remote.Loader.run
    monkeypatch.setattr(remote.Loader, "run", lambda self, *a: runs.append(1) or real(self, *a))
    app = AgentViewApp()
    async with app.run_test(size=(150, 45)) as pilot:
        await _remote_settled(pilot, app)
        await _cycles(pilot, app, n=3)  # three more 1s local refreshes
        assert app.snapshots_applied >= 4
        assert len(runs) == 1


async def test_keypresses_and_redraws_do_no_remote_work(remote_tile, tmux_server, monkeypatch):
    tmux_server.start_agent_session("alpha", "claude")
    app = AgentViewApp()
    async with app.run_test(size=(150, 45)) as pilot:
        await _remote_settled(pilot, app)
        app._refresh_timer.stop()  # only the user acts from here on
        await pilot.pause(1.5)  # let a refresh that was already in flight finish

        import subprocess

        calls = []

        def counted(owner, name):
            real = getattr(owner, name)
            monkeypatch.setattr(owner, name, lambda *a, **k: calls.append(name) or real(*a, **k))

        for owner, name in [
            (remote, "discover"), (remote, "scan_panes"), (remote, "refresh_status"), (remote, "refresh_peeks"),
            (remote.Loader, "run"), (cloudstatus, "_get"), (cloudstatus, "_token"), (state, "load_remote"),
            (state, "update_remote_status"), (tmux, "list_panes"), (tmux, "capture_scrollback"),
            (subprocess, "Popen"),
        ]:
            counted(owner, name)
        for keys in (["down"], ["up"], ["right"], ["left"], list("alp"), ["backspace"] * 3, ["tab"]):
            await pilot.press(*keys)
        await pilot.resize_terminal(110, 35)  # a full redraw
        await pilot.resize_terminal(150, 45)
        await pilot.pause(0.5)
        assert calls == []


async def test_each_refresh_lists_tmux_once_and_shares_it_with_the_remote_tiles(remote_tile, monkeypatch):
    listings = []
    real = tmux.list_panes
    monkeypatch.setattr(tmux, "list_panes", lambda: listings.append(1) or real())
    app = AgentViewApp()
    async with app.run_test(size=(150, 45)) as pilot:
        await _remote_settled(pilot, app)
        before_listings, before_snapshots = len(listings), app.snapshots_applied
        await _cycles(pilot, app, n=3)
        cycles = app.snapshots_applied - before_snapshots
        assert cycles >= 3
        assert len(listings) - before_listings <= cycles + 1  # one per refresh (+1 may be in flight)

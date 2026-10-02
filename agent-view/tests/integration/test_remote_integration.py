"""Remote (cloud) sessions against a real tmux server and the real CLI.

A pane replays what `claude --environment ccpool_…` leaves behind — the long,
soft-wrapped launch line plus the four-line "Created cloud session" block —
and then sits at a shell prompt, exactly like the delegator pane whose
``claude`` exited. The tmux server is private; nothing touches the user's.
"""
import json
import os
import shutil

import pytest

from agent_view import cloudstatus, remote, state, tmux
from agent_view.cli import main
from agent_view.tui.app import AgentTile, AgentViewApp

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


SID = "session_01VpjMyefcP66wrGW91FtrDY"
URL = f"https://claude.ai/code/{SID}"
KEY = "bitso-web-11-1790868922"

SCROLLBACK = (
    "$ claude --permission-mode auto --model claude-sonnet-5-5 --effort high "
    "--environment ccpool_012j3G7HWYn93pirmbR8txGp --settings '{\"x\":true}' "
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
    assert r.environment == "ccpool_012j3G7HWYn93pirmbR8txGp"
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
    assert main(["show", "01Vpjmy"]) == 0
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
            assert "☁" in panel and "remote session_01Vp" in panel
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

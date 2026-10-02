"""Remote (cloud) sessions: parsing, records, sidecar matching, rendering.

The fixture text is the CLI's real output for the probe session (CLI 2.1.286,
`claude --environment ccpool_… `), including the launch line that the tmux
delegator types into the pane.
"""
import json
import os
import time

import pytest

from agent_view import remote, state

SID = "session_01BBBBBBBBBBBBBBBBBBBBBB"
URL = f"https://claude.ai/code/{SID}"
KEY = "demo-repo-11-1700000000"

LAUNCH = (
    "[c@m] ➜ runner-env-probe claude --permission-mode auto --model claude-sonnet-5-5 "
    "--effort high --environment ccpool_FAKEFAKEFAKEFAKEFAKEFAKE "
    "--settings '{\"enableAllProjectMcpServers\":true}' "
    f"\"$(cat '/h/.local/share/local-tmux-agent-delegator/sessions/prompts/{KEY}.txt')\"\n"
)
BLOCK = (
    "Created cloud session: Environment diagnostics check\n"
    f"Session ID: {SID}\n"
    f"View: {URL}?from=cli&m=0\n"
    f"Resume with: claude --teleport {SID}\n"
)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ATTENTION_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("TMUX_AGENT_STATE_DIR", str(tmp_path / "delegator"))
    (tmp_path / "delegator").mkdir()
    return tmp_path


# --- parsing ----------------------------------------------------------------


def test_parse_real_output_shape():
    (c,) = remote.parse_created(LAUNCH + BLOCK + "[c@m] ➜ runner-env-probe\n")
    assert c.session_id == SID
    assert c.url == URL  # ?from=cli&m=0 dropped
    assert c.title == "Environment diagnostics check"
    assert c.environment == "ccpool_FAKEFAKEFAKEFAKEFAKEFAKE"
    assert c.delegator_key == KEY


def test_parse_without_title_or_launch_line():
    text = f"Created cloud session\nSession ID: {SID}\nView: {URL}\n"
    (c,) = remote.parse_created(text)
    assert (c.title, c.environment, c.delegator_key) == (None, None, None)


def test_parse_ignores_prose_that_merely_mentions_it():
    prose = (
        "- It prints `Created cloud session` plus a URL, and local claude exits.\n"
        "Facts: claude --environment ccpool_x prints Created cloud session and a "
        "https://claude.ai/code/session_… URL\n"
        "Created cloud session: but no id line follows\n"
        "View: https://claude.ai/code/session_01AAA\n"
    )
    assert remote.parse_created(prose) == []


def test_parse_multiple_launches_each_gets_its_own_launch_context():
    other = BLOCK.replace(SID, "session_01Other").replace("diagnostics check", "second")
    text = (
        LAUNCH + BLOCK
        + LAUNCH.replace("ccpool_FAKEFAKEFAKEFAKEFAKEFAKE", "ccpool_second").replace(KEY, "k2")
        + other + BLOCK  # the first block scrolled back in: deduped, not doubled
    )
    got = {c.session_id: c for c in remote.parse_created(text)}
    assert set(got) == {SID, "session_01Other"}
    assert got[SID].environment == "ccpool_FAKEFAKEFAKEFAKEFAKEFAKE"
    assert got["session_01Other"].environment == "ccpool_second"
    assert got["session_01Other"].delegator_key == "k2"


# --- records ----------------------------------------------------------------


def _ref(**kw):
    return state.RemoteRef(session_id=SID, url=URL, **kw)


def test_record_roundtrip_and_first_record_wins(env):
    assert state.record_remote(_ref(title="first", pane_id="%49"))
    assert not state.record_remote(_ref(title="second"))
    ref = state.load_remote()[SID]
    assert (ref.title, ref.pane_id) == ("first", "%49")
    assert ref.recorded_at > 0 and ref.created_at == ref.recorded_at


def test_record_rejects_unsafe_ids(env):
    bad = state.RemoteRef(session_id="../../etc/passwd", url="https://x")
    assert not state.record_remote(bad)
    assert state.load_remote() == {}


def test_dismiss_hides_but_is_not_rerecorded(env):
    state.record_remote(_ref())
    assert state.dismiss_remote(SID)
    assert state.load_remote()[SID].dismissed
    assert not state.record_remote(_ref())  # block still in scrollback: stays dismissed
    assert remote.discover(agents=[], panes=[]) == []


def test_dismiss_leaves_a_scrubbed_tombstone(env):
    """Removing a session drops its stored text; only the identity survives."""
    state.record_remote(_ref(title="secret title", prompt="secret prompt", repo="r", pane_id="%49",
                             created_at=1234.0))
    state.update_remote_status(SID, "finished", "secret detail", last_message="last words")
    assert state.dismiss_remote(SID)
    with open(os.path.join(state.remote_dir(), SID)) as f:
        raw = f.read()
    for gone in ("secret title", "secret prompt", "last words", "secret detail", "%49"):
        assert gone not in raw
    ref = state.load_remote()[SID]
    assert ref.dismissed and ref.url == URL and ref.created_at == 1234.0
    assert state.is_dismissed(SID) and not state.is_dismissed(GU)
    assert '"dismissed": true' in raw  # tmux/agent-attention/status.sh greps for exactly this


def test_dismiss_unknown_or_unsafe_id_is_a_noop(env):
    assert not state.dismiss_remote(SID)
    assert not state.dismiss_remote("../../etc/passwd")
    assert state.load_remote() == {}


def test_scan_never_brings_a_removed_session_back_but_an_explicit_record_does(env):
    """The launch block stays in the pane's scrollback, so only `remote record` may revive."""
    (c,) = remote.parse_created(BLOCK)
    ref = remote._build_ref(c, {"path": str(env)}, "%49", "s:1.0", None)
    assert remote.register(ref)
    assert state.dismiss_remote(SID)

    again = remote._build_ref(c, {"path": str(env)}, "%49", "s:1.0", None)
    assert not remote.register(again)  # what a scrollback scan does
    assert remote.discover(agents=[], panes=[]) == []

    got = remote.record_from_output(BLOCK)  # an explicit record
    assert [r.session_id for r in got] == [SID]
    (s,) = remote.discover(agents=[], panes=[])
    assert s.session_id == SID and not s.ref.dismissed


def test_a_status_poll_cannot_resurrect_or_update_a_removed_session(env):
    state.record_remote(_ref())
    state.dismiss_remote(SID)
    assert state.update_remote_status(SID, "running") == (None, False, None)
    assert state.load_remote()[SID].dismissed and state.load_remote()[SID].status is None


def test_dismiss_waits_for_a_status_poll_holding_the_lock(env):
    """The race that could undo a removal: a poll that read the old record, then wrote it back."""
    import fcntl
    import threading

    state.record_remote(_ref(title="t"))
    path = os.path.join(state.remote_dir(), SID)
    done = threading.Event()
    with open(path, "r+") as held:
        fcntl.flock(held, fcntl.LOCK_EX)  # a poll is mid-update
        t = threading.Thread(target=lambda: (state.dismiss_remote(SID), done.set()))
        t.start()
        assert not done.wait(0.3)  # dismiss is blocked behind the poll, not racing it
        fcntl.flock(held, fcntl.LOCK_UN)
    t.join(5)
    assert done.is_set() and state.load_remote()[SID].dismissed


def test_tombstones_outlive_the_launch_age_but_not_30_days(env):
    state.record_remote(_ref(created_at=1.0))
    old = state.load_remote()[SID]
    old.recorded_at = time.time() - 20 * 86400  # launched long ago…
    with open(os.path.join(state.remote_dir(), SID), "w") as f:
        f.write(json.dumps(old.__dict__))
    state.dismiss_remote(SID)  # …but only just removed
    state.prune_remote(7 * 86400)
    assert SID in state.load_remote()  # kept: removal is recent, so a scan can't resurrect it

    path = os.path.join(state.remote_dir(), SID)
    stale = time.time() - state.TOMBSTONE_SECONDS - 3600
    os.utime(path, (stale, stale))
    state.prune_remote(7 * 86400)
    assert SID not in state.load_remote()


def test_prune_drops_only_old_records(env):
    state.record_remote(_ref(created_at=1.0))
    old = state.load_remote()[SID]
    old.recorded_at = time.time() - 30 * 86400
    path = os.path.join(state.remote_dir(), SID)
    with open(path, "w") as f:
        f.write(json.dumps(old.__dict__))
    state.record_remote(state.RemoteRef(session_id="session_01New", url="https://x"))
    state.prune_remote(7 * 86400)
    assert set(state.load_remote()) == {"session_01New"}


# --- delegator sidecar ------------------------------------------------------


def _sidecar(dirpath, key, pane, started, **kw):
    data = {"session_key": key, "repo": "bitso-web", "worktree": "wt", "tmux_target": pane,
            "project_dir": "/nonexistent", "started_at": started, "prompt": "do the thing", **kw}
    (dirpath / f"{key}.json").write_text(json.dumps(data))


def test_find_sidecar_prefers_key_then_newest_for_pane(env):
    d = env / "delegator"
    _sidecar(d, "old", "%49", "2026-10-01T10:00:00+00:00")
    _sidecar(d, "new", "%49", "2026-10-01T15:35:22+00:00")
    _sidecar(d, "elsewhere", "%7", "2026-10-01T16:00:00+00:00")
    assert remote.find_sidecar("old", "%49", None)["session_key"] == "old"
    assert remote.find_sidecar(None, "%49", None)["session_key"] == "new"
    assert remote.find_sidecar(None, "%99", None) is None


def test_find_sidecar_ignores_records_older_than_the_tmux_server(env):
    d = env / "delegator"
    _sidecar(d, "prev-server", "%49", "2026-09-01T10:00:00+00:00")
    os.utime(d / "prev-server.json", (1000, 1000))  # pane ids restarted since
    assert remote.find_sidecar(None, "%49", since=time.time() - 60) is None


def test_summarize_flattens_and_truncates():
    assert remote.summarize(None) is None
    assert remote.summarize("a\n\n  b\tc") == "a b c"
    out = remote.summarize("x" * 500, limit=20)
    assert len(out) == 20 and out.endswith("…")


# --- status / resolve / render ----------------------------------------------


def _session(**kw):
    ref = _ref(location="bitso-web:11.1", pane_id="%49", created_at=time.time() - 120,
               created_source="delegator", title="Environment diagnostics check", **kw)
    return remote.RemoteSession(ref=ref, now=time.time(), pane_alive=True)


def test_status_is_always_unknown_open_url():
    s = _session()
    assert s.status == "unknown"
    assert s.status_text == "unknown, open URL"


def test_pane_flag_only_while_pane_is_a_bare_shell():
    s = _session()
    assert s.awaiting_flag and s.flag == f"-> remote {URL}"
    s.pane_has_agent = True  # something else runs there now
    assert not s.awaiting_flag
    s.pane_has_agent, s.pane_alive = False, False
    assert not s.awaiting_flag


def test_to_dict_is_kind_remote_and_hides_stale_pane_id():
    d = _session().to_dict()
    assert d["kind"] == "remote" and d["status"] == "unknown"
    assert d["pane_id"] == "%49" and d["launched_from"]["flag"] == f"-> remote {URL}"
    gone = _session()
    gone.pane_alive = False
    d = gone.to_dict()
    assert d["pane_id"] is None  # ids are reused after a tmux restart: not addressable
    assert d["launched_from"]["pane_id"] == "%49" and d["launched_from"]["flag"] is None


def test_resolve_by_id_fragment_url_pane_and_location():
    a, b = _session(), _session()
    b.ref = state.RemoteRef(session_id="session_01Other", url="https://claude.ai/code/session_01Other")
    both = [a, b]
    for ident in (SID, "01BBB", URL, "%49", "bitso-web:11.1"):
        assert remote.resolve(both, ident).session is a
    assert remote.resolve(both, "session_01").error == "'session_01' is ambiguous"
    assert remote.resolve(both, "nope").session is None


def test_row_lines_show_flag_context_and_unknown_status():
    s = _session(prompt="Read-only check", repo="bitso-web", branch="wt-branch", worktree="wt")
    lines = "\n".join(remote.row_lines(s))
    assert f"-> remote {URL}" in lines
    assert "bitso-web/wt@wt-branch" in lines and "launched 2m ago" in lines
    assert "prompt: Read-only check" in lines
    assert "status: unknown, open URL" in lines


def test_discover_never_raises(monkeypatch):
    monkeypatch.setattr(remote.tmux, "list_panes", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert remote.discover(agents=[]) == []


# --- documented launch: -p … --output-format json ----------------------------

GU = "session_01CCCCCCCCCCCCCCCCCCCCCC"
JSON_OUT = (
    '{"ok":true,"session_id":"%s","title":"Environment diagnostics check",'
    '"url":"https://claude.ai/code/%s?from=cli&m=0","pool_id":"ccpool_FAKEFAKEFAKEFAKEFAKEFAKE"}\n'
    % (GU, GU)
)


def test_parse_json_launch_result():
    text = 'claude -p "Read-only check, no changes" --environment ccpool_x --output-format json\n' + JSON_OUT
    (c,) = remote.parse_created(text)
    assert c.session_id == GU and c.url == f"https://claude.ai/code/{GU}"
    assert c.title == "Environment diagnostics check"
    assert c.environment == "ccpool_FAKEFAKEFAKEFAKEFAKEFAKE"  # pool_id wins over the argv guess
    assert c.prompt == "Read-only check, no changes"


def test_parse_json_pretty_printed_and_mixed_with_block():
    pretty = json.dumps(json.loads(JSON_OUT), indent=2)
    got = remote.parse_created(BLOCK + "\n" + pretty + "\n")
    assert {c.session_id for c in got} == {SID, GU}


def test_parse_json_ignores_failures_and_unrelated_objects():
    assert remote.parse_created('{"ok":false,"session_id":"%s","url":"https://x"}' % GU) == []
    assert remote.parse_created('{"session_id": "not-a-session", "url": "https://x"}') == []
    assert remote.parse_created('{"a": 1} garbage {"session_id"') == []


def test_prompt_argument_only_when_literal_on_the_launch_line():
    # `-p "$P"` / `$(cat …)` carry no usable text — leave it to the sidecar
    assert remote.parse_created('claude -p "$P" --environment ccpool_x\n' + JSON_OUT)[0].prompt is None
    assert remote.parse_created("claude -p 'single quoted' --x\n" + JSON_OUT)[0].prompt == "single quoted"


def test_git_info_names_repo_and_detached_head(tmp_path):
    import subprocess

    def git(*a):
        subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True)

    assert remote.git_info(str(tmp_path / "nope")) == (None, None)
    git("init", "-q", "-b", "main")
    git("remote", "add", "origin", "https://github.com/bitsoex/bitso-web.git")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x")
    assert remote.git_info(str(tmp_path)) == ("bitso-web", "main")
    git("checkout", "-q", "--detach")  # a clean origin/main checkout looks like this
    repo, branch = remote.git_info(str(tmp_path))
    assert repo == "bitso-web" and branch.startswith("detached@")


def test_record_from_output_registers_at_launch_time(env):
    before = time.time()
    (ref,) = remote.record_from_output(JSON_OUT, pane_id=None, prompt="Read-only check")
    assert ref.created_source == "registry" and ref.created_at >= before
    assert ref.prompt == "Read-only check" and ref.environment.startswith("ccpool_")
    assert remote.record_from_output(JSON_OUT) == []  # already registered: no duplicate
    assert set(state.load_remote()) == {GU}


def test_cli_record_passes_stdin_through_unchanged(env, monkeypatch, capsys):
    import io

    from agent_view.cli import main

    monkeypatch.delenv("TMUX_PANE", raising=False)
    monkeypatch.setattr("sys.stdin", io.StringIO(JSON_OUT))
    assert main(["remote", "record", "--prompt", "p"]) == 0
    assert capsys.readouterr().out == JSON_OUT  # byte-for-byte what the launcher parses
    assert state.load_remote()[GU].prompt == "p"


def test_cli_record_never_fails_the_launcher(env, monkeypatch, capsys):
    import io

    from agent_view.cli import main

    monkeypatch.setattr("sys.stdin", io.StringIO("not a cloud session\n"))
    assert main(["remote", "record"]) == 0
    cap = capsys.readouterr()
    assert cap.out == "not a cloud session\n" and "nothing recorded" in cap.err
    assert state.load_remote() == {}


# --- events: reactable via agent-events.log ---------------------------------


def _events(env):
    path = env / "state" / "agent-events.log"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_registry_emits_one_remote_created_in_the_fleet_shape(env):
    remote.record_from_output(JSON_OUT, pane_id=None, prompt="Read-only check")
    remote.record_from_output(JSON_OUT)  # already known: silent
    (e,) = _events(env)
    # the fleet-stream keys the orchestrator already routes on…
    assert {"pane_id", "location", "agent", "event", "message", "ts"} <= set(e)
    # …plus the markers that make it a remote event
    assert (e["stream"], e["kind"], e["event"]) == ("remote", "remote", "remote-created")
    assert (e["session_id"], e["url"]) == (GU, f"https://claude.ai/code/{GU}")
    assert e["status"] == "unknown" and e["prompt"] == "Read-only check"
    assert e["environment"] == "ccpool_FAKEFAKEFAKEFAKEFAKEFAKE"
    assert isinstance(e["ts"], float)


def test_no_terminal_or_needs_input_event_is_ever_invented(env):
    remote.record_from_output(JSON_OUT)
    remote.discover(agents=[], panes=[])
    assert {e["event"] for e in _events(env)} == {"remote-created"}  # status has no source


def test_emit_never_raises(env, monkeypatch):
    from agent_view import events

    monkeypatch.setenv("AGENT_VIEW_EVENTS_LOG", "/proc/definitely/not/writable/x.log")
    assert events.emit({"a": 1}) is False
    assert remote.record_from_output(JSON_OUT)  # still recorded despite the unwritable log


def test_status_counts_remote_sessions_and_skips_forgotten(env, capsys):
    from agent_view.cli import main

    assert main(["status"]) == 0 and capsys.readouterr().out == ""
    remote.record_from_output(JSON_OUT)
    main(["status"])
    assert "⇢ 1" in capsys.readouterr().out
    state.dismiss_remote(GU)
    main(["status"])
    assert capsys.readouterr().out == ""


def test_cli_forget_says_the_cloud_session_is_untouched_and_is_listed_nowhere_after(env, capsys, monkeypatch):
    from agent_view.cli import main

    monkeypatch.setattr("agent_view.tmux.list_panes", lambda: [])  # never scan the real tmux server
    monkeypatch.setattr("agent_view.discovery.discover", lambda: [])
    remote.record_from_output(JSON_OUT)
    assert main(["remote", "forget", GU[:14]]) == 0
    assert "cloud session is untouched" in capsys.readouterr().out
    assert main(["remote"]) == 0 and "no remote sessions known" in capsys.readouterr().out
    assert main(["ls", "--json"]) == 0 and GU not in capsys.readouterr().out
    assert state.is_dismissed(GU)

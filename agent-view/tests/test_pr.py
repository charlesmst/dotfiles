"""PR association: url extraction, check rollup, markers, precedence."""
from agent_view import pr, state


# --- extraction (hook side) -------------------------------------------------


def test_extract_from_claude_posttooluse_payload():
    payload = ('{"tool_name":"Bash","tool_input":{"command":"gh pr create --fill"},'
               '"tool_response":{"stdout":"https://github.com/bitsoex/stocks/pull/42\\n"}}')
    assert pr.extract_pr_url(payload) == "https://github.com/bitsoex/stocks/pull/42"


def test_extract_from_already_exists_notice():
    payload = ('{"command":"gh pr create","output":"a pull request for branch already '
               'exists: https://github.com/o/n/pull/7"}')
    assert pr.extract_pr_url(payload) == "https://github.com/o/n/pull/7"


def test_extract_ignores_gh_pr_view():
    # `gh pr view` also prints a URL — must NOT be recorded as a creation.
    payload = '{"command":"gh pr view 7","output":"https://github.com/o/n/pull/7"}'
    assert pr.extract_pr_url(payload) is None


def test_extract_none_without_url():
    assert pr.extract_pr_url('{"command":"gh pr create","output":"error"}') is None


def test_parse_url():
    assert pr.parse_url("https://github.com/bitsoex/stocks/pull/42") == ("bitsoex/stocks", 42)
    assert pr.parse_url("not-a-url") == (None, None)


# --- check rollup summary ---------------------------------------------------


def test_rollup_counts_mixed():
    rollup = [
        {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SUCCESS"},
        {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "FAILURE"},
        {"__typename": "CheckRun", "status": "IN_PROGRESS", "conclusion": ""},
        {"__typename": "StatusContext", "state": "SUCCESS"},
        {"__typename": "StatusContext", "state": "PENDING"},
    ]
    assert pr._rollup_counts(rollup) == (2, 1, 2)  # passed, failed, pending


def test_status_summary_variants():
    base = dict(url="u", number=5, title="t", pr_state="OPEN", is_draft=False)
    assert pr.PRStatus(**base, passed=6, failed=0, pending=0).summary() == "#5 OPEN · ✓6/6 checks"
    assert "✗2" in pr.PRStatus(**base, passed=4, failed=2, pending=0).summary()
    assert pr.PRStatus(**{**base, "pr_state": "MERGED"}, passed=0, failed=0, pending=0).summary() == "#5 MERGED"
    assert "draft" in pr.PRStatus(**{**base, "is_draft": True}, passed=0, failed=0, pending=0).summary()


# --- markers (persistence) --------------------------------------------------


def test_record_and_load_pr(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ATTENTION_DIR", str(tmp_path))
    pr.record("%3", "https://github.com/o/n/pull/9")
    m = state.load_prs()["%3"]
    assert m.url.endswith("/pull/9") and m.repo == "o/n" and m.number == 9


def test_clear_and_prune_pr(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ATTENTION_DIR", str(tmp_path))
    pr.record("%1", "https://github.com/o/n/pull/1")
    pr.record("%2", "https://github.com/o/n/pull/2")
    state.prune_prs(live_pane_ids={"%1"})
    assert set(state.load_prs()) == {"%1"}
    state.clear_pr("%1")
    assert state.load_prs() == {}


# --- association precedence -------------------------------------------------


def test_recorded_url_wins_over_derive(monkeypatch):
    from agent_view.model import AgentKind, AgentPane

    pane = AgentPane(pane_id="%1", pane_pid=1, agent_pid=2, kind=AgentKind.CLAUDE,
                     session="s", window_index="1", pane_index="1", window_name="w",
                     last_activity=0.0, pr_url="https://github.com/o/n/pull/5")
    # derive_url must never be consulted when a recorded url exists.
    monkeypatch.setattr(pr, "derive_url", lambda cwd: (_ for _ in ()).throw(AssertionError("derived")))
    assert pr.pane_pr_url(pane, children={}) == "https://github.com/o/n/pull/5"


def test_fetch_status_is_cached(monkeypatch):
    calls = {"n": 0}

    def fake_view(args, cwd=None):
        calls["n"] += 1
        return {"number": 1, "state": "OPEN", "title": "t", "url": "u",
                "isDraft": False, "statusCheckRollup": []}

    monkeypatch.setattr(pr, "_gh_pr_view", fake_view)
    pr._cache.clear()
    pr.fetch_status("https://github.com/o/n/pull/1")
    pr.fetch_status("https://github.com/o/n/pull/1")
    assert calls["n"] == 1  # second call served from cache

"""Cloud status lookup: GET-only, token-safe, any error -> unknown, transitions -> events.

A throwaway local HTTP server stands in for the API; the body is the shape of a real
response for the demo session (session_01AAA…), trimmed of its 20 KB system prompt.
"""
import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from agent_view import cloudstatus, events, remote, state

SID = "session_01AAAAAAAAAAAAAAAAAAAAAA"
TOKEN = "test-token-DO-NOT-LEAK-0123456789"


def body(**over):
    d = {
        "id": "cse_01AAAAAAAAAAAAAAAAAAAAAA", "status": "paused", "worker_status": "idle",
        "status_bucket": "completed", "connection_status": "disconnected",
        "environment_kind": "byoc", "requires_action_details_list": [],
        "created_at": "2026-10-01T17:19:32.675078Z", "last_event_at": "2026-10-01T17:20:24.645572Z",
        "post_turn_summary": {
            "status_category": "completed", "needs_action": "",
            "status_detail": "hostname, pwd, git HEAD, kubectl context, skills listed",
            "recent_action": "Read-only diagnostic complete",
        },
        "external_metadata": {"current_branches": {"": "claude/read-only-diagnostic-abc123"}},
    }
    d.update(over)
    return {"response_shape": d}  # the API nests the session under this key


FAKE_SECRETS = [
    "sk-ant-oat01-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
    "ghp_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K27uhbUJU1p1r",
    "AKIAIOSFODNN7EXAMPLE",
]
PROBE_TEXT = (
    "hostname: runner-7f9c\npwd: /home/user/bitso-web\nHEAD: 0123456789abcdef0123456789abcdef01234567\n"
    "kubectl context: bitso-stage\nsignadot: not installed\n"
    "skills: ship-pr, create-change, code-review\n/ship-pr resolves: yes\n"
    f"env dump: ANTHROPIC_API_KEY={FAKE_SECRETS[0]} GITHUB_TOKEN={FAKE_SECRETS[1]} "
    f"jwt={FAKE_SECRETS[2]} aws={FAKE_SECRETS[3]}\n" + "padding line\n" * 60
)


def ev(seq, etype, payload, source="worker"):
    return {"event_id": f"e{seq}", "event_type": etype, "source": source, "sequence_num": str(seq),
            "created_at": f"2026-10-01T17:20:{seq:02d}.000000Z", "payload": payload}


def events_body(text=PROBE_TEXT):
    """Newest-first, like the API: noise, tool use/result, an earlier and the final assistant message."""
    evs = [
        ev(9, "result", {"type": "result", "subtype": "success", "is_error": False, "result": text}),
        ev(8, "assistant", {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}),
        ev(7, "system", {"type": "system", "subtype": "status", "status": "idle"}),
        ev(6, "env_manager_log", {"type": "env_manager_log", "data": {"line": "noise"}}),
        ev(5, "user", {"type": "user", "message": {"content": [
            {"type": "tool_result", "content": [{"type": "text", "text": "0123456789abcdef0123456789abcdef01234567"}]}]}}),
        ev(4, "assistant", {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "Let me run the checks."},
            {"type": "tool_use", "name": "Bash", "input": {"command": "git rev-parse HEAD"}}]}}),
        ev(3, "system", {"type": "system", "subtype": "hook_started"}),
        ev(2, "user", {"type": "user", "message": {"content": "Read-only task. Print hostname."}}, source="client"),
        ev(1, "system", {"type": "system", "subtype": "init"}),
    ]
    return {"data": evs, "resume_cursor": "1"}


class Api:
    """Fake API: records every request; serves ``self.payload`` / ``self.code``."""

    def __init__(self):
        self.seen, self.payload, self.code, self.redirect = [], body(), 200, None
        self.events = events_body()  # served at …/events
        api = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _handle(self):
                api.seen.append((self.command, self.path, {k.lower(): v for k, v in self.headers.items()}))
                if api.redirect:
                    self.send_response(302)
                    self.send_header("Location", api.redirect)
                    self.end_headers()
                    return
                raw = json.dumps(api.events if self.path.endswith('/events') else api.payload).encode()
                self.send_response(api.code)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = _handle

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_port}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()


@pytest.fixture
def api(monkeypatch, tmp_path):
    monkeypatch.delenv("AGENT_VIEW_NO_STATUS", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", TOKEN)
    monkeypatch.setenv("AGENT_ATTENTION_DIR", str(tmp_path / "state"))
    a = Api()
    monkeypatch.setattr(cloudstatus, "BASE_URL", a.url)
    yield a
    a.srv.shutdown()


# --- derivation --------------------------------------------------------------


@pytest.mark.parametrize("over,state_", [
    ({}, "finished"),                                                       # idle + completed (the real demo)
    ({"status_bucket": "in_progress", "post_turn_summary": {"status_category": "working"}}, "idle"),
    ({"worker_status": "running"}, "running"),
    ({"worker_status": "requires_action"}, "needs-input"),
    ({"requires_action_details_list": [{"tool": "x"}]}, "needs-input"),
    ({"post_turn_summary": {"status_category": "blocked", "needs_action": "Approve the deploy?"}}, "needs-input"),
    ({"status": "failed"}, "failed"),
    ({"archived_at": "2026-10-01T18:00:00Z"}, "finished"),
    ({"worker_status": "something-new"}, "unknown"),
])
def test_derive_states(over, state_):
    assert cloudstatus.derive(body(**over)).state == state_


def test_derive_extracts_detail_and_runner_branch():
    st = cloudstatus.derive(body())
    assert st.detail == "hostname, pwd, git HEAD, kubectl context, skills listed"
    assert st.remote_branch == "claude/read-only-diagnostic-abc123"
    assert st.last_event_at.startswith("2026-10-01T17:20")


def test_derive_redacts_status_detail():
    d = body()
    d["response_shape"]["post_turn_summary"]["status_detail"] = f"pushed with GITHUB_TOKEN={FAKE_SECRETS[1]}"
    st = cloudstatus.derive(d)
    assert FAKE_SECRETS[1] not in st.detail
    assert "<redacted>" in st.detail


def test_derive_rejects_junk():
    for junk in (None, [], "x", {"response_shape": "nope"}):
        assert cloudstatus.derive(junk).state == "unknown"


# --- the request: GET only, correct path, token only in the header ------------


def test_fetch_is_a_single_get_with_the_cli_headers(api):
    st = cloudstatus.fetch(SID)
    assert st.state == "finished"
    ((method, path, headers),) = api.seen
    assert (method, path) == ("GET", f"/v1/code/sessions/{SID}")
    assert headers["authorization"] == f"Bearer {TOKEN}"
    assert headers["anthropic-version"] == "2023-06-01"


def test_nothing_but_get_is_ever_sent(api):
    remote.record_from_output(json.dumps({"ok": True, "session_id": SID, "title": "t",
                                          "url": f"https://claude.ai/code/{SID}"}))
    remote.refresh_status(remote.discover(agents=[], panes=[]), force=True)
    remote.discover(agents=[], panes=[], refresh=True)
    assert api.seen and {m for m, _, _ in api.seen} == {"GET"}


@pytest.mark.parametrize("code,reason", [
    (404, "session not found"), (401, "not authorized"), (403, "not authorized"),
    (500, "http 500"),
])
def test_http_errors_fall_back_to_unknown(api, code, reason):
    api.code = code
    st = cloudstatus.fetch(SID)
    assert (st.state, st.reason) == ("unknown", reason)


def test_redirects_are_refused_so_the_bearer_cannot_be_forwarded(api):
    api.redirect = "http://127.0.0.1:1/steal"
    st = cloudstatus.fetch(SID)
    assert st.state == "unknown"
    assert len(api.seen) == 1  # followed nothing


def test_unreachable_server_and_bad_json_are_unknown(api, monkeypatch):
    monkeypatch.setattr(cloudstatus, "BASE_URL", "http://127.0.0.1:1")
    assert cloudstatus.fetch(SID).reason == "lookup failed"
    monkeypatch.setattr(cloudstatus, "BASE_URL", api.url)
    api.payload = "just a string"
    assert cloudstatus.fetch(SID).state == "unknown"


def test_no_credential_is_unknown_and_makes_no_request(api, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN")
    monkeypatch.setattr(cloudstatus.sys, "platform", "linux")
    st = cloudstatus.fetch(SID)
    assert (st.state, st.reason) == ("unknown", "no credential")
    assert api.seen == []


def test_opt_out_makes_no_request(api, monkeypatch):
    monkeypatch.setenv("AGENT_VIEW_NO_STATUS", "1")
    assert cloudstatus.fetch(SID).state == "unknown"
    assert api.seen == []


# --- the keychain token is read once, not once per request -----------------------


@pytest.fixture
def keychain(monkeypatch):
    """A fake `security` that counts spawns; the credential is not in the environment."""
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setattr(cloudstatus.sys, "platform", "darwin")

    class K:
        spawns = 0
        expires_ms = (time.time() + 3600) * 1000
        rc = 0

    def run(cmd, **k):
        K.spawns += 1
        out = json.dumps({"claudeAiOauth": {"accessToken": TOKEN, "expiresAt": K.expires_ms}})
        return subprocess.CompletedProcess(cmd, K.rc, stdout=out, stderr="")

    monkeypatch.setattr(cloudstatus.subprocess, "run", run)
    return K


def test_keychain_token_is_read_once_per_process(keychain):
    assert [cloudstatus._token() for _ in range(5)] == [(TOKEN, None)] * 5
    assert keychain.spawns == 1


def test_parallel_first_lookups_share_one_keychain_read(keychain):
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(8) as ex:
        results = list(ex.map(lambda _: cloudstatus._token(), range(8)))
    assert results == [(TOKEN, None)] * 8 and keychain.spawns == 1


def test_an_expiring_or_forgotten_token_is_read_again(keychain):
    cloudstatus._token()
    cloudstatus.forget_token()
    cloudstatus._token()
    assert keychain.spawns == 2
    keychain.expires_ms = (time.time() + 10) * 1000  # inside the 30s margin: don't trust it
    cloudstatus.forget_token()
    cloudstatus._token()
    cloudstatus._token()
    assert keychain.spawns == 4


def test_failures_are_not_cached(keychain):
    keychain.rc = 1
    assert cloudstatus._token() == (None, "no credential")
    keychain.rc = 0
    assert cloudstatus._token() == (TOKEN, None)  # the keychain was unlocked meanwhile
    assert keychain.spawns == 2


def test_a_rejected_token_is_dropped_so_a_refreshed_one_is_picked_up(api, keychain):
    api.code = 401
    cloudstatus._token()
    assert cloudstatus.fetch(SID).reason == "not authorized"
    cloudstatus._token()
    assert keychain.spawns == 2  # the 401 forgot it


def test_many_lookups_spawn_security_once(api, keychain):
    for _ in range(4):
        cloudstatus.fetch(SID)
        cloudstatus.fetch_peek(SID)
    assert len(api.seen) == 8 and keychain.spawns == 1


# --- transitions -> events ----------------------------------------------------


def _events(tmp_path):
    p = tmp_path / "state" / "agent-events.log"
    return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []


def _register():
    remote.record_from_output(json.dumps({"ok": True, "session_id": SID, "title": "Read-only diagnostic output",
                                          "url": f"https://claude.ai/code/{SID}?from=cli&m=0",
                                          "pool_id": "ccpool_x"}))


def test_finished_is_announced_exactly_once_in_the_fleet_shape(api, tmp_path):
    _register()
    for _ in range(3):  # three polls, one state: one event
        remote.refresh_status(remote.discover(agents=[], panes=[]), force=True)
    evs = [e for e in _events(tmp_path) if e["event"] != "remote-created"]
    assert [e["event"] for e in evs] == ["remote-finished"]
    e = evs[0]
    assert {"pane_id", "location", "agent", "event", "message", "ts"} <= set(e)
    assert (e["stream"], e["kind"], e["session_id"], e["status"]) == ("remote", "remote", SID, "finished")
    assert e["previous_status"] == "unknown"
    assert e["remote_branch"] == "claude/read-only-diagnostic-abc123"
    assert "listed" in e["status_detail"] and e["url"] == f"https://claude.ai/code/{SID}"


def test_running_then_needs_input_then_finished_emit_only_the_notable_ones(api, tmp_path):
    _register()
    seq = [("running", {"worker_status": "running"}), ("needs", {"worker_status": "requires_action"}),
           ("running2", {"worker_status": "running"}), ("done", {})]
    for _, over in seq:
        api.payload = body(**over)
        remote.refresh_status(remote.discover(agents=[], panes=[]), force=True)
    names = [e["event"] for e in _events(tmp_path)]
    assert names == ["remote-created", "remote-needs-input", "remote-finished"]  # no running/idle noise


def test_failed_lookup_neither_emits_nor_clobbers_the_last_status(api, tmp_path):
    _register()
    remote.refresh_status(remote.discover(agents=[], panes=[]), force=True)
    api.code = 500
    (s,) = remote.discover(agents=[], panes=[])
    remote.refresh_status([s], force=True)
    assert s.status == "unknown" and "http 500" in s.status_text  # reads unknown this run
    assert state.load_remote()[SID].status == "finished"           # last good value kept
    api.code = 200
    remote.refresh_status(remote.discover(agents=[], panes=[]), force=True)
    assert [e["event"] for e in _events(tmp_path)].count("remote-finished") == 1  # no re-announce


def test_stale_active_state_reads_unknown_but_finished_stays_finished(api, monkeypatch):
    _register()
    api.payload = body(worker_status="running")
    (s,) = remote.discover(agents=[], panes=[], refresh=True)
    assert s.status == "running"
    s.now += 3600
    assert s.status == "unknown" and "last seen running" in s.status_text
    api.payload = body()
    (s,) = remote.discover(agents=[], panes=[])
    remote.refresh_status([s], force=True)
    s.now += 3600
    assert s.status == "finished"


def test_the_token_never_reaches_any_output_or_file(api, tmp_path, capsys):
    from agent_view.cli import main

    _register()
    main(["remote"])
    main(["remote", "watch", "--once"])
    main(["remote", "--json"])
    out = capsys.readouterr()
    assert TOKEN not in out.out and TOKEN not in out.err
    for f in (tmp_path / "state").rglob("*"):
        if f.is_file():
            assert TOKEN.encode() not in f.read_bytes(), f


def test_watch_exits_when_everything_is_terminal(api, tmp_path):
    from agent_view.cli import main

    _register()
    assert main(["remote", "watch", "--interval", "0.05", "--timeout", "5"]) == 0
    assert [e["event"] for e in _events(tmp_path)][-1] == "remote-finished"
    api.payload = body(worker_status="running")
    state.update_remote_status(SID, "running")
    assert main(["remote", "watch", "--interval", "0.05", "--timeout", "0.3"]) == 2  # still running: times out


def test_watch_once_shows_unknown_when_this_passes_lookup_fails(api, capsys):
    """A failed lookup must read unknown this pass, not a cached 'finished'."""
    from agent_view.cli import main

    _register()
    main(["remote", "watch", "--once"])
    assert "finished" in capsys.readouterr().err
    api.code = 500
    main(["remote", "watch", "--once"])
    err = capsys.readouterr().err
    assert "unknown" in err and "http 500" in err and "last seen finished" in err
    assert state.load_remote()[SID].status == "finished"  # but the last good value is kept


# --- last message / tail ------------------------------------------------------


def test_redact_removes_token_like_strings_but_keeps_readable_facts():
    from agent_view.redact import redact

    out = redact(PROBE_TEXT)
    for secret in FAKE_SECRETS:
        assert secret not in out
    assert out.count("<redacted>") >= 4
    for keep in ("hostname: runner-7f9c", "0123456789abcdef0123456789abcdef01234567",  # git sha
                 "kubectl context: bitso-stage", "session_01AAAAAAAAAAAAAAAAAAAAAA", "/ship-pr resolves: yes"):
        assert keep in redact(keep) == keep
    assert redact("Authorization: Bearer abcdefghij1234567890xyz") == "Authorization: Bearer <redacted>"
    assert redact("password = hunter2hunter2") == "password=<redacted>"
    assert "<redacted>" in redact("-----BEGIN RSA PRIVATE KEY-----\nMIIE\n-----END RSA PRIVATE KEY-----")
    assert redact("x" * 10, extra=["xxxxxxxxxx"]) == "<redacted>"


def test_excerpt_is_capped_collapsed_and_redacted():
    from agent_view.redact import excerpt

    out = excerpt(PROBE_TEXT)
    assert len(out) <= 500 and "\n" not in out and out.startswith("hostname: runner-7f9c pwd:")
    assert not any(sec in out for sec in FAKE_SECRETS)
    assert excerpt("a b\n c") == "a b c"


def test_last_message_is_the_newest_assistant_text_via_get_only(api):
    lm = cloudstatus.fetch_last_message(SID)
    assert lm.ok and lm.kind == "assistant" and lm.text.startswith("hostname: runner-7f9c")
    assert not any(sec in lm.text for sec in FAKE_SECRETS)
    ((method, path, headers),) = api.seen
    assert (method, path) == ("GET", f"/v1/code/sessions/{SID}/events")
    assert headers["authorization"] == f"Bearer {TOKEN}"


def test_last_message_falls_back_to_the_result_event(api):
    api.events = events_body()
    api.events["data"] = [e for e in api.events["data"] if e["event_type"] != "assistant"]
    lm = cloudstatus.fetch_last_message(SID)
    assert lm.kind == "result" and "signadot" in lm.text


@pytest.mark.parametrize("code,reason", [(404, "session not found"), (403, "not authorized"), (502, "http 502")])
def test_last_message_errors_are_fixed_reasons(api, code, reason):
    api.code = code
    lm = cloudstatus.fetch_last_message(SID)
    assert not lm.ok and lm.reason == reason


def test_last_message_with_no_assistant_event(api):
    api.events = {"data": [ev(1, "system", {"type": "system", "subtype": "init"})]}
    assert cloudstatus.fetch_last_message(SID).reason == "no assistant message yet"


def test_tail_is_oldest_first_skips_noise_and_redacts(api):
    t = cloudstatus.fetch_tail(SID, 10)
    kinds = [e.kind for e in t.entries]
    assert kinds == ["user", "assistant", "tool_use", "tool_result", "status", "assistant", "result"]
    assert t.entries[0].text.startswith("Read-only task")
    assert "Bash" in t.entries[2].text and "git rev-parse HEAD" in t.entries[2].text
    blob = " ".join(e.text for e in t.entries)
    assert not any(sec in blob for sec in FAKE_SECRETS) and all(len(e.text) <= 160 for e in t.entries)
    assert [e.kind for e in cloudstatus.fetch_tail(SID, 2).entries] == ["assistant", "result"]


def test_finished_event_carries_a_capped_redacted_excerpt(api, tmp_path):
    _register()
    remote.refresh_status(remote.discover(agents=[], panes=[]), force=True)
    (e,) = [x for x in _events(tmp_path) if x["event"] == "remote-finished"]
    assert e["last_message"].startswith("hostname: runner-7f9c") and len(e["last_message"]) <= 500
    assert "last message: hostname: runner-7f9c" in e["message"]
    assert not any(sec in json.dumps(e) for sec in FAKE_SECRETS) and TOKEN not in json.dumps(e)
    assert state.load_remote()[SID].last_message == e["last_message"]
    assert {m for m, _, _ in api.seen} == {"GET"}


def test_cli_show_last_and_tail(api, capsys):
    from agent_view.cli import main

    _register()
    assert main(["remote", "show", SID, "--last"]) == 0
    out = capsys.readouterr().out
    assert "last assistant" in out and "kubectl context: bitso-stage" in out
    assert "/ship-pr resolves: yes" in out and not any(sec in out for sec in FAKE_SECRETS)
    assert main(["remote", "show", SID, "--tail", "3", "--json"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert [e["kind"] for e in d["tail"]] == ["status", "assistant", "result"]
    assert main(["remote", "show", SID, "--last", "--max", "30"]) == 0
    assert "…" in capsys.readouterr().out
    api.code = 404
    assert main(["remote", "show", SID, "--last"]) == 0
    assert "unavailable: session not found" in capsys.readouterr().out


def test_cli_show_without_flags_is_the_plain_summary(api, capsys):
    from agent_view.cli import main

    _register()
    assert main(["remote", "show", SID]) == 0
    assert "kind     : remote" in capsys.readouterr().out


def test_missing_excerpt_is_backfilled_without_a_second_event(api, tmp_path):
    _register()
    api.events = {"data": []}  # first pass: the session said nothing yet
    remote.refresh_status(remote.discover(agents=[], panes=[]), force=True)
    assert state.load_remote()[SID].last_message is None
    api.events = events_body()
    remote.refresh_status(remote.discover(agents=[], panes=[]), force=True)
    assert state.load_remote()[SID].last_message.startswith("hostname: runner-7f9c")
    assert [e["event"] for e in _events(tmp_path)].count("remote-finished") == 1


# --- fetch_peek ------------------------------------------------------------------


def test_fetch_peek_is_chronological_redacted_and_get_only(api):
    pk = cloudstatus.fetch_peek(SID)
    assert pk.reason is None
    kinds = [i.kind for i in pk.items]
    assert kinds == ["user", "assistant", "tool_use", "tool_result", "assistant"]
    tool = next(i for i in pk.items if i.kind == "tool_use")
    assert tool.lines == ["Bash: git rev-parse HEAD"]
    assert pk.items[1].lines == ["Let me run the checks."]  # text before its tool call, same event
    blob = "\n".join(line for i in pk.items for line in i.lines)
    assert not any(sec in blob for sec in FAKE_SECRETS) and TOKEN not in blob
    assert "hostname: runner-7f9c" in blob
    assert {m for m, _, _ in api.seen} == {"GET"} and len(api.seen) == 1


def test_fetch_peek_caps_lines_and_width(api):
    pk = cloudstatus.fetch_peek(SID, max_events=2, width=30)
    assert len(pk.items) == 2
    assert all(len(line) <= 30 for i in pk.items for line in i.lines)
    assert max(len(i.lines) for i in pk.items) <= 24


@pytest.mark.parametrize("code,reason", [(404, "session not found"), (401, "not authorized"), (503, "http 503")])
def test_fetch_peek_errors_are_fixed_reasons(api, code, reason):
    api.code = code
    pk = cloudstatus.fetch_peek(SID)
    assert pk.items == [] and pk.reason == reason


def test_fetch_peek_without_a_credential_makes_no_request(api, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN")
    monkeypatch.setattr(cloudstatus.sys, "platform", "linux")
    assert cloudstatus.fetch_peek(SID).reason == "no credential" and api.seen == []


def test_derive_reads_the_pool_name():
    d = body(self_hosted_runner_state={"pool_id": "ccpool_x", "pool_name": "main"})
    assert cloudstatus.derive(d).pool_name == "main"

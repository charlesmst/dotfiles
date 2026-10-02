"""agent-view CLI.

Subcommands:
  (none)          open the Exposé TUI (run from a tmux popup)
  event pending   mark the calling pane as needing attention (hook entrypoint)
  event clear     clear the pending marker (hook / tmux focus entrypoint)
  status          tmux status-line fragment (pending count)
  install         wire hook configs into Claude / Cursor / Codex
  doctor          print discovery snapshot for debugging
  remote          list/open/forget/record/watch/show remote (cloud) sessions (`claude --environment`)

Hook entrypoints must stay fast and never fail the calling agent: they
swallow their own errors and exit 0.
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def _read_hook_payload(args: argparse.Namespace) -> dict:
    """Hook payload from --payload JSON (Codex) or stdin JSON (Claude/Cursor)."""
    raw = getattr(args, "payload", None)
    if not raw and not sys.stdin.isatty():
        raw = sys.stdin.read()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _extract_message(payload: dict, fallback: str) -> str:
    # Claude Notification hooks carry "message"; Codex notify carries
    # "last-assistant-message"; Cursor hooks have neither.
    for key in ("message", "last-assistant-message", "last_assistant_message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


def _resolve_pane(args: argparse.Namespace) -> str | None:
    return getattr(args, "pane", None) or os.environ.get("TMUX_PANE") or None


def _maybe_push(args: argparse.Namespace, pane: str, action: str, message: str | None) -> None:
    """Always fire a best-effort push after the marker logic. Never raises/blocks.

    Sends one JSON datagram describing what just happened so a listener (e.g. an
    orchestrator) is pushed the instant an agent finishes, blocks, or opens a
    PR — no polling, no caller opt-in. Destination is ``--notify PATH`` if
    given, else the well-known default (``state.notify_sock``). Silent no-op
    when nothing is bound there.
    """
    try:
        import time

        from . import notify as notify_mod, state, tmux

        path = getattr(args, "notify", None) or state.notify_sock()
        notify_mod.send(path, {
            "pane_id": pane,
            "location": tmux.pane_location(pane),
            "agent": getattr(args, "agent", None),
            "event": action,  # pending | clear | pr
            "message": message,  # reason for pending; PR url for pr; None for clear
            "ts": time.time(),
        })
    except Exception:
        pass  # push is best-effort; must never affect the hook


def cmd_event(args: argparse.Namespace) -> int:
    from . import state, tmux

    try:
        pane = _resolve_pane(args)
        if not pane:
            return 0
        if args.action == "clear":
            state.clear_pending(pane)
            _maybe_push(args, pane, "clear", None)
            return 0
        if args.action == "pr":
            # Record a PR the agent just created. Fast + silent: only touches
            # disk when the payload is actually a `gh pr create` with a URL.
            from . import pr as pr_mod

            url = getattr(args, "url", None)
            if not url:
                raw = args.payload or ("" if sys.stdin.isatty() else sys.stdin.read())
                url = pr_mod.extract_pr_url(raw or "")
            if url:
                pr_mod.record(pane, url)
                _maybe_push(args, pane, "pr", url)
            return 0
        # action == "pending". Only consult the payload when no explicit
        # message was given (avoids blocking on stdin unnecessarily).
        payload = {} if args.message else _read_hook_payload(args)
        # Codex notify sends {"type": ...}; only turn-complete means pending.
        ptype = payload.get("type")
        if isinstance(ptype, str) and ptype != "agent-turn-complete":
            return 0
        if args.unless_focused and tmux.pane_is_focused(pane):
            return 0
        message = args.message or _extract_message(payload, "needs attention")
        # Event kind lets consumers tell "blocked/asking" (notification) from
        # "finished a turn" (stop / turn-complete). Fall back to the payload
        # type when no explicit --event was passed.
        event = args.event
        if not event and isinstance(ptype, str):
            event = ptype
        state.mark_pending(pane, message=message, agent=args.agent, event=event)
        _maybe_push(args, pane, "pending", message)
    except Exception:
        pass  # hooks must never break the agent
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    from . import state

    count = state.count_pending()
    remote_count = state.count_remote()
    parts = []
    if count:
        parts.append(f"#[fg=yellow,bold]● {count}#[default]")
    if remote_count:  # cloud sessions exist (status unknowable locally)
        parts.append(f"#[fg=magenta,bold]⇢ {remote_count}#[default]")
    print(" ".join(parts), end="")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from . import discovery
    from .model import format_age

    from . import remote

    agents = discovery.discover()
    remotes = remote.discover(agents, refresh=True)
    if not agents:
        print("no live agent panes found")
    for a in agents:
        pending = f"  pending: {a.pending_message}" if a.pending_message else ""
        print(
            f"{a.kind.value:7} {a.state.value:8} {a.location:30} "
            f"pid={a.agent_pid:<8} idle={format_age(a.idle_seconds)}{pending}"
        )
    for s in remotes:
        where = (s.location or s.ref.pane_id or "?") + ("" if s.pane_alive else " (gone)")
        print(
            f"{'remote':7} {s.status:8} {where:30} {s.session_id}  "
            f"{s.flag if s.awaiting_flag else s.url}"
        )
    return 0


def _print_resolution_error(res, ident: str) -> None:
    from .model import format_age

    print(f"error: {res.error}", file=sys.stderr)
    if res.candidates:
        print("  candidates:", file=sys.stderr)
        for a in res.candidates:
            print(f"    {a.location:20} {a.kind.value:7} {a.window_name}", file=sys.stderr)
    else:
        print(f"  (run `agent-view ls` to see live agents)", file=sys.stderr)


def _truncate(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _pr_status_map(reports, children, derive: bool):
    """{pane_id: [(url, PRStatus|None), ...]} fetched concurrently for all PRs."""
    from concurrent.futures import ThreadPoolExecutor

    from . import pr as pr_mod

    # Flatten to (pane_id, url) pairs so every PR across every agent is fetched
    # in one concurrent pass.
    pairs: list[tuple[str, str]] = []
    for r in reports:
        for url in pr_mod.pane_pr_urls(r.pane, children, derive=derive):
            pairs.append((r.pane.pane_id, url))
    if not pairs:
        return {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        statuses = list(ex.map(pr_mod.fetch_status, [u for _, u in pairs]))
    out: dict[str, list] = {}
    for (pid, url), st in zip(pairs, statuses):
        out.setdefault(pid, []).append((url, st))
    return out


def _remote_sessions(agents):
    """Cloud sessions (`claude --environment …`) known from scrollback/records."""
    from . import remote

    return remote.discover(agents, refresh=True)


def _print_remote_section(remotes) -> None:
    """Remote rows under the local list; prints nothing when there are none."""
    from . import remote

    if not remotes:
        return
    print(f"\nremote sessions · {len(remotes)} (status: read-only lookup; unknown → open the URL)")
    for s in remotes:
        for line in remote.row_lines(s):
            print(line)


def cmd_ls(args: argparse.Namespace) -> int:
    """One-shot list of live agents + status (render once, machine-readable)."""
    from . import discovery, report

    agents = discovery.discover()
    reports = [report.report_for(a) for a in agents]
    remotes = [] if args.no_remote else _remote_sessions(agents)

    want_msg = args.last_message
    want_pr = args.pr
    children = None
    if want_msg or want_pr:
        children, _ = discovery.process_snapshot()
    prs = _pr_status_map(reports, children, derive=want_pr) if want_pr else {}

    if args.json:
        rows = []
        for r in reports:
            d = r.to_dict()
            if want_msg:
                msg, source = report.last_message(r.pane, children)
                d["last_message"] = msg
                d["transcript_source"] = source
            if want_pr and r.pane.pane_id in prs:
                d["prs"] = [
                    st.to_dict() if st else {"url": url, "state": "unknown"}
                    for url, st in prs[r.pane.pane_id]
                ]
            rows.append(d)
        rows.extend(s.to_dict() for s in remotes)  # kind: "remote"
        print(json.dumps(rows, indent=2))
        return 0

    if not reports:
        print("no live agent panes found")
        _print_remote_section(remotes)
        return 0

    for r in reports:
        p = r.pane
        line = (
            f"{p.location:16} {p.kind.value:7} {r.status.value:8} "
            f"{p.window_name:18.18} idle={p.idle_seconds:>4.0f}s"
        )
        if r.reason and r.status.value in ("done", "blocked"):
            line += f"  — {_truncate(r.reason, 50)}"
        print(line)
        if want_pr and p.pane_id in prs:
            for url, st in prs[p.pane_id]:
                print(f"                 PR {st.summary() if st else url}")
        if want_msg:
            msg, source = report.last_message(r.pane, children)
            if msg:
                print(f"                 last[{source}]: {_truncate(msg, 90)}")
    counts: dict[str, int] = {}
    for r in reports:
        counts[r.status.value] = counts.get(r.status.value, 0) + 1
    summary = " · ".join(f"{k} {v}" for k, v in sorted(counts.items()))
    print(f"\n{len(reports)} agents · {summary}")
    _print_remote_section(remotes)
    return 0


def _show_remote(s, as_json: bool) -> int:
    if as_json:
        print(json.dumps(s.to_dict(), indent=2))
        return 0
    r = s.ref
    where = (s.location or r.pane_id or "?") + ("" if s.pane_alive else " (pane gone)")
    print(f"id       : {r.session_id}")
    print("kind     : remote")
    print(f"status   : {s.status_text}")
    print(f"url      : {r.url}")
    if r.remote_branch:
        print(f"branch   : {r.remote_branch}  (the runner's own branch)")
    if r.title:
        print(f"title    : {r.title}")
    if r.environment:
        print(f"env      : {r.environment}")
    print(f"launched : {s.age} ago from {where}" + (
        "  (first seen; launch time unknown)" if r.created_source == "first-seen" else ""
    ))
    if s.awaiting_flag:
        print(f"pane     : {s.flag}")
    if r.repo or r.worktree or r.branch:
        print(f"repo     : {'/'.join(filter(None, [r.repo, r.worktree]))}"
              f"{'@' + r.branch if r.branch else ''}  (launch dir; not verified on the runner)")
    if r.prompt:
        print(f"prompt   : {r.prompt}")
    return 0


def _remote_record(args: argparse.Namespace) -> int:
    """Launch-time registry: pass stdin through unchanged, record any cloud session in it.

    ``claude -p "$P" --environment ccpool_… --output-format json | agent-view remote record``
    Output is byte-for-byte what the launcher would have seen. Like the hooks it
    never fails the caller: an unparseable stream only warns on stderr.
    """
    data = sys.stdin.read() if not sys.stdin.isatty() else ""
    sys.stdout.write(data)
    sys.stdout.flush()
    try:
        from . import remote

        pane = args.pane or os.environ.get("TMUX_PANE") or None
        got = remote.record_from_output(
            data, pane_id=pane, prompt=args.prompt, environment=args.environment
        )
        if not got and not remote.parse_created(data):
            print("agent-view: no cloud session found in input; nothing recorded",
                  file=sys.stderr)
        if args.watch and not os.environ.get("AGENT_VIEW_NO_WATCH"):
            import subprocess

            for ref in got:  # one detached poller per session; it exits when the session ends
                subprocess.Popen(
                    [sys.executable, "-m", "agent_view.cli", "remote", "watch", ref.session_id,
                     "--timeout", str(args.timeout)],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
    except Exception:
        pass  # a registry failure must never break the launch
    return 0


def _remote_show(args: argparse.Namespace) -> int:
    """Details of one remote session; ``--last`` / ``--tail N`` read its events (GET only).

    ``--last`` prints the session's last assistant message, ``--tail N`` its last N events
    as one redacted line each. Both are live read-only lookups of what the session itself
    reported; nothing is ever sent into it, and any error prints a fixed reason.
    """
    from . import cloudstatus, remote

    sessions = remote.discover(refresh=True)
    ident = args.id or (sessions[0].session_id if sessions else "")
    res = remote.resolve(sessions, ident)
    if res.session is None:
        print(f"error: {res.error}", file=sys.stderr)
        return 1
    s = res.session
    last = cloudstatus.fetch_last_message(s.session_id) if args.last else None
    tail = cloudstatus.fetch_tail(s.session_id, args.tail) if args.tail else None
    if args.json:
        d = s.to_dict()
        if last is not None:
            d["last_message_live"] = {"kind": last.kind, "at": last.at, "reason": last.reason,
                                      "text": last.text[: args.max]}
        if tail is not None:
            d["tail"] = [e.__dict__ for e in tail.entries]
            d["tail_reason"] = tail.reason
        print(json.dumps(d, indent=2))
        return 0
    if last is None and tail is None:
        return _show_remote(s, False)
    print(f"{s.session_id}  {s.status_text}")
    if last is not None:
        print(f"\nlast {last.kind or 'message'}" + (f"  ({last.at})" if last.at else "") + ":")
        if last.ok:
            body = last.text if len(last.text) <= args.max else last.text[: args.max - 1] + "…"
            print("\n".join("  " + line for line in body.splitlines()))
        else:
            print(f"  (unavailable: {last.reason})")
    if tail is not None:
        print("\nevents:")
        if tail.entries:
            for e in tail.entries:
                print(f"  {e.at[11:19] or '--:--:--'}  {e.kind:11} {e.text}")
        else:
            print(f"  (unavailable: {tail.reason or 'none'})")
    return 0


def _remote_watch(args: argparse.Namespace) -> int:
    """Poll cloud status, append transition events, exit when nothing is still active.

    Each session is looked up with a read-only GET; a change into finished / failed /
    needs-input appends one event to agent-events.log. One watch per session is
    plenty (and several are safe: transitions are claimed under a lock).
    Exit codes: 0 all watched sessions reached a terminal state · 2 timed out.
    """
    import time

    from . import cloudstatus, remote

    deadline = time.monotonic() + args.timeout
    while True:
        sessions = remote.discover(scan=False)
        if args.id:
            res = remote.resolve(sessions, args.id)
            if res.session is None:
                print(f"error: {res.error}", file=sys.stderr)
                return 1
            sessions = [res.session]
        # Judge and print the very objects the lookup updated: a failed lookup must
        # read unknown this pass, not fall back to a re-read cached value.
        for ev in remote.refresh_status(sessions, force=True):
            print(json.dumps(ev, ensure_ascii=False), flush=True)
        if args.once:
            if not args.json:
                for s in sessions:
                    print(f"{s.session_id}  {s.status_text}", file=sys.stderr)
            return 0
        if all(s.ref.status in cloudstatus.TERMINAL for s in sessions):
            return 0
        if time.monotonic() >= deadline:
            return 2
        time.sleep(args.interval)


def cmd_remote(args: argparse.Namespace) -> int:
    """List / open / forget / record remote (cloud) sessions started with `--environment`."""
    if args.action == "record":
        return _remote_record(args)
    if args.action == "watch":
        return _remote_watch(args)
    if args.action == "show":
        return _remote_show(args)

    from . import remote, state

    sessions = remote.discover(refresh=args.action == "list")
    if args.action == "list":
        if args.json:
            print(json.dumps([s.to_dict() for s in sessions], indent=2))
            return 0
        if not sessions:
            print("no remote sessions known")
            return 0
        for s in sessions:
            for line in remote.row_lines(s):
                print(line)
        print(f"\n{len(sessions)} remote sessions · status: read-only lookup; unknown → open the URL")
        return 0

    # open / forget: an id, or (open only) default to the newest session.
    if args.id:
        res = remote.resolve(sessions, args.id)
        target = res.session
        if target is None:
            print(f"error: {res.error}", file=sys.stderr)
            for c in res.candidates or []:
                print(f"    {c.session_id}  {c.url}", file=sys.stderr)
            return 1
    elif args.action == "open" and sessions:
        target = sessions[0]
    else:
        print(f"error: `remote {args.action}` needs a session id", file=sys.stderr)
        return 1

    if args.action == "forget":
        state.dismiss_remote(target.session_id)
        print(f"forgot {target.session_id} (removed from agent-view only; the cloud session is untouched)")
        return 0
    import webbrowser

    print(target.url)
    webbrowser.open(target.url)
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    """Status + last message + metadata for one agent."""
    from . import discovery, report

    agents = discovery.discover()
    res = report.resolve(agents, args.id)
    if res.pane is None:
        if not res.candidates:  # not a local agent — maybe a remote session
            from . import remote

            rres = remote.resolve(remote.discover(agents, refresh=True), args.id)
            if rres.session is not None:
                return _show_remote(rres.session, args.json)
        _print_resolution_error(res, args.id)
        return 1

    rep = report.report_for(res.pane)
    children, _ = discovery.process_snapshot()
    msg, source = report.last_message(res.pane, children)

    from . import pr as pr_mod
    pr_urls = pr_mod.pane_pr_urls(res.pane, children, derive=not args.no_pr)
    pr_items = [(u, pr_mod.fetch_status(u)) for u in pr_urls]

    if args.json:
        d = rep.to_dict()
        d["last_message"] = msg
        d["transcript_source"] = source
        if pr_items:
            d["prs"] = [
                st.to_dict() if st else {"url": u, "state": "unknown"}
                for u, st in pr_items
            ]
        print(json.dumps(d, indent=2))
        return 0

    d = rep.to_dict()
    print(f"id       : {d['id']}  ({d['pane_id']})")
    print(f"kind     : {d['kind']}")
    print(f"status   : {d['status']}" + (f"  ⟵ {d['reason']}" if d["reason"] else ""))
    print(f"blocked  : {d['blocked']}")
    print(f"window   : {d['window']}")
    print(f"idle     : {d['idle']}  (pid {d['agent_pid']})")
    for i, (url, st) in enumerate(pr_items):
        label = "pr" if len(pr_items) == 1 else f"pr[{i + 1}]"
        print(f"{label:9}: {st.summary() if st else '(status unavailable)'}")
        print(f"           {url}")
    if msg:
        print(f"\nlast message  [{source}]:")
        for line in msg.splitlines()[:40]:
            print(f"  {line}")
        extra = len(msg.splitlines()) - 40
        if extra > 0:
            print(f"  … ({extra} more lines — use `agent-view transcript {d['id']}`)")
    else:
        print(f"\n(no message available; transcript source: {source})")
    return 0


def cmd_transcript(args: argparse.Namespace) -> int:
    """Dump the transcript for one agent, read from the agent's own files."""
    from . import discovery, report
    from . import transcript as transcript_mod

    agents = discovery.discover()
    res = report.resolve(agents, args.id)
    if res.pane is None:
        _print_resolution_error(res, args.id)
        return 1

    children, _ = discovery.process_snapshot()
    t = transcript_mod.resolve(res.pane, children)
    if not t and not args.no_pane_fallback:
        t = transcript_mod.pane_transcript(res.pane)

    turns = t.turns
    if args.role:
        wanted = set(args.role)
        turns = [tn for tn in turns if tn.role in wanted]
    if args.tail and args.tail > 0:
        turns = turns[-args.tail :]

    if args.json:
        print(json.dumps({
            "id": res.pane.location,
            "source": t.source,
            "path": t.path,
            "turns": [{"role": tn.role, "text": tn.text, "ts": tn.ts} for tn in turns],
        }, indent=2))
        return 0

    print(f"# transcript {res.pane.location}  [source: {t.source}"
          + (f" · {t.path}]" if t.path else "]"))
    if not turns:
        print("(empty)")
        return 0
    for tn in turns:
        print(f"\n─── {tn.role} ───")
        print(tn.text)
    return 0


def cmd_wait(args: argparse.Namespace) -> int:
    """Block only while an agent is actively working; return the moment it isn't.

    "Working" means the pane produced output within the last ~20s (agents
    stream while they think). Anything else — ``done``/``blocked`` (a hook
    marker), ``idle``/``stale`` (quiet), or the process being gone — means the
    agent is doing nothing, so ``wait`` returns straight away with that status.
    If a hook marker is present you get the precise ``done``/``blocked`` the
    instant it fires; otherwise you get ``idle`` after output stops.

    ``--startup S`` (default 0) guards the launch race: for the first S seconds,
    an agent that has not yet been seen working is not treated as finished, so
    "trigger then wait" doesn't return before the agent has started.

    Exit codes: 0 not-working (done/blocked/idle/stale/exited) · 2 timed out
    · 3 setup error.
    """
    import time

    from . import discovery, report

    ident = args.id
    agents = discovery.discover()
    res = report.resolve(agents, ident)
    if res.pane is None:
        _print_resolution_error(res, ident)
        return 3

    if not args.json:
        print(f"waiting while {res.pane.location} ({res.pane.kind.value}) is working  "
              f"timeout={args.timeout:.0f}s poll={args.interval:.0f}s", flush=True)

    started = time.monotonic()
    deadline = started + args.timeout
    seen_working = False
    outcome: dict | None = None
    while True:
        agents = discovery.discover()
        res = report.resolve(agents, ident)
        if res.pane is None:
            outcome = {"id": ident, "status": "exited",
                       "reason": "agent process no longer present"}
            break
        rep = report.report_for(res.pane)
        working = rep.status.value == "working"
        # A "working" pane can just be the animated TUI (per-second spinner,
        # backgrounded-agent indicator) repainting after the turn is logically
        # done — especially when there's no hook marker (focused pane). Trust
        # the transcript's end-of-turn signal over pane pixels.
        if working and rep.reason is None:
            if report.transcript_finished(res.pane) is True:
                outcome = rep.to_dict()
                outcome["status"] = "done"
                outcome["reason"] = "turn ended (transcript); pane still repainting"
                break
        if working:
            seen_working = True
        # Done the moment it isn't working. The only reason to keep waiting on a
        # not-working agent is the launch race: it may not have started yet.
        in_startup = (time.monotonic() - started) < args.startup and not seen_working
        if not working and not (in_startup and rep.status.value in ("idle", "stale")):
            outcome = rep.to_dict()
            break
        if time.monotonic() >= deadline:
            if not args.json:
                print("timed out", file=sys.stderr)
            else:
                print(json.dumps({"id": ident, "status": "timeout"}, indent=2))
            return 2
        if not args.json:
            phase = "working" if working else f"{rep.status.value} (startup grace)"
            print(f"  … {phase}  idle={res.pane.idle_seconds:.0f}s", flush=True)
        time.sleep(args.interval)

    msg = ""
    source = "none"
    if args.last_message and res.pane is not None:
        children, _ = discovery.process_snapshot()
        msg, source = report.last_message(res.pane, children)

    if args.json:
        if msg:
            outcome["last_message"] = msg
            outcome["transcript_source"] = source
        print(json.dumps(outcome, indent=2))
    else:
        print(f"\n{outcome['status']}"
              + (f"  ⟵ {outcome.get('reason')}" if outcome.get("reason") else ""))
        if msg:
            print(f"\nlast message  [{source}]:")
            for line in msg.splitlines()[:40]:
                print(f"  {line}")
    return 0


def _bind_listen_socket(path: str):
    """Bind an AF_UNIX datagram socket at ``path``, clearing a stale socket.

    Returns the bound socket. Raises ValueError if ``path`` exists as a
    non-socket (we won't delete arbitrary files) or OSError if bind fails.
    """
    import os
    import socket
    import stat as stat_mod

    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    if os.path.exists(path):
        if not stat_mod.S_ISSOCK(os.stat(path).st_mode):
            raise ValueError(f"{path} exists and is not a socket")
        os.unlink(path)  # stale socket from a previous listener
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    sock.bind(path)
    return sock


def cmd_listen(args: argparse.Namespace) -> int:
    """Bind the push-notify socket and print each datagram (one JSON per line).

    Generic reader: no filtering — a consumer parses/routes the lines itself.
    """
    import os

    from . import state

    path = args.path or (getattr(args, "notify", None) or state.notify_sock())
    try:
        sock = _bind_listen_socket(path)
    except (ValueError, OSError) as exc:
        print(f"error: cannot listen on {path}: {exc}", file=sys.stderr)
        return 1

    print(f"listening on {path}  (ctrl-c to stop)", file=sys.stderr, flush=True)
    try:
        while True:
            data, _ = sock.recvfrom(65536)
            print(data.decode("utf-8", "replace"), flush=True)
    except KeyboardInterrupt:
        return 0
    finally:
        sock.close()
        try:
            os.unlink(path)
        except OSError:
            pass


def cmd_install(args: argparse.Namespace) -> int:
    from .installer import run_install

    return run_install(dry_run=args.dry_run)


def cmd_view(args: argparse.Namespace) -> int:
    if not os.environ.get("TMUX"):
        print("agent-view must run inside tmux", file=sys.stderr)
        return 1
    from .tui.app import AgentViewApp

    AgentViewApp().run()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-view",
        description="Exposé-style tmux TUI for Claude/Codex/Cursor agent panes",
    )
    sub = parser.add_subparsers(dest="command")

    event = sub.add_parser("event", help="hook entrypoints (mark/clear pending, record pr)")
    event.add_argument("action", choices=["pending", "clear", "pr"])
    event.add_argument("--pane", help="tmux pane id (default: $TMUX_PANE)")
    event.add_argument("--message", help="pending reason to display")
    event.add_argument("--url", help="PR url to record (event pr; else parsed from payload)")
    event.add_argument("--agent", help="agent kind reporting the event")
    event.add_argument(
        "--event",
        help="hook event kind: stop | turn-complete (finished) | notification (blocked)",
    )
    event.add_argument(
        "--payload", help="hook payload as a JSON argument (Codex notify style)"
    )
    event.add_argument(
        "--notify", metavar="PATH",
        help="override the push-notify socket path (default: $AGENT_VIEW_NOTIFY_SOCK "
             "or <state>/events.sock). event always fires a best-effort JSON "
             "datagram (AF_UNIX/SOCK_DGRAM) here; never blocks.",
    )
    event.add_argument(
        "--unless-focused",
        action="store_true",
        help="skip marking pending when the pane is focused",
    )
    event.set_defaults(func=cmd_event)

    status = sub.add_parser("status", help="tmux status-line fragment")
    status.set_defaults(func=cmd_status)

    doctor = sub.add_parser("doctor", help="print discovered agents")
    doctor.set_defaults(func=cmd_doctor)

    ls = sub.add_parser("ls", help="list live agents + status (render once)")
    ls.add_argument("--json", action="store_true", help="machine-readable output")
    ls.add_argument("--last-message", "-m", action="store_true",
                    help="include each agent's last message (reads transcripts)")
    ls.add_argument("--pr", action="store_true",
                    help="include each agent's PR + live status (recorded, else branch-derived; needs gh)")
    ls.add_argument("--no-remote", action="store_true",
                    help="local panes only: omit remote (cloud) sessions "
                         "(`claude --environment …`), which are otherwise "
                         "listed after the panes / as kind=remote in --json")
    ls.set_defaults(func=cmd_ls)

    rem = sub.add_parser(
        "remote",
        help="remote (cloud) sessions started with `claude --environment` "
             "(list | open | forget | record | watch | show)",
    )
    rem.add_argument("action", nargs="?", choices=["list", "open", "forget", "record", "watch", "show"],
                     default="list",
                     help="record: pass stdin through and register the cloud session it "
                          "contains (pipe `claude -p … --environment … --output-format "
                          "json` into it)")
    rem.add_argument("id", nargs="?",
                     help="session id (or unique part), URL, or launching pane; "
                          "`open` defaults to the newest")
    rem.add_argument("--json", action="store_true")
    rem.add_argument("--pane", help="record: launching tmux pane id (default: $TMUX_PANE)")
    rem.add_argument("--prompt", help="record: the prompt that was sent (shown as the summary)")
    rem.add_argument("--environment", help="record: ccpool_… id if the output lacks pool_id")
    rem.add_argument("--watch", action="store_true",
                     help="record: also start a detached `remote watch` for each new session "
                          "(emits remote-finished / -failed / -needs-input events)")
    rem.add_argument("--last", action="store_true",
                     help="show: the session's last assistant message (read-only GET, redacted)")
    rem.add_argument("--tail", type=int, default=0, metavar="N",
                     help="show: the session's last N events, one redacted line each")
    rem.add_argument("--max", type=int, default=4000, help="show --last: max chars (default 4000)")
    rem.add_argument("--once", action="store_true", help="watch: one pass, then exit")
    rem.add_argument("--interval", type=float, default=30.0, help="watch: poll seconds (default: 30)")
    rem.add_argument("--timeout", type=float, default=21600.0,
                     help="watch: give up after this many seconds (default: 21600 = 6h)")
    rem.set_defaults(func=cmd_remote)

    show = sub.add_parser("show", help="status + last message for one agent")
    show.add_argument("id", help="agent id: location (stocks:3.1) or pane id (%%42)")
    show.add_argument("--json", action="store_true")
    show.add_argument("--no-pr", action="store_true",
                      help="skip the PR lookup (no gh calls)")
    show.set_defaults(func=cmd_show)

    tr = sub.add_parser("transcript", help="dump an agent's transcript from its files")
    tr.add_argument("id", help="agent id: location (stocks:3.1) or pane id (%%42)")
    tr.add_argument("--json", action="store_true")
    tr.add_argument("--tail", type=int, default=0, help="only the last N turns")
    tr.add_argument("--role", action="append",
                    help="filter to a role (repeatable): user/assistant/tool/system")
    tr.add_argument("--no-pane-fallback", action="store_true",
                    help="fail instead of falling back to live pane text")
    tr.set_defaults(func=cmd_transcript)

    wait = sub.add_parser("wait", help="block until an agent finishes / gets blocked")
    wait.add_argument("id", help="agent id: location (stocks:3.1) or pane id (%%42)")
    wait.add_argument("--json", action="store_true")
    wait.add_argument("--last-message", "-m", action="store_true",
                      help="also print the agent's last message when done")
    wait.add_argument("--timeout", type=float, default=3600.0,
                      help="max total wait seconds (default: 3600)")
    wait.add_argument("--interval", type=float, default=3.0,
                      help="poll interval seconds (default: 3)")
    wait.add_argument("--startup", type=float, default=0.0,
                      help="for the first N seconds, don't treat a not-yet-started "
                           "agent as finished — guards trigger-then-wait (default: 0)")
    wait.set_defaults(func=cmd_wait)

    listen = sub.add_parser(
        "listen", help="bind the push-notify socket and print datagrams (one JSON/line)"
    )
    listen.add_argument(
        "path", nargs="?",
        help="socket path to bind (default: $AGENT_VIEW_NOTIFY_SOCK or <state>/events.sock)",
    )
    listen.set_defaults(func=cmd_listen)

    install = sub.add_parser("install", help="wire agent hook configs")
    install.add_argument("--dry-run", action="store_true")
    install.set_defaults(func=cmd_install)

    parser.set_defaults(func=cmd_view)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

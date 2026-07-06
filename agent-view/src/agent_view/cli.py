"""agent-view CLI.

Subcommands:
  (none)          open the Exposé TUI (run from a tmux popup)
  event pending   mark the calling pane as needing attention (hook entrypoint)
  event clear     clear the pending marker (hook / tmux focus entrypoint)
  status          tmux status-line fragment (pending count)
  install         wire hook configs into Claude / Cursor / Codex
  doctor          print discovery snapshot for debugging

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


def cmd_event(args: argparse.Namespace) -> int:
    from . import state, tmux

    try:
        pane = _resolve_pane(args)
        if not pane:
            return 0
        if args.action == "clear":
            state.clear_pending(pane)
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
        state.mark_pending(pane, message=message, agent=args.agent)
    except Exception:
        pass  # hooks must never break the agent
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    from . import state

    count = state.count_pending()
    if count:
        print(f"#[fg=yellow,bold]● {count}#[default]", end="")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from . import discovery
    from .model import format_age

    agents = discovery.discover()
    if not agents:
        print("no live agent panes found")
        return 0
    for a in agents:
        pending = f"  pending: {a.pending_message}" if a.pending_message else ""
        print(
            f"{a.kind.value:7} {a.state.value:8} {a.location:30} "
            f"pid={a.agent_pid:<8} idle={format_age(a.idle_seconds)}{pending}"
        )
    return 0


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

    event = sub.add_parser("event", help="hook entrypoints (mark/clear pending)")
    event.add_argument("action", choices=["pending", "clear"])
    event.add_argument("--pane", help="tmux pane id (default: $TMUX_PANE)")
    event.add_argument("--message", help="pending reason to display")
    event.add_argument("--agent", help="agent kind reporting the event")
    event.add_argument(
        "--payload", help="hook payload as a JSON argument (Codex notify style)"
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

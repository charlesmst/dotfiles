"""Thin wrapper around the tmux CLI.

All tmux access goes through here so tests can point everything at an
isolated tmux server via the ``AGENT_VIEW_TMUX_ARGS`` env var (e.g.
``-L agent-view-test``).
"""
from __future__ import annotations

import os
import shlex
import subprocess

PANE_FORMAT = "|".join(
    [
        "#{pane_id}",
        "#{pane_pid}",
        "#{session_name}",
        "#{window_index}",
        "#{pane_index}",
        "#{window_name}",
        "#{window_activity}",
    ]
)


def _base_cmd() -> list[str]:
    extra = os.environ.get("AGENT_VIEW_TMUX_ARGS", "")
    return ["tmux", *shlex.split(extra)]


def run(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        [*_base_cmd(), *args], capture_output=True, text=True, check=check
    )


def list_panes() -> list[dict]:
    out = run("list-panes", "-a", "-F", PANE_FORMAT).stdout
    panes = []
    for line in out.splitlines():
        parts = line.split("|")
        if len(parts) < 7:
            continue
        try:
            panes.append(
                {
                    "pane_id": parts[0],
                    "pane_pid": int(parts[1]),
                    "session": parts[2],
                    "window_index": parts[3],
                    "pane_index": parts[4],
                    "window_name": parts[5],
                    "last_activity": float(parts[6]),
                }
            )
        except ValueError:
            continue
    return panes


def capture_pane(pane_id: str, lines: int) -> str:
    """Last ``lines`` lines of a pane with ANSI colors preserved."""
    out = run("capture-pane", "-ep", "-t", pane_id).stdout
    # Drop trailing blank lines so short sessions don't render as whitespace.
    stripped = out.rstrip("\n").split("\n")
    return "\n".join(stripped[-lines:])


def jump_to_pane(session: str, window_index: str, pane_id: str) -> None:
    run("switch-client", "-t", session)
    run("select-window", "-t", f"{session}:{window_index}")
    run("select-pane", "-t", pane_id)


def kill_session(session: str) -> None:
    run("kill-session", "-t", session)


def display_message(text: str) -> None:
    run("display-message", text)


def pane_is_focused(pane_id: str) -> bool:
    """True when the pane is the active pane of a focused, attached client.

    Used to skip marking a pane pending while the user is already looking
    at it.
    """
    out = run(
        "display-message",
        "-p",
        "-t",
        pane_id,
        "#{pane_active}#{window_active}#{session_attached}",
    ).stdout.strip()
    if out[:2] != "11" or not out[2:].rstrip("0"):
        return False
    # The pane is active in an attached session; check a client viewing that
    # session actually has terminal focus (tmux >= 3.2 tracks client_focused).
    focused = run(
        "list-clients", "-F", "#{client_focused}|#{client_session}"
    ).stdout
    session = run(
        "display-message", "-p", "-t", pane_id, "#{session_name}"
    ).stdout.strip()
    for line in focused.splitlines():
        parts = line.split("|", 1)
        if len(parts) == 2 and parts[0] == "1" and parts[1] == session:
            return True
    return False

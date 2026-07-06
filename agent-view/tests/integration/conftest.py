"""Integration fixtures: a disposable tmux server + fake agent binaries.

Fake agents are symlinks to ``sleep`` named after real agent CLIs, so a
``ps`` snapshot shows e.g. ``.../bin/claude 300`` and discovery classifies
them exactly like the real thing.
"""
from __future__ import annotations

import os
import shutil
import time
import uuid

import pytest

from agent_view import tmux


@pytest.fixture
def tmux_server(tmp_path, monkeypatch):
    socket = f"agent-view-test-{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv("AGENT_VIEW_TMUX_ARGS", f"-L {socket} -f /dev/null")
    monkeypatch.setenv("AGENT_ATTENTION_DIR", str(tmp_path / "state"))

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    sleep_bin = shutil.which("sleep")
    assert sleep_bin, "sleep binary required for integration tests"
    for agent in ("claude", "codex", "cursor-agent"):
        os.symlink(sleep_bin, fake_bin / agent)

    server = TmuxTestServer(fake_bin)
    yield server
    tmux.run("kill-server")


class TmuxTestServer:
    def __init__(self, fake_bin):
        self.fake_bin = fake_bin

    def start_agent_session(self, session: str, agent: str = "claude") -> str:
        """New detached session running a fake agent; returns the pane id."""
        proc = tmux.run(
            "new-session",
            "-d",
            "-s",
            session,
            "-x",
            "180",
            "-y",
            "50",
            "-P",
            "-F",
            "#{pane_id}",
            f"exec {self.fake_bin}/{agent} 300",
            check=True,
        )
        pane_id = proc.stdout.strip()
        self._wait_for_agent(pane_id)
        return pane_id

    def start_plain_session(self, session: str) -> str:
        proc = tmux.run(
            "new-session", "-d", "-s", session, "-P", "-F", "#{pane_id}",
            f"exec {shutil.which('sleep')} 300",
            check=True,
        )
        return proc.stdout.strip()

    def _wait_for_agent(self, pane_id: str, timeout: float = 5.0) -> None:
        """Block until discovery sees an agent in the pane."""
        from agent_view import discovery

        deadline = time.time() + timeout
        while time.time() < deadline:
            if any(a.pane_id == pane_id for a in discovery.discover()):
                return
            time.sleep(0.05)
        raise AssertionError(f"agent never appeared in pane {pane_id}")

"""tmux/agent-attention/status.sh — the status-right segment the tmux config actually runs."""
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "tmux" / "agent-attention" / "status.sh"

pytestmark = pytest.mark.skipif(
    not SCRIPT.exists() or not shutil.which("bash"), reason="status.sh not in this checkout"
)


def _run(base):
    out = subprocess.run(
        ["bash", str(SCRIPT)], capture_output=True, text=True,
        env={**os.environ, "AGENT_ATTENTION_DIR": str(base)},
    )
    assert out.returncode == 0
    return out.stdout


def _remote(base, sid, **kw):
    d = base / "remote"
    d.mkdir(parents=True, exist_ok=True)
    (d / sid).write_text(json.dumps({"session_id": sid, "url": "https://x", **kw}))


def test_quiet_prints_nothing(tmp_path):
    assert _run(tmp_path) == ""


def test_pending_alone_is_unchanged(tmp_path):
    (tmp_path / "pending").mkdir()
    (tmp_path / "pending" / "%1").touch()
    assert _run(tmp_path) == "#[fg=yellow,bold]● 1#[default]"


def test_remote_count_alone_and_with_pending(tmp_path):
    _remote(tmp_path, "session_01A")
    _remote(tmp_path, "session_01B")
    assert _run(tmp_path) == "#[fg=magenta,bold]⇢ 2#[default]"
    (tmp_path / "pending").mkdir()
    (tmp_path / "pending" / "%1").touch()
    assert _run(tmp_path) == "#[fg=yellow,bold]● 1#[default] #[fg=magenta,bold]⇢ 2#[default]"


def test_forgotten_and_expired_sessions_do_not_count(tmp_path):
    _remote(tmp_path, "session_01A", dismissed=True)
    _remote(tmp_path, "session_01B")
    old = time.time() - 30 * 86400
    os.utime(tmp_path / "remote" / "session_01B", (old, old))
    assert _run(tmp_path) == ""


def test_finished_and_failed_sessions_drop_off_the_count(tmp_path):
    _remote(tmp_path, "session_01A", status="finished")
    _remote(tmp_path, "session_01B", status="failed")
    _remote(tmp_path, "session_01C", status="running")
    _remote(tmp_path, "session_01D")  # never observed: still counts
    assert _run(tmp_path) == "#[fg=magenta,bold]⇢ 2#[default]"

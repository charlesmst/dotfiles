"""Wire agent-view hook configs into Claude, Cursor and Codex.

All hook *sources* live in the dotfiles repo under ``agent-view/plugins/``;
this installer copies/merges/registers them wherever each agent expects:

  Claude Code   local plugin marketplace add + plugin install
  Cursor CLI    merge our commands into ~/.cursor/hooks.json
  Codex CLI     ensure ``notify = [.../notify.sh]`` in ~/.codex/config.toml

Idempotent: safe to re-run any time (create_links.sh calls it).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
PLUGINS_DIR = PROJECT_DIR / "plugins"
SHIM = Path.home() / ".local" / "bin" / "agent-view"

OK = "\033[32m✓\033[0m"
WARN = "\033[33m!\033[0m"
FAIL = "\033[31m✗\033[0m"


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def install_shim(dry_run: bool) -> list[str]:
    """Install the ``agent-view`` console script via ``uv tool``."""
    if shutil.which("uv") is None:
        return [f"{FAIL} uv not found — install uv first (https://docs.astral.sh/uv/)"]
    if dry_run:
        return [f"{OK} would run: uv tool install --force -e {PROJECT_DIR}"]
    proc = _run(["uv", "tool", "install", "--force", "-e", str(PROJECT_DIR)])
    if proc.returncode != 0:
        return [f"{FAIL} uv tool install failed:\n{proc.stderr.strip()}"]
    if not SHIM.exists():
        return [f"{WARN} installed, but {SHIM} not found — is ~/.local/bin on PATH?"]
    return [f"{OK} {SHIM} → editable install of {PROJECT_DIR}"]


def install_claude(dry_run: bool) -> list[str]:
    """Register the local marketplace and install the agent-view plugin."""
    if shutil.which("claude") is None:
        return [f"{WARN} claude CLI not found — skipped (re-run install later)"]
    if dry_run:
        return [
            f"{OK} would run: claude plugin marketplace add {PLUGINS_DIR}",
            f"{OK} would run: claude plugin install agent-view@agent-view",
        ]
    lines = []
    add = _run(["claude", "plugin", "marketplace", "add", str(PLUGINS_DIR)])
    if add.returncode != 0:
        if "already" in (add.stderr + add.stdout).lower():
            _run(["claude", "plugin", "marketplace", "update", "agent-view"])
            lines.append(f"{OK} claude marketplace 'agent-view' already registered (updated)")
        else:
            return [f"{FAIL} claude plugin marketplace add failed:\n{(add.stderr or add.stdout).strip()}"]
    else:
        lines.append(f"{OK} claude marketplace registered: {PLUGINS_DIR}")

    inst = _run(["claude", "plugin", "install", "agent-view@agent-view"])
    out = (inst.stderr + inst.stdout).lower()
    if inst.returncode != 0 and "already" not in out:
        lines.append(f"{FAIL} claude plugin install failed:\n{(inst.stderr or inst.stdout).strip()}")
    else:
        lines.append(f"{OK} claude plugin 'agent-view' installed (hooks: Notification/Stop/UserPromptSubmit)")
    return lines


def _merge_cursor_hooks(existing: dict, ours: dict) -> dict:
    merged: dict = dict(existing) if existing else {}
    merged.setdefault("version", 1)
    hooks: dict = dict(merged.get("hooks") or {})
    merged["hooks"] = hooks
    for event, entries in ours.get("hooks", {}).items():
        current: list = list(hooks.get(event) or [])
        known = {e.get("command") for e in current if isinstance(e, dict)}
        for entry in entries:
            if entry.get("command") not in known:
                current.append(entry)
        hooks[event] = current
    return merged


def install_cursor(dry_run: bool) -> list[str]:
    """Merge our commands into ~/.cursor/hooks.json (creates it if absent)."""
    target = Path.home() / ".cursor" / "hooks.json"
    ours = json.loads((PLUGINS_DIR / "cursor" / "hooks.json").read_text())

    existing: dict = {}
    if target.exists():
        try:
            existing = json.loads(target.read_text())
        except json.JSONDecodeError:
            return [f"{FAIL} {target} is not valid JSON — fix it and re-run"]

    merged = _merge_cursor_hooks(existing, ours)
    if merged == existing:
        return [f"{OK} cursor hooks already present in {target}"]
    if dry_run:
        return [f"{OK} would merge agent-view commands into {target}"]

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not target.is_symlink():
        shutil.copy2(target, target.with_suffix(".json.bak-agent-view"))
    if target.is_symlink():
        # e.g. dotfiles create_links.sh symlinks it; write through the link.
        target = target.resolve()
    target.write_text(json.dumps(merged, indent=2) + "\n")
    return [f"{OK} cursor hooks merged into {target}"]


def install_codex(dry_run: bool) -> list[str]:
    """Ensure ``notify`` points at our script in ~/.codex/config.toml.

    Root-level TOML keys must appear before any [table], so the line is
    inserted at the top of the file. Text-based on purpose: tomllib can't
    write, and Python 3.10 has no tomllib at all.
    """
    config = Path.home() / ".codex" / "config.toml"
    script = PLUGINS_DIR / "codex" / "notify.sh"
    wanted = f'notify = ["{script}"]'

    text = config.read_text() if config.exists() else ""
    match = re.search(r"^notify\s*=\s*(.*)$", text, flags=re.MULTILINE)
    if match:
        if str(script) in match.group(0):
            return [f"{OK} codex notify already wired in {config}"]
        return [
            f"{WARN} {config} already defines notify = {match.group(1).strip()}",
            f"  merge manually so it also calls: {script}",
        ]
    if dry_run:
        return [f"{OK} would prepend '{wanted}' to {config}"]

    config.parent.mkdir(parents=True, exist_ok=True)
    if config.exists():
        shutil.copy2(config, config.with_suffix(".toml.bak-agent-view"))
    config.write_text(f"{wanted}\n{text}")
    os.chmod(script, 0o755)
    return [f"{OK} codex notify wired in {config}"]


def install_state_dir(dry_run: bool) -> list[str]:
    from . import state

    if not dry_run:
        os.makedirs(state.pending_dir(), exist_ok=True)
    return [f"{OK} state dir: {state.pending_dir()}"]


def run_install(dry_run: bool = False) -> int:
    steps = [
        ("cli shim", install_shim),
        ("state dir", install_state_dir),
        ("claude", install_claude),
        ("cursor", install_cursor),
        ("codex", install_codex),
    ]
    failed = False
    for name, step in steps:
        try:
            lines = step(dry_run)
        except Exception as exc:  # keep going; report at the end
            lines = [f"{FAIL} {name} step crashed: {exc}"]
        for line in lines:
            print(f"[{name:9}] {line}")
        failed = failed or any(FAIL in line for line in lines)

    print()
    print("tmux binding (already in dotfiles .tmux.conf.local):")
    print('  bind-key a display-popup -E -w 90% -h 85% "$HOME/.local/bin/agent-view"')
    return 1 if failed else 0

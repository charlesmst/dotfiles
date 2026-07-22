"""Pull-request association for agent panes.

Two halves, kept apart on purpose:

* **Identity** is *recorded* when an agent creates a PR — a hook
  (Claude ``PostToolUse`` on Bash, Cursor ``afterShellExecution``) sees the
  ``gh pr create`` command and its output, and we persist the PR URL for the
  pane (see ``state.record_pr``). Recording the URL is enough: ``gh pr view
  <url>`` fetches live status from anywhere.
* **Status** (open/merged, CI checks) is *fetched on demand* from ``gh`` when
  something displays the PR, with a short in-memory TTL cache so the 1s TUI
  refresh never hammers the network. Status is never persisted — it's live.

Codex has no per-tool hook, and PRs opened in the browser are never recorded,
so ``pane_pr_url`` also falls back to deriving the PR from the pane's current
git branch. Recorded identity always wins over a derived guess.
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass

from . import proc, state
from .model import AgentPane

PR_URL_RE = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/pull/\d+")


# --- recording (hook side, no network) --------------------------------------


def extract_pr_url(raw_payload: str) -> str | None:
    """Pull a created-PR URL out of a shell-tool hook payload.

    Gated on the command actually being a ``gh pr create`` so ``gh pr view``
    (which also prints a URL) doesn't get misrecorded. The URL itself is what
    ``gh pr create`` writes to stdout (or the "already exists: <url>" notice).
    """
    if "gh pr create" not in raw_payload and "pr create" not in raw_payload:
        return None
    m = PR_URL_RE.search(raw_payload)
    return m.group(0) if m else None


def parse_url(url: str) -> tuple[str | None, int | None]:
    """('owner/name', number) from a PR URL, or (None, None)."""
    m = re.search(r"github\.com/([\w.-]+/[\w.-]+)/pull/(\d+)", url)
    if not m:
        return None, None
    return m.group(1), int(m.group(2))


def record(pane_id: str, url: str) -> None:
    repo, number = parse_url(url)
    state.record_pr(pane_id, url, repo=repo, number=number)


# --- live status (display side) ---------------------------------------------


@dataclass
class PRStatus:
    url: str
    number: int | None
    title: str
    pr_state: str  # OPEN | MERGED | CLOSED
    is_draft: bool
    passed: int
    failed: int
    pending: int

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.pending

    def summary(self) -> str:
        head = f"#{self.number} {self.pr_state}" if self.number else self.pr_state
        if self.is_draft and self.pr_state == "OPEN":
            head += " draft"
        if self.total == 0:
            return head
        if self.failed:
            return f"{head} · ✗{self.failed} of {self.total} checks"
        if self.pending:
            return f"{head} · ⣿{self.pending}/{self.total} checks"
        return f"{head} · ✓{self.passed}/{self.total} checks"

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "number": self.number,
            "title": self.title,
            "state": self.pr_state,
            "is_draft": self.is_draft,
            "checks": {"passed": self.passed, "failed": self.failed,
                       "pending": self.pending, "total": self.total},
            "summary": self.summary(),
        }


def _rollup_counts(rollup) -> tuple[int, int, int]:
    """(passed, failed, pending) from a gh statusCheckRollup list."""
    passed = failed = pending = 0
    for check in rollup or []:
        # CheckRun: status + conclusion. StatusContext: state.
        conclusion = (check.get("conclusion") or "").upper()
        status = (check.get("status") or "").upper()
        ctx_state = (check.get("state") or "").upper()
        if status and status != "COMPLETED":
            pending += 1
        elif conclusion in ("SUCCESS", "NEUTRAL", "SKIPPED") or ctx_state == "SUCCESS":
            passed += 1
        elif conclusion in ("FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED",
                            "STARTUP_FAILURE") or ctx_state in ("FAILURE", "ERROR"):
            failed += 1
        elif ctx_state in ("PENDING", "EXPECTED") or conclusion == "":
            pending += 1
        else:
            passed += 1
    return passed, failed, pending


def _gh_pr_view(args: list[str], cwd: str | None = None) -> dict | None:
    fields = "number,title,state,url,isDraft,statusCheckRollup"
    try:
        proc_result = subprocess.run(
            ["gh", "pr", "view", *args, "--json", fields],
            capture_output=True, text=True, timeout=15, cwd=cwd,
        )
    except Exception:
        return None
    if proc_result.returncode != 0:
        return None  # no PR for this branch, gh not authed, etc.
    try:
        return json.loads(proc_result.stdout)
    except json.JSONDecodeError:
        return None


def _to_status(data: dict) -> PRStatus:
    passed, failed, pending = _rollup_counts(data.get("statusCheckRollup"))
    return PRStatus(
        url=data.get("url", ""),
        number=data.get("number"),
        title=data.get("title", ""),
        pr_state=(data.get("state") or "").upper(),
        is_draft=bool(data.get("isDraft")),
        passed=passed, failed=failed, pending=pending,
    )


# process-lifetime cache: url → (fetched_at, status). Not persisted.
_cache: dict[str, tuple[float, PRStatus | None]] = {}


def fetch_status(url: str, ttl: float = 60.0) -> PRStatus | None:
    """Live PR status for a URL, cached in-process for ``ttl`` seconds."""
    now = time.time()
    hit = _cache.get(url)
    if hit and (now - hit[0]) < ttl:
        return hit[1]
    data = _gh_pr_view([url])
    status = _to_status(data) if data else None
    _cache[url] = (now, status)
    return status


# --- association (recorded, else derived) -----------------------------------


def derive_url(cwd: str) -> str | None:
    """The PR for whatever branch ``cwd`` is on, via gh (network)."""
    data = _gh_pr_view([], cwd=cwd)
    return data.get("url") if data else None


def pane_pr_urls(
    pane: AgentPane,
    children: dict[int, list[int]] | None = None,
    derive: bool = True,
) -> list[str]:
    """Recorded PR urls for the pane, or a branch-derived one as fallback.

    A session can have several recorded PRs. When none are recorded (Codex, or
    a browser-created PR) we fall back to the single PR of the pane's current
    branch, if any.
    """
    recorded = list(getattr(pane, "pr_urls", []) or [])
    if recorded:
        return recorded
    if not derive:
        return []
    from . import discovery

    if children is None:
        children, _ = discovery.process_snapshot()
    cwd = proc.first_cwd(proc.subtree_pids(pane.pane_pid, children))
    derived = derive_url(cwd) if cwd else None
    return [derived] if derived else []


def open_in_browser(url: str) -> bool:
    """Open a PR in the browser via gh; True on launch success."""
    try:
        return subprocess.run(
            ["gh", "pr", "view", url, "--web"],
            capture_output=True, text=True, timeout=15,
        ).returncode == 0
    except Exception:
        return False

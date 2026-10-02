"""Scrub token-like strings from text that came from a remote session.

A cloud session's output is arbitrary: a probe that prints its environment can
echo bearer tokens, API keys or private keys. Anything agent-view shows or writes
to the event log from a session passes through :func:`redact` first.

Deliberately over-eager on opaque secrets, deliberately gentle on things people
need to read: git SHAs (40 hex), hostnames, paths, URLs and ``session_…`` ids are
left alone.
"""
from __future__ import annotations

import re

MARK = "<redacted>"

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.S), MARK),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"), f"Bearer {MARK}"),
    (re.compile(r"\bsk-ant-[A-Za-z0-9_-]{8,}|\bsk-[A-Za-z0-9_-]{20,}"), MARK),
    (re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"), MARK),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), MARK),
    (re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), MARK),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*"), MARK),
    # NAME=value / NAME: value where NAME looks secret-bearing
    (re.compile(
        r"""(?ix)\b([A-Za-z0-9_.-]*(?:token|secret|passw(?:or)?d|passwd|api[_-]?key|apikey|credential|private[_-]?key)[A-Za-z0-9_.-]*)
            \s*[:=]\s*("[^"\n]+"|'[^'\n]+'|[^\s,;]+)"""), rf"\1={MARK}"),
    # long opaque blobs: mixed-case alphanumerics (not a 40-char git sha, not a path/word)
    (re.compile(r"(?<![A-Za-z0-9/_.-])(?=[A-Za-z0-9+/_-]*[a-z])(?=[A-Za-z0-9+/_-]*[A-Z])(?=[A-Za-z0-9+/_-]*\d)[A-Za-z0-9+/_-]{40,}={0,2}(?![A-Za-z0-9/_.-])"), MARK),
    (re.compile(r"(?<![A-Za-z0-9])[0-9a-fA-F]{41,}(?![A-Za-z0-9])"), MARK),
]


def redact(text: str, extra: list[str] | None = None) -> str:
    """``text`` with token-like strings replaced by ``<redacted>``.

    ``extra`` are exact secrets known to the caller (e.g. the live bearer token):
    they are removed first, as defence in depth.
    """
    for secret in extra or []:
        if secret and len(secret) >= 8:
            text = text.replace(secret, MARK)
    for pat, repl in _PATTERNS:
        text = pat.sub(repl, text)
    return text


def excerpt(text: str, limit: int = 500) -> str:
    """Redacted, whitespace-collapsed, at most ``limit`` characters (ellipsis if cut)."""
    flat = " ".join(redact(text).split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"

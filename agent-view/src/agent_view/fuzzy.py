"""Minimal fzf-style fuzzy subsequence matcher (no dependency needed)."""
from __future__ import annotations


def score(query: str, haystack: str) -> int | None:
    """Score a case-insensitive subsequence match; None when no match.

    Higher is better. Rewards consecutive matches and matches at word
    boundaries, mildly penalizes gaps — enough to feel like fzf for short
    session/window names.
    """
    if not query:
        return 0
    q = query.lower()
    h = haystack.lower()

    total = 0
    hi = 0
    prev_match = -2
    for ch in q:
        idx = h.find(ch, hi)
        if idx == -1:
            return None
        total += 10
        if idx == prev_match + 1:
            total += 15  # consecutive
        if idx == 0 or h[idx - 1] in " -_./:":
            total += 10  # word boundary
        total -= min(idx - hi, 10)  # gap penalty
        prev_match = idx
        hi = idx + 1
    return total

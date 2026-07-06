from agent_view.fuzzy import score


def test_empty_query_matches_everything():
    assert score("", "anything") == 0


def test_no_match_returns_none():
    assert score("xyz", "dotfiles") is None


def test_subsequence_matches():
    assert score("dtf", "dotfiles") is not None


def test_case_insensitive():
    assert score("DOT", "dotfiles") is not None


def test_consecutive_beats_scattered():
    consecutive = score("dot", "dotfiles")
    scattered = score("dts", "dotfiles")
    assert consecutive is not None and scattered is not None
    assert consecutive > scattered


def test_word_boundary_bonus():
    boundary = score("view", "agent-view")
    middle = score("view", "preview")
    assert boundary is not None and middle is not None
    assert boundary > middle

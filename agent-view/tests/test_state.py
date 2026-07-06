import os

from agent_view import state


def test_mark_and_load_pending(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ATTENTION_DIR", str(tmp_path))
    state.mark_pending("%5", message="permission needed", agent="claude")

    markers = state.load_pending()
    assert markers["%5"].message == "permission needed"
    assert markers["%5"].since > 0


def test_clear_pending(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ATTENTION_DIR", str(tmp_path))
    state.mark_pending("%5")
    state.clear_pending("%5")
    assert state.load_pending() == {}
    state.clear_pending("%5")  # idempotent


def test_legacy_empty_marker_files_are_valid(tmp_path, monkeypatch):
    """The old shell hooks `touch` empty files — must still be readable."""
    monkeypatch.setenv("AGENT_ATTENTION_DIR", str(tmp_path))
    os.makedirs(tmp_path / "pending")
    (tmp_path / "pending" / "%7").touch()

    markers = state.load_pending()
    assert markers["%7"].message == "needs attention"


def test_prune_drops_dead_panes(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ATTENTION_DIR", str(tmp_path))
    state.mark_pending("%1")
    state.mark_pending("%2")
    state.prune_pending(live_pane_ids={"%1"})
    assert set(state.load_pending()) == {"%1"}


def test_view_mode_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ATTENTION_DIR", str(tmp_path))
    assert state.load_view_mode() == "grid"  # default
    state.save_view_mode("list")
    assert state.load_view_mode() == "list"
    state.save_view_mode("nonsense")  # ignored
    assert state.load_view_mode() == "list"
    (tmp_path / "view-mode").write_text("garbage")
    assert state.load_view_mode() == "grid"


def test_count_pending(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ATTENTION_DIR", str(tmp_path))
    assert state.count_pending() == 0
    state.mark_pending("%1")
    state.mark_pending("%2")
    assert state.count_pending() == 2

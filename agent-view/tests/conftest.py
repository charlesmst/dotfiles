import pytest


@pytest.fixture(autouse=True)
def _no_cloud_status_lookups(monkeypatch):
    """Tests must never read a credential or touch the network. cloudstatus tests opt back in."""
    monkeypatch.setenv("AGENT_VIEW_NO_STATUS", "1")
    monkeypatch.setenv("AGENT_VIEW_NO_WATCH", "1")
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)

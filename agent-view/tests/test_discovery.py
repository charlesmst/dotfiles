from agent_view.discovery import classify_command, find_agent
from agent_view.model import AgentKind


def test_classify_plain_binaries():
    assert classify_command("claude --continue") == AgentKind.CLAUDE
    assert classify_command("/usr/local/bin/claude") == AgentKind.CLAUDE
    assert classify_command("codex exec") == AgentKind.CODEX
    assert classify_command("cursor-agent") == AgentKind.CURSOR


def test_classify_cursor_wrapper_forms():
    assert classify_command("bash /home/u/.local/bin/cursor-agent") == AgentKind.CURSOR
    assert (
        classify_command("agent --flag /x/cursor-agent/versions/1.0/agent")
        == AgentKind.CURSOR
    )


def test_classify_codex_node_wrapper():
    assert classify_command("node /usr/local/bin/codex") == AgentKind.CODEX
    assert (
        classify_command("node /x/node_modules/@openai/codex/bin/codex.js")
        == AgentKind.CODEX
    )


def test_classify_rejects_non_agents():
    assert classify_command("vim claude.md") is None
    assert classify_command("zsh") is None
    assert classify_command("node server.js") is None
    assert classify_command("") is None


def test_find_agent_walks_process_tree():
    # pane shell (10) → wrapper (20) → claude (30)
    children = {10: [20], 20: [30]}
    agents = {30: AgentKind.CLAUDE}
    assert find_agent(10, children, agents) == (30, AgentKind.CLAUDE)


def test_find_agent_none_when_tree_has_no_agent():
    assert find_agent(10, {10: [20]}, {}) is None


def test_find_agent_survives_pid_cycles():
    children = {10: [20], 20: [10]}
    assert find_agent(10, children, {}) is None

"""Exposé-style grid TUI over live agent panes.

Runs inside a tmux popup. No daemon: data is rebuilt every second from
``tmux list-panes`` + one ``ps`` snapshot, previews via ``capture-pane``.

Keys:
  type to filter (fzf-style) · arrows/tab move · enter jump
  ctrl-d kill agent process · ctrl-k kill tmux session · ctrl-r refresh
  esc clear filter / quit · ctrl-c quit
"""
from __future__ import annotations

import math
import os
import signal
import time

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Grid
from textual.events import Key
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Label, Static

from .. import discovery, fuzzy, state, tmux
from ..model import AgentKind, AgentPane, AgentState, format_age

KIND_BADGES = {
    AgentKind.CLAUDE: ("C", "cyan"),
    AgentKind.CURSOR: ("✦", "magenta"),
    AgentKind.CODEX: ("X", "green"),
}

STATE_ICONS = {
    AgentState.PENDING: ("●", "yellow"),
    AgentState.WORKING: ("⠿", "bright_blue"),
    AgentState.IDLE: ("·", "grey50"),
    AgentState.STALE: ("✖", "red"),
}

PREVIEW_CAPTURE_LINES = 60


def grid_dimensions(count: int) -> tuple[int, int]:
    """(columns, rows) for an Exposé grid of ``count`` tiles."""
    if count <= 0:
        return 1, 1
    cols = math.ceil(math.sqrt(count))
    rows = math.ceil(count / cols)
    return cols, rows


class AgentTile(Static):
    """One agent pane: bordered live preview with badge/state title."""

    def __init__(self, agent: AgentPane) -> None:
        super().__init__(id=f"tile-{agent.pane_id.lstrip('%')}")
        self.agent = agent
        self._lines: list[Text] = []

    def update_agent(self, agent: AgentPane, preview_ansi: str) -> None:
        self.agent = agent
        text = Text.from_ansi(preview_ansi)
        self._lines = list(text.split("\n")) if preview_ansi else []
        self._style_for_state()
        self.refresh(layout=False)

    def _style_for_state(self) -> None:
        a = self.agent
        badge, badge_color = KIND_BADGES[a.kind]
        icon, icon_color = STATE_ICONS[a.state]
        title = f" [{badge_color} bold]{badge}[/] [{icon_color}]{icon}[/] [bold]{a.location}[/]"
        if a.title:
            title += f" · {a.title}"
        self.border_title = title + " "

        if a.state == AgentState.PENDING:
            msg = (a.pending_message or "needs attention").replace("[", r"\[")
            since = format_age(time.time() - a.pending_since) if a.pending_since else ""
            self.border_subtitle = f" [yellow bold]● {msg[:60]}[/] [dim]{since}[/] "
        elif a.state == AgentState.STALE:
            self.border_subtitle = (
                f" [red bold]stale {format_age(a.idle_seconds)}[/]"
                f" [dim]— ^k to kill[/] "
            )
        elif a.state == AgentState.WORKING:
            self.border_subtitle = " [bright_blue]working[/] "
        else:
            self.border_subtitle = f" [dim]idle {format_age(a.idle_seconds)}[/] "

        for st in AgentState:
            self.set_class(a.state == st, f"-{st.value}")

    def render(self) -> Text:
        height = max(1, self.content_size.height)
        visible = self._lines[-height:]
        if not visible:
            return Text("")
        result = Text("\n").join(visible)
        # Crop, don't wrap: pane content is already wrapped at the source
        # pane's width; re-wrapping at tile width would garble alignment.
        result.no_wrap = True
        result.overflow = "crop"
        return result

    def on_click(self) -> None:
        app = self.app
        if isinstance(app, AgentViewApp):
            app.select_pane(self.agent.pane_id)


class SnapshotReady(Message):
    """Posted (thread-safely) by the refresh worker with fresh data."""

    def __init__(self, agents: list[AgentPane], previews: dict[str, str]) -> None:
        super().__init__()
        self.agents = agents
        self.previews = previews


class ConfirmScreen(ModalScreen[bool]):
    """y/enter confirms, n/esc cancels."""

    DEFAULT_CSS = """
    ConfirmScreen { align: center middle; }
    ConfirmScreen > Label {
        padding: 1 3;
        border: heavy red;
        background: $surface;
    }
    """

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        yield Label(f"{self.message}\n\n[bold]y[/] confirm · [bold]n[/] cancel")

    def on_key(self, event: Key) -> None:
        event.stop()
        if event.key in ("y", "enter"):
            self.dismiss(True)
        elif event.key in ("n", "escape", "ctrl-c"):
            self.dismiss(False)


class AgentViewApp(App[None]):
    CSS = """
    Screen { background: $background; }
    #grid {
        layout: grid;
        grid-gutter: 0 0;
        height: 1fr;
    }
    AgentTile {
        border: round #5f5f5f;
        padding: 0 1;
        width: 100%;
        height: 100%;
        overflow: hidden hidden;
        border-title-color: $text;
        color: $text;
    }
    AgentTile.-pending { border: round yellow; }
    AgentTile.-working { border: round steelblue; }
    AgentTile.-stale { border: round darkred; color: $text-muted; }
    AgentTile.-selected { border: heavy white; }
    AgentTile.-pending.-selected { border: heavy yellow; }
    AgentTile.-working.-selected { border: heavy steelblue; }
    AgentTile.-stale.-selected { border: heavy red; }
    #statusbar { height: 1; dock: bottom; padding: 0 1; }
    #empty { content-align: center middle; height: 1fr; color: $text-muted; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.agents: list[AgentPane] = []  # last full discovery, sorted
        self.filtered_agents: list[AgentPane] = []  # after fuzzy filter
        self.filter_query = ""
        self.selected = 0
        self._previews: dict[str, str] = {}
        self._tile_order: list[str] | None = None  # pane ids currently mounted

    def compose(self) -> ComposeResult:
        yield Grid(id="grid")
        yield Static(id="statusbar")

    def on_mount(self) -> None:
        self.refresh_data()
        self.set_interval(1.0, self.refresh_data)

    # -- data ----------------------------------------------------------

    def refresh_data(self) -> None:
        self.run_worker(
            self._refresh_worker, thread=True, exclusive=True, group="refresh"
        )

    def _refresh_worker(self) -> None:
        agents = discovery.discover()
        previews = {
            a.pane_id: tmux.capture_pane(a.pane_id, PREVIEW_CAPTURE_LINES)
            for a in agents
        }
        self.post_message(SnapshotReady(agents, previews))

    async def on_snapshot_ready(self, message: SnapshotReady) -> None:
        self.agents = message.agents
        self._previews = message.previews
        await self._rebuild_view()

    def _filtered(self) -> list[AgentPane]:
        if not self.filter_query:
            return list(self.agents)
        scored = []
        for agent in self.agents:
            s = fuzzy.score(self.filter_query, agent.filter_haystack())
            if s is not None:
                scored.append((agent.sort_key(), -s, agent))
        scored.sort(key=lambda t: (t[0], t[1]))
        return [t[2] for t in scored]

    async def _rebuild_view(self) -> None:
        selected_pane = (
            self.filtered_agents[self.selected].pane_id
            if self.filtered_agents and self.selected < len(self.filtered_agents)
            else None
        )
        self.filtered_agents = self._filtered()

        # Keep selection on the same pane when possible.
        self.selected = 0
        for i, agent in enumerate(self.filtered_agents):
            if agent.pane_id == selected_pane:
                self.selected = i
                break

        # Query the base screen, not the app: App.query_one searches the
        # *active* screen, which is the ConfirmScreen while a kill dialog
        # is open — and the refresh interval keeps ticking behind it.
        grid = self.screen_stack[0].query_one("#grid", Grid)
        new_order = [a.pane_id for a in self.filtered_agents]
        if new_order != self._tile_order:
            await grid.remove_children()
            self._tile_order = new_order
            if not self.filtered_agents:
                await grid.mount(
                    Static(
                        "no matching agent panes" if self.filter_query
                        else "no live agent panes — press esc to close",
                        id="empty",
                    )
                )
            else:
                cols, rows = grid_dimensions(len(self.filtered_agents))
                grid.styles.grid_size_columns = cols
                grid.styles.grid_size_rows = rows
                await grid.mount_all(AgentTile(a) for a in self.filtered_agents)

        tiles = list(grid.query(AgentTile))
        for i, (agent, tile) in enumerate(zip(self.filtered_agents, tiles)):
            tile.update_agent(agent, self._previews.get(agent.pane_id, ""))
            tile.set_class(i == self.selected, "-selected")
        self._update_statusbar()

    def _update_statusbar(self) -> None:
        pending = sum(1 for a in self.agents if a.state == AgentState.PENDING)
        stale = sum(1 for a in self.agents if a.state == AgentState.STALE)
        counts = f"{len(self.filtered_agents)}/{len(self.agents)} agents"
        if pending:
            counts += f" · [yellow]● {pending}[/]"
        if stale:
            counts += f" · [red]✖ {stale} stale[/]"
        help_text = (
            "[dim]enter[/] jump  [dim]^d[/] kill agent  [dim]^k[/] kill session"
            "  [dim]^r[/] refresh  [dim]esc[/] quit"
        )
        query = self.filter_query.replace("[", r"\[")
        bar = f"[bold]filter>[/] {query}[blink]▏[/]   {counts}   {help_text}"
        self.screen_stack[0].query_one("#statusbar", Static).update(bar)

    # -- selection / actions -------------------------------------------

    @property
    def current(self) -> AgentPane | None:
        if self.filtered_agents and 0 <= self.selected < len(self.filtered_agents):
            return self.filtered_agents[self.selected]
        return None

    def select_pane(self, pane_id: str) -> None:
        for i, agent in enumerate(self.filtered_agents):
            if agent.pane_id == pane_id:
                self.selected = i
                self._highlight_selection()
                return

    def _highlight_selection(self) -> None:
        tiles = list(self.query(AgentTile))
        for i, tile in enumerate(tiles):
            tile.set_class(i == self.selected, "-selected")

    def _move_selection(self, delta: int) -> None:
        if not self.filtered_agents:
            return
        self.selected = max(0, min(len(self.filtered_agents) - 1, self.selected + delta))
        self._highlight_selection()

    def _jump(self) -> None:
        agent = self.current
        if agent is None:
            return
        state.clear_pending(agent.pane_id)
        tmux.jump_to_pane(agent.session, agent.window_index, agent.pane_id)
        self.exit()

    def _kill_agent(self) -> None:
        agent = self.current
        if agent is None:
            return

        def _confirmed(yes: bool | None) -> None:
            if yes and agent is not None:
                try:
                    os.kill(agent.agent_pid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    pass
                state.clear_pending(agent.pane_id)
                self.set_timer(0.4, self.refresh_data)

        self.push_screen(
            ConfirmScreen(
                f"Kill [bold]{agent.kind.value}[/] process (pid {agent.agent_pid})"
                f" in [bold]{agent.location}[/]?"
            ),
            _confirmed,
        )

    def _kill_session(self) -> None:
        agent = self.current
        if agent is None:
            return
        others = sum(1 for a in self.agents if a.session == agent.session) - 1
        extra = f" ({others} more agent(s) inside!)" if others > 0 else ""

        def _confirmed(yes: bool | None) -> None:
            if yes and agent is not None:
                tmux.kill_session(agent.session)
                state.clear_pending(agent.pane_id)
                self.set_timer(0.4, self.refresh_data)

        self.push_screen(
            ConfirmScreen(
                f"Kill tmux session [bold]{agent.session}[/]{extra}?"
            ),
            _confirmed,
        )

    # -- input ----------------------------------------------------------

    async def on_key(self, event: Key) -> None:
        key = event.key
        if key == "escape":
            event.stop()
            if self.filter_query:
                self.filter_query = ""
                await self._rebuild_view()
            else:
                self.exit()
        elif key == "ctrl+c":
            event.stop()
            self.exit()
        elif key == "enter":
            event.stop()
            self._jump()
        elif key == "ctrl+d":
            event.stop()
            self._kill_agent()
        elif key == "ctrl+k":
            event.stop()
            self._kill_session()
        elif key == "ctrl+r":
            event.stop()
            self.refresh_data()
        elif key in ("left", "shift+tab"):
            event.stop()
            self._move_selection(-1)
        elif key in ("right", "tab"):
            event.stop()
            self._move_selection(1)
        elif key in ("up", "down"):
            event.stop()
            cols, _ = grid_dimensions(len(self.filtered_agents))
            self._move_selection(-cols if key == "up" else cols)
        elif key == "backspace":
            event.stop()
            if self.filter_query:
                self.filter_query = self.filter_query[:-1]
                await self._rebuild_view()
        elif key == "ctrl+u":
            event.stop()
            if self.filter_query:
                self.filter_query = ""
                await self._rebuild_view()
        elif event.is_printable and event.character:
            event.stop()
            self.filter_query += event.character
            await self._rebuild_view()

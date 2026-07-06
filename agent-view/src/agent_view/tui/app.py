"""Exposé-style TUI over live agent panes, with two views.

Runs inside a tmux popup. No daemon: data is rebuilt every second from
``tmux list-panes`` + one ``ps`` snapshot, previews via ``capture-pane``.

Views (ctrl-l toggles, choice persists):
  grid  Exposé wall of live tiles, one per agent
  list  compact rows on the left + scrollable deep preview on the right

Keys:
  type to filter (fzf-style) · arrows/tab move · enter jump
  ctrl-d kill agent process · ctrl-k kill tmux session · ctrl-r refresh
  ctrl-l toggle grid/list · pgup/pgdn scroll preview (list view)
  esc clear filter / quit · ctrl-c quit
"""
from __future__ import annotations

import math
import os
import signal
import time

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Grid, Horizontal, VerticalScroll
from textual.events import Click, Key
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

GRID_CAPTURE_LINES = 60
LIST_CAPTURE_LINES = 300  # includes scrollback: the preview is scrollable


def grid_dimensions(count: int) -> tuple[int, int]:
    """(columns, rows) for an Exposé grid of ``count`` tiles."""
    if count <= 0:
        return 1, 1
    cols = math.ceil(math.sqrt(count))
    rows = math.ceil(count / cols)
    return cols, rows


def fit(text: str, width: int) -> str:
    if len(text) > width:
        return text[: width - 1] + "…"
    return text.ljust(width)


def title_markup(agent: AgentPane) -> str:
    badge, badge_color = KIND_BADGES[agent.kind]
    icon, icon_color = STATE_ICONS[agent.state]
    location = agent.location.replace("[", r"\[")
    title = f" [{badge_color} bold]{badge}[/] [{icon_color}]{icon}[/] [bold]{location}[/]"
    if agent.title:
        escaped = agent.title.replace("[", r"\[")
        title += f" · {escaped}"
    return title + " "


def subtitle_markup(agent: AgentPane) -> str:
    if agent.state == AgentState.PENDING:
        msg = (agent.pending_message or "needs attention").replace("[", r"\[")
        since = (
            format_age(time.time() - agent.pending_since)
            if agent.pending_since
            else ""
        )
        return f" [yellow bold]● {msg[:60]}[/] [dim]{since}[/] "
    if agent.state == AgentState.STALE:
        return (
            f" [red bold]stale {format_age(agent.idle_seconds)}[/]"
            f" [dim]— ^k to kill[/] "
        )
    if agent.state == AgentState.WORKING:
        return " [bright_blue]working[/] "
    return f" [dim]idle {format_age(agent.idle_seconds)}[/] "


def ansi_preview(preview_ansi: str) -> Text:
    text = Text.from_ansi(preview_ansi)
    # Crop, don't wrap: pane content is already wrapped at the source
    # pane's width; re-wrapping at preview width would garble alignment.
    text.no_wrap = True
    text.overflow = "crop"
    return text


class AgentTile(Static):
    """One grid tile: bordered live preview with badge/state title."""

    def __init__(self, agent: AgentPane) -> None:
        super().__init__(id=f"tile-{agent.pane_id.lstrip('%')}")
        self.agent = agent
        self._lines: list[Text] = []

    def update_agent(self, agent: AgentPane, preview_ansi: str) -> None:
        self.agent = agent
        text = Text.from_ansi(preview_ansi)
        self._lines = list(text.split("\n")) if preview_ansi else []
        self.border_title = title_markup(agent)
        self.border_subtitle = subtitle_markup(agent)
        for st in AgentState:
            self.set_class(agent.state == st, f"-{st.value}")
        self.refresh(layout=False)

    def render(self) -> Text:
        height = max(1, self.content_size.height)
        visible = self._lines[-height:]
        if not visible:
            return Text("")
        result = Text("\n").join(visible)
        result.no_wrap = True
        result.overflow = "crop"
        return result

    def on_click(self, event: Click) -> None:
        app = self.app
        if isinstance(app, AgentViewApp):
            app.select_pane(self.agent.pane_id)
            if getattr(event, "chain", 1) >= 2:
                app.jump_to_selected()


class AgentListPanel(Static):
    """Left panel of the list view; one row per agent, click to select."""

    def on_click(self, event: Click) -> None:
        app = self.app
        if isinstance(app, AgentViewApp):
            app.select_list_row(event.y, chain=getattr(event, "chain", 1))


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
    #list-view { height: 1fr; }
    #agent-list {
        width: 46;
        height: 1fr;
        padding: 0 1;
        border: round #5f5f5f;
    }
    #preview {
        width: 1fr;
        height: 1fr;
        border: round #5f5f5f;
        padding: 0 1;
        border-title-color: $text;
        scrollbar-size-vertical: 1;
    }
    #preview.-pending { border: round yellow; }
    #preview.-working { border: round steelblue; }
    #preview.-stale { border: round darkred; }
    #statusbar { height: 1; dock: bottom; padding: 0 1; }
    #empty { content-align: center middle; height: 1fr; color: $text-muted; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.agents: list[AgentPane] = []  # last full discovery, sorted
        self.filtered_agents: list[AgentPane] = []  # after fuzzy filter
        self.filter_query = ""
        self.selected = 0
        self.view_mode = state.load_view_mode()
        self._previews: dict[str, str] = {}
        self._tile_order: list[str] | None = None  # pane ids currently mounted
        self._preview_pane: str | None = None  # pane shown in the list preview
        self.snapshots_applied = 0  # refresh cycles completed (tests wait on it)

    def compose(self) -> ComposeResult:
        yield Grid(id="grid")
        with Horizontal(id="list-view"):
            yield AgentListPanel(id="agent-list")
            with VerticalScroll(id="preview"):
                yield Static(id="preview-content")
        yield Static(id="statusbar")

    def on_mount(self) -> None:
        # Show only the persisted view from the first frame (no flash of
        # the other layout while the first snapshot is captured).
        self.query_one("#grid", Grid).display = self.view_mode == "grid"
        self.query_one("#list-view", Horizontal).display = self.view_mode == "list"
        self.refresh_data()
        self.set_interval(1.0, self.refresh_data)

    # -- data ----------------------------------------------------------

    def refresh_data(self) -> None:
        self.run_worker(
            self._refresh_worker, thread=True, exclusive=True, group="refresh"
        )

    def _refresh_worker(self) -> None:
        agents = discovery.discover()
        deep = self.view_mode == "list"
        lines = LIST_CAPTURE_LINES if deep else GRID_CAPTURE_LINES
        previews = {
            a.pane_id: tmux.capture_pane(a.pane_id, lines, include_history=deep)
            for a in agents
        }
        self.post_message(SnapshotReady(agents, previews))

    async def on_snapshot_ready(self, message: SnapshotReady) -> None:
        self.agents = message.agents
        self._previews = message.previews
        await self._rebuild_view()
        self.snapshots_applied += 1

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
        base = self.screen_stack[0]
        grid = base.query_one("#grid", Grid)
        list_view = base.query_one("#list-view", Horizontal)
        grid.display = self.view_mode == "grid"
        list_view.display = self.view_mode == "list"

        if self.view_mode == "grid":
            await self._rebuild_grid(grid)
        else:
            self._render_list()
        self._update_statusbar()

    async def _rebuild_grid(self, grid: Grid) -> None:
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

    def _render_list(self) -> None:
        base = self.screen_stack[0]
        panel = base.query_one("#agent-list", AgentListPanel)
        preview = base.query_one("#preview", VerticalScroll)
        content = base.query_one("#preview-content", Static)

        if not self.filtered_agents:
            panel.update(
                Text(
                    "no matching agent panes" if self.filter_query
                    else "no live agent panes — press esc to close",
                    style="dim",
                )
            )
            preview.border_title = ""
            preview.border_subtitle = ""
            for st in AgentState:
                preview.set_class(False, f"-{st.value}")
            content.update(Text(""))
            self._preview_pane = None
            return

        rows = Text(no_wrap=True, overflow="crop")
        for i, agent in enumerate(self.filtered_agents):
            badge, badge_color = KIND_BADGES[agent.kind]
            icon, icon_color = STATE_ICONS[agent.state]
            selected = i == self.selected
            row = Text()
            row.append("▸ " if selected else "  ", style="bold white")
            row.append(badge, style=f"{badge_color} bold")
            row.append(" ")
            row.append(icon, style=icon_color)
            row.append(" ")
            row.append(fit(agent.location, 22))
            row.append(fit(agent.title or "-", 10), style="dim")
            age_style = "red" if agent.state == AgentState.STALE else "dim"
            row.append(format_age(agent.idle_seconds).rjust(4), style=age_style)
            if selected:
                row.stylize("reverse")
            rows.append_text(row)
            if i < len(self.filtered_agents) - 1:
                rows.append("\n")
        panel.update(rows)

        agent = self.filtered_agents[self.selected]
        preview.border_title = title_markup(agent)
        preview.border_subtitle = subtitle_markup(agent)
        for st in AgentState:
            preview.set_class(agent.state == st, f"-{st.value}")

        selection_changed = self._preview_pane != agent.pane_id
        self._preview_pane = agent.pane_id
        # Terminal-follow: stick to the bottom (newest output) unless the
        # user scrolled up to read history.
        at_bottom = preview.scroll_offset.y >= preview.max_scroll_y - 1
        content.update(ansi_preview(self._previews.get(agent.pane_id, "")))
        if selection_changed or at_bottom:
            self.call_after_refresh(
                lambda: preview.scroll_end(animate=False)
            )

    def _update_statusbar(self) -> None:
        pending = sum(1 for a in self.agents if a.state == AgentState.PENDING)
        stale = sum(1 for a in self.agents if a.state == AgentState.STALE)
        counts = f"{len(self.filtered_agents)}/{len(self.agents)} agents"
        if pending:
            counts += f" · [yellow]● {pending}[/]"
        if stale:
            counts += f" · [red]✖ {stale} stale[/]"
        other = "list" if self.view_mode == "grid" else "grid"
        help_text = (
            "[dim]enter[/] jump  [dim]^d[/] kill agent  [dim]^k[/] kill session"
            f"  [dim]^l[/] {other}"
        )
        if self.view_mode == "list":
            help_text += "  [dim]pgup/pgdn[/] scroll"
        help_text += "  [dim]esc[/] quit"
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
                self._show_selection()
                return

    def select_list_row(self, row: int, chain: int = 1) -> None:
        if self.view_mode != "list" or not (0 <= row < len(self.filtered_agents)):
            return
        self.selected = row
        self._render_list()
        if chain >= 2:
            self.jump_to_selected()

    def _show_selection(self) -> None:
        if self.view_mode == "list":
            self._render_list()
            return
        tiles = list(self.screen_stack[0].query(AgentTile))
        for i, tile in enumerate(tiles):
            tile.set_class(i == self.selected, "-selected")

    def _move_selection(self, delta: int) -> None:
        if not self.filtered_agents:
            return
        self.selected = max(0, min(len(self.filtered_agents) - 1, self.selected + delta))
        self._show_selection()

    def jump_to_selected(self) -> None:
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

    async def _toggle_view_mode(self) -> None:
        self.view_mode = "list" if self.view_mode == "grid" else "grid"
        state.save_view_mode(self.view_mode)
        self._tile_order = None  # force a grid rebuild when switching back
        await self._rebuild_view()
        self.refresh_data()  # re-capture at the right depth

    def _scroll_preview(self, page_delta: int) -> None:
        if self.view_mode != "list":
            return
        preview = self.screen_stack[0].query_one("#preview", VerticalScroll)
        if page_delta < 0:
            preview.scroll_page_up(animate=False)
        else:
            preview.scroll_page_down(animate=False)

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
            self.jump_to_selected()
        elif key == "ctrl+d":
            event.stop()
            self._kill_agent()
        elif key == "ctrl+k":
            event.stop()
            self._kill_session()
        elif key == "ctrl+r":
            event.stop()
            self.refresh_data()
        elif key == "ctrl+l":
            event.stop()
            await self._toggle_view_mode()
        elif key in ("pageup", "pagedown"):
            event.stop()
            self._scroll_preview(-1 if key == "pageup" else 1)
        elif key in ("left", "shift+tab"):
            event.stop()
            self._move_selection(-1)
        elif key in ("right", "tab"):
            event.stop()
            self._move_selection(1)
        elif key in ("up", "down"):
            event.stop()
            if self.view_mode == "list":
                delta = -1 if key == "up" else 1
            else:
                cols, _ = grid_dimensions(len(self.filtered_agents))
                delta = -cols if key == "up" else cols
            self._move_selection(delta)
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

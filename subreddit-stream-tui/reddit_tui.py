#!/usr/bin/env python3
"""
Reddit r/webdev live comment viewer.

Usage:
    export REDDIT_CLIENT_ID=your_client_id
    export REDDIT_CLIENT_SECRET=your_client_secret
    export REDDIT_SUB=name_of_your_sub
    python reddit_tui.py

Get credentials at https://www.reddit.com/prefs/apps
Create a "script" type app. The redirect URI can be http://localhost:8080.
"""

import os
import praw
import re
import threading
import webbrowser

from collections import deque
from datetime import datetime, timezone
from textwrap import wrap

_URL_RE = re.compile(r"https?://")

from praw.models import Comment as PrawComment
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, ListItem, ListView, Static

SUBREDDIT = os.environ['REDDIT_SUB']
MAX_ROWS = 200
USER_AGENT = "webdev-tui/1.0"

_submission_age_cache: dict[str, float] = {}


def ts_to_local_timezone(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()


def age_str(utc_ts: float) -> str:
    """Return human-readable age from a UTC timestamp (e.g. '3m', '2h', '4d')."""
    delta = datetime.now(timezone.utc).timestamp() - utc_ts
    if delta < 60:
        return f"{int(delta)}s"
    if delta < 3600:
        return f"{int(delta / 60)}m"
    if delta < 86400:
        return f"{int(delta / 3600)}h"
    return f"{int(delta / 86400)}d"


def get_thread_age(comment: PrawComment) -> str:
    """Return the age of the parent thread, caching the timestamp to avoid extra API calls."""
    link_id = comment.link_id
    if link_id not in _submission_age_cache:
        try:
            _submission_age_cache[link_id] = comment.submission.created_utc
        except Exception:
            return "?"
    return age_str(_submission_age_cache[link_id])


class CommentItem(ListItem):
    """A single comment block with author, body, and link each on their own line."""

    DEFAULT_CSS = """
    CommentItem {
        height: auto;
        padding: 0 0 1 0;
        margin: 0;
    }
    CommentItem > Static {
        height: auto;
        padding: 0;
        margin: 0;
        background: transparent;
    }
    CommentItem:focus > Static.header {
        color: $success-lighten-2;
    }
    """

    def __init__(
        self,
        author: str,
        preview: str,
        posted: str,
        thread_age: str,
        thread_old: bool,
        link: str,
    ) -> None:
        super().__init__()
        self.link_url = link
        self._author = author
        self._preview = preview
        self._posted = posted
        self._thread_age = thread_age
        self._thread_old = thread_old

    def compose(self) -> ComposeResult:
        age_markup = (
            f"[bold red]{self._thread_age}[/bold red]"
            if self._thread_old
            else self._thread_age
        )
        yield Static(
            f"[bold green]u/{self._author}[/bold green]  "
            f"[dim]{self._posted}  ·  thread [/dim]{age_markup}[dim] old[/dim]",
            classes="header",
        )
        yield Static(self._preview, classes="body")
        yield Static(self.link_url, classes="link")


class RedditTUI(App[None]):
    """Live subreddit comment viewer."""

    TITLE = f"/r/{SUBREDDIT} – Live Comments"
    CSS = """
    Screen {
        background: $surface;
    }
    ListView {
        height: 1fr;
    }
    #status {
        height: 1;
        padding: 0 1;
        background: $panel;
        color: $text-muted;
    }
    CommentItem Static.link {
        color: $accent;
    }
    CommentItem Static.body {
        color: $text;
    }
    """
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("c", "clear_list", "Clear"),
        Binding("p", "toggle_pause", "Pause/Resume"),
        Binding("enter", "open_link", "Open in browser"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._items: deque[CommentItem] = deque()
        self._paused = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield ListView(id="list")
        yield Static("Starting…", id="status")
        yield Footer()

    def on_mount(self) -> None:
        threading.Thread(target=self._start_stream, daemon=True, name="reddit-stream").start()

    def _start_stream(self) -> None:
        """Stream comments from Reddit in a daemon thread using PRAW."""
        client_id = os.environ.get("REDDIT_CLIENT_ID", "")
        client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "")

        if not client_id or not client_secret:
            self.call_from_thread(
                self._set_status,
                "[red]REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET are not set. "
                "Create a 'script' app at reddit.com/prefs/apps[/red]",
            )
            return

        try:
            reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=USER_AGENT,
            )
            subreddit = reddit.subreddit(SUBREDDIT)
            self.call_from_thread(
                self._set_status,
                "Streaming r/webdev  ·  [bold]P[/bold] pause  "
                "[bold]C[/bold] clear  [bold]Enter[/bold] open link  [bold]Q[/bold] quit",
            )

            # Show the {MAX_ROWS} most recent comments immediately (API returns newest-first).
            for comment in reversed(list(subreddit.comments(limit=MAX_ROWS))):
                self.call_from_thread(self._add_item, comment)

            # Stream only comments that arrive after this point.
            for comment in subreddit.stream.comments(skip_existing=True):
                self.call_from_thread(self._add_item, comment)
        except Exception as exc:
            self.call_from_thread(self._set_status, f"[red]Stream error: {exc}[/red]")

    def _set_status(self, msg: str) -> None:
        self.query_one("#status", Static).update(msg)

    def _add_item(self, comment: PrawComment) -> None:
        lv = self.query_one("#list", ListView)

        author = getattr(comment.author, "name", "[deleted]")
        raw = comment.body.strip().replace("\n", " ").replace("  ", " ")
        width = lv.content_region.width - 2
        all_lines = wrap(raw, width=width)
        lines = all_lines[:3]
        if len(all_lines) > 3:
            lines[-1] += "…"
        prefix = "[red]\\[!\\][/red] " if _URL_RE.search(raw) else ""
        preview = prefix + "\n".join(lines)
        posted = ts_to_local_timezone(comment.created_utc).strftime('%H:%M')
        thread_age = get_thread_age(comment)
        thread_old = (
            comment.link_id in _submission_age_cache
            and datetime.now(timezone.utc).timestamp() - _submission_age_cache[comment.link_id]
            > 30 * 86400
        )
        link = f"https://reddit.com{comment.permalink}"

        item = CommentItem(author, preview, posted, thread_age, thread_old, link)
        lv.append(item)
        self._items.append(item)

        # Remove oldest items once we exceed MAX_ROWS.
        while len(self._items) > MAX_ROWS:
            oldest = self._items.popleft()
            oldest.remove()

        if not self._paused:
            lv.scroll_end(animate=False)

    def action_quit(self) -> None:
        self.exit()

    def action_clear_list(self) -> None:
        self.query_one("#list", ListView).clear()
        self._items.clear()

    def action_toggle_pause(self) -> None:
        self._paused = not self._paused
        if self._paused:
            self._set_status("[yellow]⏸ Paused — press P to resume[/yellow]")
        else:
            self._set_status(
                "Streaming r/webdev  ·  [bold]P[/bold] pause  "
                "[bold]C[/bold] clear  [bold]Enter[/bold] open link  [bold]Q[/bold] quit"
            )
            self.query_one("#list", ListView).scroll_end(animate=False)

    def action_open_link(self) -> None:
        """Open the highlighted comment's permalink in the default browser."""
        lv = self.query_one("#list", ListView)
        item = lv.highlighted_child
        if isinstance(item, CommentItem):
            webbrowser.open(item.link_url)


def main() -> None:
    RedditTUI().run(mouse=False)


if __name__ == "__main__":
    main()

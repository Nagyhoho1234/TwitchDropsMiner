from __future__ import annotations

import re
import asyncio
import logging
from time import time
from getpass import getpass
from collections import abc
from datetime import datetime
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from translate import _
from constants import OUTPUT_FORMATTER
from exceptions import ExitRequest, MinerException

if TYPE_CHECKING:
    from yarl import URL

    from twitch import Twitch
    from channel import Channel
    from utils import Game, _T
    from inventory import DropsCampaign, TimedDrop


logger = logging.getLogger("TwitchDrops")


class _ConsoleOutputHandler(logging.Handler):
    # console counterpart of gui._TKOutputHandler
    def __init__(self, output: HeadlessGUIManager):
        super().__init__()
        self._output = output

    def emit(self, record: logging.LogRecord) -> None:
        self._output.print(self.format(record))


@dataclass
class LoginData:
    # console counterpart of gui.LoginData (duck-type compatible)
    username: str
    password: str
    token: str


class HeadlessStatusBar:
    """
    Console counterpart of gui.StatusBar: prints the status line whenever it changes.
    Consecutive statuses that differ only in digits (e.g. "(1/20)" progress counters)
    are considered the same status, to avoid flooding the console during inventory fetch.
    """
    _DIGITS = re.compile(r"\d+")

    def __init__(self, manager: HeadlessGUIManager):
        self._manager = manager
        self._text: str = ''

    def update(self, text: str) -> None:
        if text == self._text:
            return
        changed: bool = self._DIGITS.sub('#', text) != self._DIGITS.sub('#', self._text)
        self._text = text
        if changed:
            self._manager.print(f"Status: {text}")

    def clear(self) -> None:
        self._text = ''


class HeadlessWebsocketStatus:
    """
    Console counterpart of gui.WebsocketStatus: keeps the per-websocket state in memory
    without printing anything - connection details are already logged by the websocket logger.
    """
    def __init__(self, manager: HeadlessGUIManager):
        self._items: dict[int, dict[str, Any]] = {}

    def update(self, idx: int, status: str | None = None, topics: int | None = None) -> None:
        if status is None and topics is None:
            raise TypeError("You need to provide at least one of: status, topics")
        entry = self._items.setdefault(idx, {"status": '', "topics": 0})
        if status is not None:
            entry["status"] = status
        if topics is not None:
            entry["topics"] = topics

    def remove(self, idx: int) -> None:
        self._items.pop(idx, None)


class HeadlessLoginForm:
    """
    Console counterpart of gui.LoginForm.

    For the OAuth device code flow (the primary login path), the activation URL and code
    are printed to the console, so the user can complete the login on any other device.
    The username/password flow falls back to interactive console prompts.
    """
    def __init__(self, manager: HeadlessGUIManager):
        self._manager = manager
        self._status: str = ''
        self._user_id: int | None = None
        self.update(_("gui", "login", "logged_out"), None)

    def clear(self, login: bool = False, password: bool = False, token: bool = False) -> None:
        # nothing to clear - console prompts don't retain their input
        pass

    async def ask_login(self) -> LoginData:
        self.update(_("gui", "login", "required"), None)
        while True:
            self._manager.print(_("gui", "login", "request"))
            try:
                username: str = (
                    await self._manager.coro_unless_closed(
                        asyncio.to_thread(input, "Username: ")
                    )
                ).strip()
                password: str = await self._manager.coro_unless_closed(
                    asyncio.to_thread(getpass, "Password: ")
                )
                token: str = (
                    await self._manager.coro_unless_closed(
                        asyncio.to_thread(input, "2FA token (leave empty if not applicable): ")
                    )
                ).strip()
            except EOFError:
                raise MinerException(
                    "No interactive console is available to enter the login credentials"
                )
            login_data = LoginData(username, password, token)
            # basic input data validation, mirroring gui.LoginForm.ask_login
            if not 3 <= len(login_data.username) <= 25:
                continue
            if len(login_data.password) < 8:
                continue
            if login_data.token and len(login_data.token) < 6:
                continue
            return login_data

    async def ask_enter_code(self, page_url: URL, user_code: str) -> None:
        self.update(_("gui", "login", "required"), None)
        self._manager.print(_("gui", "login", "request"))
        self._manager.print(
            '\n'.join((
                "Open this page in a browser on any device to log in:",
                f"    {page_url}",
                f"...and enter this code when asked: {user_code}",
                "The miner will continue automatically once the login is confirmed.",
            ))
        )

    def update(self, status: str, user_id: int | None) -> None:
        if (status, user_id) == (self._status, self._user_id):
            return
        self._status = status
        self._user_id = user_id
        user_str: str = str(user_id) if user_id is not None else '-'
        self._manager.print(f"Login status: {status}, user ID: {user_str}")


class HeadlessCampaignProgress:
    """
    Console counterpart of gui.CampaignProgress.

    Instead of an asyncio countdown task driving progress bar labels, this keeps
    a timestamp of when the current "watch minute" started. minute_almost_done()
    replicates the GUI semantics: True when no minute countdown is running,
    or when it has ALMOST_DONE_SECONDS or less left of the 60 seconds.
    This feeds the watch loop's progress watchdog, so it must stay faithful.
    """
    TIMER_SECONDS = 60
    ALMOST_DONE_SECONDS = 10

    def __init__(self, manager: HeadlessGUIManager):
        self._manager = manager
        self._drop: TimedDrop | None = None
        # time() of when the current 60s minute countdown was started, None when not running
        self._timer_start: float | None = None
        # (drop id, current minutes) of the last progress line printed
        self._printed: tuple[str, int] | None = None
        # (confirmed, transport, has unconfirmed minutes) of the last verification state
        self._verification: tuple[bool, str, bool] | None = None

    @property
    def current_drop(self) -> TimedDrop | None:
        # the currently displayed (mined) drop, if any
        return self._drop

    def start_timer(self) -> None:
        if self._timer_start is None:
            if self._drop is not None and self._drop.remaining_minutes > 0:
                self._timer_start = time()
            # NOTE: the GUI displays a single time update otherwise - nothing to do here

    def stop_timer(self) -> None:
        self._timer_start = None

    def minute_almost_done(self) -> bool:
        # already or almost done
        if self._timer_start is None:
            return True
        elapsed: float = time() - self._timer_start
        if elapsed >= self.TIMER_SECONDS:
            # the GUI timer task ends itself once the full minute elapses
            self._timer_start = None
            return True
        return elapsed >= self.TIMER_SECONDS - self.ALMOST_DONE_SECONDS

    def update_verification(
        self, confirmed: bool, transport: str, unconfirmed_minutes: int
    ) -> None:
        # print state changes only, to avoid per-minute console spam
        state: tuple[bool, str, bool] = (confirmed, transport, unconfirmed_minutes > 0)
        if state == self._verification:
            return
        self._verification = state
        if confirmed:
            message: str = "Watch progress: verified by Twitch"
        elif unconfirmed_minutes > 0:
            message = f"Watch progress: unverified for the last {unconfirmed_minutes} minute(s)"
        else:
            message = "Watch progress: unknown"
        self._manager.print(f"{message} (transport: {transport})")

    def clear_verification(self) -> None:
        self._verification = None

    def display(
        self, drop: TimedDrop | None, *, countdown: bool = True, subone: bool = False
    ) -> None:
        self._drop = drop
        self.stop_timer()
        if drop is None:
            # clear the drop display
            self._printed = None
            self.clear_verification()
            return
        if countdown:
            # restart our "watch minute" timer
            self.start_timer()
        # print a progress line, but only when the drop or its progress actually changed
        printed: tuple[str, int] = (drop.id, drop.current_minutes)
        if printed != self._printed:
            self._printed = printed
            campaign: DropsCampaign = drop.campaign
            self._manager.print(
                f"Mining: {drop.rewards_text()} ({campaign.game.name}), "
                f"drop: {drop.progress:.1%} ({drop.current_minutes}/{drop.required_minutes} min), "
                f"campaign: {campaign.progress:.1%} "
                f"({campaign.claimed_drops}/{campaign.total_drops})"
            )


class HeadlessChannelList:
    """
    Console counterpart of gui.ChannelList: there's no channel table to maintain,
    so everything is a no-op. get_selection() always returns None, meaning
    "no channel manually selected" to the channel switching logic.
    """
    def __init__(self, manager: HeadlessGUIManager):
        self._manager = manager

    def shrink(self) -> None:
        pass

    def clear_watching(self) -> None:
        pass

    def set_watching(self, channel: Channel) -> None:
        pass

    def get_selection(self) -> Channel | None:
        return None

    def clear_selection(self) -> None:
        pass

    def clear(self) -> None:
        pass

    def display(self, channel: Channel, *, add: bool = False) -> None:
        pass

    def remove(self, channel: Channel) -> None:
        pass


class HeadlessTrayIcon:
    """
    Console counterpart of gui.TrayIcon: notifications are printed to the console,
    icon changes only track the state name.
    """
    TITLE = "Twitch Drops Miner"
    ICON_STATES = ("pickaxe", "active", "idle", "error", "maint")

    def __init__(self, manager: HeadlessGUIManager):
        self._manager = manager
        self._icon_state: str = "pickaxe"

    def stop(self) -> None:
        pass

    def quit(self) -> None:
        self._manager.close()

    def minimize(self) -> None:
        pass

    def restore(self) -> None:
        pass

    def notify(
        self, message: str, title: str | None = None, duration: float = 10
    ) -> asyncio.Task[None] | None:
        # do nothing if the user disabled notifications
        if not self._manager._twitch.settings.tray_notifications:
            return None
        flat_message: str = message.replace('\n', ' ')
        if title:
            self._manager.print(f"Notification: {title}: {flat_message}")
        else:
            self._manager.print(f"Notification: {flat_message}")
        return None

    def update_title(self, drop: TimedDrop | None) -> None:
        pass

    def change_icon(self, state: str) -> None:
        if state not in self.ICON_STATES:
            raise ValueError("Invalid icon state")
        self._icon_state = state


class HeadlessInventoryOverview:
    # console counterpart of gui.InventoryOverview: there's no inventory tab to render
    def __init__(self, manager: HeadlessGUIManager):
        self._manager = manager

    async def add_campaign(self, campaign: DropsCampaign) -> None:
        pass

    def clear(self) -> None:
        pass

    def refresh(self) -> None:
        pass

    def update_drop(self, drop: TimedDrop) -> None:
        pass


class HeadlessSettingsPanel:
    # console counterpart of gui.SettingsPanel: settings are managed via the settings file
    def __init__(self, manager: HeadlessGUIManager):
        self._manager = manager

    def set_games(self, games: set[Game]) -> None:
        pass

    def reload_priority_display(self) -> None:
        pass

    def clear_selection(self) -> None:
        pass


class HeadlessWeeklyPicker:
    # console counterpart of gui.WeeklyPicker: there's no "This Week" tab to refresh
    def __init__(self, manager: HeadlessGUIManager):
        self._manager = manager

    def refresh(self) -> None:
        pass


class _StubWidget:
    # accepts and discards widget configuration calls (e.g. button state changes)
    def config(self, *args: Any, **kwargs: Any) -> None:
        pass

    def configure(self, *args: Any, **kwargs: Any) -> None:
        pass


class HeadlessHelpTab:
    # console counterpart of gui.HelpTab: only the invalidate button is touched externally
    def __init__(self, manager: HeadlessGUIManager):
        self._invalidate_button = _StubWidget()


class HeadlessGUIManager:
    """
    Drop-in replacement for gui.GUIManager, providing the same public interface
    without any tkinter usage. All output goes to the console (stdout) instead.

    Used when the application is started with the --headless flag,
    allowing the miner to run on servers and other environments without a display.
    """
    # print the session stats summary at most once per hour
    SESSION_STATS_INTERVAL = 3600

    def __init__(self, twitch: Twitch):
        self._twitch: Twitch = twitch
        self._running: bool = False
        self._close_requested = asyncio.Event()
        # GUI component counterparts
        self.tray = HeadlessTrayIcon(self)
        self.status = HeadlessStatusBar(self)
        self.websockets = HeadlessWebsocketStatus(self)
        self.login = HeadlessLoginForm(self)
        self.progress = HeadlessCampaignProgress(self)
        self.channels = HeadlessChannelList(self)
        self.inv = HeadlessInventoryOverview(self)
        self.settings = HeadlessSettingsPanel(self)
        self.weekly = HeadlessWeeklyPicker(self)
        self.help = HeadlessHelpTab(self)
        # session stats state
        self._session_stats: tuple[int, int, int] = (0, 0, 0)
        self._session_printed: float = 0.0
        self.update_session_stats(drops=0, minutes=0, campaigns=0)
        # register logging handler
        self._handler = _ConsoleOutputHandler(self)
        self._handler.setFormatter(OUTPUT_FORMATTER)
        logger = logging.getLogger("TwitchDrops")
        logger.addHandler(self._handler)
        if (logging_level := logger.getEffectiveLevel()) < logging.ERROR:
            self.print(f"Logging level: {logging.getLevelName(logging_level)}")

    @property
    def running(self) -> bool:
        return self._running

    @property
    def close_requested(self) -> bool:
        return self._close_requested.is_set()

    async def wait_until_closed(self):
        # wait until the application is requested to close
        await self._close_requested.wait()

    async def coro_unless_closed(self, coro: abc.Awaitable[_T]) -> _T:
        # In Python 3.11, we need to explicitly wrap awaitables
        tasks = [asyncio.ensure_future(coro), asyncio.ensure_future(self._close_requested.wait())]
        done: set[asyncio.Task[Any]]
        pending: set[asyncio.Task[Any]]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        if self._close_requested.is_set():
            raise ExitRequest()
        return await next(iter(done))

    def prevent_close(self):
        self._close_requested.clear()

    def start(self):
        self._running = True

    def stop(self):
        self.progress.stop_timer()
        self._running = False

    def close(self, *args) -> int:
        """
        Requests the application to close.
        """
        self._close_requested.set()
        # notify client we're supposed to close
        self._twitch.close()
        return 0

    def close_window(self):
        """
        No window to close in headless mode - only invalidates the logging handler.
        """
        logging.getLogger("TwitchDrops").removeHandler(self._handler)

    # these are here to interface with underlaying GUI components
    def save(self, *, force: bool = False) -> None:
        # no image cache is used in headless mode - nothing to save
        pass

    def grab_attention(self, *, sound: bool = True):
        # there's no window to restore or bell to ring in headless mode
        pass

    def set_games(self, games: set[Game]) -> None:
        self.settings.set_games(games)

    def display_drop(
        self, drop: TimedDrop, *, countdown: bool = True, subone: bool = False
    ) -> None:
        self.progress.display(drop, countdown=countdown, subone=subone)

    def clear_drop(self):
        self.progress.display(None)

    def print(self, message: str):
        # print to the console, mirroring the GUI output format
        stamp = datetime.now().strftime("%X")
        if '\n' in message:
            message = message.replace('\n', f"\n{stamp}: ")
        print(f"{stamp}: {message}", flush=True)

    def update_session_stats(self, *, drops: int, minutes: int, campaigns: int) -> None:
        # store the session stats, print the summary at most once per hour
        stats: tuple[int, int, int] = (drops, minutes, campaigns)
        changed: bool = stats != self._session_stats
        self._session_stats = stats
        now: float = time()
        if changed and now - self._session_printed >= self.SESSION_STATS_INTERVAL:
            self._session_printed = now
            self.print(
                _("gui", "session", "summary").format(
                    drops=drops, minutes=minutes, campaigns=campaigns
                )
            )

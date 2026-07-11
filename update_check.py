from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from translate import _
from utils import task_wrapper
from version import FORK_VERSION

if TYPE_CHECKING:
    from twitch import Twitch
    from constants import JsonType


logger = logging.getLogger("TwitchDrops")


RELEASES_URL: str = (
    "https://api.github.com/repos/Nagyhoho1234/TwitchDropsMiner/releases/latest"
)
UPDATE_USER_AGENT: str = f"TwitchDropsMiner/{FORK_VERSION}"
# first check happens shortly after startup, then once per day
INITIAL_DELAY: float = 15
CHECK_INTERVAL: float = 24 * 60 * 60


async def check_for_update(twitch: Twitch) -> None:
    """
    Performs a single update check against the fork's GitHub releases.

    Compares the latest release tag to FORK_VERSION. Announces newer versions in the GUI
    (output log + tray notification), logs-only when up to date.
    Never raises: all errors are swallowed and logged.
    """
    try:
        session = await twitch.get_session()
        # NOTE: GitHub API requires a User-Agent header on all requests
        async with session.get(
            RELEASES_URL, headers={"User-Agent": UPDATE_USER_AGENT}
        ) as response:
            if response.status != 200:
                logger.warning(f"Update check failed: HTTP {response.status} from GitHub API")
                return
            data: JsonType = await response.json()
    except Exception:
        # covers connection errors, timeouts, proxy issues and malformed JSON
        logger.warning("Update check failed", exc_info=True)
        return
    tag_name = data.get("tag_name")
    if not isinstance(tag_name, str) or not tag_name:
        logger.warning(f"Update check failed: no 'tag_name' in GitHub response: {data!r}")
        return
    if tag_name == FORK_VERSION:
        logger.info(f"Update check: {FORK_VERSION} is the latest version")
        return
    html_url = data.get("html_url") or ""
    message = _("gui", "update", "available").format(version=tag_name)
    twitch.print(message)
    if html_url:
        twitch.print(html_url)
    twitch.gui.tray.notify(f"{message}\n{html_url}".strip(), "Update Available")


@task_wrapper
async def update_check_loop(twitch: Twitch) -> None:
    """
    Background task: checks for updates shortly after startup, then every 24 hours.

    The settings flag is re-read on every cycle, so toggling it takes effect
    without a restart. Checks never raise, so the loop runs for the app's lifetime.
    """
    await asyncio.sleep(INITIAL_DELAY)
    while True:
        if twitch.settings.update_check:
            await check_for_update(twitch)
        await asyncio.sleep(CHECK_INTERVAL)

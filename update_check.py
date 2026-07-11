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


def _release_number(tag: str) -> int | None:
    """
    Extracts N from a "v16-fork.N" tag. Returns None for any other format.
    """
    prefix = "v16-fork."
    if tag.startswith(prefix) and tag[len(prefix):].isdigit():
        return int(tag[len(prefix):])
    return None


def _is_newer(remote_tag: str, local_tag: str) -> bool:
    """
    True only when the remote release is actually newer than the local build.
    A local build ahead of the latest release, or an equal tag, is not "newer".
    Unparseable (format-drifted) remote tags count as newer, so users get notified.
    """
    if remote_tag == local_tag:
        return False
    remote = _release_number(remote_tag)
    local = _release_number(local_tag)
    if remote is None or local is None:
        return True
    return remote > local


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
    if not _is_newer(tag_name, FORK_VERSION):
        logger.info(f"Update check: {FORK_VERSION} is the latest version")
        return
    html_url = data.get("html_url") or ""
    # defense in depth: only surface the release URL when it points at this fork's
    # releases - a spoofed API response must not be able to display an arbitrary link
    if not html_url.startswith("https://github.com/Nagyhoho1234/TwitchDropsMiner/"):
        html_url = ""
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

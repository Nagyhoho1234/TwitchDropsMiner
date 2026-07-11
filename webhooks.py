from __future__ import annotations

import logging
# NOTE: monotonic is used for debounce intervals - unlike time(), it can't jump
# when the system clock is adjusted (e.g. NTP sync on a Raspberry Pi without an RTC)
from time import monotonic
from typing import Any, TYPE_CHECKING

import aiohttp

if TYPE_CHECKING:
    from twitch import Twitch
    from inventory import TimedDrop, DropsCampaign


logger = logging.getLogger("TwitchDrops")


class WebhookNotifier:
    """
    Sends Discord-compatible webhook notifications for internal miner events.

    Subscribes to the Twitch instance's event bus and POSTs simple JSON messages
    ({"content": "..."}) to the webhook URL from the settings. If the URL is empty,
    nothing is sent. All errors are swallowed and logged - a webhook failure
    must never affect mining.
    """
    # Debounce interval for repeated "login required" alerts
    LOGIN_ALERT_INTERVAL: float = 30 * 60  # seconds
    # Debounce interval for repeated transport rotations: during a total outage the
    # watchdog cycles transports every 15 minutes - one notice per hour is plenty,
    # the stalled/recovered pair already tells the user everything actionable
    ROTATION_ALERT_INTERVAL: float = 60 * 60  # seconds
    # Per-request timeout - webhooks are fire-and-forget and mustn't hang around
    REQUEST_TIMEOUT: float = 30  # seconds

    def __init__(self, twitch: Twitch):
        self._twitch: Twitch = twitch
        self._last_login_alert: float = 0.0
        self._last_rotation_alert: float = 0.0
        twitch.on_event("drop_claimed", self._on_drop_claimed)
        twitch.on_event("campaign_discovered", self._on_campaign_discovered)
        twitch.on_event("campaign_finished", self._on_campaign_finished)
        twitch.on_event("mining_stalled", self._on_mining_stalled)
        twitch.on_event("transport_rotated", self._on_transport_rotated)
        twitch.on_event("mining_recovered", self._on_mining_recovered)
        twitch.on_event("login_required", self._on_login_required)

    async def send(self, content: str) -> bool:
        """
        POSTs a message to the configured Discord webhook URL.
        Returns True if the message was delivered, False otherwise. Never raises.

        NOTE: This deliberately avoids Twitch.request(), which retries connection
        errors indefinitely and prints them to the GUI output - for a notification,
        failing fast and quietly is the correct behavior instead.
        """
        url: str = self._twitch.settings.webhook_url.strip()
        if not url:
            return False
        try:
            session = await self._twitch.get_session()
            kwargs: dict[str, Any] = {}
            if self._twitch.settings.proxy:
                kwargs["proxy"] = self._twitch.settings.proxy
            async with session.post(
                url,
                json={"content": content},
                timeout=aiohttp.ClientTimeout(total=self.REQUEST_TIMEOUT),
                **kwargs,
            ) as response:
                if response.status >= 400:
                    logger.warning(f"Webhook delivery failed: HTTP {response.status}")
                    return False
            return True
        except Exception as exc:
            # NOTE: no exc_info here - aiohttp exception messages can embed the webhook URL,
            # which contains the webhook's secret token, and must not end up in the log file
            logger.warning(f"Webhook delivery failed: {type(exc).__name__}")
            return False

    async def _on_drop_claimed(self, drop: TimedDrop) -> None:
        await self.send(f"🎁 Drop claimed: {drop.name} ({drop.campaign.game})")

    async def _on_campaign_discovered(self, campaign: DropsCampaign) -> None:
        await self.send(f"🆕 New campaign: {campaign.name} ({campaign.game})")

    async def _on_campaign_finished(self, campaign: DropsCampaign) -> None:
        await self.send(f"🏁 Campaign finished: {campaign.name} ({campaign.game})")

    async def _on_mining_stalled(self, minutes: int, transport: str) -> None:
        await self.send(
            f"⚠️ Miner stalled: Twitch has not counted watch time for {minutes} minutes "
            f"(method: {transport}). Trying another method — check on me if this repeats."
        )

    async def _on_transport_rotated(self, old: str, new: str) -> None:
        now: float = monotonic()
        if now - self._last_rotation_alert < self.ROTATION_ALERT_INTERVAL:
            return
        self._last_rotation_alert = now
        await self.send(f"🔄 Watch method switched: {old} → {new}")

    async def _on_mining_recovered(self, transport: str) -> None:
        await self.send(
            f"✅ Mining recovered — progress is being counted again (method: {transport})"
        )

    async def _on_login_required(self) -> None:
        now: float = monotonic()
        if now - self._last_login_alert < self.LOGIN_ALERT_INTERVAL:
            return
        self._last_login_alert = now
        await self.send("🔑 Login required — the miner is waiting for login and is NOT mining!")

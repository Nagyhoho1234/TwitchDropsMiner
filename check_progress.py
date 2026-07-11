"""
Read-only verification helper: queries Twitch's Inventory GQL endpoint directly
(using the same login token as the miner) and prints server-side drop progress.
Not part of the application - used to independently confirm mining works.
"""
import asyncio
import sys

import aiohttp

from constants import ClientType, GQL_QUERIES


async def main() -> None:
    jar = aiohttp.CookieJar()
    jar.load("dist/cookies.jar")
    client = ClientType.ANDROID_APP
    cookie = jar.filter_cookies(client.CLIENT_URL)
    token = cookie["auth-token"].value
    headers = {
        "Authorization": f"OAuth {token}",
        "Client-ID": client.CLIENT_ID,
        "User-Agent": client.USER_AGENT,
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.post(
            "https://gql.twitch.tv/gql", json=GQL_QUERIES["Inventory"]
        ) as response:
            data = await response.json()
    if "errors" in data and data["errors"]:
        print("GQL ERROR:", data["errors"])
        sys.exit(1)
    inventory = data["data"]["currentUser"]["inventory"]
    campaigns = inventory["dropCampaignsInProgress"] or []
    if not campaigns:
        print("No campaigns in progress.")
    for campaign in campaigns:
        print(f"{campaign['game']['name']} - {campaign['name']}")
        for drop in campaign["timeBasedDrops"]:
            drop_self = drop.get("self") or {}
            print(
                f"    {drop['name']}: "
                f"{drop_self.get('currentMinutesWatched', '?')}"
                f"/{drop['requiredMinutesWatched']} min, "
                f"claimed: {drop_self.get('isClaimed', '?')}"
            )


if __name__ == "__main__":
    asyncio.run(main())

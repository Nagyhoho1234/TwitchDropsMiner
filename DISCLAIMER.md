# Disclaimer & scope of this fork

This is a personal, good-faith fork of the open-source
[DevilXD/TwitchDropsMiner](https://github.com/DevilXD/TwitchDropsMiner) (MIT licensed).
It exists to keep the tool working during upstream gaps and to add quality-of-life
features. This note states plainly what it is — and, more importantly, what it is **not**.

## What I did

- **Quality-of-life improvements only**: Discord webhook notifications, on-screen "is
  progress actually being counted" indicators, campaign ETAs, a session summary, a weekly
  campaign picker, headless mode, window-position memory, a full set of UI translations,
  and general stability/robustness hardening.
- **A compatibility fix** for the July 2026 breakage, where Twitch changed which watch-event
  transport it counts (mirroring what upstream and other contributors did — see upstream
  issues [#1038](https://github.com/DevilXD/TwitchDropsMiner/issues/1038) and
  [#1099](https://github.com/DevilXD/TwitchDropsMiner/issues/1099), and PR
  [#1102](https://github.com/DevilXD/TwitchDropsMiner/pull/1102)).
- **A self-healing watch-transport watchdog** that switches between the tool's *existing*
  transports when one stops being counted, so it recovers from that class of breakage
  automatically.

All of these are wrappers, UI, and resilience around the tool's **pre-existing** behavior.

## What I did NOT do

- I did **not** discover, introduce, or disclose any new security vulnerability.
- I did **not** invent a new way to bypass anything. The underlying mechanism this tool
  relies on — that Twitch Drops watch-time is credited from client "minute-watched"
  telemetry without requiring real video playback — is **long-standing, public, and well
  known to Twitch**. This class of tool has existed for years, and Twitch has repeatedly
  and deliberately deployed countermeasures against it (anti-bot integrity checks in 2022,
  watch-event transport changes in 2026). There is nothing novel here to report.
- Because nothing new was found, no separate security disclosure is warranted — this file
  *is* the transparency statement.

## Nature and intent

- This is a hobby/weekend project built on public code, offered openly and MIT-licensed so
  the maintainer or anyone else can take, review, or ignore any part of it. The relevant
  changes have been offered to upstream.
- **Using any drop-mining tool may violate Twitch's Terms of Service.** That is a choice and
  risk that rests entirely with each user and their own Twitch account. This fork does not
  encourage ToS violations; it maintains and improves an already-public tool.
- This fork is **not** a long-term maintained project. Once upstream ships its own fixes,
  please switch back to it.

If a rights-holder has concerns about anything here, I'm happy to discuss and act in good
faith — this project is not adversarial and hides nothing.

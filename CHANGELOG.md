# Fork Changelog

This fork tracks [DevilXD/TwitchDropsMiner](https://github.com/DevilXD/TwitchDropsMiner)
master, with the changes below applied on top. If upstream ships its own fix for an issue
listed here, prefer upstream's version.

## v16-fork.6 — 2026-07-11

### Changed
- **Watch-transport rotation is now bounded to a single pass**, to keep the
  self-healing watchdog from ever looking unusual to Twitch. It tries each
  alternate watch method once; if none restores server-confirmed progress, it
  concludes this is a Twitch-side outage (not something switching can fix),
  settles back on the last-known-good method, and only alerts — instead of
  cycling watch methods indefinitely. In normal operation nothing changes (the
  miner keeps using the single current method, same rate, same payload); this
  only affects behavior during a total outage, where it now behaves like a
  browser that's also getting nothing rather than continuously emitting through
  non-current methods.

## v16-fork.5 — 2026-07-11

### Added
- **All fork features localized in all 21 languages.** The ~41 new UI strings
  (This Week tab, webhook settings, trust indicators, ETAs, session summary,
  verify button, update notifications) are now translated into every bundled
  language instead of falling back to English. Machine-translated strings are
  marked with a trailing `#` to make their unreviewed status transparent —
  English and Hungarian are fully reviewed and carry no markers. Native-speaker
  corrections are welcome: fix the string, drop the `#`, open a PR.
  Existing human translations were never modified; placeholders were verified
  programmatically for every string.

## v16-fork.4 — 2026-07-11

Security & stability hardening release, based on two dedicated adversarial reviews of
the entire fork delta. Neither review found any critical or high-severity issue; the
key property — the Twitch auth token/cookies can never reach the Discord webhook or
GitHub hosts — was formally verified. Everything below is defense-in-depth:

### Security
- Headless console output strips control characters, so remote-sourced names
  (campaigns, games, drops) can't inject ANSI/OSC escape sequences into the
  operator's terminal.
- Webhook delivery failures no longer log full exception details, which could
  embed the webhook URL (it contains the webhook's secret token).
- The update notification only displays release URLs pointing at this fork's
  repository (a spoofed API response can't surface an arbitrary link).
- The playlist watch transport refuses non-HTTPS chunk URLs from playlist data.
- Debug-level request logging redacts the Authorization header, so `--log -vvvv`
  can no longer write the OAuth token into the log file (pre-existing upstream
  behavior, fixed here).

### Stability
- Watch-method-switch webhook alerts are debounced to once per hour — during a
  total Twitch outage the rotation fires every 15 minutes, and your alert channel
  should tell you something is wrong, not bury you in noise (the single
  stalled/recovered alert pair is unaffected).
- Headless console writes go through a dedicated thread: on Windows, selecting
  text in a console (QuickEdit mode) blocks writes, and this previously could
  freeze mining itself until the selection was cleared.
- Duration/debounce timers use the monotonic clock, immune to system clock jumps
  (e.g. NTP sync on a Raspberry Pi without an RTC).
- The GUI output pane is capped at 5000 lines, bounding memory growth over
  multi-week runs (pre-existing upstream behavior, fixed here).

## v16-fork.3 — 2026-07-11

Implements the most-requested items from the upstream issue tracker.

### Added
- **Headless mode** (upstream [#17](https://github.com/DevilXD/TwitchDropsMiner/issues/17),
  the most-upvoted request): run with `--headless` for servers and Raspberry Pi —
  no GUI and no tkinter required at all. Login uses the device-code flow printed
  to the console; progress, status, notifications and trust indicators are logged
  as console lines. Works alongside the Discord webhook notifications for full
  remote monitoring.
- **New-campaign alerts** (upstream [#767](https://github.com/DevilXD/TwitchDropsMiner/issues/767)):
  when a reload discovers a campaign that wasn't there before, the miner prints it,
  sends a tray notification, and posts a Discord webhook message.
- **Window position & size memory** (upstream [#146](https://github.com/DevilXD/TwitchDropsMiner/issues/146),
  [#1092](https://github.com/DevilXD/TwitchDropsMiner/issues/1092)): restored on startup,
  with multi-monitor safety — a position saved on a disconnected monitor falls back
  to default placement instead of restoring off-screen.
- **Skip unfinishable campaigns** (upstream [#955](https://github.com/DevilXD/TwitchDropsMiner/issues/955),
  Settings → General, off by default): don't spend watch time on active campaigns
  whose remaining runtime is shorter than the watch time they still require.

### Fixed
- **Blank settings.json after reboot** (upstream [#1042](https://github.com/DevilXD/TwitchDropsMiner/issues/1042)):
  settings are now flushed to disk before the atomic rename, so a crash or power
  loss can no longer leave an empty file behind.
- **"Stream state change for a non-existing channel" ERROR spam**
  (upstream [#110](https://github.com/DevilXD/TwitchDropsMiner/issues/110)): these are a
  benign cleanup race and are now logged at trace level only.

### Verified
- **Python 3.14.6 on Windows** (for upstream [#1081](https://github.com/DevilXD/TwitchDropsMiner/issues/1081)):
  all dependencies install, every module imports, PyInstaller packages successfully,
  and the resulting exe launches — no code changes required.

## v16-fork.2 — 2026-07-11

### Added
- **Discord webhook notifications** (Settings → General → webhook URL + Test button):
  drop claimed, campaign finished, and — most importantly — an alert when the miner
  is NOT actually mining: watch time not being counted by Twitch (stall + recovery),
  watch method switched, and login required. No more waiting for days on a silently
  broken miner.
- **Trust indicators**: the Main tab now shows whether drop progress is
  server-confirmed by Twitch ("Confirmed by Twitch ✔" / "Not confirmed for X min ⚠")
  and which watch method is in use, plus a "Verify" button in the Help tab that
  checks the current drop's progress directly against the Twitch servers.
- **Update check**: on startup (and daily), the miner checks this fork's GitHub
  releases and notifies when a newer build is available (can be disabled in Settings).
- **ETAs**: the current drop shows its wall-clock finish estimate; inventory
  campaigns show "≈ Xh Ym left".
- **Session summary**: drops claimed / minutes mined (server-confirmed only) /
  campaigns finished this session, on the Main tab.
- **"This Week" tab** (adopted from upstream PR #1100, fully localized): weekly
  campaign picker with one-click account linking and priority-list apply.
- **Internal event bus** on the Twitch class — all features above are decoupled
  subscribers, making them easy to upstream or remove independently.
- All new UI strings localized (English + Hungarian, linguistically reviewed).

## v16-fork.1 — 2026-07-11

### Fixed
- **Drop progress frozen since 2026-07-10** (upstream issue
  [#1099](https://github.com/DevilXD/TwitchDropsMiner/issues/1099)): Twitch stopped
  counting the GQL `sendSpadeEvents` mutation as watch time. Watch events are now sent
  to the Spade POST endpoint again, with the enriched payload the web client sends
  (`client_time`, `game`, `game_id`, `is_live`, `minutes_logged`). Based on upstream PR
  [#1102](https://github.com/DevilXD/TwitchDropsMiner/pull/1102). Verified server-side
  via the Inventory GQL operation: continuous minute-by-minute progression across three
  concurrent campaigns, including automatic drop claiming.

### Added
- **Hungarian localization** (`lang/Magyar.json`): full translation of the UI.
  AI-translated, then reviewed in a separate linguistic pass for natural,
  idiomatic Hungarian (grammar, register, terminology consistency, no calques).
  Verified that all accented characters (including ő/ű) load and render
  correctly in every GUI font; the log file is now written as UTF-8 so accented
  characters (in any language, or in channel names) can't corrupt logging.
- **Watch transport watchdog**: Twitch has flip-flopped twice in 2026 between counting
  Spade POST and GQL watch events (upstream issues
  [#1038](https://github.com/DevilXD/TwitchDropsMiner/issues/1038), #1099), each time
  silently breaking the miner for days until patched. The miner now knows all three
  watch transports (`spade`, `gql`, `playlist`) and rotates to the next one
  automatically if watch events are sent but Twitch confirms no drop progress for
  15 consecutive minutes. Progress confirmation uses real server signals only
  (websocket `drop-progress` events and `CurrentDrop` GQL minute increases);
  GQL outages hold the counter rather than counting as dead minutes, and no
  transport failure can crash the watch loop.
- `check_progress.py`: standalone read-only helper that queries Twitch's Inventory GQL
  endpoint with the miner's saved login (`dist/cookies.jar`) and prints server-side
  drop progress — useful to verify mining actually counts, independently of the GUI.

### Changed
- The duplicated Spade/GQL `minute-watched` payload dictionaries were unified into a
  single `_watch_properties()` builder, so the two can no longer drift apart
  (`client_time` is also regenerated per send now, instead of being cached).

### Build notes
- Build with python.org **Python 3.10** (matching upstream CI):
  `python -m venv env310 && env310/Scripts/pip install -r requirements.txt pyinstaller && env310/Scripts/pyinstaller build.spec`
- Do **not** build with a Conda/Anaconda Python — PyInstaller silently omits the Tcl/Tk
  DLLs and the resulting exe fails with `DLL load failed while importing _tkinter`.

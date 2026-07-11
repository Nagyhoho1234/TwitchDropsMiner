# Fork Changelog

This fork tracks [DevilXD/TwitchDropsMiner](https://github.com/DevilXD/TwitchDropsMiner)
master, with the changes below applied on top. If upstream ships its own fix for an issue
listed here, prefer upstream's version.

## 2026-07-11

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

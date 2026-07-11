# Fork Development Guide

Engineering reference for the changes this fork adds on top of
[DevilXD/TwitchDropsMiner](https://github.com/DevilXD/TwitchDropsMiner) `master`.
Read this before modifying fork features. For the user-facing change list see
[CHANGELOG.md](CHANGELOG.md); for release history see the bottom of this file.

---

## 1. Design backbone: the internal event bus

Every fork feature is a **decoupled subscriber** on a tiny event bus living on the
`Twitch` class (`twitch.py`). This is deliberate: it keeps features separable so any
one can be upstreamed or removed without touching the others.

```python
twitch.on_event(name, callback)   # register; callback gets event data as kwargs
twitch.emit_event(name, **data)   # fire; sync callbacks called directly,
                                  # coroutine callbacks scheduled as tasks
```

- `emit_event` wraps each callback in `try/except` — a broken listener can never crash
  mining. Coroutine tasks are strong-referenced in `self._event_tasks` (asyncio only
  weak-refs tasks, so this prevents mid-flight GC).
- Subscriptions are registered **once per process**, all inside `Twitch.__init__`
  (and `WebhookNotifier.__init__`, itself constructed there). The `Twitch` instance
  survives `ReloadRequest`, so listeners are never re-registered → no duplicate-handler
  multiplication across reloads.

### Event catalog

| Event | Data (kwargs) | Emitted from |
|-------|---------------|--------------|
| `drop_claimed` | `drop` | claim paths in `twitch.py` |
| `campaign_discovered` | `campaign` | `fetch_inventory` (first fetch silent, see `_known_campaigns`) |
| `campaign_finished` | `campaign` | claim paths |
| `mining_stalled` | `minutes`, `transport` | `_rotate_watch_transport` (once per stall) |
| `transport_rotated` | `old`, `new` | `_rotate_watch_transport` |
| `mining_recovered` | `transport` | `_watch_loop` recovery branches |
| `login_required` | — | auth flow in `twitch.py` |
| `watch_minute` | `confirmed`, `transport`, `unconfirmed_minutes` | end of every `_watch_loop` cycle (~1/min) |

**Adding an event:** emit it at the producer site with `self.emit_event("name", **data)`,
document it in the `Twitch.__init__` comment block and in the table above, then subscribe
where needed.

---

## 2. Watch transports & the self-healing watchdog

Twitch has silently stopped counting one watch-event transport twice in 2026
(#1038: Spade→GQL; #1099: GQL→Spade). The fork makes the transport swappable and
self-healing.

- **Transports** (`constants.py: WATCH_TRANSPORTS = ("spade", "gql", "playlist")`):
  - `spade` — POST `minute-watched` to the Spade endpoint (current web-client method)
  - `gql` — `sendSpadeEvents` GQL mutation (web-client method Apr–Jul 2026)
  - `playlist` — HEAD on an HLS chunk (legacy; least browser-like, only ever transient)
- **Dispatch** (`channel.py: Stream.send_watch`): picks the transport by
  `twitch._watch_transport_idx`. All transport sends are exception-contained so a failing
  transport can never kill the critical `_watch_loop`.
- **Watchdog** (`twitch.py: _watch_loop` + `_rotate_watch_transport`): counts consecutive
  minutes where watch events are sent, a drop is earnable, but **no server-confirmed
  progress** occurs. "Confirmed" = a websocket `drop-progress` event OR `CurrentDrop` GQL
  showing a minute increase. Locally-estimated ("bumped") minutes deliberately don't count.
  After `WATCH_TRANSPORT_SWITCH_MINUTES` (15) dead minutes it rotates.
- **Bounded rotation (detectability):** rotation is capped to a **single pass**
  (`_rotations_since_stall`). It tries each alternate transport once; if none restores
  progress it settles back on `_known_good_transport_idx` (the last transport that produced
  confirmed progress ≈ what the browser uses) and only alerts. This avoids ever cycling
  non-current methods indefinitely during a total outage. `_known_good_transport_idx` and
  `_rotations_since_stall` reset whenever real progress is confirmed.

The watchdog is also what powers the trust indicators and stall webhooks (via the
`watch_minute` / `mining_stalled` / `mining_recovered` events).

---

## 3. Feature modules (self-contained new files)

| File | Feature | Wiring |
|------|---------|--------|
| `webhooks.py` | `WebhookNotifier` — Discord webhook alerts (claims, new/finished campaigns, **stall/recover/login** alerts). Debounced: login 30 min, rotation 1 h (monotonic clock). | Constructed in `Twitch.__init__`; subscribes to the bus. |
| `update_check.py` | Startup + daily GitHub-releases check vs `FORK_VERSION`; tray/console notice on a newer release. Real version compare, URL gated to this repo. | `update_check_loop` started in `_run`, cancelled in `shutdown`. |
| `headless.py` | `HeadlessGUIManager` — drop-in for `gui.GUIManager` with **zero tkinter**, for servers/Pi. Console output, device-code login. | `Twitch.__init__` picks it when `settings.headless` (`--headless`); `gui`/tkinter imported lazily only in GUI mode. |
| `check_progress.py` | Standalone read-only verifier: queries Inventory GQL with `dist/cookies.jar`, prints server-side drop minutes. **Not** bundled into the exe. | Run manually: `env310\Scripts\python check_progress.py` |

---

## 4. GUI additions (`gui.py`)

All in the existing tkinter GUI, all strings via `_(...)`:
- **Trust indicators** (`CampaignProgress`): server-verified ✔/⚠ line + active watch method,
  driven by the `watch_minute` event; `Verify` button in Help tab → `twitch.verify_drop_progress`.
- **ETAs**: drop finish clock-time (`CampaignProgress`) + per-campaign "≈ Xh Ym left"
  (`InventoryOverview`).
- **Session summary** (`GUIManager` main tab): drops/minutes/campaigns via `SessionStats` +
  `update_session_stats`.
- **This Week tab** (`WeeklyPicker`): weekly campaign picker (adopted from upstream PR #1100,
  fully localized). Refreshed from `fetch_inventory`.
- **Window geometry memory** (`GUIManager`): save on close / restore on start, multi-monitor
  safe, via `settings.window_geometry` (uses `root.geometry()` getter for Windows round-trip).
- **Settings checkboxes**: `update_check`, `skip_unfinishable`; webhook URL entry + Test button.

Output pane (`ConsoleOutput`) is capped at `MAX_LINES = 5000` to bound multi-week memory.

---

## 5. Settings (`settings.py`)

Added fields (in `SettingsFile`, `default_settings`, and the `Settings` annotations):

| Field | Default | Notes |
|-------|---------|-------|
| `webhook_url` | `""` | Discord webhook, plaintext (not a secret worth encrypting locally) |
| `update_check` | `True` | toggle in Settings → General |
| `window_geometry` | `""` | `"WxH+X+Y"` string |
| `skip_unfinishable` | `False` | toggle in Settings → General |
| `headless` | (args only) | resolved from `--headless` via `Settings.__getattr__`, no file field |

`json_save` (`utils.py`) now `flush()`+`fsync()`s before the atomic rename (upstream #1042).

---

## 6. Translations (`translate.py` + `lang/*.json`)

- **`English.json` is the source of truth.** In dev mode `translate.py` regenerates it from
  `default_translation` on import — so **add new keys to `default_translation` in `translate.py`**
  (both the `TypedDict` and the value), then import once to regenerate `English.json`.
- **Fallback:** missing keys in any language are backfilled from English by `merge_json`
  (`utils.py`), so a missing key **cannot** crash — it just shows English.
- **`#` unreviewed marker:** machine-translated strings end with a trailing ` #`
  (punctuation-aware: before a trailing `": "`). English and Hungarian are human-reviewed and
  carry **no** marker. To graduate a string: fix it and drop the `#`.
- **21 languages** bundled. Helper `.claude/apply_translations.py` applied the machine batch
  with placeholder-parity validation (never overwrites existing human strings).
- **Always verify** after editing: key-set parity and `{placeholder}` parity vs English for
  every language (the apply script does this; see §7).

---

## 7. Build, verify, release

### Build (Windows)
```bash
python -m venv env310                       # MUST be python.org Python 3.10 (matches upstream CI)
env310/Scripts/pip install -r requirements.txt pyinstaller
env310/Scripts/pyinstaller build.spec       # → dist/Twitch Drops Miner (by DevilXD).exe
```
**⚠ Do NOT build with a Conda/Anaconda Python.** PyInstaller silently omits the Tcl/Tk DLLs and
the exe dies with `DLL load failed while importing _tkinter`. (Python 3.14 is verified working
too — see `env314/` and upstream #1081 — but releases stay on 3.10 until upstream bumps.)

### Verify before shipping
```bash
# compile + import every module
env310/Scripts/python -c "import py_compile,glob; [py_compile.compile(f,doraise=True) for f in glob.glob('*.py')]"
env310/Scripts/python -c "import twitch, gui, headless, webhooks, update_check"
# headless must not import tkinter
env310/Scripts/python -c "import sys; sys.modules['tkinter']=None; import headless"
# EN/HU key + placeholder parity (adapt the snippet in git history / apply_translations.py)
# smoke run + independent server-side check
env310/Scripts/python check_progress.py
```
For substantial changes, run an adversarial review (a `code-reviewer` subagent) and, for new
UI strings, a Hungarian/native linguistic review — that's the workflow used throughout.

### Release
1. Bump `FORK_VERSION` in `version.py` (e.g. `v16-fork.7`).
2. Add a `CHANGELOG.md` section.
3. Commit (author identity **must** be `Nagyhoho1234 <Nagyhoho1234@users.noreply.github.com>` —
   never the global git identity).
4. Rebuild the exe, smoke-test it.
5. `git push fork master` then
   `gh release create v16-fork.7 --repo Nagyhoho1234/TwitchDropsMiner --title ... --notes ... "dist/Twitch Drops Miner (by DevilXD).exe"`
6. fork.2+ users get the in-app update notification automatically (that's what `FORK_VERSION`
   drives), so bumping it matters.

---

## 8. How to make common changes

- **New notification / feature reacting to a mining event** → subscribe on the bus in
  `Twitch.__init__` (or in `WebhookNotifier` for a Discord message). If the trigger doesn't
  exist yet, add an event (§1).
- **New setting** → add to `settings.py` (3 places) + a translation key + a GUI checkbox
  mirroring `update_check`/`skip_unfinishable` (and a headless no-op if relevant).
- **New user-visible string** → `translate.py` `default_translation` + `TypedDict`, regenerate
  `English.json`, add to other langs (or leave English fallback + `#`).
- **Touch the watch loop** → re-read §2; the loop is `@task_wrapper(critical=True)` so an
  unhandled exception terminates the miner. Keep all new I/O exception-contained.
- **Headless parity** → any new external `gui.<x>` access must have a matching
  `HeadlessGUIManager` member, or headless AttributeErrors at runtime.

---

## 9. Release history

| Tag | Summary |
|-----|---------|
| v16-fork.1 | July-2026 Spade watch fix (#1099), transport watchdog, Hungarian |
| v16-fork.2 | Event bus, Discord webhooks + stall alerts, trust indicators, update check, ETAs, session summary, This Week tab (#1100) |
| v16-fork.3 | Headless mode (#17), new-campaign alerts (#767), window memory (#146/#1092), skip-unfinishable (#955); fixes #110/#1042; Python 3.14 verified (#1081) |
| v16-fork.4 | Security & stability hardening (two adversarial reviews) |
| v16-fork.5 | All fork features localized in all 21 languages (`#` = unreviewed) |
| v16-fork.6 | Bounded transport rotation (detectability hardening) |

## 10. Upstream engagement (relationship: track master, prefer upstream fixes, MIT)

- **PR [#1103](https://github.com/DevilXD/TwitchDropsMiner/pull/1103)** — Hungarian translation (base keys only; likely merge).
- **Issue [#1099](https://github.com/DevilXD/TwitchDropsMiner/issues/1099)** — watchdog design offered + detectability Q answered.
- **Issue [#1081](https://github.com/DevilXD/TwitchDropsMiner/issues/1081)** — Python 3.14-on-Windows verification reported.
- **PR [#1102](https://github.com/DevilXD/TwitchDropsMiner/pull/1102)** — verified-fix confirmation for the Spade fix.

When upstream ships an official fix, `git pull` and prefer DevilXD's version; the fork features
are decoupled subscribers, so each can be re-offered as a focused PR on request.

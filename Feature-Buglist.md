# **New and Unsorted Features/Bugs**


*(L4 — `[PRIORITY] Test-sweep flake stabilization` — DONE 2026-05-12 via Group 14. Sweep: 809 passed / 0 failed / 0 errors / 15 skipped. See `completed-archive.md`.)*

*(L6 — Details modal pops up after editing from global search — DONE 2026-05-14 via Group 10 Session A (item 10.11). `openEditWizard` and `openCloneWizard` now only set a return-id when a spool/filament details modal is actually visible at launch. See `completed-archive.md`.)*


*(L17 — `[RECURRING] Modal / overlay Z-ordering` — DONE 2026-05-11 via Group 15. `window.mountOverlay()` is now the canonical helper; 5 inline overlays migrated; symptom checklist + z-index ladder documented in CLAUDE.md "Project Conventions". See `completed-archive.md`.)*


*(L37 — `[RECURRING] data/locations.json corruption` — PARTIAL 2026-05-12. Hardening (1) per-call temp filename + (2) verify-after-write tripwire shipped on `feature/locations-json-write-hardening`. Monitor prod hub.log for `verify-after-write FAILED` critical lines; (3) explicit truncate and (4) Docker named volume deferred pending recurrence signal. See `completed-archive.md`.)*




* Keeping the screen on when afk, still causes the screen to blank out. Confirmed on laptop, not on desktop. _[ON HOLD — OS-level power management, not fixable in app code. Candidate mitigations if we care: Wake Lock API (`navigator.wakeLock.request('screen')`) gated behind a toggle in the nav bar; only works when the tab is foreground. Worth considering if we add a kiosk/shop-floor mode.]_
* Config button, for configuing certain things in the system without having to edit a config file manually in a text editor. **Decision: Full-schema design first.** The architecture must be extensible so adding new configurable items "just works" without code changes to the config UI itself. The schema should be self-describing (key, label, type, default, section, validation rules) so the UI can render any new entry automatically. This will pull in the "Make as much of Command Center user configurable as possible" item. When we sit down for design: define the schema format, config storage (JSON file vs. DB table), import/export format, and a section hierarchy. _[NEEDS DESIGN SESSION — schedule a dedicated design discussion before any code starts.]_

* Filabridge status light is still blinking on and of, just more eraticly now. Need to look into this further. _[ON HOLD — hardware/firmware on the filabridge device itself. Not actionable from this repo until we can instrument the device side or get a usage log with timestamps correlated to filabridge-side network events.]_


* Check why FIL:58 wasn't marked as labeled when scanned. The `label_printed` field was retired in M7 and replaced with `needs_label_print` (boolean) — barcode-scan path now updates this field at `app.py:921-922, 968-969`. The FIL:58 case specifically needs manual repro to see whether the update fires and why Activity Log was silent. Could be because FIL:58 is an old physical swatch with no prior spoolman state. _[ON HOLD — need to locate or reprint the FIL:58 physical label/swatch before repro can be attempted. When found: scan with DevTools open → Network tab → `/api/identify_scan` response + Activity Log ticker.]_


* Sub-bug: "Display modal on Display modal" — _[PARTIAL FIX 2026-05-12 (Group 8.3 / `feature/keyboard-nav-polish`) — `openSpoolDetails` and `openFilamentDetails` now route through `_hideSiblingDetailsModal` at function entry, which forcibly closes the sibling details modal (with a 400ms retry to defeat BS5's mid-fade-in `.hide()` ignore). The silent-refresh path (`silent=true`) is intentionally exempt so sync-pulse only repaints the active modal. Covers details↔details stacking.]_ _[FOLLOW-UP 2026-05-14 via `feature/buglist-sweep-2026-05-14` — Wizard↔details stacking now also closes the sibling pair: `_hideSiblingDetailsModal` is exposed as `window.hideAllDetailsModals` and `openWizardModal()` calls it before launching. Covers the 2026-04-29 lock-up where wizard-on-top-of-details triggered a `state.processing` race. Regression coverage in `test_wizard_closes_details_siblings.py` (2 tests — filament-details closes on wizard open + helper-exposure smoke). The leftover frontend-freeze symptom at L28 should be retested with the same scenario.]_

* An unknow issue caused the frontend to lock up, causing it to no longer update to take barcodes. A hard refresh (Control shift R and Control F5) fixed it. We need to figure out what caused this, and fix it so it doesn't happen again. This could be related to the eject button issue above. Also seemed to have cause updates to filabridge to stop until the front end was refreshed. _[RECURRED 2026-04-29 — now believed to be the same root cause as the "Display modal on Display modal" bug at L20. Derek observed the crash twice when the details modal and the Add/Edit Wizard were both open. Likely a modal-on-modal race condition (e.g. wizard open fires while details modal's silent-refresh is mid-flight → unhandled promise rejection → `state.processing` stuck true → all barcode input and FilaBridge updates freeze).]_

  **🔬 NEXT REPRO — capture before refresh (Derek, this is the note to come back to — joint with L122)**

  The L26 follow-up landed 2026-05-14 (wizard now closes details siblings on open via `window.hideAllDetailsModals`, see `test_wizard_closes_details_siblings.py`) which should kill the most-likely root cause. If the freeze RECURS after that fix, the capture below tells us which path to investigate next. Pairs with L122 (active-print confirm overlay "blocked / cancelled / hidden") — the symptoms can overlap, and the same DevTools capture answers both.

  **Don't hard-refresh first.** When you notice the freeze (scans not registering / FilaBridge updates stopped) OR the active-print overlay misbehaves, do this:

  1. Press F12 to open DevTools.
  2. Console tab → screenshot any **red** errors. Scroll up — the FIRST error is usually the root cause; later ones are downstream noise.
  3. Network tab → screenshot any rows in red (failed) OR rows still in "Pending" state. Right-click → "Save all as HAR" if you can; that captures the full request/response timeline.
  4. Take a screenshot of the dashboard showing which modals are open AND the state of the buffer / activity log.
  5. Note from memory:
       - What were you doing in the last 30 seconds? (Scan? Open a modal? Click a button?)
          A. I opened up a dryer box location, removed an extra filament (it was a box so it was 2/1) using the force feature. I was looking at the deployed status of a filament which was incorrectly marked ad deployed to the Core1-M0, when the actual printer had somethinge else in it. (filabrige was correct, but for some reason this item was still in it)
          I have pictures of the console, but didn't see any red errors in network. Please remind me to find the pictures from around 8:35pm on 5/18/2026.
       - Did the freeze happen instantly or did the UI feel slow before locking?
       - For L122 specifically: did the active-print confirm overlay try to appear and get dismissed by something? Was it during a scan flow (top-bar input) or while clicking a slot inside the Location Manager modal? The answer tells us which overlay was at fault.
  6. NOW you can hard-refresh.
  7. Dump everything into a new comment under this item (or paste into chat).

  Fix-path implications based on what the capture shows:
   - Pending `/api/identify_scan` or `/api/smart_move` XHR → backend Spoolman write hung; check Spoolman + filabridge connectivity.
   - Red `state.processing` reference in console → the modal-on-modal race wasn't fully fixed by L26; need to find the remaining path that sets it without a finally-clearing it.
   - L122 symptom on a SCAN flow → likely fixed already (`_confirmActivePrintScan` migrated to `mountOverlay` in `feature/buglist-sweep-2026-05-14`). If it still happens, the migration may need a different tier or focus-guard option.
   - L122 symptom on a SLOT CLICK inside Location Manager → `_confirmActivePrintAssign` in `inv_loc_mgr.js` (still hand-rolled). Migration is a ~30-line copy of the scan-side fix.




* Need to do something about the fact that if a toolhead has multiple slots assigned to it for a dryer box, that new spool assignments don't automatically take over the current toolhead's assigned spool. **Decision: (c) Leave it to the user via Quick-Swap.** Intent is ambiguous — a new spool landing in a shared box may not mean the user wants to switch the active toolhead assignment (e.g., staging spools for later). Quick-Swap is the deliberate, explicit action for swapping. No auto-switch or auto-prompt. _[RESOLVED — no code change needed.]_

*(L32 — `PRINTER:<id>` sentinel for printer-pool slot binding — DONE 2026-05-13 via Group 9.2. All four sub-items complete; Quick-Swap grid now renders a "🏭 Printer Pool" banner row for sentinel slots with deposit-flow handoff. See `completed-archive.md`.)*

*(L37/L39 — Default-Unassigned + location selector "Flow" cleanup — DONE 2026-05-14 via Group 10 Session A (items 10.3 + 10.2). Wizard combobox now shows full list on focus, highlights current selection, and placeholder advertises Unassigned default. See `completed-archive.md`.)*


*(L40 — Legacy QR code scans triggering the help overlay — DONE 2026-05-14 via `feature/buglist-sweep-2026-05-14`. `shortcuts_registry.js` capture-phase `?` handler now detects an in-flight scan (non-empty `state.scanBuffer` + `state.scanStartTime` within 500ms) and lets `?` flow through to the scan accumulator instead of popping the overlay. Regression coverage in `test_quickswap_ui_e2e.py::test_shortcuts_overlay_question_mark_mid_scan_does_not_trigger`.)*

*(L42 — Version number stale — DONE 2026-05-14, ENHANCED 2026-05-15 via `feature/buglist-sweep-2026-05-14`. Round 1: replaced hardcoded `VERSION = "v154.26..."` constant with a source-file mtime stamp. Round 2: added git commit resolution via `inventory-hub/_gen_build_info.py` — a standalone helper that walks up for `.git`, parses `HEAD` + `logs/HEAD` directly (no git binary required), and writes `inventory-hub/.build_info` with the format `<short_sha>|<unix_ts>`. `app.py` runs the helper on startup AND reads the file; falls back to mtime if .git is unreachable. Frontend now renders `commit <sha> • YYYY-MM-DD HH:MM` in user-local time, with mtime fallback. `.build_info` is gitignored — for auto-update per commit install the post-commit hook via `bash setup-and-rebuild/install_build_info_hook.sh` (per-clone, idempotent); for prod, run `python inventory-hub/_gen_build_info.py` before `docker build` so the file gets baked into the image. Regression coverage in `test_build_version_badge.py` (3 tests — accepted-format match, legacy `v154.x` literal gone, commit-attrs present when .git reachable).)*

* Unknown crash on Filament command center after auto deduct fired. Had to refresh browser window to get QR code scans working? Need to check code for any breaks.
Logs Below from Prod server:
2026-04-27 18:04:33.899463+00:00Collecting flask
2026-04-27 18:04:33.976420+00:00Downloading flask-3.1.3-py3-none-any.whl.metadata (3.2 kB)
2026-04-27 18:04:34.019279+00:00Collecting requests
2026-04-27 18:04:34.032112+00:00Downloading requests-2.33.1-py3-none-any.whl.metadata (4.8 kB)
2026-04-27 18:04:34.056354+00:00Collecting blinker>=1.9.0 (from flask)
2026-04-27 18:04:34.069011+00:00Downloading blinker-1.9.0-py3-none-any.whl.metadata (1.6 kB)
2026-04-27 18:04:34.100922+00:00Collecting click>=8.1.3 (from flask)
2026-04-27 18:04:34.114885+00:00Downloading click-8.3.3-py3-none-any.whl.metadata (2.6 kB)
2026-04-27 18:04:34.139339+00:00Collecting itsdangerous>=2.2.0 (from flask)
2026-04-27 18:04:34.151649+00:00Downloading itsdangerous-2.2.0-py3-none-any.whl.metadata (1.9 kB)
2026-04-27 18:04:34.178137+00:00Collecting jinja2>=3.1.2 (from flask)
2026-04-27 18:04:34.194351+00:00Downloading jinja2-3.1.6-py3-none-any.whl.metadata (2.9 kB)
2026-04-27 18:04:34.264374+00:00Collecting markupsafe>=2.1.1 (from flask)
2026-04-27 18:04:34.277629+00:00Downloading markupsafe-3.0.3-cp311-cp311-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl.metadata (2.7 kB)
2026-04-27 18:04:34.316278+00:00Collecting werkzeug>=3.1.0 (from flask)
2026-04-27 18:04:34.328327+00:00Downloading werkzeug-3.1.8-py3-none-any.whl.metadata (4.0 kB)
2026-04-27 18:04:34.453735+00:00Collecting charset_normalizer<4,>=2 (from requests)
2026-04-27 18:04:34.465855+00:00Downloading charset_normalizer-3.4.7-cp311-cp311-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl.metadata (40 kB)
2026-04-27 18:04:34.472784+00:00━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 40.9/40.9 kB 6.7 MB/s eta 0:00:00
2026-04-27 18:04:34.498572+00:00Collecting idna<4,>=2.5 (from requests)
2026-04-27 18:04:34.518411+00:00Downloading idna-3.13-py3-none-any.whl.metadata (8.0 kB)
2026-04-27 18:04:34.561527+00:00Collecting urllib3<3,>=1.26 (from requests)
2026-04-27 18:04:34.573095+00:00Downloading urllib3-2.6.3-py3-none-any.whl.metadata (6.9 kB)
2026-04-27 18:04:34.608041+00:00Collecting certifi>=2023.5.7 (from requests)
2026-04-27 18:04:34.624093+00:00Downloading certifi-2026.4.22-py3-none-any.whl.metadata (2.5 kB)
2026-04-27 18:04:34.666017+00:00Downloading flask-3.1.3-py3-none-any.whl (103 kB)
2026-04-27 18:04:34.683495+00:00━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 103.4/103.4 kB 6.1 MB/s eta 0:00:00
2026-04-27 18:04:34.705494+00:00Downloading requests-2.33.1-py3-none-any.whl (64 kB)
2026-04-27 18:04:34.709807+00:00━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 64.9/64.9 kB 20.5 MB/s eta 0:00:00
2026-04-27 18:04:34.727383+00:00Downloading blinker-1.9.0-py3-none-any.whl (8.5 kB)
2026-04-27 18:04:34.744259+00:00Downloading certifi-2026.4.22-py3-none-any.whl (135 kB)
2026-04-27 18:04:34.760510+00:00━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 135.7/135.7 kB 9.4 MB/s eta 0:00:00
2026-04-27 18:04:34.772258+00:00Downloading charset_normalizer-3.4.7-cp311-cp311-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (214 kB)
2026-04-27 18:04:34.798196+00:00━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 214.1/214.1 kB 8.5 MB/s eta 0:00:00
2026-04-27 18:04:34.817317+00:00Downloading click-8.3.3-py3-none-any.whl (110 kB)
2026-04-27 18:04:34.826891+00:00━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 110.5/110.5 kB 12.7 MB/s eta 0:00:00
2026-04-27 18:04:34.844838+00:00Downloading idna-3.13-py3-none-any.whl (68 kB)
2026-04-27 18:04:34.850785+00:00━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 68.6/68.6 kB 13.5 MB/s eta 0:00:00
2026-04-27 18:04:34.862310+00:00Downloading itsdangerous-2.2.0-py3-none-any.whl (16 kB)
2026-04-27 18:04:34.879394+00:00Downloading jinja2-3.1.6-py3-none-any.whl (134 kB)
2026-04-27 18:04:34.890062+00:00━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 134.9/134.9 kB 13.9 MB/s eta 0:00:00
2026-04-27 18:04:34.907644+00:00Downloading markupsafe-3.0.3-cp311-cp311-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (22 kB)
2026-04-27 18:04:34.927759+00:00Downloading urllib3-2.6.3-py3-none-any.whl (131 kB)
2026-04-27 18:04:34.942405+00:00━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 131.6/131.6 kB 9.5 MB/s eta 0:00:00
2026-04-27 18:04:34.962707+00:00Downloading werkzeug-3.1.8-py3-none-any.whl (226 kB)
2026-04-27 18:04:34.988332+00:00━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 226.5/226.5 kB 9.0 MB/s eta 0:00:00
2026-04-27 18:04:35.069738+00:00Installing collected packages: urllib3, markupsafe, itsdangerous, idna, click, charset_normalizer, certifi, blinker, werkzeug, requests, jinja2, flask
2026-04-27 18:04:37.434452+00:00Successfully installed blinker-1.9.0 certifi-2026.4.22 charset_normalizer-3.4.7 click-8.3.3 flask-3.1.3 idna-3.13 itsdangerous-2.2.0 jinja2-3.1.6 markupsafe-3.0.3 requests-2.33.1 urllib3-2.6.3 werkzeug-3.1.8
2026-04-27 18:04:37.434642+00:00WARNING: Running pip as the 'root' user can result in broken permissions and conflicting behaviour with the system package manager. It is recommended to use a virtual environment instead: https://pip.pypa.io/warnings/venv
2026-04-27 18:04:37.552489+00:002026-04-27T18:04:37.552489452Z
2026-04-27 18:04:37.552530+00:00[notice] A new release of pip is available: 24.0 -> 26.1
2026-04-27 18:04:37.552541+00:00[notice] To update, run: pip install --upgrade pip
2026-04-27 18:04:37.922140+00:002026-04-27 11:04:37,921 - INFO - 🛠️ Server v154.26 (Scale Weights Update) Started
2026-04-27 18:04:37.931279+00:00* Serving Flask app 'app'
2026-04-27 18:04:37.931305+00:00* Debug mode: off
2026-04-27 18:12:28.591071+00:002026-04-27 11:12:28,590 - INFO - DIRTY SPOOL DATA: {'used_weight': 553}
2026-04-27 20:47:23.870960+00:002026-04-27 13:47:23,870 - INFO - DIRTY SPOOL DATA: {'used_weight': 574}
2026-04-27 20:55:33.876324+00:002026-04-27 13:55:33,876 - WARNING - ⚠️ <b>Smart Load:</b> Ejecting #254 from CORE1-M0...
2026-04-27 20:55:34.246172+00:002026-04-27 13:55:34,246 - INFO - 🖨️ #225 [Legacy: 137] Stronghero3D PETG (Chameleon Mirror Chrome) -> CORE1-M0
2026-04-27 20:56:18.554475+00:002026-04-27 13:56:18,554 - INFO - 🪑 Auto-slot: CR-MDB-1 has free slot 4 — assigning spool there
2026-04-27 20:56:18.927858+00:002026-04-27 13:56:18,927 - INFO - 📦 #254 [Legacy: 125] Prusament PC (Black) -> Dryer CR-MDB-1 [Slot 4]
2026-04-27 20:56:18.967039+00:002026-04-27 13:56:18,966 - INFO - ⚡ Auto-deployed Spool #254 — Prusament PC (Black) → <b>CORE1-M0</b> (source: CR-MDB-1:SLOT:4)
2026-04-27 22:09:22.457261+00:002026-04-27 15:09:22,456 - INFO - 🔄 Auto-Recovering FilaBridge Error for 🦝 XL...
2026-04-27 22:28:47.552550+00:002026-04-27 15:28:47,552 - INFO - ✔️ Auto-deducted 193.3g from Spool #228 (RAM-Fetch): [542.0g at start ➔ 348.7g remaining]
2026-04-27 22:28:47.841658+00:002026-04-27 15:28:47,841 - INFO - ✔️ Auto-deducted 26.4g from Spool #226 (RAM-Fetch): [972.1g at start ➔ 945.8g remaining]
2026-04-27 22:28:48.063675+00:002026-04-27 15:28:48,063 - INFO - ✔️ Auto-deducted 110.5g from Spool #240 (RAM-Fetch): [937.0g at start ➔ 826.5g remaining]
2026-04-27 22:28:48.323606+00:002026-04-27 15:28:48,323 - INFO - ✔️ Auto-deducted 25.8g from Spool #230 (RAM-Fetch): [627.0g at start ➔ 601.2g remaining]
2026-04-28 05:43:08.762694+00:002026-04-27 22:43:08,762 - INFO - ℹ️ Spool #225 already verified
2026-04-28 05:45:44.058353+00:002026-04-27 22:45:44,058 - INFO - 📦 Auto-archived Spool #225 (remaining weight hit 0) — moved to UNASSIGNED
2026-04-28 05:45:44.543018+00:002026-04-27 22:45:44,542 - WARNING - 🗑️ Force Unassigned #225
2026-04-28 05:48:22.747416+00:002026-04-27 22:48:22,747 - INFO - ✔️ Spool #246 Label Verified
2026-04-28 05:48:27.938720+00:002026-04-27 22:48:27,938 - INFO - 🔎 CORE1-M0: 0 item(s)
2026-04-28 05:48:27.956696+00:002026-04-27 22:48:27,956 - WARNING - SCAN LOG: Legacy Location Barcode Scanned (CORE1-M0)
2026-04-28 05:48:28.502090+00:002026-04-27 22:48:28,501 - INFO - 🖨️ #246 [Legacy: 137] Stronghero3D PETG (Chameleon Mirror Chrome) -> CORE1-M0


*(L122 — Active-print confirm overlay blocked/cancelled/hidden — PARTIAL 2026-05-14 via `feature/buglist-sweep-2026-05-14`. The scan-side `_confirmActivePrintScan` in `inv_cmd.js` was rolled by hand (createElement + appendChild + document keydown) and could end up blocked behind a sibling modal — the exact symptom Derek reported. Migrated to `window.mountOverlay({ tier: 'confirm' })` so it inherits the canonical 20100 z-index, focus-guard, and Escape-via-onEscape discipline. Regression coverage in `test_active_print_scan_overlay.py` (2 tests — mount + z-index assertion, Escape cancels). Existing `test_doassign_buffer_safety.py` active-print suite (7 tests for the assign-side overlay in `inv_loc_mgr.js`) still green — that overlay still uses the hand-rolled pattern but is exercised through a different code path; migrating it is a natural follow-up but no symptom yet maps to it specifically. _[NEEDS REPRO — Derek should confirm the next time the symptom occurs whether it was on the scan path (now fixed) or the manage-modal slot-assign path (still hand-rolled). If the latter, the same mountOverlay migration applies to `_confirmActivePrintAssign` in inv_loc_mgr.js:~1110.]_)*

*(L124 — Toolhead scan assigns ALL buffer spools — DONE 2026-05-14 via `feature/buglist-sweep-2026-05-14`. `processScan` in `inv_cmd.js:251` now inspects the scanned location's `Type` / `Max Spools` against `state.allLocations`. For single-occupancy targets (Tool Head / MMU Slot / No MMU Direct Load / `Max Spools <= 1`), only the topmost held spool is passed to `performContextAssign`; the rest stay in the buffer. Toast surfaces the partial outcome ("Toolhead holds 1 spool — assigning #N; M stays in buffer"). `performContextAssign` now accepts an explicit `spoolIdsOverride` subset and only drops the actually-moved spools from `state.heldSpools` on success. Multi-spool destinations (Dryer Box, Shelf, etc.) retain the original bulk-assign behavior. Regression coverage in `test_toolhead_scan_single_spool.py` — one test asserts the toolhead-single-spool branch, one asserts the multi-spool dryer-box branch still sends the full buffer.)*

*(L130 — Location search box should show all locations after selection — DONE 2026-05-14 via Group 10 Session A (item 10.10). Same `wizardBindCombobox` fix as 10.2; mirror behavior added to `promptEditLocation` Force-Location dialog. See `completed-archive.md`.)*

*(L128 — "Already verified" Activity Log spam — REVERTED 2026-05-15 via `feature/buglist-sweep-2026-05-14`. The 2026-05-14 first iteration replaced the log line with a 1.5s toast on every scan; Derek's verdict was "the toast is probably worse than just adding to activity log" — the toast is more visually disruptive than a one-line append, AND blocks reading of any prior toast. Activity Log entry is back; the `label_already_verified` response field is preserved for future surfaces that want the signal, but the frontend no longer toasts. Better mitigation for blind-scan volume is the log-pause indicator (L286 — click to pause, no accidental hover-pauses anymore).)*

*(L130 — Force-location should clear deployed status — DONE 2026-05-14 via `feature/buglist-sweep-2026-05-14`. `perform_smart_move` GENERIC branch in `logic.py:620` now `pop()`s `physical_source` / `physical_source_slot` when the target is NOT a toolhead. (Previously only the DRYER MOVE branch cleared them; the GENERIC branch — which handles Force-Location → Room/Cart/Shelf — left stale ghost extras intact, so `spoolman_api.search_inventory.is_deployed` kept flagging the spool as still on a toolhead because its ghost source was a toolhead.) The Force-Location UI in `inv_details.js:promptEditLocation` already filters toolheads out of the destination list, so this fix covers every reachable force-location target. Regression coverage in `test_deployed_flag_preservation.py::test_force_move_to_room_clears_ghost_trail`.)*

* If possible, set certain text fields to only prompt with auto fill on some (perhaps none) fields. I think this might be a setible somewhere in the code to prevent a list of previously used values for showing up. Most of the time, this is just getting in the way for me. _[DONE 2026-05-12 (Group 8.4 / `feature/keyboard-nav-polish`) — Quick-Weigh suppression from Group 13 extended to 14 more inputs across 6 files: location ID/name, manual spool ID, wizard search/external/color, edit-filament hex/external query, global search/color, FilaBridge recovery delta. Free-form notes (`editfil-comment`, `vendoredit-comment`, `wiz-spool-comment`) deliberately left as default — history may help there. Regression coverage in `test_keyboard_nav_polish.py::test_autofill_suppressed_on_internal_inputs` and `test_freeform_comments_keep_browser_autofill`.]_

*(L138 — at-a-glance Printer Status widget — DONE 2026-05-13 via Group 9.3. Dashboard widget with stylized per-printer schematic (color-tinted toolhead blocks + remaining-weight bars + low-stock cue), reorderable via ▲▼ arrows, collapsible to a single inline chip strip. See `completed-archive.md`.)*

* These seem interesting, and it would be great to find a way to use this in some fassion. Just putting this here as a future thing, or as something to keep in mind.
https://github.com/pubeldev/prusa_exporter
https://github.com/prusa3d/Prusa-Firmware-Buddy/blob/master/doc%2Fmetrics.md

*(L140 — Printer Status widget hides Core One on prod — DONE 2026-05-16 via `feature/buglist-sweep-2026-05-14`. Root cause was `inv_printer_status.js:_aggregate()` filtering out any printer whose toolheads had zero bound dryer-box `slot_targets` — `if (!bound.length) return;`. Derek's prod environment has bindings for XL (`LR-MDB-1 → XL-1/2/3`, `LR-MDB-2 → XL-4/5`) but Core One runs dryer-boxless by design (no need yet), so it never met the filter. The dryer-box binding was the wrong gating criteria. Fix: render every printer in `printer_map`. Unbound toolheads now show a `🔗 no bound slot` placeholder tile (dashed yellow border, both in the expanded row and the collapsed compact chip) so the printer is visible AND the user gets a clear hint that nothing's wired up yet. Bound toolheads continue to render with their current contents. Test renamed + flipped: `test_widget_shows_unbound_printers_with_placeholder` replaces the old `test_widget_hidden_when_no_bound_toolheads` (which was asserting the bug, not the desired behavior).)*

*(Derek aside 2026-05-16: Core One MMU slots `CORE1-M1` through `CORE1-M5` are unused now that he's not planning to use the MMU anymore. Recommend removing those `MMU Slot` rows from `locations.json` to clean up the printer-status widget render. **Add to backlog: L140 follow-up — remove unused CORE1 MMU rows + decide whether `CORE1-M0` should be renamed from "No MMU Direct Load" to simply "Tool Head"** so it reads consistently with the XL toolheads.)*

*(L142 — Add an Unknown location for physically-lost spools — DONE 2026-05-15 via `feature/buglist-sweep-2026-05-14` (Group 18.1, first half). Virtual `UNKNOWN` row injected into `/api/locations` with `Type: "Unknown"` and Name `❓ Unknown (Physically Lost)`. Derek's visual-treatment choices: icon `❓`; sort position **bottom** of the list; spool-card badge is **yellow caution** (`bg-warning text-dark`). Yellow band applied at three surfaces so the visual is consistent everywhere: (1) Location Manager TABLE row type-badge (inv_core.js, the bigger list view), (2) Location Manager MANAGE-MODAL title bar (inv_loc_mgr.js, when you click into the UNKNOWN row), (3) spool-card location badge (ui_builder.js, both search + buffer modes), (4) Spool Details modal location pill (inv_details.js — previously blue; now yellow with `❓ Unknown` text and a click-through to the Manage modal for UNKNOWN). Force-Location dropdown surfaces it (not filtered out — Type='Unknown' isn't in the exclusion list). `logic.resolve_scan` accepts bare `UNKNOWN` as a valid location target. `perform_smart_move`'s GENERIC branch clears `physical_source` ghost trail on non-toolhead destinations (L130 lineage). Most spools landing here will be ghost rows from the old spreadsheet system that got used up without a proper update — the yellow badge makes them easy to spot for cleanup. Regression coverage in `test_unknown_location_bucket.py` (4 tests).)*

*(L144 — Filament sample + label-confirmed status on Display modal — DONE 2026-05-14, EDIT-SIDE 2026-05-15 via `feature/buglist-sweep-2026-05-14` (Group 17.1 both halves). Display side: two new fact-card rows on the Filament Details modal — "🎨 Swatch Printed" (reads `extra.sample_printed` → ✅ Yes / No / unknown) and "🏷️ Label Confirmed" (reads `extra.needs_label_print` tri-state → ✅ Confirmed / 🖨️ Needs print / unknown). Edit side (Derek's pick: option b — surface via existing dynamic-field rendering): both flags were already registered in `setup_fields.py:filament_standards` as boolean fields; only `needs_label_print` was in the wizard's hide list (line 1369). Un-hidden, so both now surface as native checkbox inputs in the wizard's Filament Extras section (`#wiz-fil-dynamic-extra-fields`) when editing a filament. Regression coverage in `test_filament_sample_label_status.py` (display) + `test_wizard_surfaces_label_and_sample_flags.py` (edit). Spool-level `needs_label_print` stays filtered out on the spool tab — it's system-managed by the create-new flow and shouldn't be hand-toggled.)*

*(L146 — Filament-modal "Queue all active spools" should NOT auto-open the Print Queue modal — DONE 2026-05-14 via `feature/buglist-sweep-2026-05-14` (Group 17.2). Handler in `inv_details.js:413` no longer calls `window.openQueueModal()` after success; instead toasts "Queued N labels — open Print Queue to review" (4 s). Users can keep queuing labels from other filaments/spools without dismissing the panel each time. Regression coverage in `test_filament_queue_all_no_auto_open.py`.)*

*(L148 — Queue-label button on just-created spool — DONE 2026-05-14, REVISED 2026-05-15 via `feature/buglist-sweep-2026-05-14` (Group 17.3). After a successful create-wizard run, `inv_wizard.js` renders a "🖨️ #N" chip per `created_spools[]` id in the dedicated `#wiz-postcreate-actions` row in the modal footer (alongside Cancel + Create Inventory). The 2026-05-15 revision moved chips out of `#wiz-status-msg` because the 3-second post-success "Make a change to add more..." auto-prompt was overwriting them before the user could click. Clicking the chip enqueues the label via `window.addToQueue` and disables itself to visually mark it as done. `wizardReset()` clears the row so a fresh wizard open doesn't show stale chips. Regression coverage in `test_wizard_queue_label_chips.py`.)*

*(L150 — Add-new affordance in duplicate Legacy ID picker — DONE 2026-05-14 via `feature/buglist-sweep-2026-05-14` (Group 17.4). `duplicate_picker.js` now renders an "➕ Add new spool" button when the candidate list carries a `filament_id` (always true for ambiguous-legacy-id scans). Clicking routes through the existing `window.openNewSpoolFromFilamentWizard(filamentId)` flow so the user lands in the wizard with the parent filament pre-selected. The scan is aborted (legacy id is still ambiguous until the new spool gets its own ID:NNN label). Null-guard hides the button when filament metadata is absent. Regression coverage in `test_duplicate_picker_add_new.py` (2 tests — happy path + null-guard).)*

*(L152 — Surface empty-spool weight on Filament Details modal — DONE 2026-05-14 via `feature/buglist-sweep-2026-05-14` (Group 17.5, recommendation B). New "⚖️ Empty Spool: <N>g [↩ filament / ↩ vendor / not set]" fact-card row added to `modals_details.html` and populated by `inv_details.js` using the canonical `window.resolveEmptySpoolWeightSource` cascade from `weight_utils.js`. Inheritance badge tells the user where the value came from (filament's own value vs vendor inheritance) so they don't need to round-trip through the Edit modal. Regression coverage in `test_filament_empty_spool_weight_row.py`.)*

*(L154 — Audit mode refinement — DONE 2026-05-15/16 via `feature/buglist-sweep-2026-05-14` (Group 18.2 Part A + Part B visual panel + label improvement). On audit `CMD:DONE`, every spool expected at the audited location but not scan-confirmed is moved to the virtual `UNKNOWN` bucket with `extra.fcc_pre_audit_location` set as a recovery breadcrumb. Per-spool Activity Log entry + the end-of-audit Missing/Extra summary both use `#N <display label>` (brand material color) instead of bare IDs. `CMD:CANCEL` skips the auto-park (user explicitly bailing).

  **Part B — Visual Audit Panel (Derek 2026-05-15: "more visual than just relying on activity log alone"):** New `mountOverlay`-based panel auto-opens when audit becomes active (toggleAudit / CMD:AUDIT). Shows the location being audited + a tile grid for every expected spool (color swatch, brand+material+name, weight, slot) with per-tile status: ✅ scanned (green border + bg), ⬜ not scanned (gray), ⚠️ rogue (yellow). Live stats header: `<found>/<total>` found, missing, rogue. Polls `/api/audit_session` every 2s while open so tiles tick as scans come in. Closes automatically on CMD:DONE/CMD:CANCEL. "Hide" button dismisses without ending the audit. Activity Log still fires every message — the panel is additive, not a replacement (Derek 2026-05-15: "I still like the idea of having the activity log reference too").

  New backend endpoint `GET /api/audit_session` returns the enriched payload (per-spool display label, color hex, multi_color_hexes for gradient swatches, remaining weight, slot) so the frontend doesn't do per-id Spoolman lookups itself. Cheap when no audit active (returns `{active:false}` immediately).

  `fcc_pre_audit_location` added to `SYSTEM_MANAGED_EXTRAS` AND to `REQUIRED_SPOOL_EXTRAS` so app startup auto-registers the field on any Spoolman that's missing it (fixes the 2026-05-16 prod break where the field wasn't registered and the auto-park PATCH 400'd with "Unknown extra field fcc_pre_audit_location"). Also added to `setup-and-rebuild/setup_fields.py` for the canonical full-rebuild path.

  **Audit exit UX corrections (Derek 2026-05-16):**
  - The AUDIT deck-button toggle now sends `CMD:CANCEL` (not `CMD:DONE`) when bailing out, so an accidental second click doesn't force-move unscanned spools to UNKNOWN. The destructive commit path is the explicit "✅ Done & Auto-Park" button in the panel.
  - The visual panel surfaces both actions as click-targets AND scannable QR codes: "✅ Done & Auto-Park" (CMD:DONE) and "❌ Cancel Audit" (CMD:CANCEL). Previously the panel only had a "Hide" button — the user could dismiss the panel but couldn't end the audit without re-clicking the deck button (which used to be the auto-park trap).
  - New `CMD:CANCEL` scan-command parser in `logic.py:resolve_scan` (the audit code already handled `cmd == 'cancel'` but nothing produced that cmd value). Registered in `shortcuts_registry.js` so the `?` help reference covers it.

  **Idle-timeout watchdog (Derek 2026-05-16):** an audit session left "active" with no human behind the wheel (browser tab closed mid-audit, page refresh, server restart cycles during dev — Derek confirmed this happened during a recent session) used to haunt the dashboard indefinitely; the panel would auto-open on every subsequent load. Added `state.AUDIT_IDLE_TIMEOUT_SECONDS = 30 * 60` + a `last_activity_ts` field on `AUDIT_SESSION` (updated on every audit-mode scan via `api_identify_scan`) + `_check_audit_idle_timeout()` helper called from `/api/logs` (5s heartbeat) and `/api/audit_session` (direct queries). When the session is stale beyond 30 min, the watchdog force-cancels and writes a yellow Activity Log entry explaining what happened so the user notices on the next refresh. Sessions missing `last_activity_ts` entirely (pre-watchdog state migration) get the timer seeded to "now" instead of cancelled.

  Regression coverage: `test_audit_auto_park_unknown.py` (12 tests — including new `test_audit_idle_timeout_auto_cancels_stale_session`, `test_audit_idle_timeout_leaves_fresh_session_alone`, `test_audit_idle_timeout_seeds_missing_timestamp` for the watchdog + the earlier `test_resolve_scan_recognizes_cmd_cancel` and `test_required_spool_extras_includes_fcc_pre_audit_location` regression guards), `test_audit_session_endpoint.py` (3 tests), `test_audit_visual_panel.py` (1 e2e). _[Parent/child rollup so scanning all of a cart's shelves counts toward auditing the cart itself is still a future enhancement on top of this — would need to expand the audit session to span multiple locations.]_)*

* Scanns of prusament filament should also update min/max bed and nozzle tempratures, on existing filaments. These value should stay the same, but there is some lagacy data entry where this data wasn't 

* Scann prusament data link into the search field in spool section fails to grab all available data and add it to the available fields in the UI of Add/Edit Wizzard, on an existing spool in the system. Scanning that data should update/add those fields. Except being if the current weight of the spool doesn't match the weight on the data card, implying that it was used, in those cases, current weights should be left alown, but total weight, and other elements should be updateable. (Basically perserve current usage amount, but update all other fields.)

* Edit filament - Advanced tab - Import from external section, when expanded then condensed, a bit of the source dropdown box still shows after colapsing.

* Setting a dryerbox slot that's attached to a toolhead to empty, doesn't propagate an empty field setting to filabridge. It thinks the old spool is still in that slot.

There continues to be inconsistency with switching out spools when a box slot is attached to a head, either ejecting doesn't fully clear all values, or only pulls it from the box, but not the toolhead. I have to take the new spool, assigne it to the box, remove the old spool from the box, and manually assign it to the toolhead directly. So we need to deep dive into that whole system and find out why this is still a problem. I've included the logs below to try and out line the the flow better than me trying to type it.
[17:02:49] 🗑️ Force Unassigned #240
[17:02:48] 📦 Auto-archived Spool #240 (remaining weight hit 0) — moved to UNASSIGNED
[17:01:11] ⏏️ Ejected #240 to Room LR
[17:00:46] ℹ️ Spool #240 already verified
[16:55:56] ⚡ Auto-deployed Spool #241 — Jessie Premium PETG (Transition Spool) → XL-3 (source: LR-MDB-1:SLOT:3)
[16:55:56] 🖨️ #241 Jessie Premium PETG (Transition Spool) -> XL-3
[16:55:53] 📦 #241 Jessie Premium PETG (Transition Spool) -> Dryer LR-MDB-1 [Slot 3]
[16:55:48] ℹ️ Spool #241 already verified
[16:54:09] 🖨️ #241 Jessie Premium PETG (Transition Spool) -> XL-3
[16:54:04] ℹ️ Spool #241 already verified
[16:54:00] ↩️ Returned #240 -> LR-MDB-1
[16:53:25] ✅ Spool #240 → LR-MDB-1:SLOT:3 → XL-3
[16:53:25] ⚡ Auto-deployed Spool #240 — Jessie Premium PETG (Transition Spool) → XL-3 (source: LR-MDB-1:SLOT:3)
[16:53:25] 🖨️ #240 Jessie Premium PETG (Transition Spool) -> XL-3
[16:53:23] 📦 #240 Jessie Premium PETG (Transition Spool) -> Dryer LR-MDB-1 [Slot 3]
[16:53:11] ⏏️ Ejected #241 to Room CR
[16:53:11] ✔️ Spool #241 Label Verified
[16:52:59] ⏏️ Ejected #240 to Room LR
[16:52:59] ℹ️ Spool #240 already verified
[16:52:55] ℹ️ Spool #240 already verified
[16:52:48] ↩️ Returned #240 -> LR-MDB-1
[16:52:48] ℹ️ Spool #240 already verified
[16:52:44] ℹ️ Spool #240 already verified

# **Active Backlog (Organized by Feature Area)**

## 📋 Activity Log
* Make the Activity Log more ubiquitous so it can be the authoritative feedback channel instead of toasts. Currently the log pane sits on the dashboard only — modal-heavy workflows (Location Manager, Wizard, Details) hide it, so the toast has to carry the full message + display time for the blind-scanner case. Candidate approaches (pick one, or stack them):
    - **Persistent mini-log widget**: a small scrollable strip that survives at the bottom/corner of the screen even when modals are open. Z-index above `.modal-backdrop` so it never gets covered. Shows the last N entries with category icons.
    - **"N new events" pill** in a corner that flashes when the log ticks. Click opens a compact log overlay. Same discipline as the `?` shortcuts overlay.
    - **Modal-aware docking**: while any modal is open, a condensed log bar docks to the modal itself (top or bottom of the modal body). Hides when no entries have arrived recently.
  Once the log is always visible, toast durations can drop further and we can rely on the log for the full narrative — toasts become purely "happened now" flashes.

## 🎨 UI & Theming
* Refactor the longer "strip" cards used in the Location Manager window. Merge the horizontal layout with modern grid card features without cramping the text or making the button layout look weird.
* High-Contrast Pop (White Text/colored text + Heavy Black Shadow/or similar color shadowing) - EVERYWHERE. Adaptive High-Contrast Pop (Shadows Only) on colors. Maintain existing colors, but give them a pop appropriate for their color.
* Theres a little animation and modal that appears when you add a new Slicer Profile in the Add/edit enventory wizzard. Its so nifty I want this used in other places. (I'm not sure if this is a sweetalert2 thing, or if we implemented ourselves.)


## ⌨️ Keyboard Navigation
* Audit and implement consistent keyboard navigation across the entire UI. Currently only the force location modal and wizard material/multiselect dropdowns support arrow keys, Enter, and Escape. Every modal, dropdown, list, and interactive element should have a unified keyboard interaction pattern: arrow keys to navigate, Enter to select/confirm, Escape to dismiss/go back, Tab to move between controls, and auto-focus on the primary input when a modal opens. _[PARTIAL 2026-05-12 (Group 8.1 / `feature/keyboard-nav-polish`) — full audit of 24 modals/overlays completed. Reference impls (mountOverlay-based, e.g. `weight_entry.js`, the bind-picker feeds combobox in `inv_loc_mgr.js`) already have full kb-active arrow-nav + Enter + Escape + auto-focus. `vendorEditModal` already auto-focuses on both Add and Edit paths. Delete overlays' Cancel-on-Enter (broad warning step) + Confirm-on-Enter (type-the-id step) is intentional UX. Only `locModal` actually lacked auto-focus — added: Add path focuses `#edit-id`, Edit path focuses + select()s `#edit-name`. Confirmed by `test_loc_modal_add_focuses_id_field` and `test_loc_modal_edit_focuses_name_field_and_selects`. **Focus-trap follow-up audit (2026-05-12, same session)**: Derek raised concern that Tab could leak from a modal into background modals or browser chrome. Probed every modal in single, stacked, and modal-on-offcanvas configurations (incl. `spoolModal` / `filamentModal` with their custom Escape handler bypassing `data-bs-keyboard`). All 16 surfaces correctly trap Tab and Shift+Tab via Bootstrap's `_enforceFocus`; topmost modal owns focus when stacked; Escape dismisses every surface. Could NOT reproduce the leak Derek saw — possible explanations: fixed by inv_core.js z-index stacking work, browser-specific (probe is Chromium), or a browser-level shortcut (Ctrl+Tab) that Playwright's `Tab` doesn't simulate. Locked the current correct behavior in with `test_modal_focus_trap.py` (19 tests covering single-modal trap, modal-on-modal stacking, modal-on-offcanvas, custom-Escape paths, auto-focus landing target). If the leak resurfaces, capture exact key combo + which modals are open before refreshing.]_

## 🗂️ Modals & Add Inventory Wizard
* Help button to provide information on how to use a modal, and to try and store information about how things work in the code.
*(L192 — Maintain multi-spool creation ability — DONE 2026-05-14 via Group 10 Session A (item 10.7). No code change required; verified via existing `test_wizard_per_spool_scan_*` suite that the qty-driven row sync still works after the Session A changes. See `completed-archive.md`.)*
* Create an assignment tool/system to pair existing/migrated Spoolman IDs directly to physical legacy spools being updated (specifically for bulk-imported identical spools sharing a single legacy ID).
*(L162 — Consolidate duplicate purchase link fields — DONE 2026-05-14 via Group 10 Session B (item 10.4). Single spool-tab `wiz-spool-purchase_url` with smart-fallback placeholder advertising the inherited filament URL; `wizardReset` now also clears `input[type="url"]` (the "doesn't clear between usages" bug). See `completed-archive.md`.)*
*(L163 — Slicer profile auto-add to current filament — DONE 2026-05-14 via Group 10 Session B (item 10.5). New `window.wizardOnNewChoiceAdded` hook fires after the schema refresh and selects the freshly-added value on the wizard's working filament. Mirrors the existing `inv_details.js:promptEditSlicerProfile` pattern. See `completed-archive.md`.)*
*(L164 — Spoolman field ordering bug — DONE 2026-05-14 via Group 10 Session B (item 10.6). Backend `FIELD_ORDER` constant + `_enrich_field_order` in `app.py` stamps each field dict with a canonical order index; the wizard's pre-existing `.sort((a,b) => (a.order||0) - (b.order||0))` now actually works. Unknown keys pin to 9999 (end). See `completed-archive.md`.)*
*(L165 — SweetAlert2 nested modal audit — DONE 2026-05-14 via Group 10 Session B (item 10.8). All three `Swal.fire` sites in `inv_wizard.js` (unsaved-changes confirm, field-sync picker, add-new-choice prompt) migrated to `window.mountOverlay()`. Closes the `.cmd-deck` scrollbar-shift symptom on the unsaved-changes prompt. See `completed-archive.md`.)*

## 🔍 Search, Display & Filtering
*(L209 — Search by remaining weight — DONE 2026-05-14 via `feature/buglist-sweep-2026-05-14`. `min_weight` was already wired up (offcanvas-search + `search_inventory`). Added the symmetric `max_weight` filter — new input next to Min g in `offcanvas_search.html`, propagated through `inv_search.js` (trigger list, executeSearch, clear-all, has-state checks) and `app.py:/api/search` into `spoolman_api.search_inventory`. Regression coverage in `test_search_max_weight.py` (3 tests — both backend bounds + frontend input wiring).)*



## ⚡ Quick-Swap Enhancements
*(L208 — Denser `SpoolCardBuilder` cards inside the Quick-Swap grid — DONE 2026-05-13 via Group 9.1. New `'quickswap'` variant + adopted in `inv_quickswap.js`; action footer integrates Details/Edit/Queue/Eject directly from each bound slot. See `completed-archive.md`.)*

*(L216 — Slot-render-order arrows inconsistent — DONE 2026-05-14 via `feature/buglist-sweep-2026-05-14`. Switched to one arrow per button, both pointing in the visual direction of slot numbering: `Left → Right` / `Right → Left`. Same `→` glyph on both labels removes the prior asymmetry.)*

*(L218 — Shortcuts overlay click-through — DONE 2026-05-14 via `feature/buglist-sweep-2026-05-14`. Added `#fcc-shortcuts-overlay-backdrop` sibling at z-index 10000 (just below the panel's 10001) with `onclick="toggleShortcutsOverlay()"`. `toggleShortcutsOverlay` shows/hides both elements together. Regression coverage in `test_quickswap_ui_e2e.py::test_shortcuts_overlay_backdrop_dismisses_overlay`. Existing button + `?`-key toggle tests still pass.)*

## 📍 Location Management & Scanning
* **[CRITICAL DESIGN — blocks Project Color Loadout]** Make the Location Manager less brittle and more concrete. The current model is held together by string-prefix tricks and synthesis heuristics, not real entity relationships:
  - **Printer is not a real entity.** `🦝 Core One Upgraded` exists nowhere on disk — it's conjured at runtime by grouping toolhead LocationIDs whose prefix splits the same way (`CORE1-M0`, `CORE1-M1`, … → synthetic `CORE1` with friendly name pulled from `printer_map.printer_name`). This session's regression proved how fragile that is: a stale `XL` parent row with `Type: ""` made the whole synthesizer skip and "🦝 Core One Upgraded" rendered under "Unassigned virtual storage" until I patched the synthesizer to also seed from `printer_map`.
  - **Hierarchy is encoded in strings, not data.** `LR-MDB-1` packs Room (`LR`), device class (`MDB`), and instance (`1`) into one barcode. Moving a portable box (PM/PJ class) to a new room would require renaming, which destroys the printed barcode. Today every consumer that wants to walk the tree calls `loc.split('-')[0]` — there are at least a dozen such call sites. One typo per row corrupts the entire dashboard rendering (proven this session twice).
  - **No formal Toolhead → Printer parentage.** `printer_map` lives in `config.json`, separate from `locations.json`'s toolhead rows. The two are joined by exact uppercase string match on LocationID. Drift between the two files (one has CORE1-M0/M1, other doesn't) silently breaks deduction + grouping. The MMU M0/M1 alias dedup we shipped this sweep is itself a heuristic patching that drift.
  - **Loaders fail silently.** Pre-bug-2 fix, `load_locations_list()` returned `[]` on JSONDecodeError and the dashboard rendered with no Names / Types / Grouping — the user blamed a feature commit. We loud-failed the loader, but the underlying schema is so loose that a single typo in a single string field still takes everything down. The integrity tests we added (`test_locations_json_integrity.py`) are guarding a brittle data shape, not a robust schema.

  **Concrete recommendations** for the design session:
  1. **First-class `Printer` entity in `locations.json`** with: `id`, `printer_name` (the user-facing label, owns the emoji), `model`, `mmu_attached: bool`, `prusalink_creds_ref`. Replace the synthesizer entirely.
  2. **`parent_id` foreign key on every row** (toolhead → printer; dryer-box-slot → toolhead; box → room or printer). Retire `loc.split('-')[0]` site-by-site. Once retired, a typo in a string field can't break grouping — the FK is the truth.
  3. **Decouple the printed barcode from the hierarchy.** Barcodes become opaque IDs (e.g. `B7DK29`) — the hierarchy lives in `parent_id`. A `PM` box can move rooms without re-printing.
  4. **Move `printer_map` into `locations.json`.** A Printer row owns a `toolheads: [{id, position, mmu_routed: bool}]` list. Eliminates the cross-file drift class entirely. The MMU alias problem dissolves: a Printer with `mmu_attached: true` has exactly one toolhead per position; alias rows go away.
  5. **Schema validation on write, not just on read.** `save_locations_list` rejects rows with missing `Type` / `parent_id` / unknown FK target. The empty-Type and orphan-parent classes cease to exist.
  6. **Migration path:** Phase 1 — introduce `parent_id` alongside prefix parsing, emit a migration that backfills FKs from existing prefix structure. Phase 2 — migrate consumers one at a time (synthesizer first, then `_resolve_active_locs_for_printer`, then `get_bindings_for_machine`, then the Location Manager UI grouping). Phase 3 — retire prefix parsing and delete the synthesizer.

  **Why this blocks Project Color Loadout** ([docs/Project-Color-Loadout/](docs/Project-Color-Loadout/)): a Loadout binds N filaments to a *specific Printer instance*. Today there is no Printer instance to bind to — only a synthesized name conjured from prefix grouping. A loadout would have nothing to anchor on; saving "Apply Loadout to 🦝 Core One Upgraded" would store a string that breaks the moment someone renames the printer in `printer_map`. Concrete schema makes loadouts trivial; without it, any loadout work pays the brittleness tax twice (once to ship, again when the loadout-to-printer link drifts).

  _[IN PROGRESS — Phase 1A shipped 2026-04-25 on `feature/locations-parent-id-phase-1a`. Subsequent phases tracked below.]_

  **Phase tracker (kept here so we don't lose the thread between sessions):**
  - [x] **Phase 1A — additive plumbing** (2026-04-25). Added `parent_id` field, `derive_parent_id_from_prefix`, `resolve_parent`, and `migrate_parent_ids_if_needed` to [locations_db.py](inventory-hub/locations_db.py); wired the startup migration into [app.py](inventory-hub/app.py) with timestamped backup; added ~15 unit tests in [test_dryer_bindings.py](inventory-hub/tests/test_dryer_bindings.py) plus 3 integrity-contract tests in [test_locations_json_integrity.py](inventory-hub/tests/test_locations_json_integrity.py). **No consumer reads `parent_id` yet** — purely sets up the data so Phases 1B/2 can migrate consumers safely.
  - [ ] **Phase 1B — first consumer migration**: replace `split('-')[0]` at [app.py:879](inventory-hub/app.py#L879) (room-occupancy parent extraction in the synthesizer) with `locations_db.resolve_parent`. Smallest possible consumer change; proves the abstraction works in production.
  - [ ] **Phase 2 — remaining backend consumer migrations**: [app.py:900](inventory-hub/app.py#L900) (synthesizer printer-prefix seed); [locations_db.py:210](inventory-hub/locations_db.py#L210) (`_known_printer_prefixes`); [logic.py:596](inventory-hub/logic.py#L596) (smart_eject room prefix); [spoolman_api.py:456,464](inventory-hub/spoolman_api.py#L456) (child-of-parent matching for spool location queries). One per commit; each gets its own integration test.
  - [ ] **Phase 2.5 — frontend consumer migrations**: [inv_core.js:407–408,498](inventory-hub/static/js/modules/inv_core.js#L407) (sort + parent-row styling); [inv_loc_mgr.js:344](inventory-hub/static/js/modules/inv_loc_mgr.js#L344) (sentinel-option derivation). API surface stays the same; JS reads the new `parent_id` field instead of splitting LocationID.
  - [ ] **Phase 3 — first-class `Printer` rows on disk**: persist what the synthesizer at [app.py:872–958](inventory-hub/app.py#L872) currently conjures. Add `Printer` to the required-Type list in `_required_keys_for`. Migrate `printer_name` from `config.json:printer_map` into the Printer row's `Name` field. Retire the runtime synthesizer. Tighten `parent_id` validation: every non-null `parent_id` must point to a real on-disk row. **This is the phase that unblocks Project Color Loadout.**
  - [ ] **Phase 4 — fold `printer_map` into `locations.json`**: add a `toolheads` array on the Printer row carrying `position` and `mmu_routed`. Retire `config.json:printer_map`. Update `_resolve_active_locs_for_printer`, `get_bindings_for_machine`, `validate_slot_targets`, and `/api/printer_map` to read from the new shape. MMU M0/M1 alias dedup heuristic dissolves (a Printer with `mmu_attached: true` has exactly one toolhead per position).
  - [ ] **Phase 5 — retire prefix parsing**: delete `derive_parent_id_from_prefix` and the fallback inside `resolve_parent`. Remove all remaining `split('-')[0]` sites. Add write-time schema validation that rejects `save_locations_list` calls with missing or orphan `parent_id`. Decouple printed barcodes from hierarchy strings (per recommendation #3 above).

* 🔄 **Bulk Moves**: The ability to scan Box A (Source) and Shelf B (Destination) and say "Move EVERYTHING from Box A to Shelf B."
* Shapeshifting QR Codes in more places (like Audit button).

*(L251 — Buffer-scan assign-all-at-once — VERIFIED + CLOSED 2026-05-14 via `feature/buglist-sweep-2026-05-14`. `test_toolhead_scan_single_spool.py::test_multispool_dryer_box_scan_still_sends_full_buffer` directly asserts that scanning a multi-spool destination (dryer box / shelf / cart) sends the entire buffer in a single `/api/smart_move` POST. The new L124 toolhead branch is the only single-spool carve-out; everything else preserves the legacy bulk-assign behavior. No new repros needed.)*
* Location Manager not syncing status across browser instances? _[ON HOLD — requires a real-time transport (SSE / WebSocket) on the backend. Current architecture is pull-only via `/api/locations` polling. Non-trivial; revisit after mobile mode since that work will establish the multi-client baseline anyway.]_

## 🎟️ Print Queue, Labels & Filament Usage
*(Group 3 — Print Queue & Label Management — completed 2026-04-28; see `completed-archive.md` for resolved items.)*

## 🧪 Testing
*(L263 `test_visual_quickswap_confirm_overlay` baseline mismatch — DONE 2026-05-12 via Group 14.4 — baseline re-captured at the new Group-15 mountOverlay shape. See `completed-archive.md`.)*

*(L264 `test_details_modal_interactions` offcanvas-backdrop intercept — DONE 2026-05-12 via Group 14.3 + 14.6 follow-up. Defensive teardown promoted to `conftest.reset_dom_state_js`; page-wide `.fcc-card-action-btn` scoped to `#offcanvasSearch`. See `completed-archive.md`.)*

*(Group 16 testing-hardening items — parallel `tests/` directory consolidated, `_open_manage` helper promoted to `open_manage_modal` conftest fixture (10 files migrated), `reset_dom_state_js` adopted in 6 more e2e test files, Windows pip/pytest interpreter mismatch documented — DONE 2026-05-12. See `completed-archive.md`.)*

## ⚙️ App Flow, Architecture & Database
* **MOBILE** Make the entire app mobile friendly so NFC/Scanning works on phones. (Perhaps a desktop mode to utalize barcode scanners, and a mobile mode of mostly touch interface and scanning barcodes/QR codes and NFC tags). The main difference being that mobile mode won't relye on all the inlaid barcode/qr codes we currently have in the interface currently for interacting with the UI elements.
* Refactor dashboard to be more modular if possible, and reduce token size/context requirements.
* Make as much of Command Center user configurable as possible, using UI elements and a config import/export feature.
* When changes are made to Spoolman extra fields, they usually ignore sort order in the database. We need a way to restore sort order.
* **Clean up filament attributes** — remove dead/duplicate entries from the `filament_attributes` choice list, AND add input validation so new garbage entries can't be created in the first place. _[2026-04-28 audit: Spoolman is the source of truth (CSVs no longer authoritative). Total 34 choices on the field; 27 actually used across 180 filaments. Spoolman's API rejects choice removal via POST (`400 "Cannot remove existing choices."`), so a true cleanup requires the snapshot-restore migration pattern (template: `migrate_container_slot_to_text` in `setup-and-rebuild/setup_fields.py`): snapshot all filaments' `filament_attributes` values → `force_reset` delete the field schema → recreate with cleaned choices → restore filtered values. Heavy for purely cosmetic dropdown cleanup; deferred until the migration is worth the time.

  **Prevention guards — DONE 2026-05-14 via Group 10 Session B (item 10.9).** Shared `choice_validation.js` module (`normalizeChoice`, `validateNewChoice`, `levenshtein`) with all five guards from the original spec (min length ≥3, leading/trailing punctuation rejection, fuzzy/prefix/normalized-key match warning with "Did you mean?" overlay, two-step confirm before commit, live canonical preview). Hooked into the wizard's `wizardPromptNewChoice` mountOverlay (stateful content-swap stages so Escape isn't lost to a capture-phase race) AND into `wizardAddMultiChoiceChip`'s silent blur-commit path AND into `inv_details.js:addAttrChip` for parity. See `completed-archive.md`. **Bulk-cleanup migration above still deferred** — guards stop new garbage from being added; existing dead choices still need the snapshot-restore migration when prioritized.

  **Confirmed safe to delete** (Derek 2026-04-28): `Carbon-Fiber` (dupe of `Carbon Fiber`), `Tran` (truncated), `Transparent; High-Speed` (semicolon-bogus), `Wood` (superseded by `Wood Filled`), `F` (typo).
  **Keep:** `+` — represents PLA+ filaments (currently displayed as `+ PLA`, but the value itself is intentional). Filament #132 (Creality Rainbow) uses it correctly.
  **Investigate before deciding:** `For Infill` — was used to flag color-switch / prototype-only filaments not meant for visible prints. Codebase grep confirms no replacement mechanism exists; if Derek wants a different infill-flag UX, that should be a separate item. Otherwise keep.
  `Matte Pro` — likely orphaned from a prior wipe-and-replace, currently unused. Probably safe to delete but Derek wants to confirm origin first.

  **Bad data to fix** (out of scope for choice cleanup): no orphaned values found in actual records — everything stored references either a still-valid choice or `+` (intentional).

  **Approach when ready:** Write `setup-and-rebuild/migrate_filament_attributes.py` following `migrate_container_slot_to_text` template. Should be runnable from host with config_loader path setup, ask for confirmation, snapshot → force_reset → recreate → restore. Verify against a live Spoolman dev instance with backup before touching prod.

  **SCRIPT SHIPPED 2026-05-16** via `feature/buglist-sweep-2026-05-14`. `setup-and-rebuild/migrate_filament_attributes.py` is the generalizable cleanup tool — `DELETE_CHOICES` + `FLAG_CHOICES` sets at the top are the only thing to edit for future cleanup runs against this or any other choice-type Spoolman extra field. Dry-run on dev validated: 5 deletions (`Carbon-Fiber`, `F`, `Tran`, `Transparent; High-Speed`, `Wood`) → 29 choices remaining, snapshot covers 111 filaments. **For Infill + Matte Pro are NOT in the delete list** — `For Infill` is in FLAG_CHOICES pending Derek's prod check (Derek 2026-05-16: "I want to flag filament for infill use but I'm not sure if I use that flag or do it differently"; needs prod check). Dev shows zero filaments using either flagged choice — safe to add to DELETE_CHOICES once prod is confirmed.

  **To run against prod:** (1) BACKUP Spoolman DB first (Spoolman's field DELETE is destructive at the schema level). (2) Point your shell at the prod `config.json`. (3) `python setup-and-rebuild/migrate_filament_attributes.py` — analyzes first, asks `yes` to commit.

  **AUTO-RUN AT STARTUP 2026-05-19** (Derek 2026-05-19: "Can this just run on its own first run and clean things up? I don't like running things on prod myself, cause finding it and running it is kind of a pain."). The same cleanup logic now lives in `spoolman_api.ensure_filament_attributes_cleaned()` and is called from `app.py` startup right after `ensure_required_extras()`. First boot on a dirty Spoolman runs the cleanup with the same safety net (FLAG_CHOICES auto-promote on zero usage, kept-with-log on any usage); subsequent boots take an early-return path with one field-definition GET. Failures are caught + WARNING-logged so they never crash startup. Defensive guard: if Spoolman returns zero filaments while the field still exists, the cleanup skips (transient state, not "everything unused" — retried next boot). Activity Log surfaces a summary line when cleanup actually fires so the user notices what happened.

  The standalone script in `setup-and-rebuild/` stays as a future-proof generalizable tool for cleaning OTHER choice fields (just edit the constants at the top), but you don't need to run it for filament_attributes — it'll just happen on the next prod restart.

  Regression coverage: `test_filament_attributes_auto_cleanup.py` (7 tests — idempotent no-op, first-boot delete, flag-in-use preserved, flag-zero-usage auto-promoted, transient zero-filaments guard, network-error swallowed, post-failure non-crashing).]_
* Continue to support Spoolman's "Import from External" feature for filaments... _[Status of existing parsers + a gap list of unimplemented sources lives in the module docstring at the top of `inventory-hub/external_parsers.py` as of 2026-05-13 (Group 11). The audit + dropdown cleanup landed; the items below are the still-unimplemented sources.]_
    - open-filament-database
    - Prusament spool specific data links
    - Open Print Tags (Initialize, Read, and Write)
* Maybe we should figure out a way to set up a dev version for Spoolman and filabridge.
*(L286 — Auto-refresh pause button — DONE 2026-05-14, REVISED 2026-05-15 via `feature/buglist-sweep-2026-05-14`. Click-to-toggle the `#log-status` indicator is the ONLY pause path. The hover-mouseenter/leave pause that lived on `#live-logs` was removed in the follow-up because it caused accidental pauses Derek didn't realize were active — exactly the frustration the buglist item described. Server-side `RECENT_LOGS` is bounded at 50, so resume backfills with whatever ticked while paused. Regression coverage in `test_log_sticky_pause.py` (2 tests — click-toggle + assert hover handlers gone).)*
* Need to add a routine to clean up the logs after a while.
* Refactoring setup code to be dynamic. On brand new installs, maintain existing code to get it started.
* Continue to support Spoolman's ability to pull data from the vendor up to filament (Empty Weight), and from Filament to Spool (price, etc.)
* Add the ability to configure which extra fields should be bound and propagated to the other type of item. (Filament <-> Spool).
* Spools might need to have a text field added to store the product data (Prusament link, etc.).
* Add background refreshing used in Location Manager, etc... to update spool text (update weight other data).
*(L293 — Python server auto-reload on code changes — DONE 2026-05-14 via `feature/buglist-sweep-2026-05-14`. `app.run(...)` now reads `FCC_DEV` env var; when set to `1` / `true` / `yes` / `on`, passes `use_reloader=True` so werkzeug watches files and auto-restarts on edit. Defaults to off so the TrueNAS prod image keeps its current single-process behavior — no reload churn or behavior changes in prod unless the env var is explicitly set. To enable on the dev container, add `FCC_DEV=1` to the env section of the dev compose/spec (or `docker exec` with `-e FCC_DEV=1` for ad-hoc).)*


# **On Hold**
* Amazon Parser: Multi-pack spools with different colors (e.g. 4x1kg) currently calculate as a single 4000g spool instead of 4 individual 1000g spools.
* `test_amazon_parser_matching` is failing — BeautifulSoup4 is not installed in the Docker container. Parser returns empty results because the import fails silently. Blocked until `pip install beautifulsoup4` is added to the Docker image. Found during structural test fix work (4/15/2026).
* Continue to support Spoolman's "Import from External" feature... Purchase emails, or Amazon/Vendor product pages, Onlyspoolz.com.
* Standardize the size of all QR codes to match that of the sizes used on the command center. (Audit, eject, drop, etc).
* If legacy barcode has no spools attached to it, UI should warn about this, perhaps give option to add new spool?
* Spoolman ExternalID is not a visible field in Spoolman UI. Very low priority.
* A way to compare the specs of two filaments side by side.


# **Overarching Issue**
I think we've inadvertently created 3 levels of logic/complexity here:
1. The physical, Scanning stuff and efficiently Moving it
2. A UI layer, for debugging, but should only really need to be looked at to confirm things
3. A full on interface that is easier to move spools around than having to use Spoolman's lackluster interface.
All 3 of these things are important and have value. We should table for now, and come back to once we've gotten more of the functionality in place.

## Stuff to watch ##

# ** Filabridge Error Recovery **
* Keep an eye on filabridge errors and note the type of recovery method used to fill in the missing weight data. (Fast-Fetch or RAM-Fetch) To see if Fast-Fetch (Based on a HTTP Range request of a file.) works.
*(L324 — Filabridge ↔ Spoolman reconcile utility — DONE 2026-05-16 via `feature/buglist-sweep-2026-05-14`. Shipped as the first inhabitant of a new Config / Admin modal scaffold (the ⚙️ button now sits next to `?` in the nav bar). Per Derek's "having both options would be nice" — both resolution paths are surfaced per-mismatch row:
  - **Trust Spoolman** → clears the stale FilaBridge toolhead entry via `_fb_write(printer, th, 0)`. Spoolman's location wins.
  - **Trust FilaBridge** → writes Spoolman `location = <fb_location>` for the affected spool. System-managed extras (container_slot, physical_source, etc.) are preserved — this is a "rewrite Spoolman to match the truth FB already accepted" op, not a smart_move.

  Two new endpoints: `GET /api/filabridge/reconcile` (scans, returns mismatches with both views) and `POST /api/filabridge/reconcile/apply` (resolves one row). UI: `configModal` opens via the ⚙️ button, presents a table of mismatches with action buttons per row + a per-row spool display label. After applying any fix the scan auto-reruns so the table reflects the current state.

  Config UI scaffold (Derek 2026-05-16: "I've been wanting to add a configuration button and system this would be a nice way to start that up for future feature use"). The modal is structured as a series of Bootstrap `.card` panels — adding future sections (user preferences, choice cleanup launcher, etc.) is a matter of dropping another card into `modals_config.html` and adding its JS to `inv_config.js`. The existing card pattern is the contract.

  Build Info section added as the second card: surfaces the resolved commit SHA + timestamps from the L42 round 2 stamp. Read-only.

  Regression coverage: `test_filabridge_reconcile.py` (8 backend tests — clean/mismatch/orphan-position/zero-spool detection + both apply paths + payload validation) and `test_config_modal_smoke.py` (2 e2e — modal opens, scan renders results).)*

# **New related project to be integrated **

* [Feature] Build Project Color Loadout Add-on -> (See /docs/Project-Color-Loadout/)
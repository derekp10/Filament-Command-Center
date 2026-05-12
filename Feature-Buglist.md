# **New and Unsorted Features/Bugs**


* **[PRIORITY — block for next session, delegate-friendly] Test-sweep flake stabilization.** Full pytest sweep on 2026-05-11 came back 772 passed, 12 failed, 6 errors. NONE of the failures/errors trace to Group 13 changes (verified by re-running impacted suites in isolation — they pass clean). But the noise is real and gets in the way of finishing future groups cleanly. The agent picking this up should triage all 18 items into "real bug" / "test isolation issue" / "missing dep" / "baseline re-capture" buckets and fix each in the smallest possible commit. Specific items:
  - **5× `test_delete_ui_e2e.py`** (Group 4 delete-flow surface) — `test_spool_gear_dropdown_exposes_delete`, `test_spool_delete_step1_renders_warning`, `test_spool_delete_step2_requires_id_match`, `test_spool_delete_escape_closes_overlay`, `test_spool_delete_overlay_clears_when_modal_closes`. Likely test-state pollution from a prior test leaving a spool in a delete-prone state, OR a real regression in the gear-dropdown wiring. Run in isolation first to bisect.
  - **2× quickswap** — `test_quickswap_deposit_and_header.py::test_deposit_confirm_overlay_names_the_spool_and_toolhead` and `test_return_overlay_and_refresh.py::test_quickswap_refreshes_manage_view_after_yes`. Both show the confirm overlay either not appearing or the refresh not firing. Pre-existing flakes; reproduce by running quickswap suite alone.
  - **1× `test_ui_details_modal_e2e.py::test_details_modal_interactions`** — already tracked at L274 (offcanvas-backdrop click intercept). Likely the same root cause class as the Z-order recurring issue at L4; may be partially absorbed by the canonical overlay-mount helper when that lands. Until then: defensive offcanvas-close at test-setup time, or quarantine + sort-order-pin so it always runs first.
  - **3× visual regressions** — `test_quickswap_visual.py::test_visual_quickswap_grid`, `test_visual_quickswap_kb_active`, `test_visual_shortcuts_overlay` plus `test_feeds_section_visual.py::test_visual_feeds_section_collapsed`. Baselines stale relative to current renders. Verify each layout is correct visually, then `UPDATE_VISUAL_BASELINES=1 pytest <file>` to re-capture and commit the PNGs. Already tracked at L273; bundle the re-captures here.
  - **1× `test_external_parsers.py::test_amazon_parser_matching`** — missing `beautifulsoup4` Python package (env, not code). Already tracked at L317 / L324. Either `pip install beautifulsoup4` into the dev container (and add to requirements-dev.txt) so the test runs, or skip-decorate with `@pytest.mark.skipif(not _BS4_AVAILABLE, reason="...")` so it doesn't fail the sweep.
  - **6× `test_force_location_keyboard_e2e.py`** — ALL 6 errored in the sweep but ALL 7 PASS when the file runs in isolation. Pure test-isolation / state-pollution issue. The agent should pin down which earlier test leaks state that breaks force-location autofocus/arrow/Enter/Esc, then either fix that test's teardown or pin force-location's setup to be self-cleaning.

  Goal: a clean green sweep so the next group's regression run can be trusted at face value, without having to bisect "is this my change or pre-existing noise" every time.

* **[Repro added — likely simple cleanup] Details/display modal pops up after editing a spool from the global search, even though search was the source.** Repro: Search for a spool via the global search FAB → click the **Edit** button on a search result → wizard opens → cancel the wizard → the spool's **display/details modal** loads in place. Derek's read: probably a "dirty" pattern where every Edit Wizard close path unconditionally opens the details modal on exit, regardless of where the edit was initiated from. The wizard should restore focus/UI to wherever it was launched (search results panel in this case), not always fall back to details. Likely lives in the wizard-close callback. This is **possibly related but probably distinct from** the "Display modal on Display modal" simultaneous-modal-stack bug at L67 (keeping that entry as-is in case the underlying race is the same). Likely cleanup target: the wizard's `onCancel` / `onClose` handler in [inv_wizard.js](inventory-hub/static/js/modules/inv_wizard.js) — search for a call to `openSpoolDetails` / `openFilamentDetails` in the close path and gate it on `wizardLaunchedFromDetails`-style state instead of always firing.


* **[RECURRING — squash for good] Modal / overlay Z-ordering keeps biting us.** Every few weeks a new modal-on-modal or overlay-on-modal flow lands its top layer BELOW the host modal or backdrop, manifesting as "click triggered something, but I can't see it" — most recently 2026-05-11 when Group 13's 13.1 fix mounted `<WeightEntry>` inside the open Bootstrap modal subtree to defeat its focus-trap and inherited a worse problem (overlay rendered behind sibling modal chrome). Reverted to the body-mount + focusin-guard approach. Prior incidents are scattered through commit history (escape-confirm overlay, nested-Swal kills, quickswap confirm overlay z-index bumps). We need a **single canonical overlay-mount helper** that every inline overlay (`<WeightEntry>`, force-location, escape-confirm, quickswap-confirm, missing-tare prompt, delete-confirm, force-eject confirm, etc.) uses, with a documented z-index ladder above Bootstrap's modal stack and a focus-guard pattern that doesn't depend on DOM-subtree mounting. Out-of-scope items uncovered while writing this entry that the helper must also handle: Bootstrap `_enforceFocus` neutralization (today's 13.1 lesson), backdrop occlusion on `<select>` and offcanvas-search elements (see `test_ui_details_modal_e2e` flake at L233), `data-bs-keyboard="false"` parent modal interplay so Escape doesn't get double-handled (see Group 4 delete-modal escape work), and a uniform cleanup-on-host-close so an overlay never outlives the modal that spawned it.

  **Symptom checklist for "is this another Z-order incident":**
  - Click registers (toast/log fires) but expected overlay isn't visible.
  - Closing the host modal "reveals" the overlay where it was hiding underneath.
  - Tab/keyboard focus lands on elements behind a visually-foregrounded overlay.
  - Click on overlay does nothing because a backdrop ate the pointer event.
  - Two overlays both think they're "on top" and dismiss each other.

  **Acceptance for the canonical helper (when picked up):**
  1. Single `mountOverlay({ id, html, onClose, allowEscape, allowBackdropClick })` entry point in a new `static/js/modules/overlay_mount.js`.
  2. Mounts at `document.body`, z-index above Bootstrap's modal (1055) but below toast/snackbar tier (today nothing uses higher than ~9999; the new convention should be 20000-29999 for inline overlays).
  3. Focus-guard helper that neutralizes Bootstrap's `_enforceFocus` for events targeting our overlay (capture-phase `focusin` + `stopImmediatePropagation`).
  4. Auto-cleanup on `hidden.bs.modal` of the topmost host modal, so closing the LocMgr modal also tears down any inline overlay that LocMgr spawned (today this is ad-hoc — closeQuickswapConfirm exists, but every overlay has its own pattern).
  5. Each call returns a handle with `close()` + a `dismissed` promise so call sites can `await` user resolution without nesting callbacks.
  6. Existing overlays migrated one at a time; the helper coexists with raw-DOM overlays during transition.

  Worth scheduling as its own design session — this is a coordination problem more than a code problem. Document the z-index ladder in CLAUDE.md when the helper lands.


* **[RECURRING — needs deeper fix] `data/locations.json` corruption: "valid content + duplicate tail" pattern.** First seen 2026-04-28 (fixed in commit `8430d81` Group 4 — `locations_db.save_locations_list` switched to atomic `.tmp` + `fsync` + `os.replace`, dev file repaired). **Recurred 2026-05-11 during Group 13 Phase C** with the SAME fingerprint: file ends in `]` (valid JSON) followed by a stray partial-record tail (e.g. `] "Yes",\n        "parent_id": "XL"\n    }\n]`). Dev `/api/locations` endpoint returned a `locations_corrupt` error and ~29 UI/integration tests cascaded into ERRORs due to fixture failures. Repaired in-place by truncating to the first balanced `]` from the right; pre-repair backup at `data/locations.json.pre-13.x-repair-*.bak`.

  **Investigation findings (Group 13 Phase C, 2026-05-11):**
  - EVERY Python writer of `locations.json` goes through `save_locations_list` ([inventory-hub/locations_db.py:134](inventory-hub/locations_db.py#L134)) which uses the atomic pattern correctly. Confirmed by grep: only `open(JSON_FILE, 'w')` references are the migration-from-CSV path (one-time, never executes after first install) and the load-side `open(JSON_FILE, 'r')` reader.
  - No test fixture writes the real file — all test fixtures monkeypatch `locations_db.JSON_FILE` to a `tmp_path`. The `DumpExploder` "JSON Write Error" entries in `hub.log` are red herrings: they're test fixtures that share `state.logger` but redirect their file writes via monkeypatch.
  - The `seed_dryer_box` conftest fixture DOES write the real container file (PUT `/api/dryer_box/<id>/bindings`), but goes through `set_dryer_box_bindings` → `save_locations_list` so it's atomic.
  - **Leading hypothesis: Docker Desktop on Windows bind-mount filesystem mediation quirk.** When the container's `os.replace(tmp, JSON_FILE)` runs against a host NTFS file via the gRPCfuse/9P-style sharing layer, truncation of the host file may not always propagate when new content is shorter than the old. The Linux container sees the replaced file at the correct size; the host file retains stale bytes past the new EOF. This is consistent with the observed "valid content + duplicate tail" fingerprint (the new write ends in `]`; the stale bytes are leftover from a longer prior file).
  - Cannot prove the Docker hypothesis without `docker exec` access or a reproducible test against the bind-mount.

  **Candidate hardening (not yet implemented):**
  1. **Defensive read-back-and-verify** in `save_locations_list`: after `os.replace`, re-read the file and `json.loads()`. If parsing fails, log critical + attempt one more atomic write of the same content. Logs and re-tries are cheap; silent corruption is expensive.
  2. **Unique temp filename per call** (`tempfile.NamedTemporaryFile(dir=DATA_DIR, prefix='locations.', suffix='.tmp', delete=False)`) instead of fixed `JSON_FILE + ".tmp"`. Eliminates the theoretical race where two concurrent writers share the same `.tmp` (Flask is multi-threaded; the fixed name is a footgun).
  3. **Post-write explicit truncate** of the host file to the written byte count. Belt-and-suspenders against any rename-doesn't-propagate-truncation behavior.
  4. **Move runtime state out of the bind-mounted directory** — mount `data/` as a named Docker volume instead of a host bind. Trades easy-host-inspection for filesystem correctness. Probably the cleanest long-term answer for prod (TrueNAS) too.

  **When picked up:** Implement (1) + (2) as a tight pair (cheap, defensible, low blast radius). (3) is optional belt-and-suspenders. (4) is a separate config change worth weighing once dev/prod hygiene is stable.




* Keeping the screen on when afk, still causes the screen to blank out. Confirmed on laptop, not on desktop. _[ON HOLD — OS-level power management, not fixable in app code. Candidate mitigations if we care: Wake Lock API (`navigator.wakeLock.request('screen')`) gated behind a toggle in the nav bar; only works when the tab is foreground. Worth considering if we add a kiosk/shop-floor mode.]_
* Config button, for configuing certain things in the system without having to edit a config file manually in a text editor. **Decision: Full-schema design first.** The architecture must be extensible so adding new configurable items "just works" without code changes to the config UI itself. The schema should be self-describing (key, label, type, default, section, validation rules) so the UI can render any new entry automatically. This will pull in the "Make as much of Command Center user configurable as possible" item. When we sit down for design: define the schema format, config storage (JSON file vs. DB table), import/export format, and a section hierarchy. _[NEEDS DESIGN SESSION — schedule a dedicated design discussion before any code starts.]_

* Filabridge status light is still blinking on and of, just more eraticly now. Need to look into this further. _[ON HOLD — hardware/firmware on the filabridge device itself. Not actionable from this repo until we can instrument the device side or get a usage log with timestamps correlated to filabridge-side network events.]_


* Check why FIL:58 wasn't marked as labeled when scanned. The `label_printed` field was retired in M7 and replaced with `needs_label_print` (boolean) — barcode-scan path now updates this field at `app.py:921-922, 968-969`. The FIL:58 case specifically needs manual repro to see whether the update fires and why Activity Log was silent. Could be because FIL:58 is an old physical swatch with no prior spoolman state. _[ON HOLD — need to locate or reprint the FIL:58 physical label/swatch before repro can be attempted. When found: scan with DevTools open → Network tab → `/api/identify_scan` response + Activity Log ticker.]_


* Sub-bug: "Display modal on Display modal" — suspect this is the filament→spool chain at [inv_details.js:304](inventory-hub/static/js/modules/inv_details.js#L304) interacting with the silent-refresh paths at lines 386/395. Needs its own reproduction trace before fixing. _[PARTIAL REPRO 2026-04-29 — Derek reports the crash appears to happen when the spool/filament details modal and the Add/Edit Wizard are both engaged simultaneously. Observed twice. This is likely the same root cause as the frontend lock-up at L22 below — a modal-on-modal race condition leaving `state.processing` stuck or an unhandled promise rejection. Next occurrence: capture DevTools Console + Network tabs BEFORE refreshing; `console.trace` wrapper around `openFilamentDetails` / `openSpoolDetails` / wizard open to see the call stack at the double-open.]_

* An unknow issue caused the frontend to lock up, causing it to no longer update to take barcodes. A hard refresh (Control shift R and Control F5) fixed it. We need to figure out what caused this, and fix it so it doesn't happen again. This could be related to the eject button issue above. Also seemed to have cause updates to filabridge to stop until the front end was refreshed. _[RECURRED 2026-04-29 — now believed to be the same root cause as the "Display modal on Display modal" bug at L20. Derek observed the crash twice when the details modal and the Add/Edit Wizard were both open. Likely a modal-on-modal race condition (e.g. wizard open fires while details modal's silent-refresh is mid-flight → unhandled promise rejection → `state.processing` stuck true → all barcode input and FilaBridge updates freeze). Next occurrence: DON'T hard-refresh first. Open DevTools → Console and Network tabs, screenshot pending XHRs and any red errors, then refresh.]_




* Need to do something about the fact that if a toolhead has multiple slots assigned to it for a dryer box, that new spool assignments don't automatically take over the current toolhead's assigned spool. **Decision: (c) Leave it to the user via Quick-Swap.** Intent is ambiguous — a new spool landing in a shared box may not mean the user wants to switch the active toolhead assignment (e.g., staging spools for later). Quick-Swap is the deliberate, explicit action for swapping. No auto-switch or auto-prompt. _[RESOLVED — no code change needed.]_

* No way to assigne a slot to a printer without having a toolhead assigned to it. It would be nice if we could assign slots to a printer so they show up for possible easy swaping, but not actually being assigned to a toolhead. (in cases where the dryer box is basically ment for a printer, but we can't use a slot because of layout. Prusa XL and LR-MDB-1:SLOT:4 is a good example.) **Decision: Sentinel value approach** — `slot_targets` will accept a `"PRINTER:<id>"` value (e.g. `"PRINTER:XL"`) in addition to strict toolhead LocationIDs. The Quick-Swap grid renders these as printer-affiliated slots (with a distinct visual treatment), but `perform_smart_move`'s auto-deploy logic skips sentinel-valued targets so no toolhead assignment is made. Changes needed: ~~(1) `slot_targets` validation to allow the new prefix~~ _[DONE 2026-04-23 — `validate_slot_targets` + `is_printer_sentinel` in `locations_db.py`]_, ~~(2) Location Manager dropdown to include printers as targets (grouped separately from toolheads)~~ _[DONE 2026-04-23 — `_printerSentinelOptions` inside the Feeds combobox, `buildFeedsCombobox` + `_comboHydrate` both pick them up]_, (3) Quick-Swap grid to render a "Printer Pool" banner row for sentinel slots _[NEEDS IMPLEMENTATION — sentinels round-trip through save/load correctly but do not surface in the Quick-Swap grid yet. When picked up, the natural place is the printer-aggregation view in `inv_quickswap.js` (Printer-type locations aggregate per-toolhead rows today via `resolvePrinterNameForPrinterLoc`); add a "Printer Pool" row that lists every (box, slot) whose target === `PRINTER:<thisPrinter>`. Tap/Enter should probably hand off to the existing deposit flow since there's no toolhead to swap.]_, ~~(4) `perform_smart_move` guard to skip auto-deploy for sentinel targets~~ _[DONE 2026-04-23 — guard at `logic.py` perform_smart_move bound_toolhead section]_. Backend tests: `test_dryer_bindings.py::test_validate_accepts_printer_sentinel_with_known_prefix` + siblings. UI E2E: `test_loc_mgr_bindings_ui_e2e.py::test_feeds_combobox_exposes_printer_sentinel_options` + round-trip.

* Newly created spools generated by the add/edit wizzard, should default to unassigned if a location isn't provided.

* Need to retool how the location selector works in the add/edit wizzard. It doesn't "Flow" properly. Having to delete the existing text to get the full list to change it is a bit clunky.


* I think the add/edit inventory wizard is too complicated, we should definitely do a clean up pass on this and all of it's processes. I like what's here, but it's a lot of data. The functionality is good, but it just really needs some modernization or something. it's very clunky. We should try and make it more intuitive to use.

* Lagacy QR code scans cause the ? button to engage and pop up the help window. Not sure if theres a good fix for this.

* Fix version number that no longer gets updated. (Remove, or find a way to update it when we do updates.)

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


* Spools on a toolhead (yes, some how multiple are on there.) Cannot be changed once a print is started becasue the confirm change modal is being blocked, canceled, or hidden, preventing the user from swaping out filaments while a print is warming up. This wasn't intended. As I can easily forget to change a spool out during the begining of a print.

* Scanning a toolhead with multiple filaments in the command center buffer, cause all filaments to be assigned to the toolhead. This shouldn't happen. Only the top most item on the list should be assigned to the toolhead. The rest should stay in the buffer. Scan was the toolhead QR code directly (Core1-M0).

* Location search box should display all locations once a vaild location is selected or loaded in the Add/Edit wizzard. This should be propigated to other location search text boxes, if not already present.

* Constantly being prompted that a filament or spool is verified every scan on the activity log, is a bit much, we need a way to tone that down some, or as I hate to say it, possibly turn it off. We should have another way for the user to verify this. Instead of continuing to notifying them in the Activity Log.

* Forcing a location using the location edit in the spool display modal, should proably update depolyed status to be off, unless the location selected is a toolhead. (Asuming toolheads are a valid target for this location update.)

* Quick weight modal that displays when adjusting weights on spools won't let me change the value in the text field, seems that it won't receve focus?

* A Spool in LR-MDB-2 When auto ejected, was still assigned to the dryer box (2/2) but wasn't visible in the UI. Need to find out why and fix. Had to be found/scanned and force moved to get it fixed.
[00:11:40] ↩️ Returned #106 -> LR-MDB-2
[00:11:40] ⚠️ Smart Load: Ejecting #106 from XL-4...
[00:11:40] 📦 #230 IIID Max PLA (Transition (Color Change)) -> Dryer LR-MDB-2 [Slot 1]

* Seems to be that the unsorted list is missing in dryerbox locations now? anything that seem so fall into this catagory just doesn't show up, even though the box states (5/4) need to investigate whats going on there.

* Location search boxes should also be able to search based on the LOC: Value (LR-MDB-1)

* If possible, set certain text fields to only prompt with auto fill on some (perhaps none) fields. I think this might be a setible somewhere in the code to prevent a list of previously used values for showing up. Most of the time, this is just getting in the way for me.

* **[Feature]** Easy way to see what filaments are active on the printers at a glance, and how much filament is left in them. This item could possibly be grouped with the Project Color Loadout, It may contain some over lap with the systems in there. But I'd like to have this sooner, as I keep doing it lately to check to see if I should change spools now, or see if I can fit in one more print.

* Seem sthat the weight update bug (that happens in the dedicated weight modal), the text box un-editable one, seems to occure when accessing from filament cards in location mamanger? Up and down works, but text input directly is impossible for them for some reason.

* Remove "Alex Clamp" text from warning in weight modal when weight is < 0g. This text in the warning doesn't need to be in there. Its just a feature added by another AI.

* Assigning a spool directly to a toolhead, doens't properly update the slot in the dryerbox. Dryer box has to be updated agagain seperatly. The dryerbox and tool head (slot assignments seem to desync if toolhead is the first target.) Filaments hitting 0 also cause some weird unassignment sync. It will get removed from the slot location in filabrige, but still remain in locations/slots. This whole systenm needs another pass to to work more logically.

* Forcing a empty spool weight fill in when updating a spool that doesn't have an empty spool weight, when using the gross function sholdn't prevent the user from entering a weight if the don't know, or can't find the empty spool weight. We need to check if this is the case, and if so, give the user the option to skip adding an empty spool weight. This is preventing me from updating the weight on a spool. This is while in the quick weight modal.

* Ejecting from main menu while the printer is in a non idle state causes the location to not be updated/removed from the toolhead. I was in the process of preping to insert another new filament into the printer. This shouldn't be a blocking move. Also the modal to aprove came up twice, and did nothing when selecting yes. So theres that too.

* Quick weight modal, should have a way to set a perfered weighing methiod. I currently use gross more when I'm working on a filament swap than the additive. I'd like to be able to change the default mode, instead of it always defaulting to additive. Not sure how we do this. perhaps added to a general system configuration mode, which has yet to be implemented. 

* These seem interesting, and it would be great to find a way to use this in some fassion. Just putting this here as a future thing, or as something to keep in mind.
https://github.com/pubeldev/prusa_exporter
https://github.com/prusa3d/Prusa-Firmware-Buddy/blob/master/doc%2Fmetrics.md


## Prusament Enhancements ##
* Ability to merge duplicate filaments. Sometimes created when the existing filament card and the one the parcer generates based on prusament filaments don't match exactly. _[PARTIAL 2026-04-26 — duplicate **prevention** is in: tier-1 product-id matcher prefers filaments tagged with the same /spool/<id>/ as the scan, plus a duplicate-picker UI when the matcher can't disambiguate so the user picks (or chooses Create new). What's still missing: **merging existing duplicates** — a UI affordance that re-points all spools from one filament to another and archives/deletes the source. The picker prevents you from making MORE duplicates; you still need a way to clean up the ones already in the DB.]_

* **[Cleanup]** Audit the wizard's "Import from External" panel — which parsers actually still work, which are stale, what's the current dropdown showing? The user reported "I've completely forgotten what parcers we have set up there that work" — the Step 2 import-from-external surface needs a documentation pass and probably a deprecation pass. Code lives in `inventory-hub/external_parsers.py` (PrusamentParser, AmazonParser, SpoolmanParser, possibly others) and the dropdown is wired in `templates/components/modals_wizard.html`. As of 2026-04-26, Prusament works (per the per-spool scan flow); Amazon needs BeautifulSoup4 which isn't installed in dev (test_external_parsers.py::test_amazon_parser_matching fails locally for that reason); 3DFP / Spoolman-native should be re-tested. Worth combining with a UX refresh if we're touching that surface.

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
* Audit and implement consistent keyboard navigation across the entire UI. Currently only the force location modal and wizard material/multiselect dropdowns support arrow keys, Enter, and Escape. Every modal, dropdown, list, and interactive element should have a unified keyboard interaction pattern: arrow keys to navigate, Enter to select/confirm, Escape to dismiss/go back, Tab to move between controls, and auto-focus on the primary input when a modal opens.

## 🗂️ Modals & Add Inventory Wizard
* Help button to provide information on how to use a modal, and to try and store information about how things work in the code.
* Maintain the ability to add multiple spools of the same type at the same time.
* Create an assignment tool/system to pair existing/migrated Spoolman IDs directly to physical legacy spools being updated (specifically for bulk-imported identical spools sharing a single legacy ID).
* We now have 2 purchase links for spools, one that virtually links to the filament value, the other is on it's own but part of the spool. We need to look into the code here and pair down to only one fied if possible, but retain functionality. Linked field enharrenting the value possibly. Or we just fix the code so it looks at what is available and takes the one that exists, with a preference for the spool specific one, which may be more uptodate, or specific for the pricing. One of them, the first one on the page, seems to not clear between usanges.
* Adding a new slicer profile should automatically add that profile to the current filament being edited.
* Spoolmans field ordering bug causing fields in the Add/Edit enventory window to move if a custom field is modified or has new items added to it. Need to look at locking down the order of things.
* SweetAlert2 does not support nested modals — calling `Swal.fire()` while one is already open replaces the first one. Any future confirmation dialogs inside SweetAlert modals must use inline overlay divs (see force location modal's `#fcc-escape-confirm-overlay` pattern) instead of nested `Swal.fire()` calls. Audit existing code for any other nested Swal usage.

## 🔍 Search, Display & Filtering
* Search by and filter by remaining weight.



## ⚡ Quick-Swap Enhancements
* **Denser spool/filament cards inside the Quick-Swap grid**: reuse the existing `SpoolCardBuilder` system (the one that renders cards in the dashboard, Location Manager, etc.) so each bound slot shows a real filament card instead of the current custom button. That would unlock integrating more actions — Eject, Details, Edit, Print Queue — directly from the Quick-Swap view without extra trips through other modals. Needs a new card variant (e.g. `'quickswap'` mode) that omits some details to keep the grid compact while retaining the shared styling and interaction code. Reference: [inv_quickswap.js](inventory-hub/static/js/modules/inv_quickswap.js) grid render + [ui_builder.js](inventory-hub/static/js/modules/ui_builder.js) `SpoolCardBuilder.buildCard()`.

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

* Scanning a storage location (Any, dryerbox, Cart, etc) doesn't assign all items in the buffer to that cart, it requires you to scan the location multiple times in order to assign them all to it. _[LIKELY ALREADY FIXED — `performContextAssign` at inv_cmd.js:270 and `/api/smart_move` both accept a `spools[]` list and iterate the entire buffer. See the `[ALEX FIX] Bulk Assign` comment on inv_cmd.js:272. On next occurrence, capture the Network tab's `/api/smart_move` POST payload to confirm only one spool id was sent — if so the bug is upstream of the payload construction, in the buffer state. Otherwise close this out.]_
* Location Manager not syncing status across browser instances? _[ON HOLD — requires a real-time transport (SSE / WebSocket) on the backend. Current architecture is pull-only via `/api/locations` polling. Non-trivial; revisit after mobile mode since that work will establish the multi-client baseline anyway.]_

## 🎟️ Print Queue, Labels & Filament Usage
*(Group 3 — Print Queue & Label Management — completed 2026-04-28; see `completed-archive.md` for resolved items.)*

## 🧪 Testing
* `test_quickswap_visual.py::test_visual_quickswap_confirm_overlay[chromium]` — visual baseline mismatch: baseline `quickswap-confirm-overlay.png` is 800×234, actual capture is 800×426. Overlay grew taller (likely the deposit affordance / active-print banner from `feature/dryer-box-machine-quickswap`). Fix: visually verify the new layout is correct, then re-capture with `UPDATE_VISUAL_BASELINES=1 pytest inventory-hub/tests/test_quickswap_visual.py` and commit the updated PNG. Found 2026-05-07 during Group 7 wrap-up regression sweep.
* `test_ui_details_modal_e2e.py::test_details_modal_interactions[chromium]` — `Page.click(".fcc-card-action-btn[title='View Details']")` times out at 30s because `<div class="offcanvas-backdrop fade show">` (and an `offcanvasSearch` `<select>` underneath) intercepts the click. Same flake class as the test-ordering failures noted Apr 21 (passes in isolation, fails when prior tests leak an open offcanvas). Investigation: identify which test ahead of this one opens an offcanvas / search panel and doesn't close it, or add a defensive offcanvas-close at the start of `test_details_modal_interactions`. Found 2026-05-07.

## ⚙️ App Flow, Architecture & Database
* **MOBILE** Make the entire app mobile friendly so NFC/Scanning works on phones. (Perhaps a desktop mode to utalize barcode scanners, and a mobile mode of mostly touch interface and scanning barcodes/QR codes and NFC tags). The main difference being that mobile mode won't relye on all the inlaid barcode/qr codes we currently have in the interface currently for interacting with the UI elements.
* Refactor dashboard to be more modular if possible, and reduce token size/context requirements.
* Make as much of Command Center user configurable as possible, using UI elements and a config import/export feature.
* When changes are made to Spoolman extra fields, they usually ignore sort order in the database. We need a way to restore sort order.
* **Clean up filament attributes** — remove dead/duplicate entries from the `filament_attributes` choice list, AND add input validation so new garbage entries can't be created in the first place. _[2026-04-28 audit: Spoolman is the source of truth (CSVs no longer authoritative). Total 34 choices on the field; 27 actually used across 180 filaments. Spoolman's API rejects choice removal via POST (`400 "Cannot remove existing choices."`), so a true cleanup requires the snapshot-restore migration pattern (template: `migrate_container_slot_to_text` in `setup-and-rebuild/setup_fields.py`): snapshot all filaments' `filament_attributes` values → `force_reset` delete the field schema → recreate with cleaned choices → restore filtered values. Heavy for purely cosmetic dropdown cleanup; deferred until the migration is worth the time.

  **Prevention (actionable now — ship before any cleanup migration; an ounce of prevention is worth a pound of cure since removal is so expensive):** Every dead choice in the audit looks like an input-time error that the API made permanent: `Tran` (truncated — user hit enter before finishing `Transparent`), `Wood` (typed before `Wood Filled` existed), `Carbon-Fiber` (hyphen-vs-space dupe of `Carbon Fiber`), `Transparent; High-Speed` (semicolon-as-separator misuse), `F` (1-char typo). Concrete guards to add to the wizard's "+ Add new attribute" affordance (and any future Edit Filament parity surface):
    - **Minimum length** (≥3 chars) — blocks `F`-class typos.
    - **Trim + reject leading/trailing whitespace or punctuation** (`;`, `,`, `:`, `/`) — blocks `Transparent; High-Speed`-class separator confusions; users trying to add multiple attributes that way should be redirected to add them one at a time.
    - **Fuzzy/prefix match warning** — when the new value is within 1–2 Levenshtein edits of an existing choice, OR is a prefix of an existing choice, OR collapses to the same string after lowercasing + removing non-alphanumerics, surface a "Did you mean: <existing>?" prompt with two options: "Use existing" (the safe default) vs. "Add as new anyway" (requires deliberate confirmation). This is the single highest-value guard — would catch `Tran` → `Transparent`, `Wood` → `Wood Filled`, `Carbon-Fiber` → `Carbon Fiber` automatically.
    - **Two-step confirm for add-new** — adding a new choice to a field schema is rare and high-impact (Spoolman makes it permanent). The affordance should feel more like a settings change than a casual dropdown pick. After the fuzzy-match warning passes, surface a confirm dialog: "Add '<value>' as a permanent new filament attribute? This cannot be undone via the UI."
    - **Live preview of the canonical stored value** — show what will be stored after trim/normalization so users can see e.g. that `  Wood Filled  ` collapses to `Wood Filled` (and that `wood filled` would become a *new* choice distinct from `Wood Filled` if case-sensitivity bites).

    Likely lives in the wizard's dynamic-extra add-choice flow — search `inv_wizard.js` for the existing "+ Add new" handler on the materials/attributes multiselect (the same surface that landed in Edit Filament Wave 5/6). Apply the same guards consistently to any other add-new-choice entry point. Worth doing as its own small group/task even though the bulk cleanup migration stays deferred — prevention pays off the next time someone adds an attribute, while the migration only pays off once.

  **Confirmed safe to delete** (Derek 2026-04-28): `Carbon-Fiber` (dupe of `Carbon Fiber`), `Tran` (truncated), `Transparent; High-Speed` (semicolon-bogus), `Wood` (superseded by `Wood Filled`), `F` (typo).
  **Keep:** `+` — represents PLA+ filaments (currently displayed as `+ PLA`, but the value itself is intentional). Filament #132 (Creality Rainbow) uses it correctly.
  **Investigate before deciding:** `For Infill` — was used to flag color-switch / prototype-only filaments not meant for visible prints. Codebase grep confirms no replacement mechanism exists; if Derek wants a different infill-flag UX, that should be a separate item. Otherwise keep.
  `Matte Pro` — likely orphaned from a prior wipe-and-replace, currently unused. Probably safe to delete but Derek wants to confirm origin first.

  **Bad data to fix** (out of scope for choice cleanup): no orphaned values found in actual records — everything stored references either a still-valid choice or `+` (intentional).

  **Approach when ready:** Write `setup-and-rebuild/migrate_filament_attributes.py` following `migrate_container_slot_to_text` template. Should be runnable from host with config_loader path setup, ask for confirmation, snapshot → force_reset → recreate → restore. Verify against a live Spoolman dev instance with backup before touching prod.]_
* Continue to support Spoolman's "Import from External" feature for filaments...
    - open-filament-database
    - Prusament spool specific data links
    - Open Print Tags (Initialize, Read, and Write)
* Maybe we should figure out a way to set up a dev version for Spoolman and filabridge.
* Change auto refresh to be a pause button instead for live activity.
* Need to add a routine to clean up the logs after a while.
* Refactoring setup code to be dynamic. On brand new installs, maintain existing code to get it started.
* Continue to support Spoolman's ability to pull data from the vendor up to filament (Empty Weight), and from Filament to Spool (price, etc.)
* Add the ability to configure which extra fields should be bound and propagated to the other type of item. (Filament <-> Spool).
* Spools might need to have a text field added to store the product data (Prusament link, etc.).
* Add background refreshing used in Location Manager, etc... to update spool text (update weight other data).
* Python server auto-reload on new code changes.


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
* **Filabridge ↔ Spoolman reconcile utility.** Admin action (button in Config or a top-bar widget) that reads `/api/status` from filabridge and cross-checks every non-zero toolhead mapping against Spoolman's `location` field. For each mismatch, offer two choices: (a) "Trust Spoolman — unmap filabridge" (clears the stale entry) or (b) "Trust filabridge — update Spoolman" (writes the toolhead into Spoolman's `location`). Today this is fixable only via a manual Python one-liner (see `acf309c` / `efa15dd` discussion 2026-04-22). The new `_fb_spool_location()` pre-flight in `logic.py` prevents *new* desyncs, but doesn't heal ghost mappings created by earlier bugs, manual DB edits, or the retired `suppress_fb_unmap` code path — once a ghost exists, it persists until the affected spool gets moved through the fixed path.

# **New related project to be integrated **

* [Feature] Build Project Color Loadout Add-on -> (See /docs/Project-Color-Loadout/)
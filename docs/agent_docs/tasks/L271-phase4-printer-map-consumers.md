# L271 Phase 4 — prep: `printer_map` consumer map + plan (for a FRESH chat)

**Status (2026-06-04, end of session):** **Steps 1–4 DONE + pushed** on `feature/l271-phase-4` (origin, clean tree). Phase 3.5 is **DEPLOYED to prod** (`origin/main` `a070cff`). **Step 4 (the cutover) is COMPLETE** — the Printer rows' `toolheads[]` are now the SOLE source; the editor PUT writes the rows (not config); `config:printer_map` is retired-as-writer and kept ONLY as the boot-time priming seed. **Remaining on the branch: Step 5 (Group 20 — needs live FilaBridge repro) + the prod deploy.**

> **✅ STEP 4 COMPLETE (2026-06-04).** Decisions taken (both as recommended): **KEEP `config:printer_map`** (it's load-bearing — gitignored instance data the deploy doesn't touch, so it PRIMES prod's rows' `toolheads[]` on first boot; also the rollback net) and **stop writing it**; **KEEP `_canonicalize_printer_map`** as the PUT's validator, retire only `save_printer_map`. What shipped: (1) `get_active_printer_map` drops the config fallback → rows are the sole source; (2) the `/api/printer_map` PUT canonicalizes → guards against the **row-sourced** `old_map` (was config) → writes `toolheads[]`+`Name` onto the rows authoritatively (`save_locations_list`, 500 on fail) → **fails CLOSED 409** if locations is unreadable; (3) the startup fold is **`prime_only=True`** (primes a never-folded row e.g. prod's first boot, but NEVER overwrites a folded row, so a UI edit isn't reverted from the now-stale config seed); (4) `save_printer_map` retired. **Bonus fix:** the editor **rename** (printer_name → Printer-row `Name`) now propagates — the Step-3 GET shim had silently broken it (neither migration touches `Name`); the PUT now syncs it. **🛑 HARD CONSTRAINT honored:** `position` IS the FilaBridge `toolhead_id` (0-based) — the PUT stores it VERBATIM (test `test_put_printer_map_preserves_arbitrary_positions_verbatim` pins a deliberately non-contiguous set; no auto-renumber). **Behavior change to know:** `config:printer_map` is now read-only-at-boot — hand-editing it + restart no longer takes effect (prime-only); all edits go through the Settings editor UI. **Verified:** host pytest green across `test_config_save`/`test_l271_phase4_toolheads`/`test_dryer_bindings` + step-2 seam files; live `:8000` idempotent PUT round-trip (config byte-unchanged) + rename round-trip (propagates, config untouched, reverts); dev `locations.json` stays 53 rows / XL→5 / CORE1→1.

**Step 4 work (verified line refs):** (1) rework `/api/printer_map` PUT (`app.py:~2804-2846`) to write `toolheads[]` onto the Printer rows — group the editor payload by printer PREFIX (= Printer row LocationID), extract `{location_id, position}` (verbatim), `save_locations_list` instead of `config_loader.save_printer_map`; create a Printer row for a brand-new printer; after this the post-PUT sync block (`app.py:~2833-2845`) becomes a no-op/removable. (2) point `_printer_map_blocked_removals` old_map (`app.py:~2816`) at `get_active_printer_map()` (rows); the guard logic (scan slot_targets + Spoolman occupancy) stays unchanged. (3) drop the config fallback in `locations_db.get_active_printer_map` (`locations_db.py:~763-770`) so rows are sole source. (4) retire `config_loader.save_printer_map` (`config_loader.py:~462-479`) + `_canonicalize_printer_map` (`~430-459`) + the `load_config` printer_map key-uppercasing (`~103/161`) — grep for any other callers first; the startup fold migration `migrate_printer_map_to_toolheads_if_needed` becomes a no-op once config has no printer_map (keep it harmless or remove). (5) Test seams: stub `locations_db.get_active_printer_map` for PUT tests (the GET shim from Step 3 already works unchanged). **Downstream FilaBridge/eject/dryer logic needs NO change** — it consumes `get_active_printer_map`, so the source switch is invisible. **Test seams** (when a swap reddens a test): stub `locations_db.get_active_printer_map`, or an autouse fixture delegating it to the stubbed `config_loader.load_config` (see `test_active_print_backend_enforcement.py`, `test_filabridge_recovery.py`). Keep the `/api/printer_map` GET/PUT shape so the 4 JS modules stay unchanged.

### `printer_map` PRIMER (Derek asked "what is this / how did printers get in?")

`printer_map` is a **dict in `config.json`** mapping each **toolhead LocationID → `{printer_name, position}`**. Current value:
```jsonc
{ "XL-1":{"printer_name":"🦝 XL","position":0}, "XL-2":{…1}, "XL-3":{…2}, "XL-4":{…3},
  "XL-5":{"printer_name":"🦝 XL","position":5},        // NOTE the gap: no position 4
  "CORE1":{"printer_name":"🦦 Core One Upgraded","position":0} }
```
**How it was configured (verified via git, 2026-06-04 — NOT CSV-derived, NOT FilaBridge-populated):** `printer_map` has been **hand-authored directly in `config.json` since the repo's very first commit** (`6e2d663`, 2026-01-22). Git history shows it does **NOT** derive from the old CSV (the CSV→JSON migration `_ensure_json_migration` migrates *locations* only — the CSV has no printer→toolhead aggregation), and the retired `feeder_map` (M7) was a *separate* dryer-slot map. What IS recent is the **Settings editor UI** (L18 Phase 3 — `inv_settings.js renderPrinterMap`/`pmRender` → GET/PUT `/api/printer_map` → `config_loader.save_printer_map`); before that, the map was edited by hand-editing `config.json`. (Derek's "it derives from the old CSV" memory is unconfirmed in this repo's history — it was hand-authored config from day 1; any pre-repo lineage predates git.) **Nothing regenerates it** at runtime/startup — the editor PUT is the only writer — so retiring it is safe + one-way. The **`printer_name` you entered defines the printer** ("🦝 XL", "🦦 Core One Upgraded" exist because they were typed here). FilaBridge is separate: it supplies printer *credentials/state* keyed BY `printer_name`, but never populated this map.

**⚠️ `position` IS the FilaBridge toolhead index (0-based; verified — Derek was right about the linkage):** `position` is sent **VERBATIM** to FilaBridge as `toolhead_id`. `logic.py:140` `_fb_write` POSTs `{"printer_name":…, "toolhead_id": <position>, "spool_id":…}` to `{fb_url}/map_toolhead`; `perform_smart_move` builds `dest_th = (p['printer_name'], p['position'])` (logic.py:591) and passes it straight through (test pins: `position 3 → toolhead_id 3`). **FilaBridge is 0-based**, so XL's 5 toolheads are indices **0–4**. **CORRECTION (Derek 2026-06-04): the earlier `XL-5→position-5` was a TYPO, NOT a meaningful gap** — FB index 5 doesn't exist, so that slot's reference would have broken; only harmless because it was dev-side. Derek fixed it to **4**. *Verified all three are now `4`, contiguous 0..4: dev config.json, the dev Printer-row `toolheads[]`, and PROD config.json.* ⇒ **Step 4's PUT must store/send `position` VERBATIM — never auto-renumber/compact/normalize.** (A *deliberate* non-contiguous set could exist if a physical toolhead were removed, so the editor must not "helpfully" resequence; the USER enters correct 0-based indices, the system just passes them through.) Add a Step-4 test pinning that a PUT preserves arbitrary positions verbatim (incl. a deliberately non-contiguous one) — proving no auto-renumber. `position` is also load-bearing for the MMU M0/M1 de-dup (aliases share a position) + dryer-box slot ordering.

**What L271 Phase 4 is doing:** moving this map OUT of `config.json` and ONTO each first-class `Type:"Printer"` row in `locations.json` as a `toolheads:[{location_id, position}]` array (the `printer_name` becomes the Printer row's `Name` — verified the *complete* set of FB-load-bearing fields is just `location_id`+`position`, nothing else). Steps 1–3 made everything READ from the rows; Step 4 makes the editor WRITE to the rows and retires the `config.json` copy.

## ✅ Step 1 COMPLETE — schema + accessor + dual-read migration (`4287ed6`)

**Schema (LOCKED):** each first-class `Type:"Printer"` row gets `toolheads:[{location_id, position}]`. **`printer_name` is NOT stored per toolhead** — the Printer row's `Name` is the single source of truth (kills the cross-file drift class). Grouping is by printer **PREFIX** = the row's unique `LocationID` (not by name → two printers sharing a display name can't cross-contaminate). Live result: `XL → [{XL-1,0}…{XL-5,5}]` (position gap at 4 preserved), `CORE1 → [{CORE1,0}]` (dual-role single toolhead).

**The de-risking lever (`locations_db.build_printer_map_from_rows`):** an inverse accessor that reconstructs the **byte-identical** `{LOCID_UPPER:{printer_name,position}}` dict that `config_loader.load_config()['printer_map']` exposes today (printer_name injected from the row `Name`; keys uppercased). **Verified on the live :7913 container: `build_printer_map_from_rows() == config printer_map` exactly.** So every step-2 consumer is a **one-line data-source swap** (`cfg.get('printer_map')` → `locations_db.build_printer_map_from_rows(loc_list)`) with provably identical output — the Phase-2/3.5 method. No consumer reads it yet (dual-read; printer_map still authoritative).

**Shipped:** `migrate_printer_map_to_toolheads_if_needed` (startup, after Phase 3.5; idempotent + re-syncs on a printer_map edit; clears stale; backup) + the `/api/printer_map` PUT post-save sync (keeps toolheads[] current on edit, no reboot). 13 tests in `test_l271_phase4_toolheads.py` (incl. live round-trip, MMU-alias `position` preservation, drift-resolution). Verified idempotent (re-run `changed=False` on real on-disk data) + `/api/printer_map` byte-identical vs baseline.

**Bonus fix (in the same commit):** the long-standing dev-data wipe ([[reference_fcc_e2e_sweep_pollution]] "53→2 via the rename/bindings test") was `test_config_save.py`'s printer_map PUT tests stubbing `load_locations_list` but NOT `save_locations_list`, so the PUT post-save sync overwrote the real `data/locations.json` with a 2-row stub. `_ref_env` now no-ops `save_locations_list`. Dev locations.json stays 53 rows across the full sweep.

## ✅ Step 2 (safe reads) PARTIAL — `ef285c9` (2a) + `395493c` (2b)

Swap pattern: `config_loader.load_config()['printer_map']` → **`locations_db.get_active_printer_map(loc_list)`** (the dual-read wrapper: rows' toolheads[] with config fallback). The `locations_db` helpers that take `printer_map` as a *param* (`_known_printer_prefixes`, `_resolve_printer_name`, `validate_slot_targets`, `get_bindings_for_machine`) need NO change — their callers now pass the accessor's dict.

- **2a (`ef285c9`)** — added `get_active_printer_map`; swapped `spoolman_api.search_inventory` deployed-state filter. Live: `deployed_targets` identical, `/api/search?deployed=deployed` → same 6 spools.
- **2b (`395493c`)** — swapped **8 read-only app.py consumers**: dryer-binding validation (`api_dryer_box_bindings_put`, `api_single_slot_binding_put`), `api_printer_state`, `api_machine_toolhead_slots`, the 2 FilaBridge error-recovery snapshots, the FB `/status` reverse-map, `_pulse_section_printer_status`. Live: 200s + correct data; 179 tests green; dev locations.json stays 53 rows.
- **Test-seam note:** tests that stubbed `config_loader.load_config` to inject a printer_map for a swapped endpoint now stub `locations_db.get_active_printer_map` instead (`test_search_deployed_filter`, `test_printer_status_box_bounding`, `test_printer_state_api`). The live A/B proved real behavior is unchanged; only the unit seam moved.

### ⛔ Step 2 REMAINING — the fragile / write batch (DEFERRED, needs live FilaBridge repro + its own focused session)
All still read `cfg.get('printer_map')` (untouched, dual-read keeps them correct):
- **`logic.py`** move/eject/undo/force-unassign + helpers (`_active_print_info_for_location`, `_toolhead_of`) — outage-prone; migrate with a real ghost-trail spool on the live container, **NOT unit tests alone**.
- **app.py weight/MMU paths**: `api_quickswap_return` (2958), `api_fb_aggressive_parse` (3653), the auto-recover task (4721) — these call `_resolve_active_locs_for_printer` (MMU M0/M1 dedup) and DEDUCT weight. Migrate `_resolve_active_locs_for_printer`'s callers to pass `get_active_printer_map()`; the helper keeps `position` (the dedup key).
- **Editor** `/api/printer_map` GET (2703) + PUT (2812) + `_printer_map_blocked_removals` → that's **Step 3** (compat shim), not step 2.

## Verified consumer inventory (2026-06-04, 6-agent workflow vs live code — line numbers CONFIRMED)

> Step-1 baseline lines (pre Step-2 edits; the 2b swaps shifted a few by ±2). Step 2 swaps each `cfg.get('printer_map')` → `get_active_printer_map(loc_list)`, **safe reads first (DONE), fragile `logic.py` move/eject LAST with live FilaBridge repro.**

- **locations_db.py**: `_known_printer_prefixes`@497, `_resolve_printer_name`@515, `migrate_printers_to_rows_if_needed`@544 (keep), `validate_slot_targets`@799/837, `set_dryer_box_bindings`@886, `get_bindings_for_machine`@953 (reverse name→toolheads).
- **app.py (16)**: startup migration@247, `_resolve_active_locs_for_printer`@400 (**MMU M0/M1 dedup** — keep `position`!), dryer bindings PUT@2597/2874, `api_printer_state`@2646, `/api/printer_map` GET@2665 / PUT@2772 / `_printer_map_blocked_removals`@2711, quickswap return@2931, `/api/machine/<name>/toolhead_slots`@3139, fb recovery@3574, auto-deduct@3626, fb-status reverse-lookup@3929, fb error-recovery snapshot@4664, fb auto-recover task@4695, `_pulse_section_printer_status`@4836.
- **logic.py (FRAGILE — outage-prone, migrate LAST)**: `_active_print_info_for_location`@28, `_toolhead_of`@64, `perform_smart_move`@399 (`target in printer_map`@497/555, `printer_map[target]`@593, reverse-lookup@749), `perform_smart_eject`@833 (@851/852/962), `perform_force_unassign`@995 (@1010/1011), `perform_undo`@1049 (@1055/1056/1063/1064/1072/1073). All use membership / index / `.items()` on the dict → the accessor serves them byte-identically.
- **spoolman_api.py**: `search()` deployed filter@1498 (`{k.upper() for k in pm.keys()}`).
- **config_loader.py (STORAGE layer — dissolves in step 4)**: `load_config` uppercases keys@161, `_canonicalize_printer_map`@431, `save_printer_map`@462.
- **prusalink_api.py**: no direct printer_map read (consumes `printer_name` as a param — no change).
- **Frontend (5, all fetch `/api/printer_map`)**: `inv_loc_mgr.js` `fetchPrinterMap`@305 + `_printerSentinelOptions`@348 (builds `PRINTER:<prefix>` via `split('-',1)[0]`) + feeds combobox@371, `inv_printer_status.js` `_aggregate`@80, `inv_quickswap.js` `resolvePrinterNameForToolhead`@20 + section@86, `inv_settings.js` `pmRender`/`pmSave`@249/274 (the EDITOR). **Step-3 strategy: keep `/api/printer_map` GET/PUT as a compat SHIM reading/writing the Printer rows' toolheads[] — the 4 read modules stay unchanged; only the editor's writer + the referential guard move to the row-backed store.**

**Original prep notes (for context) below.**

**Goal:** fold `config.json:printer_map` into a `toolheads[]` array on each first-class `Type:"Printer"` row in `locations.json`, retire `printer_map`, and dissolve Group 20 (20.1/20.2/20.3). Keep `printer_map` readable for one release (**dual-read**) as a safety net, then remove.

## Current `printer_map` (config.json at repo root — single-file bind mount, see [[reference_fcc_config_json_bind_mount]])
```jsonc
{ "XL-1":{"printer_name":"🦝 XL","position":0}, "XL-2":{...1}, "XL-3":{...2},
  "XL-4":{...3}, "XL-5":{"printer_name":"🦝 XL","position":5},   // NOTE: position GAP at 4
  "CORE1":{"printer_name":"🦝 Core One Upgraded","position":0} }
```
Proposed Printer-row shape (preserve `position` — the MMU dedup keys on it):
```jsonc
{ "LocationID":"XL", "Type":"Printer", "Name":"🦝 XL", "parent_id":"LR",
  "toolheads":[ {"location_id":"XL-1","position":0}, … {"location_id":"XL-5","position":5} ] }
```

## Consumer inventory (verified 2026-06-04 by an Explore sweep — ~50 reads, 1 write)

### Python — READS
- **locations_db.py**: `_known_printer_prefixes` (~497), `_resolve_printer_name` (~515), `migrate_printers_to_rows_if_needed` (~544, Phase-3 one-time — keep but it can read rows), `validate_slot_targets` (~799 + `_known_printer_prefixes` @816 + printer_map.keys() @837), `set_dryer_box_bindings` (~886 passthrough), `get_bindings_for_machine` (~953 reverse-lookup name→toolheads).
- **app.py**: `_resolve_active_locs_for_printer` (~400 — **MMU M0/M1 dedup**, queries PrusaLink mmu flag), `/api/toolhead_info` (~2646), **`/api/printer_map` GET (~2664)** + **PUT (~2771)** + `_printer_map_blocked_removals` (~2711 referential guard), `/api/dryer/bindings` PUT (~2597/2872), `/api/toolhead_smart_eject` (~2926 `pm_keys_up`), `/api/machine/<name>/toolhead_slots` (~3138), `/api/filabridge_spool_assign` (~3569), `/api/auto_deduct_gcode_usage` (~3623) + `_error` recovery (~4664) [both use `_resolve_active_locs_for_printer` + `processed_positions` dedup], `_pulse_section_printer_status` (~4836 Printer-Status aggregator), startup migration (~237).
- **logic.py** (~24 reads, the FRAGILE paths): `_active_print_info_for_location` (~11), `_toolhead_of` (~51), `perform_smart_move` (~397, `target in printer_map` @497/555, `printer_map[target]` @593, reverse-lookup @748), `perform_smart_eject` (~833, @851/962), `perform_return_to_origin` (~995), `perform_undo` (~1049).
- **spoolman_api.py**: `search()` deployed_state filter (~1495 builds `{k.upper() for k in pm}`).
- **config_loader.py** (storage layer): `load_config` uppercases printer_map keys (~160, runtime only, never persisted), `load_config_raw` (raw round-trip), `_canonicalize_printer_map` (~431), `save_printer_map` (~462).

### Python — WRITES
- **app.py `/api/printer_map` PUT** (~2771) → `config_loader.save_printer_map` (the ONLY writer; the editor UI).

### JavaScript (all fetch `/api/printer_map`)
- **inv_loc_mgr.js**: `fetchPrinterMap` + `state.printerMap` (~301), `_printerSentinelOptions` (~348 — frontend `_known_printer_prefixes`; builds `PRINTER:<id>` sentinels by `firstId.split('-',1)[0]`), toolhead pre-check (~1096).
- **inv_printer_status.js** (~83), **inv_quickswap.js** (~83), **inv_settings.js** (the printer_map EDITOR — GET ~339 + PUT ~310), **inv_config.js** (~47 renders the editor).

## Tricky bits (don't miss)
1. **MMU M0/M1 dedup** (`_resolve_active_locs_for_printer`): toolheads can share a `position` (CORE1-M0 + CORE1-M1 @ pos 0); the heuristic queries PrusaLink mmu flag to pick the active alias so gcode auto-deduct doesn't double-deduct. **The `toolheads[]` schema MUST keep `position`** or this breaks.
2. **Position gap** (XL-5 @ position 5, no 4): nothing may assume positions are 0..N-1.
3. **`/api/printer_map` is consumed by 4 JS modules.** Options: (A) keep GET as a read-only compat shim built from Printer rows; (B) point JS at `/api/locations` Printer rows. The PUT/editor + `_printer_map_blocked_removals` referential guard need a new home (inline toolhead edit on the Printer row, preserving the "can't remove a toolhead still bound to a slot / holding spools" safety).
4. **`logic.py` move/eject/undo** is the fragile, outage-prone surface — migrate with LIVE FilaBridge repro, not unit tests alone.

## Recommended Phase 4 step order (each its own commit, verify on live :7913 + :5001)
1. **Additive migration** `migrate_printer_map_to_toolheads_if_needed` — write `toolheads[]` onto each Printer row from printer_map; **dual-read** (printer_map stays). Idempotent + backup. **LOW risk, no behavior change.** ← safe first step.
2. Add a `printer_map`-shaped accessor in locations_db that reads from the Printer rows' `toolheads[]` (so consumers swap data source without logic changes). Migrate the READ consumers to it (locations_db, then app.py, then logic.py — each A/B byte-identical), keeping printer_map as fallback.
3. Frontend: point the 4 JS modules at the new source; rework the editor (inline on Printer row) + the referential guard.
4. Retire `printer_map` (config.json) once all readers migrated; drop the dual-read.
5. **Group 20** (the payoff): 20.3 toolhead-delete cascade → orphaned spools to `UNASSIGNED` + Activity-Log breadcrumb (Derek's decision); 20.2 single-slot box auto-attach on assign / detach on eject (`Max Spools <= 1` only); **20.1 eject stale-store — REQUIRES live repro of the L206 capture first** (trace which of the 3 stores stays stale; prime suspects in `20-toolhead-binding-unbind-cluster.md`). MMU M0/M1 alias dedup dissolves (a Printer with one toolhead per position).

**Tests (heaviest phase):** `test_dryer_bindings.py`, `test_filabridge_*`, an MMU-dedup pin, a new `test_l271_toolhead_delete_cascade.py` (orphan→UNASSIGNED), Group 20 live repro.
**Prod:** ⚠️ migration on prod config + locations.json; back up both; verify FilaBridge bindings + printer status post-deploy (Derek hits "play" on the TrueNAS cron).

> **Dev-data note:** the full E2E sweep wipes the dev `locations.json` (pre-existing pollution — [[reference_fcc_e2e_sweep_pollution]]); restore from a 53-row baseline + re-run the migrations / restart before verifying.

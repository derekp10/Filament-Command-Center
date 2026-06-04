# L271 Phase 4 — prep: `printer_map` consumer map + plan (for a FRESH chat)

**Status:** **STEP 1 SHIPPED to dev 2026-06-04** (`feature/l271-phase-4`, `4287ed6`); steps 2–5 pending. Phase 3.5 merged to `dev` (`c889102`). Phase 4 is the **heaviest, HIGH-risk** phase — it touches the eject / FilaBridge / one-spool-one-toolhead subsystem behind multiple past prod outages, and Group 20.1 explicitly **needs live FilaBridge repro** ("do NOT patch blind"). Resume in a fresh chat: *"continue L271 Phase 4 step 2 — read `docs/agent_docs/tasks/L271-location-manager-phase-plan.md` + `docs/agent_docs/tasks/L271-phase4-printer-map-consumers.md`"*.

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

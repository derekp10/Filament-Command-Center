# L271 — Location Manager Redesign: Full Phased Implementation Plan

**Status:** IN PROGRESS (authored 2026-06-03 from a verified 24-consumer code map). Phases 1A + 1B + 2 shipped; 2.5 → 3 → 4 → 5 pending.
**Branch (per phase):** `feature/l271-phase-2`, `feature/l271-phase-2_5`, … (one branch per phase, each merged before the next starts).
**Risk:** escalates by phase — **2 = low, 2.5 = low/medium, 3 = HIGH, 4 = HIGH, 5 = medium.** Phases 3-4 change `locations.json` schema + retire `printer_map`, so they need a startup migration AND prod replication (TrueNAS, Spoolman :7912, `\\TRUENAS\App_Data\InventoryHub`).
**Verify every phase against the LIVE Docker container** (real Spoolman :7913 + FilaBridge :5001) — unit tests alone don't hit the real topology (see [[feedback_adversarial_review_runtime_lens]]).

> **▶ EXECUTION — start this in a FRESH chat.** This is a multi-session (~22-31h) architectural project; run it with a clean context window, not appended to a bugfix-sweep chat. This document is the complete, self-contained handoff — a new session needs nothing else. **To begin:** open a new chat and say *"start L271 Phase 2 — read `docs/agent_docs/tasks/L271-location-manager-phase-plan.md`"*. Work one consumer-migration per commit, merge each phase green before the next. The `Feature-Buglist.md` phase tracker + this plan are the source of truth between sessions.

---

## 1. Why this exists (the payoff)

A spool's "where / is it loaded" is encoded across **three stores that drift**:
1. Spoolman `location` (the row's LocationID string)
2. Spoolman `extra.physical_source` / `container_slot` (ghost-deploy trail)
3. FilaBridge's toolhead→spool map

…plus dryer-box `slot_targets`, plus the hierarchy is parsed out of the **LocationID string** (`loc.split('-')[0]`) rather than a real relationship, and the Printer entity is **synthesized at runtime** from prefix grouping (`🦝 Core One Upgraded` exists nowhere on disk).

Two concrete payoffs end the bug class:
- **Dissolves Group 20** (the toolhead binding/unbind cluster — buglist 33/37/43 + L206). Once bindings are FK relationships, an eject updates ONE field and a toolhead-row delete cascades. The repeated partial fixes (13.6 → L204 → L206-still-open) stop recurring. See [20-toolhead-binding-unbind-cluster.md](20-toolhead-binding-unbind-cluster.md).
- **Unblocks Project Color Loadout.** `docs/Project-Color-Loadout/database_schema.sql` binds a project to `target_printer TEXT` (e.g. `"Prusa XL 5T"`) — a free string that breaks the moment the synthesized printer name changes. Phase 3 gives a stable `Printer.id` to anchor to.

---

## 2. Current state (what's already done + the consumer inventory)

**Shipped:**
- **Phase 1A** (2026-04-25): `parent_id` field added to each `locations.json` row; `derive_parent_id_from_prefix`, `resolve_parent`, `migrate_parent_ids_if_needed` in [locations_db.py](../../../inventory-hub/locations_db.py); startup migration wired in [app.py](../../../inventory-hub/app.py) with timestamped backup; ~15 unit tests. **No consumer reads `parent_id` yet.**
- **Phase 1B** (2026-05-25): one consumer migrated — `resolve_parent` in the `/api/locations` synthesizer room-occupancy aggregation ([app.py:1427](../../../inventory-hub/app.py#L1427)).
- **Phase 2** (2026-06-03, branch `feature/l271-phase-2`): all 4 **backend** consumers below routed through `resolve_parent`, one commit each. Each was verified IDENTICAL against the live 238-spool dev container (real Spoolman :7913) before committing, and pinned in [test_l271_phase2_consumers.py](../../../inventory-hub/tests/test_l271_phase2_consumers.py) (40 passed). Migrated: `get_room_from_location` (logic.py:786 — the central room deriver, so `perform_smart_eject`'s room fallback at logic.py:960 inherited it free), `perform_smart_eject` room-hierarchy bypass (logic.py:888), `get_spools_at_location_strict` (spoolman_api.py:1336/1343), `_build_location_match` (spoolman_api.py:1233/1241). `import locations_db` added to spoolman_api.py (no cycle).

**The remaining prefix-parse / synthesis consumers to migrate** (verified map 2026-06-03; ~~struck~~ rows shipped in Phase 2), grouped by target phase:

| Phase | File:Line | Symbol | Current | Derives | Risk |
|-------|-----------|--------|---------|---------|------|
| **2 ✅** | [spoolman_api.py:1233](../../../inventory-hub/spoolman_api.py#L1233) | `_build_location_match` | `'-' not in target … sloc.startswith(target+'-')` | parent (child-of-parent loc match) | med |
| **2 ✅** | [spoolman_api.py:1241](../../../inventory-hub/spoolman_api.py#L1241) | `_build_location_match` | same, for ghost `physical_source` | parent | med |
| **2 ✅** | [spoolman_api.py:1336](../../../inventory-hub/spoolman_api.py#L1336) | `get_spools_at_location_strict` | `bare = '-' not in target` | parent (flag) | low |
| **2 ✅** | [spoolman_api.py:1343](../../../inventory-hub/spoolman_api.py#L1343) | `get_spools_at_location_strict` | `bare and (sloc.startswith(target+'-') …)` | parent | med |
| **2 ✅** | [logic.py:793](../../../inventory-hub/logic.py#L793) | `get_room_from_location` | `loc_id.split('-')[0]` | **room (central deriver)** | low |
| **2 ✅** | [logic.py:889](../../../inventory-hub/logic.py#L889) | `perform_smart_eject` | `saved_source.startswith(current+'-')` | parent | med |
| **2 ✅** | [logic.py:949](../../../inventory-hub/logic.py#L949) | `perform_smart_eject` | `get_room_from_location(current)` | room | low |
| **2.5** | [inv_core.js:461-462](../../../inventory-hub/static/js/modules/inv_core.js#L461) | sort comparator | `(LocationID||'').split('-')[0]` | parent | med |
| **2.5** | [inv_core.js:555](../../../inventory-hub/static/js/modules/inv_core.js#L555) | tree-indent | `LocationID.split('-')[0]` | parent | med |
| **2.5** | [app.py:1418](../../../inventory-hub/app.py#L1418) | synthesizer | `loc.split('-')[0]` (comment/legacy) | parent | low |
| **2.5** | [spoolman_api.py:1478](../../../inventory-hub/spoolman_api.py#L1478) | `search_inventory` | builds toolhead set from `printer_map` keys | printer (already correct) | low |
| **3** | [app.py:1452](../../../inventory-hub/app.py#L1452) | synthesizer (printer injection) | `str(loc_id).upper().split('-',1)[0]` | printer | **high** |
| **3** | [app.py:1476](../../../inventory-hub/app.py#L1476) | printer-type detection | `c_loc.startswith(parent+'-')` | printer | high |
| **3** | [app.py:1488](../../../inventory-hub/app.py#L1488) | synthetic name lookup | prefix match for `printer_name` | printer | high |
| **3** | [inv_loc_mgr.js:358](../../../inventory-hub/static/js/modules/inv_loc_mgr.js#L358) | `_printerSentinelOptions` | `firstId.split('-',1)[0]` | printer | high |
| **4** | [locations_db.py:387](../../../inventory-hub/locations_db.py#L387) | `_known_printer_prefixes` | `ku.split('-',1)[0]` | printer | low |
| **4** | [locations_db.py:587](../../../inventory-hub/locations_db.py#L587) | `get_bindings_for_machine` | `th_id.split('-',1)[0]` | printer | low |
| **4** | [app.py:2608](../../../inventory-hub/app.py#L2608) | `_printer_prefix` | `k.split('-',1)[0]` | printer | med |
| **5** | [locations_db.py:325](../../../inventory-hub/locations_db.py#L325) | `derive_parent_id_from_prefix` | `s.split('-',1)[0]` | parent (the engine) | — |

---

## 3. Target data model

```jsonc
// locations.json row — Printer (first-class, Phase 3+)
{ "LocationID": "CORE1", "Type": "Printer", "Name": "🦝 Core One Upgraded",
  "parent_id": "LR",                     // room FK (nullable)
  "model": "Prusa Core One", "mmu_attached": false,
  "toolheads": [                          // Phase 4: printer_map folded in
    { "position": 0, "LocationID": "CORE1-M0", "mmu_routed": false }
  ]
}
// every non-Printer row carries parent_id (toolhead→printer, box→room, slot→box)
```

- **`parent_id` is the single source of hierarchy truth.** `loc.split('-')[0]` is retired site-by-site; once gone, a typo in a LocationID can't break grouping.
- **Barcodes decouple from hierarchy** (Phase 5): LocationID can become an opaque ID; moving a portable PM box to a new room no longer requires reprinting.
- **`printer_map` (config.json) dissolves** into the Printer row's `toolheads` array (Phase 4) — eliminates the cross-file drift class and the MMU M0/M1 alias dedup heuristic.

---

## 4. The phases

> **Invariant for every phase:** the `/api/locations` response shape and the on-disk row shape stay backward-compatible WITHIN the phase; each phase merges green before the next starts; each consumer migration is its own commit with an integration test that pins behavior BEFORE and AFTER (so a regression is obvious).

### Phase 2 — Backend consumer migration (low risk)
**Goal:** replace every backend `split('-')[0]` / `startswith(parent+'-')` with `locations_db.resolve_parent(...)` (which already falls back to prefix parsing internally, so behavior is identical until Phase 5 removes the fallback). Proves the abstraction in production with zero observable change.

**Order (one commit each):**
1. [logic.py:793](../../../inventory-hub/logic.py#L793) `get_room_from_location` → `resolve_parent(loc_id)`. **Do first** — it's the central room deriver; [logic.py:949](../../../inventory-hub/logic.py#L949) then falls out for free.
2. [logic.py:889](../../../inventory-hub/logic.py#L889) `perform_smart_eject` parent check → `resolve_parent(saved_source) == current_location`. ⚠️ This is in the fragile eject path — test against the live container with a real ghost-trail spool.
3. [spoolman_api.py:1336+1343](../../../inventory-hub/spoolman_api.py#L1336) `get_spools_at_location_strict` → resolve children via `parent_id` instead of `bare`/`startswith`. ⚠️ Spool-location queries feed the dashboard + printer status; verify counts match pre-migration on a seeded dev.
4. [spoolman_api.py:1233+1241](../../../inventory-hub/spoolman_api.py#L1233) `_build_location_match` → `parent_id` lookup for both `location` and `physical_source`.

**Tests:** extend `test_dryer_bindings.py` / add `test_l271_phase2_consumers.py` — for each migrated consumer, an A/B test asserting identical output for a representative tree (room → printer → toolhead → box → slot). **Reuse `reset_dev.py` seed** for a deterministic baseline (Group 19).
**Prod:** none — no schema change, no behavior change.

### Phase 2.5 — Frontend consumer migration (low/medium risk)
**Prerequisite:** the `/api/locations` payload must EXPOSE `parent_id` per row (Phase 1A wrote it to disk; confirm the synthesizer passes it through to each row in the response — add it if absent). This is the only backend change in 2.5.

**Migrate (one commit each):**
1. [inv_core.js:461-462](../../../inventory-hub/static/js/modules/inv_core.js#L461) sort comparator → read `row.parent_id` (fallback to current split if field absent, for safety during rollout).
2. [inv_core.js:555](../../../inventory-hub/static/js/modules/inv_core.js#L555) tree-indent → `row.parent_id` (null = top-level).

**Tests:** `test_dashboard_pulse_frontend.py` / a new `test_l271_location_tree_render.py` — assert the Location Manager table renders the same tree order + indent with `parent_id`-driven logic. Visual-regression baseline for the table if the DOM order is load-bearing.
**Prod:** none (API stays same; field is additive).

### Phase 3 — First-class Printer rows; retire the synthesizer (HIGH risk) — **unblocks Color Loadout**
**Goal:** persist what [app.py:1452-1488](../../../inventory-hub/app.py#L1452) currently conjures at runtime.

**Steps:**
1. **Migration** (`migrate_printers_to_rows_if_needed`, startup, timestamped backup like Phase 1A): for each distinct printer in `config.json:printer_map`, write a `Type:"Printer"` row to `locations.json` with `LocationID` = the printer key, `Name` = `printer_map[...].printer_name` (owns the emoji), `parent_id` = its room (resolved from a toolhead's room), `model`/`mmu_attached` best-effort. Idempotent: skip if the Printer row already exists.
2. Add `"Printer"` to the required-Type list in `_required_keys_for`.
3. Migrate the 3 `app.py` synthesizer consumers + [inv_loc_mgr.js:358](../../../inventory-hub/static/js/modules/inv_loc_mgr.js#L358) to read the on-disk Printer rows (Type + parent_id) instead of prefix-grouping. **Retire the runtime synthesizer.**
4. Tighten validation: every non-null `parent_id` must point to a real on-disk row (warn-don't-crash on orphans, log them).
5. **Color Loadout hook:** `target_printer` now anchors to `Printer.LocationID` (stable) instead of the synthesized display name.

**Tests:** `test_locations_json_integrity.py` extended for the Printer Type; `test_printer_status_widget.py` must stay green (it consumes the synthesized printers today); a migration test (dirty printer_map → Printer rows on disk, idempotent on 2nd boot). **Full live E2E** — the dashboard printer status + Location Manager grouping are the highest-traffic consumers.
**Prod:** ⚠️ run the migration on prod `locations.json`. Back up `\\TRUENAS\App_Data\InventoryHub\locations.json` first. The startup migration handles it, but verify the prod render after deploy.

### Phase 4 — Fold `printer_map` into `locations.json` (HIGH risk) — **dissolves Group 20**
**Goal:** the Printer row owns a `toolheads: [{position, LocationID, mmu_routed}]` array; retire `config.json:printer_map`.

**Steps:**
1. **Migration**: copy each `printer_map` entry onto its Printer row's `toolheads` array. Keep `printer_map` readable for one release (dual-read) as a safety net, then remove.
2. Migrate [locations_db.py:387](../../../inventory-hub/locations_db.py#L387) `_known_printer_prefixes`, [locations_db.py:587](../../../inventory-hub/locations_db.py#L587) `get_bindings_for_machine`, [app.py:2608](../../../inventory-hub/app.py#L2608) `_printer_prefix`, plus `_resolve_active_locs_for_printer`, `validate_slot_targets`, `/api/printer_map` to read the `toolheads` array. The **MMU M0/M1 alias dedup heuristic dissolves** (a Printer with `mmu_attached:true` has exactly one toolhead per position).
3. **Group 20 folds in here** (the whole reason to prefer this over symptom-patching):
   - **20.1 / L206** — eject/reassign now flips ONE FK + the FilaBridge unmap (already in place via L204). The three-store drift collapses because the toolhead binding is a real relationship, not a prefix join. Re-run the L206 repro capture to confirm the stale-store is gone.
   - **20.2** — single-slot dryer-box auto-attach: when a spool in a `Max Spools <= 1` box is assigned to a toolhead, set the box's `parent_id`/binding to that toolhead; clear on eject. Hook the same assign/eject points.
   - **20.3** — toolhead-row delete cascade (Derek's decision): when a toolhead/Printer row is deleted, relocate each orphaned Spoolman spool to its **last-known room** — derive from the spool's `physical_source` ghost trail (its box's `parent_id` room) or the deleted toolhead's parent Printer's room — and **fall back to `UNASSIGNED`** when no room can be inferred. Write an Activity-Log breadcrumb naming the old toolhead.

**Tests:** `test_dryer_bindings.py`, `test_filabridge_*`, a new `test_l271_toolhead_delete_cascade.py` (orphan → room vs UNASSIGNED), and the Group 20 live repro. **Heaviest test phase.**
**Prod:** ⚠️ migration on prod config + locations.json; back up both; verify FilaBridge bindings + printer status post-deploy.

> **20.3 timing — DECIDED (Derek 2026-06-03): fold into Phase 4, no standalone.** It's not pressing on prod, so it ships with the rest of the toolhead-delete cascade here rather than as an early one-off.

### Phase 5 — Retire prefix parsing + write-time validation (medium risk)
**Steps:**
1. Delete [locations_db.py:325](../../../inventory-hub/locations_db.py#L325) `derive_parent_id_from_prefix` and the prefix fallback inside `resolve_parent`. Any row missing `parent_id` is now a hard data error (the migrations guaranteed it's set).
2. Remove all remaining `split('-')[0]` sites (grep must return zero).
3. `save_locations_list` **rejects** rows with missing/orphan `parent_id` or missing `Type` (write-time validation — the empty-Type + orphan-parent bug classes cease to exist).
4. ~~Decouple printed barcodes from hierarchy~~ — **DEFERRED (Derek 2026-06-03): keep human-readable `XX-YY-ZZ-NN` labels for now** (avoids reprints; revisit later). The hierarchy still moves to `parent_id` internally; the printed LocationID just stays readable. The PM single-slot boxes are the portable case (see Decision 2) but their label identifies the box, not its current feed. A label-generation/printing re-evaluation is a future companion task, not part of Phase 5.

**Tests:** `test_locations_json_integrity.py` write-validation cases; a CI grep test asserting no `split('-')[0]` remains in the location code paths.
**Prod:** low — by now prod data is already FK-clean from the earlier migrations.

---

## 5. Sequencing, dependencies, and effort

```
1A ✅ → 1B ✅ → [2] → [2.5] → [3 *] → [4 **] → [5]
                                  ↑          ↑
                       unblocks Color    dissolves Group 20
                          Loadout        (20.1/20.2/20.3)
```
- **Hard dependency:** 2 before 2.5 (frontend needs the field surfaced + backend proven); 2.5 before 3 (don't retire the synthesizer while consumers still prefix-parse); 3 before 4 (toolheads attach to real Printer rows); 4 before 5 (don't delete the fallback until everything reads FKs).
- **Rough effort:** Phase 2 ~3-4h, 2.5 ~2-3h, 3 ~6-8h, 4 ~8-12h (incl. Group 20), 5 ~3-4h. **Total ~22-31h** across several sessions.
- **Each phase is independently shippable + reversible** (additive migrations with backups; dual-read windows on 3 and 4).

## 6. Decisions (resolved by Derek 2026-06-03)
1. **20.3 timing → FOLD INTO PHASE 4.** Not a priority; no standalone early-exit. The toolhead-delete orphan cascade ships as part of Phase 4 when bindings are first-class.
2. **Barcode decoupling (Phase 5 step 4) → DEFERRED; keep human-readable labels.** Keep the current `XX-YY-ZZ-NN` scheme for now (avoids reprinting). Revisit in the future. **Important nuance Derek surfaced:** the boxes that *can* move are the **single-slot Polymaker (PM) dryer boxes** (they attach to a toolhead — this is exactly the 20.2 case), NOT the room/printer-anchored boxes (which he doesn't foresee moving). So a PM box's printed label identifies the *box*, while its dynamic "where is it feeding" lives in `parent_id`/binding — keeping readable labels + FK-tracked binding is consistent and needs no reprints. Derek also flagged that **the whole labeling/printing scheme will likely be re-evaluated** as this lands (the `XX-YY-ZZ-NN` format was chosen for unique-yet-findable-by-eye labels); treat label generation as a future companion task to Phase 5, not part of it.
3. **Color Loadout start → WAIT.** Derek wants bugfixes + stabilization first before committing to the feature. Phase 3 *unblocks* it (gives a stable `Printer.id` to anchor `target_printer`) but does not require starting it. (Context: Project Color Loadout IS the color-tracking/profiles system — it binds a project's slicer slots to preferred filaments/colors/weights per printer, with a print queue + swap optimizer + reusable "palettes"; see `docs/Project-Color-Loadout/`. It just can't anchor reliably until Phase 3.)

## 7. Safety / rollback
- Every migration takes a timestamped `locations.json` / `config.json` backup before writing (Phase 1A pattern).
- Phases 3-4 keep the old path readable (dual-read) for one release so a bad migration is recoverable by reverting the consumer, not the data.
- Per [[reference_fcc_spoolman_dev_vs_prod]], dev (:7913) is isolated from prod (:7912) — validate each phase on dev with a `reset_dev.py` seed baseline before prod replication.
- Per [[feedback_adversarial_review_runtime_lens]], cross-reference docker-compose mounts and verify against the live container — `locations.json` is a directory bind-mount (the EBUSY single-file gotcha applies to `config.json`, not locations.json).

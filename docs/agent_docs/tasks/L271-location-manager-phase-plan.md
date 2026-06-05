# L271 — Location Manager Redesign: Full Phased Implementation Plan

**Status:** IN PROGRESS (authored 2026-06-03 from a verified 24-consumer code map). Phases 1A + 1B + 2 + 2.5 + 3 shipped — **Phase 3 deployed to prod + verified 2026-06-03** (`main` 31bdd3c); **3.5 (true multi-level nesting) MERGED to `dev` 2026-06-04** (`c889102`; pending prod). **Phase 4 STEP 1 shipped to dev 2026-06-04** (`feature/l271-phase-4` `4287ed6`: `toolheads[]` schema + `build_printer_map_from_rows` byte-identical accessor + dual-read migration; see the Phase-4 section + `L271-phase4-printer-map-consumers.md` for the locked schema, verified consumer map, and step 2–5 plan). Phase 4 steps 2–5 → 5 pending.
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
- **Phase 2.5** (2026-06-03, branch `feature/l271-phase-2_5`): the **frontend** tree consumers. A discovery sweep + completeness critic found the tree logic is **5 sites** in [inv_core.js](../../../inventory-hub/static/js/modules/inv_core.js) `_renderLocationsPayload` (not the 2 originally scoped). Migrated to read `row.parent_id` with a split fallback: sort comparator (461-462) and tree-indent `parentId`/`isChild` (555/560). **`hasChildren` (564) deliberately NOT migrated** — it's a `startsWith` descendant query, and parent_id is flat (first-segment) this phase while synthesized descendant rows are null, so a parent_id-equality rewrite would diverge (a synthesized printer could lose its expand toggle); it moves to Phase 3 when hierarchy is truly nested. **Backend prereq**: `parent_id` is now on *every* `/api/locations` row — the 3 synthesized dicts + the Spoolman-native row + a write-time stamp in `api_save_location` (so created/edited rows carry it immediately). Tree grouping compares **case-insensitively** (a Spoolman name / unnormalized form entry can be mixed-case while `parent_id` is uppercased). Verified: logic A/B 0 diffs over 55 live rows + pixel-identical visual baseline + POST→GET integration test. **Adversarially reviewed** (19-agent workflow: 14 findings → 2 root issues — non-uniform `parent_id` + case-sensitivity — both fixed). Pinned in [test_l271_location_tree_render.py](../../../inventory-hub/tests/test_l271_location_tree_render.py).
- **Phase 3** (2026-06-03, dev `feature/l271-phase-3` → `main` 31bdd3c, **deployed to prod + verified**): first-class on-disk `Type:"Printer"` rows via `migrate_printers_to_rows_if_needed` (XL appended; Core One promoted in place + blank-stub deleted), and the **printer half** of the `/api/locations` synthesizer retired (now Virtual-Rooms-only). Printers stay top-level roots (`parent_id=None`); room-nesting deferred to Phase 3.5. See the boxed note in the Phase 3 section below for the full scope + decisions. Pinned in [test_l271_phase3_printer_rows.py](../../../inventory-hub/tests/test_l271_phase3_printer_rows.py).

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
| **2.5 ✅** | [inv_core.js:461-462](../../../inventory-hub/static/js/modules/inv_core.js#L461) | sort comparator | `(LocationID||'').split('-')[0]` → `row.parent_id` (case-insensitive) | parent | med |
| **2.5 ✅** | [inv_core.js:555+560](../../../inventory-hub/static/js/modules/inv_core.js#L555) | tree-indent | `parentId`/`isChild` → `row.parent_id`; `hasChildren`@564 startsWith stays → **Phase 3** | parent | med |
| ~~2.5~~ done@1B | [app.py:1418](../../../inventory-hub/app.py#L1418) | synthesizer | live code already `resolve_parent` (Phase 1B); only a legacy comment names the split | parent | — |
| → **4** | [spoolman_api.py:1478](../../../inventory-hub/spoolman_api.py#L1478) | `search_inventory` | builds toolhead set from `printer_map` keys — no parent split, correct as-is; folds in when `printer_map` dissolves | printer | low |
| **3 ✅** | [app.py:1452](../../../inventory-hub/app.py#L1452) | synthesizer (printer injection) | **RETIRED** — printers are first-class on-disk rows | printer | **high** |
| **3 ✅** | [app.py:1476](../../../inventory-hub/app.py#L1476) | printer-type detection | **RETIRED** — `is_printer` detection removed | printer | high |
| **3 ✅** | [app.py:1488](../../../inventory-hub/app.py#L1488) | synthetic name lookup | **RETIRED** — `printer_name` lookup removed | printer | high |
| → **4** | [inv_loc_mgr.js:358](../../../inventory-hub/static/js/modules/inv_loc_mgr.js#L358) | `_printerSentinelOptions` | reads `printer_map` (not synthesized rows); folds in when `printer_map` dissolves | printer | high |
| **4** | [locations_db.py:387](../../../inventory-hub/locations_db.py#L387) | `_known_printer_prefixes` | `ku.split('-',1)[0]` | printer | low |
| **4** | [locations_db.py:587](../../../inventory-hub/locations_db.py#L587) | `get_bindings_for_machine` | `th_id.split('-',1)[0]` | printer | low |
| **4** | [app.py:2608](../../../inventory-hub/app.py#L2608) | `_printer_prefix` | `k.split('-',1)[0]` | printer | med |
| **5** | [locations_db.py:325](../../../inventory-hub/locations_db.py#L325) | `derive_parent_id_from_prefix` | `s.split('-',1)[0]` | parent (the engine) | — |

> **⚠️ Phase 3.5 re-migrates the 4 Phase-2 backend consumers.** They read `resolve_parent` as "the room" — true only while `parent_id` is the flat first-segment. When Phase 3.5 flips `parent_id` to the *immediate* parent, `get_room_from_location` (logic.py:798) moves to `resolve_room`, and the `perform_smart_eject` bypass (logic.py:900) + `_build_location_match` (spoolman_api.py:1238/1246) + `get_spools_at_location_strict` (spoolman_api.py:1351) move to `is_descendant`. See the Phase 3.5 section for the de-risking strategy.

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

> **✅ SHIPPED TO PROD 2026-06-03** (dev `feature/l271-phase-3` → `main` 31bdd3c, deployed via the TrueNAS update cron; verified via the share — CORE1 now `Type:"Printer"`, XL row landed, migration `.bak` written, 0 dup/blank). Implemented as `migrate_printers_to_rows_if_needed` (locations_db) + the printer-half retirement of the synthesizer. **Scope was trimmed by Derek's decisions:** (a) Core One stays **dual-role** — promoted in place to `Type:"Printer"`, spools stay at `CORE1`, no Spoolman migration; extensible to N toolheads for the INDX upgrade. (b) Printers stay **top-level roots** (`parent_id=None`) — true **room-nesting was deferred to a new Phase 3.5** because the tree is currently flat 2-level and nesting requires a full multi-level renderer (recorded rooms: XL→`LR`, Core One→`CR`; plus a wanted "pin printers to top" option). (c) `model`/`mmu_attached` → Phase 4; orphan-`parent_id` validation → Phase 5 (would noise on PM/PJ/TST). The duplicate/blank-Type CORE1 corruption is auto-repaired by the migration. Verified: `/api/locations` byte-identical except the intended CORE1 fix; idempotent; visual baseline refreshed; 127 tests. **Prod step below is still required.**

**Goal:** persist what [app.py:1452-1488](../../../inventory-hub/app.py#L1452) currently conjures at runtime.

**Steps:**
1. **Migration** (`migrate_printers_to_rows_if_needed`, startup, timestamped backup like Phase 1A): for each distinct printer in `config.json:printer_map`, write a `Type:"Printer"` row to `locations.json` with `LocationID` = the printer key, `Name` = `printer_map[...].printer_name` (owns the emoji), `parent_id` = its room (resolved from a toolhead's room), `model`/`mmu_attached` best-effort. Idempotent: skip if the Printer row already exists.
2. Add `"Printer"` to the required-Type list in `_required_keys_for`.
3. Migrate the 3 `app.py` synthesizer consumers + [inv_loc_mgr.js:358](../../../inventory-hub/static/js/modules/inv_loc_mgr.js#L358) to read the on-disk Printer rows (Type + parent_id) instead of prefix-grouping. **Retire the runtime synthesizer.**
4. Tighten validation: every non-null `parent_id` must point to a real on-disk row (warn-don't-crash on orphans, log them).
5. **Color Loadout hook:** `target_printer` now anchors to `Printer.LocationID` (stable) instead of the synthesized display name.

**Tests:** `test_locations_json_integrity.py` extended for the Printer Type; `test_printer_status_widget.py` must stay green (it consumes the synthesized printers today); a migration test (dirty printer_map → Printer rows on disk, idempotent on 2nd boot). **Full live E2E** — the dashboard printer status + Location Manager grouping are the highest-traffic consumers.
**Prod:** ⚠️ run the migration on prod `locations.json`. Back up `\\TRUENAS\App_Data\InventoryHub\locations.json` first. The startup migration handles it, but verify the prod render after deploy.

### Phase 3.5 — True multi-level nesting (HIGH risk — touches the eject + location-query paths) — IN PROGRESS

> **Carved out of Phase 3** (Derek 2026-06-03: "first-class Printers now, nest later"). Phase 3 left printers as top-level roots (`parent_id=None`) and the tree as a **flat 2-level** model (every row sits at one indent under its first-segment root). Phase 3.5 makes the hierarchy *genuinely nested* — `parent_id` becomes each row's **immediate** parent (room→printer→toolhead, cart→rows, …) — and rebuilds the renderer + occupancy + the room/child backend resolvers to walk that multi-level tree.

**Decisions (Derek 2026-06-03, via AskUserQuestion):**
1. **Nesting depth → FULL immediate-parent.** Re-derive *every* row to its immediate parent (room→printer→toolhead AND cart→cart-rows, etc.), not printers-only.
2. **"Pin printers to top" → a TOGGLE that lifts printers to a pinned top group.** ON = printers (+ their toolheads) float to a pinned group at the very top for quick access; OFF (default) = printers nest under their room. Persisted in `localStorage` (`fcc.locMgr.pinPrintersTop`) per the pre-Config-system preference convention.
3. **Room occupancy → TRANSITIVE.** A room's "X Total" includes ALL descendants transitively (incl. the nested printer's toolhead spools). This is also *required* to avoid a regression: once cart-rows re-parent to carts, the old single-level rollup would drop them from the room total (verified: CR "89 Total" today == sum of every CR descendant + 5 floating).

**The consequence the original plan under-scoped — 4 backend consumers break under immediate-parent `parent_id`.** Phase 2 migrated these to `resolve_parent`, which today returns the ROOM only because `parent_id` is the flat first-segment. Once `parent_id` is the *immediate* parent, `resolve_parent(CR-CT-1-R1)` returns `CR-CT-1` (the cart), not `CR` (the room) — so all four must walk the chain instead:

| File:Line | Symbol | Needs | Why it breaks on flat→immediate |
|-----------|--------|-------|----------------------------------|
| [logic.py:798](../../../inventory-hub/logic.py#L798) | `get_room_from_location` | `resolve_room` (walk to top-level room) | returns the cart, not the room → eject relocates a cart-row spool to the cart |
| [logic.py:900](../../../inventory-hub/logic.py#L900) | `perform_smart_eject` bypass | `is_descendant` | only direct children match → eject-loop guard stops firing for grandchildren |
| [spoolman_api.py:1238/1246](../../../inventory-hub/spoolman_api.py#L1238) | `_build_location_match` | `is_descendant` | a room query misses spools in cart-rows (dashboard / printer status / grids) |
| [spoolman_api.py:1351](../../../inventory-hub/spoolman_api.py#L1351) | `get_spools_at_location_strict` | `is_descendant` | the printer_map-removal safety guard under-counts |

**De-risking strategy (the Phase 2 method, reused):** land the hierarchy-walk helpers + migrate each consumer **proving byte-identical behavior on the current flat tree FIRST** (where room == immediate parent, so `resolve_room`/`is_descendant` reduce to the old equality), one commit each. THEN flip the data — the same helpers are correct in the nested world (`resolve_room(CR-CT-1-R1)`: CR-CT-1-R1→CR-CT-1→CR→None = CR ✓; `is_descendant(CR-CT-1-R1, CR)` walks the chain ✓). A defect can't hide: the A/B pins identity pre-flip; the live container verifies post-flip.

**Steps (one commit each, verified against the live :7913 / 238-spool container):**
1. **Helpers** — `resolve_room(row_or_id, loc_list)` (walk `parent_id` up to the top-level room, skipping the `TST/TEST/PM/PJ` pseudo-prefixes; cycle-guarded) and `is_descendant(child, ancestor, loc_list)` (walk up; cycle-guarded) in [locations_db.py](../../../inventory-hub/locations_db.py). Pure additive; no consumer reads them yet.
2. **Migrate `get_room_from_location`** → `resolve_room` (logic.py). A/B identical on current tree.
3. **Migrate `perform_smart_eject` bypass** → `is_descendant` (logic.py). ⚠️ fragile eject path — test with a real ghost-trail spool on the live container.
4. **Migrate `_build_location_match` + `get_spools_at_location_strict`** → `is_descendant` (spoolman_api.py). ⚠️ feeds dashboard/printer-status/grids — A/B counts on the live container.
5. **Data migration** `migrate_immediate_parent_ids_if_needed(loc_list, printer_map)` (locations_db, startup, timestamped backup like Phase 1A):
   - **Immediate parent** = the longest LocationID prefix (strip trailing `-SEGMENT` repeatedly) that matches an existing on-disk row; fall back to `derive_parent_id_from_prefix` (flat first-segment) when no on-disk ancestor exists — keeps the `PM/PJ/TST` boxes pointing at their (virtual-room) prefix exactly as today.
   - **Printers** (`Type:"Printer"`) → their room: auto-derive from a toolhead child's `Location` field matched to a `Room` row's `Name` (XL toolheads carry "Living Room" → `LR`); fall back to the recorded override map `{XL: LR, CORE1: CR}` for printers with no derivable Location (CORE1 is dual-role with no toolhead children); else `None` + WARN. Validate the resolved room is a real on-disk Room row before assigning.
   - **Idempotency + respect-override rule:** only re-derive a row whose current `parent_id` still equals its OLD default (`derive_parent_id_from_prefix`, i.e. it carries the Phase-1A/2.5 flat value) AND whose target differs. Rows already at their immediate target, or carrying an operator-set value that differs from both, are left alone. This is idempotent (2nd boot = no-op) and never clobbers a deliberate re-parent.
6. **Transitive occupancy** (app.py `/api/locations` synthesizer): replace the single-level `room_occupancy` rollup with a transitive subtree walk (`subtree_total[anc] += count` for every ancestor, skipping `TST/PM/PJ`, cycle-guarded). Switch the "X Total (Y floating)" display from the `"-" not in lid` (dash-free) test to **`has_children(lid)`** (a real parent in the tree) so every parent — room, printer, AND cart — shows its subtree total + floating, while leaves (dryer boxes, drawers, shelves, the dual-role CORE1) show `curr/max` or `n items`. **Expected /api diff** (pin in a test): `CR` 89→**90** (CORE1's 1 spool folds in; CORE1's ghost home PM-DB-5 is pseudo-excluded so no double-count), `CORE1` "1 Total (1 floating)"→**"1/1"** (now a childless leaf under CR), carts gain subtree totals (`CR-CT-1` "3 items"→**"19 Total (3 floating)"**), `DR`/`XL`/PM/PJ/TST unchanged. **`LR` stays 7** (NOT 9) — review fix #2: a spool deployed at XL-1/XL-4 is the SAME physical spool already counted via its ghost home-box LR-MDB-1/2, so the room total dedups by spool id rather than summing the toolhead copy + the ghost copy.
7. **Multi-level renderer** ([inv_core.js](../../../inventory-hub/static/js/modules/inv_core.js) `_renderLocationsPayload`, tree branch — only when `sortBy==='LocationID'`): build a `parent_id`→children map (case-insensitive); DFS render with depth-based indent; **nested collapse** via a `state.locCollapsed` set + a per-row ancestor chain (`data-ancestors`) so collapsing a room hides its printer AND toolheads, and re-expanding restores each node's own collapsed state; migrate `hasChildren` (564/593) OFF `startsWith` ONTO the parent_id child-map (now safe — hierarchy is genuinely nested). **Pin toggle** in the Location Manager header (`modals_loc_mgr.html`): when ON, render printer subtrees first under a "★ Printers" divider and drop them from their room's children. Register the toggle's keyboard story via `window.registerShortcut` if it gets a hotkey.
8. **Tests + visual baseline:** migration unit tests (immediate-parent algorithm, printer-room derivation, idempotency, override-respect, PM/PJ/TST fallback), transitive-occupancy A/B, `resolve_room`/`is_descendant` unit tests, a `test_l271_phase35_*` pin/tree-render test, and a **fresh visual baseline** for the nested tree (`UPDATE_VISUAL_BASELINES=1`). `test_l271_phase2_consumers.py` + `test_l271_location_tree_render.py` must stay green.
**Adversarial review (2026-06-04, 26-agent workflow → 17 confirmed findings).** The implementation as first written had real bugs the review caught; all HIGH + MEDIUM are FIXED on the branch (commits `fix(L271-P3.5 review): …`):
- **#1/#5/#9 (HIGH) — destructive blast radius.** Switching the `get_spools_at_location` matchers to transitive `is_descendant` meant a room-level clear/delete swept (and unmounted) actively-printing toolhead spools (active-print guard bypassed — a room isn't in `printer_map`), a cart delete cascaded to its rows, and audit/scan silently became whole-subtree. **Fix:** location queries match by the **location STRING** (flat first-segment, `derive_parent_id_from_prefix`), deliberately distinct from the nested `parent_id` tree (which drives render / occupancy / room resolution). Restores EXACT pre-3.5 query scope (room→cart-rows but not toolheads; cart direct-only); verified byte-identical across all 54 live locations.
- **#2 (HIGH) — room total double-count.** A deployed spool is in `occupancy_map` twice (toolhead loc + ghost home-box); both now rolled into the same room. **Fix:** the rollup counts DISTINCT spool ids per ancestor. Live LR "9 Total"→"7 Total" (= the true distinct count).
- **#3/#8 (HIGH/MED) — stored XSS + space-delimited collapse.** **Fix:** `escHtml` on every interpolated LocationID/Name/Type; `data-ancestors` JSON-encoded (survives space-containing ids); toggle + QR delegated off data attributes (no inline onclick carrying a raw id).
- **#4/#6 (HIGH/MED) — edit un-nests printers / orphans.** **Fix:** `api_save_location` preserves `parent_id` on an in-place edit (only create/rename re-derives); the printer migration branch leaves `parent_id` unchanged when the room is unresolvable (no dashed-printer orphan-to-None).
- **#7/#10 (MED) — test gaps.** **Fix:** replaced the tautological occupancy-consistency test with an independent distinct-spool oracle; added pure-function tests for `ancestors_of` / `immediate_parent_for` + the #4/#6 cases.
- **#15/#16 (LOW) — FIXED:** prune `state.locCollapsed` to live parents each render; disable + grey the Pin-Printers button outside the LocationID sort.
- **DEFERRED LOW (documented, not fixed — low impact, atypical triggers):** **#11** `perform_smart_eject` rebuilds the parent_map per call (redundant disk I/O on a small file; correctness unaffected); **#12** the migration can't distinguish an operator-chosen top-level printer (`parent_id:null`) from the default-null (nesting printers IS the phase's intent; no current operator wants a top-level printer); **#13** auto-derived printer room beats the override on a stale toolhead `Location` (prod-safe today; logs only INFO — consider WARN on divergence); **#14** the Phase-3/Phase-3.5 startup blocks each reload from disk, so a failed Phase-3 save yields a one-boot carts-nested/printers-not split-brain (self-healing next boot; can't trigger on the upcoming deploy since prod already has Phase 3); **#17** pin-ON + collapse-room leaves pinned printers visible while the room Total still counts them (non-destructive display nuance; arguably intended).

**Prod:** ⚠️ same as Phase 3 — back up `\\TRUENAS\App_Data\InventoryHub\locations.json`; the startup migration re-derives parent_ids + sets printer rooms; verify the prod render (nesting + room totals) after deploy.

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

#### Phase 5 scope ADDITIONS — Edit-UI + shelf nesting (Derek 2026-06-04, after 3.5 hit prod)

> **Unifying theme:** today the hierarchy is *implicit in the LocationID string* — `parent_id` is **derived from the dash-prefix at save time** (`api_save_location` → `immediate_parent_for`; the edit modal sends only ID/Name/Type/Max, never `parent_id`) and is **never shown or editable**. Phase 5 flips this: `parent_id` becomes the **explicit, visible, editable** source of truth and the ID becomes just a label. Derek's three observations below are all symptoms of the implicit model; they're the UI/data-model slice of Phase 5 and should be scoped together here.

1. **Explicit Parent selector + show `parent_id` in the Edit Location modal** (folds observations *(a)* + *(c)* into one). Today `modals_loc_mgr.html#locModal` shows only ID / Name / Type / Max Spools. Add: (i) a read-out of the current `parent_id` + ancestor breadcrumb (the DB-structure visibility Derek wants), and (ii) an editable **Parent** dropdown (valid parents grouped by kind: Room → Printer → Cart → …) that SENDS `parent_id` on save. The migrations already "respect operator-set `parent_id`" (3.5 review fix #4 only re-derives rows still at the default), so an explicit editor is safe with the existing logic. This is effectively the first real slice of "explicit parent_id".
2. **Add `"Printer"` to the Type dropdown** *(observation (a), 2nd half)*. Phase 3 made printers first-class rows but `edit-type` was never updated — its options are Storage / Dryer Box / Shelf / Room / Cart / Tool Head / MMU Slot / Virtual Room, **no Printer**. Add it (and reconcile with Phase-4 toolheads[] ownership — hand-creating a Printer shouldn't fight the printer_map fold).
3. **Real intermediate Wall/Row rows for shelf nesting** *(observation (b) — DECISION: REAL ROWS, Derek 2026-06-04).* Shelf sections (`CR-WLN-R1-SC1`…) sit **flat under the room** because the wall (`WLN`) and row (`R1`/`R2`) levels live ONLY in the ID string — no node exists, so `immediate_parent_for` parents each section to the longest *real-row* prefix = `CR`. Fix: a migration that **creates the intermediate Wall + Row rows** (e.g. `CR-WLN` "Computer Room Wall North", `CR-WLN-R1` "… Row 1") so the tree nests Room → Wall → Row → Section. **Open scope-time question:** reuse the existing `Shelf` Type for the grouping nodes vs. add a `Zone`/`Wall`/`Row` grouping Type. **Reference data = PROD** (8 Shelf rows: `CR-WLN-R1/R2-SC1–4`; dev only seeded R1×4 — a thin seed). The renderer + transitive occupancy already handle arbitrary depth (3.5), so this is mostly a data-migration + Type decision, not a renderer change.
4. **Prod data cleanup (trivial):** `CR-WLN-R2-SC3`'s *Name* reads "…Row 2 Section **1**" (copy-paste typo; the ID is correct). Fix the friendly name during the shelf-nesting pass.

**Note (Derek 2026-06-04):** do NOT implement these now — they're parked for Phase 5 where they're actively scoped. Captured here so nothing is lost.

> **✅ SHIPPED TO DEV 2026-06-04** (branch `feature/l271-phase-5`, off the post-Group-20 `main` 9650106; commit 5413eb8). The three scope-additions are done; the **original** Phase-5 prefix-retirement (steps 1-3 above: delete `derive_parent_id_from_prefix` + the `resolve_parent` fallback, zero-`split('-')[0]` grep gate, write-time orphan rejection) is a **separate later slice** and was deliberately NOT touched — these additions are its groundwork.
> **Decisions (Derek 2026-06-04, AskUserQuestion):** (1) **NEW `Wall` + `Row` grouping Types** (not reuse-`Shelf`) — distinct badges + lets the wizard exclude structural nodes from spool-assignment (the leaf Sections stay `Type:"Shelf"` and still hold spools). (2) Type dropdown gained **`Printer` + `No MMU Direct Load`** (the latter fixes the same silent-Type-rewrite latent bug for the real `CORE1-M0` row). (3) Group 20 was **released to `main` first** (9650106) so Phase 5 branched off a complete tree.
> **What shipped:** (a) `#edit-parent` <select> (optgroup-by-kind, excludes self+descendants) + `#edit-parent-breadcrumb` ancestry readout; `saveLocation` sends `parent_id` (Auto → omit/derive-preserve, Top-level → explicit null, else the chosen id) and surfaces save errors; `openAddModal` now resets `#edit-type` (latent bug). Backend: `api_save_location` validates an explicit `parent_id` (must be a real row or a PM/PJ/TST pseudo-prefix; rejects self + descendant cycles via `is_descendant`) → 400 + error body. (b) Wall/Row badges (`inv_core.js`/`inv_loc_mgr.js`), wizard exclusion (`inv_wizard.js`). (c) `locations_db.migrate_shelf_grouping_rows_if_needed` — generic (derives Wall/Row ids + Names from each shelf's segments/Name; `_name_before_token` truncation is typo-robust), self-contained (sets section `parent_id` itself → a fixpoint for the 3.5 pass), idempotent, respects operator overrides; wired at startup after the Phase-3.5 block with a `pre-wall-row-synthesis-migration-{stamp}.bak`.
> **Verified:** dev nests **Room → Wall → Row → Shelf** (CR → CR-WLN → CR-WLN-R1 → SC1..4; "24 Total" transitive rollup; Names "Computer Room Wall North" / "… Row 1"); Parent selector + breadcrumb render; validation rejects nonexistent/self/descendant parents (live). Tests: `tests/test_l271_phase5.py` (325 unit + 5 live integration green); broad locations regression 320 green; visual baseline still within 1% (no recapture needed). **The prod `CR-WLN-R2-SC3` Name typo ("Section 1") is fixed during the prod deploy** (a direct friendly-name edit — dev has no R2 row). **Prod:** the startup migration synthesizes CR-WLN + CR-WLN-R1 + CR-WLN-R2 and nests all 8 sections; back up locations.json first; verify nesting + the typo fix after deploy.

---

## 5. Sequencing, dependencies, and effort

```
1A ✅ → 1B ✅ → 2 ✅ → 2.5 ✅ → 3 ✅* → [3.5] → [4 **] → [5]
                                   ↑                ↑
                        unblocks Color         dissolves Group 20
                           Loadout             (20.1/20.2/20.3)
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

# L298 — Bulk Moves: Phased Plan & Design Decisions

> **Status:** SCOPING (2026-07-07). Research complete (6-agent workflow, all claims file:line-grounded). No code yet — this doc + the design decisions below gate the build.
> **Feature:** "Scan Box A (source) and Shelf B (destination), then *move EVERYTHING from Box A to Shelf B*." (Feature-Buglist.md "🔄 Bulk Moves"; working-groups L298, UNBLOCKED 2026-06-04 once the L271 data model shipped.)

## TL;DR — the engine already exists

`logic.perform_smart_move(target, raw_spools, target_slot=None, origin='', auto_deploy=True, confirm_active_print=False)` ([logic.py:335](../../../inventory-hub/logic.py#L335) → `_perform_smart_move_impl` [:371](../../../inventory-hub/logic.py#L371)) **already accepts a location string in `raw_spools` and expands it to every spool there** ([logic.py:399-406](../../../inventory-hub/logic.py#L399)) via `spoolman_api.get_spools_at_location`. So:

```python
perform_smart_move("SHELF-B", ["PM-DB-XL-L"])   # moves everything at PM-DB-XL-L → SHELF-B, ONE undo record
```

already works, and per-spool it does read-merge-write of `extra` (sibling-wipe-safe), single-occupancy auto-eject, `container_slot`/`physical_source` ghost trails, auto-deploy, active-print DEST guard, per-spool Activity-Log lines, and `LAST_SPOOLMAN_ERROR` surfacing. **Bulk Moves must delegate to it, never hand-roll spool writes** (that path is the root of the 2026-04-26/27 prod outages — CLAUDE.md "Spool / Filament write surfaces").

**What's missing is the wrapper, not the mover:** (1) a source→dest *initiation* flow, (2) a pre-flight that resolves the source set + checks capacity + skips the right classes, (3) a preview/confirm step, (4) an honest per-spool tally + aggregate feedback, and (5) safety guards the single-move path does NOT have (capacity, source-side active-print, self/descendant).

## What already exists (reuse map)

| Need | Reuse | Ref |
|---|---|---|
| The actual move | `perform_smart_move(dest, [source_loc])` — one call, one undo record | [logic.py:335](../../../inventory-hub/logic.py#L335), [:399-406](../../../inventory-hub/logic.py#L399) |
| Enumerate "everything in A" | `get_spools_at_location_detailed(A)` (id + slot + is_ghost + archived) | [spoolman_api.py:1360](../../../inventory-hub/spoolman_api.py#L1360) |
| "Operate on a whole location" precedent | `clear_location` — skips ghosts + slotted, reports `skipped_slotted[]` | [routes_scan.py:232-279](../../../inventory-hub/routes_scan.py#L232) |
| Two-location scan flow | **Audit mode** (scan source → hold in session → CMD:DONE/CANCEL) — near-isomorphic | [logic.py:1073](../../../inventory-hub/logic.py#L1073), [inv_cmd.js:370](../../../inventory-hub/static/js/modules/inv_cmd.js#L370) |
| Multi-state deck QR | `registerShapeshiftQR` — its own comment names Bulk Moves as the intended reuse | [inv_cmd.js:159-214](../../../inventory-hub/static/js/modules/inv_cmd.js#L159) |
| Free-slot arithmetic | `{1..maxSlots} − occupied` inside `perform_smart_move` | [logic.py:436-467](../../../inventory-hub/logic.py#L436) |
| Multi-location one-fetch bucket | `bucket_spools_by_location` (for the preview) | [spoolman_api.py:1423](../../../inventory-hub/spoolman_api.py#L1423) |
| Preview / confirm UI | audit panel `openAuditPanel` + Quick-Swap confirm + `attachConfirmQRs` | [inv_cmd.js:370](../../../inventory-hub/static/js/modules/inv_cmd.js#L370), [inv_quickswap.js](../../../inventory-hub/static/js/modules/inv_quickswap.js) |
| Active-print confirm contract | `{status:'requires_confirm', confirm_type:'active_print'}` → mountOverlay → retry with flag | [logic.py:418-434](../../../inventory-hub/logic.py#L418) |
| Self/descendant guard | `locations_db.is_descendant` (exists, NOT wired into moves today) | [locations_db.py:430](../../../inventory-hub/locations_db.py#L430) |

## Design decisions (the forks) — ✅ ALL DECIDED 2026-07-07 (Derek)

| # | Fork | **Decision** |
|---|------|--------------|
| D1 | Initiation | **BOTH** — `CMD:BULKMOVE` scan mode **and** a Location-Manager "Move all → " button |
| D2 | Nested source scope | **FLAT / non-recursive** (safe; won't sweep a nested printer's live toolhead) |
| D3 | Capacity overflow (bounded dest) | **BLOCK + report** (unbounded Room/Shelf/Cart = no cap) |
| D4 | Undo | **HARDEN undo first** (Phase 0) — snapshot + restore the system-managed extras |

**D1 — Initiation pattern (BOTH).** Ship two entries to the same backend + preview:
- **`CMD:BULKMOVE` deck-QR mode**, cloning audit: a shapeshift QR cycles idle → *scan source* → *scan dest* → *commit*, with a server session (`BULK_MOVE_SESSION`, mirror `AUDIT_SESSION` + its idle-watchdog). Fully scanner-driven; `registerShapeshiftQR` was built for exactly this.
- **A Location-Manager "Move all → …" button** that arms a destination scan (parallels `triggerEjectAll`) — mouse entry.
- (Rejected: reusing the buffer — collides with today's empty-buffer location-scan semantics.)

**D2 — Source scope (FLAT).** Reuse the deliberately **flat/first-segment** enumeration ([spoolman_api.py:1294-1321](../../../inventory-hub/spoolman_api.py#L1294)) — a Room reaches its cart-rows but NOT a nested printer's toolheads. Safe: a bulk move can't accidentally sweep an actively-printing nested toolhead. (A recursive subtree opt-in can be a later v2 with per-toolhead active-print guards re-added.)

**D3 — Capacity overflow (BLOCK + report).** Unbounded destinations (Room/Shelf/Cart, `Max Spools` 0/blank) = no cap. **Bounded** destinations (Dryer Box slots): if source movable count > free slots, **block the whole batch** with a clear message ("SHELF-B has 2 free of 4; source has 5 — nothing moved"). This is a NEW pre-flight (no move path guards capacity today).

**D4 — Undo (HARDEN first, Phase 0).** `perform_undo` today restores **only `location`**, NOT the `SYSTEM_MANAGED_EXTRAS` — [logic.py:1029-1030](../../../inventory-hub/logic.py#L1029). Phase 0 upgrades the undo record to snapshot the per-spool `extra` (≥ `container_slot` / `physical_source` / `physical_source_slot`) at move time ([logic.py:482](../../../inventory-hub/logic.py#L482)) and restore it ([:1029](../../../inventory-hub/logic.py#L1029)), so a bulk undo is a **true rollback** (spools return to their exact slot + ghost state). Also improves every single-move undo; fills the stubbed `test_missing_ghost_cleanup_on_undo`.

**Decisions with a safe default (stated, not blocking — flag if you disagree):**
- **Single-occupancy destination** (Tool Head / MMU Slot / Printer): **reject** the bulk move (auto-eject would chain-unseat every spool but the last — [logic.py:484-499](../../../inventory-hub/logic.py#L484)).
- **Slotted destination (Dryer Box):** land **slotless/staging** (inherits the deliberate bulk-slotless design [logic.py:436-441](../../../inventory-hub/logic.py#L436); auto-slot-fill + auto-deploy is new logic, defer to v2).
- **Skip classes** (mirror `clear_location`, report as "left in place"): deployed **ghosts** (`is_ghost`), **slotted/loaded** toolhead/MMU feeds, **archived** (invisible to the sweep anyway), and **buffered** held spools.
- **Source-side active-print:** add a pre-flight (single-move only guards the DEST) so a bulk move can't yank a spool off a live toolhead unprompted.
- **Self/descendant:** reject target == source or target a descendant of source.
- **Preview/confirm required:** "N will move → DEST, K skipped (reason)" + one Commit/Cancel, per Derek's established audit-panel/cancel-review pattern.
- **Fail-closed enumeration:** use the `_strict` reader so a transient Spoolman outage doesn't make the source look empty (a silent no-op).

## Phased build plan

- **Phase 0 (if D4=b) — Undo hardening.** Snapshot per-spool `extra` (≥ the 3 SYSTEM_MANAGED_EXTRAS) into the undo record; restore them in `perform_undo`. Fill the stubbed `test_missing_ghost_cleanup_on_undo` ([test_logic_undo.py:123](../../../inventory-hub/tests/test_logic_undo.py#L123)). Benefits single moves too.
- **Phase 1 — Backend endpoint.** `POST /api/bulk_move {source, dest, confirm_active_print?}` in `routes_scan.py` (or `routes_locations.py`): resolve source via `get_spools_at_location_detailed` (fail-closed), apply the skip rules, run the capacity + single-occupancy + self/descendant + source-active-print pre-flights, then **one `perform_smart_move(dest, [movable_ids], confirm_active_print=...)`**, and return an honest `{moved, skipped:[{id,reason}], failed:[{id,err}], requires_confirm?}` tally. Pin with unit tests (mirror `clear_location` + `test_auto_slot_pick`).
- **Phase 2 — Scan/mode wiring (D1).** `CMD:BULKMOVE` in `resolve_scan` + `api_identify_scan` + `inv_cmd.js:processScan`; `BULK_MOVE_SESSION` in `state.py` with an idle-watchdog; `registerShapeshiftQR` deck slot (idle → source → dest → commit); a `/api/bulk_move_session` poll like `/api/audit_session`. (+ optional Location-Manager button.)
- **Phase 3 — Preview/confirm UI.** A `mountOverlay` panel (audit-panel shape): stats header, "Will move" / "Skipped (reason)" tile sections (reuse `_renderTile`), Commit/Cancel as button+QR pairs; active-print `requires_confirm` surfaced as one batch confirm.
- **Phase 4 — Feedback + edge hardening + full test sweep.** Per-spool INFO lines come free from `perform_smart_move`; add one aggregate summary line (`🔀 Bulk move A → B: moved N, skipped K, failed J`) + one typed toast (success if J==0 else warning/error ≥7s). Register a keyboard shortcut. Adversarial review + `RUN_INTEGRATION` sweep.

## Risks to respect (from the safety audit)
Sibling-wipe on `extra` (delegate to `perform_smart_move`, never inline-PATCH); ghost double-listing (a deployed spool shows in both its toolhead AND home box — skip ghosts); source-side active-print gap (DEST-only guard today); partial-failure-reports-success (`perform_smart_move` returns bare `{status:success}` even if 3/8 rejected — collect a per-spool tally); dryer `slot_targets` dangling (moving OUT of a bound box leaves the box feeding a toolhead with nothing — flag/clear); O(N) printer probes (a printer-adjacent bulk commit can be slow — the L3 latency memo; consider async + progress); global-session hijack (a second tab / stale session — needs the audit idle-watchdog + CMD:CANCEL bail).

## Prior art / alignment
No prior Bulk-Moves design note existed. Align the source/dest **picker** with the pending sub-location-add redesign (both are "pick a location in the tree"). The Project Color Loadout "Scrap-Buster" spool-eligibility loop (`docs/Project-Color-Loadout/api_flow.md:45-53`) is the closest "operate on a filtered spool set across locations" logic — reuse its skipped-because reasoning shape for the "K skipped" tally. Loadout is a separate SQLite add-on, not the Spoolman move path.

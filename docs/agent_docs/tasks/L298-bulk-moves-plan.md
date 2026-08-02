# L298 — Bulk Moves: Phased Plan & Design Decisions

> **Status:** 🚧 IN PROGRESS — **Phase 0 (undo-hardening) + Phase 1 (backend `POST /api/bulk_move`) DONE** on branch `feature/bulk-moves-l298-p1` (2026-07-11). Phases 2–4 remain. See the 🚀 HANDOFF block below for exactly where to pick up.
> **Feature:** "Scan Box A (source) and Shelf B (destination), then *move EVERYTHING from Box A to Shelf B*." (Feature-Buglist.md "🔄 Bulk Moves"; working-groups L298, UNBLOCKED 2026-06-04 once the L271 data model shipped.)

## 🚀 HANDOFF — where the next chat picks up (2026-07-11, Phase 1 complete)

**Git / branch state:**
- **Phase 1 is committed on `feature/bulk-moves-l298-p1`** (branched off `dev` `472e013`), NOT yet merged to `dev`:
  - `f45afe9` — **undo wire-sanitization hotfix** (see the ⚠️ note below; a Phase-0 regression caught live).
  - `96f87bc` — **the `POST /api/bulk_move` endpoint** + `get_spools_at_location_detailed_strict` + 24 tests + route pin.
- **Not merged to `dev` yet** — Phase 1 is backend-only (no UI entry). Options: keep stacking Phases 2–4 on this branch, or merge Phase 1 to `dev` first (backend is inert without a caller, so either is safe). Nothing on `main`/prod (pre-existing prod-pull backlog; one `dev→main` release ships everything).
- **⚠️ Unstaged `Feature-Buglist.md` note** (Group 34 finicky auto-IDs, Derek's voice) was present in the working tree during Phase 1 — deliberately left UNSTAGED/untouched; it belongs to Group 34, not this branch.

**✅ Phase 0 DONE:** `perform_smart_move` snapshots pre-move system-managed extras into `undo_record['extras']`; `perform_undo` restores them → a bulk/single undo is a TRUE rollback (exact slot + ghost trail, siblings preserved, legacy records restore location-only).

**⚠️ Phase-1 UNDO HOTFIX (`f45afe9`) — read this:** Phase 0's undo added `extra` to a RAW `requests.patch` in `perform_undo`, sending the empties unwrapped (`''` not `'""'`). Spoolman `400`s the WHOLE PATCH (location included) → **every undo silently no-op'd while reporting success.** The mock-only Phase-0 tests couldn't see the wire-format rejection; caught only by live verification. Fixed by routing `perform_undo`'s spool-restore + ejection-revert through `spoolman_api.update_spool` (sanitize + read-merge-write + surfaces `LAST_SPOOLMAN_ERROR`). New pin `test_undo_extra_payload_reaches_spoolman_wire_sanitized` runs the REAL `update_spool` (mocks only HTTP) and asserts every wire extra is valid JSON. **Lesson: verify undo/move write paths against the LIVE container, not just mocks.**

**✅ Phase 1 DONE — `POST /api/bulk_move` in `routes_scan.py` (`api_bulk_move`):** `{source, dest, confirm_active_print?}` →
1. fail-closed source resolve via new `spoolman_api.get_spools_at_location_detailed_strict` (raises on outage);
2. skip classes (ghost/archived/buffered/toolhead-loaded — the D2 flat-scope Printer-source guard), reported as `skipped:[{id,reason}]`;
3. pre-flights: unknown-dest reject (dest must be in `loc_info_map`) · self/descendant (`is_descendant`) · single-occupancy dest · capacity (D3, fail-closed occupancy read) · source-side active-print;
4. ONE `perform_smart_move(dest, movable_ids, origin='bulk_move', auto_deploy=False, confirm_active_print=…)` — **`auto_deploy=False`** (bulk = relocate/park, not load-onto-printer; also sidesteps the auto-deploy chain's swallowed-confirm/false-log quirk). **⚠️ DECISION TO CONFIRM: is `auto_deploy=False` right, or should a bulk-into-a-bound-dryer-slot deploy onto the toolhead?**
5. honest tally via source readback, reconciled against dest (FLAT-vs-TREE fix) → `{success, moved, moved_ids, skipped, failed}`.
- Adversarially reviewed (Workflow, runtime-topology lens): 23 raw → 4 confirmed → all fixed (dest-existence, buffer-id guard, readback scope, auto_deploy). Live-verified on `localhost:8000`; full offline sweep **2178 passed / 38 skipped / 0 failed**.

**✅ Phase 2 DONE (2026-08-01) — `4b0e0fe` backend + `7fa990b` frontend.**
- **`BULK_MOVE_SESSION`** in `state.py` (idle → awaiting_source → awaiting_dest → preview), cloning `AUDIT_SESSION`'s in-place-mutation discipline + a lazy idle watchdog.
- **Shared core extracted:** `logic.plan_bulk_move()` (dry run — fail-closed source resolve, skip rules, every pre-flight, NO writes) + `logic.execute_bulk_move()` (one `perform_smart_move` + readback tally). **Phase 1's `/api/bulk_move` is now a thin shell over the same core**, so the preview a user confirms is computed by the SAME code that guards the commit. Phase 1's 27 tests passed unchanged = the behavior-preservation proof.
- **Entries (D1 = both):** `CMD:BULKMOVE` deck QR (4-state `registerShapeshiftQR`: BULK MOVE → SCAN SRC → SCAN DEST → COMMIT) and the LM **"Move all →"** button (in `updateManageTitle`, so it renders for every location type — `renderList`'s eject-all target doesn't exist in the live template; suppressed on single-occupancy rows).
- **Routes:** `GET /api/bulk_move_session` (panel poll) + `POST /api/bulk_move_session` (start/set_dest/commit/cancel); `bulk_move_active` + `bulk_move_stage` on `/api/logs`.
- **🔒 Safety invariants:** scanning a DESTINATION **never auto-commits** (stages a preview, waits for explicit CMD:DONE / button); **commit RE-PLANS against live state** (never trusts the stored preview); audit ↔ bulk-move are **mutually exclusive**; a non-blocking lock refuses a **re-entrant commit**; `start` refuses to **silently replace** an armed session.
- Adversarial review: 55 raw → 12 confirmed → 7 distinct, **all fixed** (incl. two HIGHs: partial-failure-reports-success, and the deck tile painting `idle` over a live session which made the button a disguised Cancel). 32 session tests. Full sweep **2210 / 0**. Live-verified: arm → source → dest → preview (no move) → commit → undo.

**✅ Review debt CLEARED (2026-08-02).** The first Phase-2 review lost 17/61 agents to a token limit. Rather than re-run it, all **55** findings were re-verified **against the POST-FIX code** by a **5-agent batched** workflow (`wf_2d9c077c-aae`) — 14 findings per agent, agents reading their slice from disk. Result: 31 still live, of which **11 were fixed immediately**:
- **scan-buffer deadlock (HIGH)** — every session-routed scan answers `cmd:'clear'`; with a non-empty buffer that raised "Clear entire Buffer?" on `#confirmModal` (z 1100) *behind* the panel (z 20000), and `state.activeModal='confirm'` then swallowed the destination scan AND `CMD:DONE`. Now: never clear the buffer mid-bulk-move (buffered spools are a documented skip class anyway).
- **`onclick` JS-string interpolation (MED, flagged by 4 independent lenses)** — the LM button built `triggerBulkMove('<LocationID>')` with `escAttr`, which escapes for an HTML *attribute*, not JS source. Now the id rides `data-bulk-src` and the handler reads `this.dataset.bulkSrc`.
- **mouse-path partial-failure toast (MED)** — `commitBulkMove` bailed on `!success`, so 8-of-10 moved toasted a flat "Bulk move failed" and skipped the refresh, while the scan path (already fixed) reported honestly. The two commit paths now agree.
- **blocked plan advanced to `preview` (MED)** — since the stage rides the heartbeat, a refused dest turned the deck tile GREEN "COMMIT" with a `CMD:DONE` QR. Now only a committable plan (`ok` or `require_confirm`) advances.
- **`require_confirm` dropped `movable_ids` (LOW→real)** — the active-print preview showed "0 will move" and DISABLED Commit, making that safety path unreachable from the panel. Fixed + `canCommit` now allows `require_confirm`.
- **Hide tooltip** advertised reopening via the deck button, which actually CANCELS.

**⏳ 17 re-verified findings DEFERRED → [L298-phase2-deferred-findings.md](L298-phase2-deferred-findings.md).** Already verified against current code, so Phase 3 can action them directly. The ones that matter most:
- **MED** cancel racing an in-flight commit reports "nothing moved" while the move proceeds (the commit lock doesn't cover cancel);
- **MED** `commitBulkMove` uses `fetchT`'s 15s abort against an O(N) Spoolman write → a *completed* move can report failure;
- **MED** `bulk_move_session_snapshot` does an unbounded N+1 Spoolman fan-out **every 2s** with no in-flight guard — a natural fix when Phase 3 rewrites the panel;
- **LOW** `/api/dashboard_pulse` omits `bulk_move_active`; no bulk-move Playwright E2E yet (siblings: `test_shapeshift_qr_helper_e2e.py`, `test_audit_visual_panel.py`).

**⏭️ NEXT — Phase 3: rich preview/confirm UI.** Phase 2's panel is deliberately lean (stage prompt, counts, movable/skipped rows, commit+cancel as button AND QR). Phase 3 enriches it: reuse `_renderTile`-style tiles (weight/slot/swatch), group the skipped rows by reason, surface the capacity/block messages inline, and make the active-print `requires_confirm` a proper in-panel confirm rather than a `requestConfirmation` hop.

**Then Phase 4** (unchanged): feedback + edge hardening + full `RUN_INTEGRATION` sweep + a keyboard shortcut. Per-spool INFO lines + the aggregate summary line already land; the typed toast is wired in `commitBulkMove`. **All decisions locked:** D1 = both entries · D2 = FLAT scope · D3 = BLOCK+report · D4 = ✅ · `auto_deploy=False` confirmed by Derek (auto-assigning to toolheads mid-bulk "would just make a mess", and it breaks when the source holds more than the dest can take).

**Build/verify recipe (this repo):** pytest runs on the HOST via `"C:/Python314/python.exe" -m pytest tests/... -p no:cacheprovider -q` (Windows interpreter mismatch — see CLAUDE.md Testing); the live dev container is `http://localhost:8000`; prefix `RUN_INTEGRATION=1` to enable `@pytest.mark.integration` + live-server E2E; `.py`/`.html`/`.js` hot-reload on the dev container (FCC_DEV=1). Cadence held all of Group 34 + Phase 0: **build → adversarial review (Workflow, runtime-topology lens) → verify against the live container → full offline sweep → commit**; repeat per phase.

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

- **Phase 0 — Undo hardening. ✅ DONE 2026-07-11 (`b4a26e8`, on `dev`).** Snapshotted per-spool `extra` (the 3 SYSTEM_MANAGED_EXTRAS) into `undo_record['extras']`; restored via read-merge-write in `perform_undo` (siblings preserved, legacy records back-compat). Filled the stubbed `test_missing_ghost_cleanup_on_undo` + added `test_undo_restores_prior_slot_and_ghost`. Benefits single moves too. 11 undo + 110 blast-radius + full sweep (2150) green.
- **Phase 1 — Backend endpoint. ✅ DONE 2026-07-11 (`96f87bc`, branch `feature/bulk-moves-l298-p1`).** `POST /api/bulk_move` in `routes_scan.py` (`api_bulk_move`): new fail-closed `spoolman_api.get_spools_at_location_detailed_strict`, skip rules, five pre-flights (added unknown-dest reject beyond the plan's four), one `perform_smart_move(dest, movable_ids, auto_deploy=False, …)`, honest readback tally. 24 tests + route pin. Adversarial review (23→4→all fixed). Bundled with the `f45afe9` undo wire-sanitization hotfix (a Phase-0 regression caught live). Full sweep 2178/0.
- **Phase 2 — Scan/mode wiring (D1). ✅ DONE 2026-08-01 (`4b0e0fe` + `7fa990b`).** `BULK_MOVE_SESSION` + idle watchdog; `CMD:BULKMOVE` through `resolve_scan`/`api_identify_scan`/`processScan`; 4-state shapeshift deck slot; `GET`+`POST /api/bulk_move_session`; LM "Move all →" button. Shared `plan_bulk_move`/`execute_bulk_move` core extracted (Phase 1 endpoint refactored onto it). Review 55→12→7 all fixed. Sweep 2210/0.
- **Phase 3 — Preview/confirm UI.** A `mountOverlay` panel (audit-panel shape): stats header, "Will move" / "Skipped (reason)" tile sections (reuse `_renderTile`), Commit/Cancel as button+QR pairs; active-print `requires_confirm` surfaced as one batch confirm.
- **Phase 4 — Feedback + edge hardening + full test sweep.** Per-spool INFO lines come free from `perform_smart_move`; add one aggregate summary line (`🔀 Bulk move A → B: moved N, skipped K, failed J`) + one typed toast (success if J==0 else warning/error ≥7s). Register a keyboard shortcut. Adversarial review + `RUN_INTEGRATION` sweep.

## Risks to respect (from the safety audit)
Sibling-wipe on `extra` (delegate to `perform_smart_move`, never inline-PATCH); ghost double-listing (a deployed spool shows in both its toolhead AND home box — skip ghosts); source-side active-print gap (DEST-only guard today); partial-failure-reports-success (`perform_smart_move` returns bare `{status:success}` even if 3/8 rejected — collect a per-spool tally); dryer `slot_targets` dangling (moving OUT of a bound box leaves the box feeding a toolhead with nothing — flag/clear); O(N) printer probes (a printer-adjacent bulk commit can be slow — the L3 latency memo; consider async + progress); global-session hijack (a second tab / stale session — needs the audit idle-watchdog + CMD:CANCEL bail).

## Prior art / alignment
No prior Bulk-Moves design note existed. Align the source/dest **picker** with the pending sub-location-add redesign (both are "pick a location in the tree"). The Project Color Loadout "Scrap-Buster" spool-eligibility loop (`docs/Project-Color-Loadout/api_flow.md:45-53`) is the closest "operate on a filtered spool set across locations" logic — reuse its skipped-because reasoning shape for the "K skipped" tally. Loadout is a separate SQLite add-on, not the Spoolman move path.

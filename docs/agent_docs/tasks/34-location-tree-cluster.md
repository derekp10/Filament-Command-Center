# Group 34: 🌳 Location-Tree Cluster

**Branch name (when started):** `feature/group-34-location-tree-cluster` (or one sub-branch per phase, merged green before the next — the L271 per-phase pattern; this is a multi-session group).
**Estimated effort:** LARGE / multi-session (~15–25 hrs). Phase 0 ~2–3h · Phase-5 retirement ~4–6h · add-redesign ~8–12h · (Bulk Moves is its own already-scoped build, adjacent).
**Risk:** **MEDIUM–HIGH.** Backend prefix-retirement touches safety-critical spool matchers + boot migrations + a new write-time validation gate; the add-redesign is frontend + a shelf-grouping migration change (prod data). Each phase merges green + verifies against the live container before the next.

> **Status: 🚧 IN PROGRESS (PARTIAL) — Phase 0 + Phase-5 retirement + add-redesign S1–S4 built & verified, on `feature/group-34-location-tree-cluster` → merged to `dev` 2026-07-11.** Graduated from the epic planning sprint ([planning-sprint-epic-grouping.md](planning-sprint-epic-grouping.md)). The three constituent epics each have a full phased plan doc (below); this file is the orchestration brief that sequences them into one group and states the shared Phase 0.
>
> **Progress (2026-07-11):**
> - ✅ **Phase 0 — shared spine** (`55be529`): `location_prefix()` split + all 13 load-bearing callers re-pointed byte-identically; `save_locations_list` newly-introduced-orphan write-guard (own-first-segment keystone; fail-open; Phase-1A/feeder check the save return); `window.buildLocationTree` extracted + render/`_locDescendants`/`_locBreadcrumbChain` re-wired. 13-agent adversarial review (3 findings folded in). Offline 2139 + live 47 green.
> - ✅ **Phase-5 prefix-retirement** (`2b16869`): deleted the `derive_parent_id_from_prefix` alias; scoped grep-gate CI test (`test_prefix_derivation_is_retired`) — no retired name, no bare `split('-')[0]` in backend. `strict` confinement verified already-satisfied (no change). Offline 2140 + live 105 green.
> - ✅ **Sub-location add-redesign S1–S4** (`52990bd`): per-row ➕ Add-child (suppressed on Printer/toolhead/synthetic) + Type/Max inference + auto-gen editable id + `mountOverlay` tree picker over `buildLocationTree` (same save contract, cycle-guarded, host-cascade). 11-agent adversarial review → 2 bugs fixed+pinned (HIGH stored-XSS: `window.escAttr` was never exported; LOW cycle-guard data-source race). Full offline 2150 + live E2E green.
> - ⏸️ **S5 (add-redesign Phase 4) — DEFERRED by Derek 2026-07-11** (see its plan doc): explicit "create missing levels" + demote `migrate_shelf_grouping_rows_if_needed` to legacy backfill. Lowest value-to-risk of the cluster — recursive Add-child already builds any hierarchy, so S5 is convenience + migration-cleanup, and it touches a prod-data boot migration. Revisit deliberately, on its own branch. **🔒 Derek's mandate: S5's build steps MUST begin with a `locations.json` backup — baked into the S5 plan so it isn't forgotten.**
> - ⏭️ **Next build: Bulk Moves (L298)** — adjacent, independent, own plan; not gated on Phase 0.

## The three constituent epics (each has its own plan doc)

| Epic | Plan doc | Role in the group |
|---|---|---|
| **L271 Phase-5 prefix-retirement** | [L271-phase5-prefix-retirement-plan.md](L271-phase5-prefix-retirement-plan.md) | The **backend spine** — retire the hierarchy prefix-parse, make `parent_id` authoritative, add write-time validation. |
| **Sub-location add redesign** | [sub-location-add-redesign-plan.md](sub-location-add-redesign-plan.md) | The **UX layer** — built on the now-authoritative explicit-`parent_id` model. |
| **Bulk Moves (L298)** | [L298-bulk-moves-plan.md](L298-bulk-moves-plan.md) | **Adjacent** (its own already-scoped build, 4 locked decisions). **NOT gated on Phase 0** (corrected 2026-07-07) — the flat matcher exists today; the only link is a forward constraint that Phase-5's retirement keep the matcher flat. Least-coupled of the three; could ship first. |

## Why one group (commonality pass, 2026-07-07)

A grounded 6-reader research workflow **refuted** the sprint's preliminary "build a location-tree PICKER once, use it 3×" thesis: Bulk Moves is scan-first (no picker), Phase-5 is backend-only (no UI), and only the add-redesign has a primary picker need. **The genuine shared 3× surface is the `parent_id` MODEL**, not a widget:

1. **`location_prefix()` first-segment helper** — Phase-5 splits it out of `derive_parent_id_from_prefix` and re-points **all** still-load-bearing callers (the 4 flat matchers, the synthesizer, the migration guards, `immediate_parent_for`'s Auto fallback, the room-resolution fallback). **One-directional constraint (corrected):** Phase-5's retirement must keep the matcher FLAT; Bulk Moves (unbuilt) relies on that flat scope but is NOT gated on Phase 0. The add-redesign reuses the segment vocabulary for id-generation.
2. **Write-time `parent_id` validation in `save_locations_list`** (shared **2×**, corrected) — Phase-5 adds it (validating only newly-changed rows); the add-redesign requires it (deep chains mustn't silently orphan). *(Bulk Moves does NOT write through it — `perform_smart_move` writes spool records, not location rows.)*
3. **`is_descendant` / `build_parent_map`** model primitives — Phase-5 write-check cycle guard + add-redesign picker cycle guard + Bulk Moves self/descendant guard.
4. **A shared `buildLocationTree(rows)` frontend helper** — the tree-walk is currently duplicated 3× (`_renderLocationsPayload`, `_locDescendants`, `_locBreadcrumbChain`); extract once, consumed by the LM render + the add-redesign tree picker.

## Locked decisions (Derek 2026-07-07, via AskUserQuestion)

- **Q1 group shape → Model-framed, Bulk Moves adjacent.**
- **Q2 Phase-5 → SPLIT the helper** (new `location_prefix()`; retire only the hierarchy fallbacks — the buglist's literal "delete `derive_parent_id_from_prefix`" is stale/unsafe: it has 5 load-bearing runtime consumers incl. 4 deliberately-flat safety matchers).
- **Q3 add-redesign → FULL redesign** (per-row "Add child" + auto-gen editable id + Type/Max inference + explicit grouping-row creation + tree picker).
- **Q4 sequencing → Phase-5 FIRST**, then the add-redesign on the clean explicit-`parent_id` model.

## 🚫 Cluster-wide hard invariant — NO FORCED RELABELING (Derek 2026-07-07)

Derek has a large legacy physical-label backlog (many location labels miss the `LOC:` prefix; spool labels too) and finds the reprint-nag demoralizing. Binds every phase:
1. **Existing LocationIDs are immutable** — auto-generation is new-rows-only; never rename/re-mint an existing id.
2. **Scan resolution stays backward-compatible with every existing label form** — `LOC:<id>`, legacy `LEGACY:`/`LEG:`/`OLD:`, and **bare prefix-less ids** ([logic.py:209-228](../../../inventory-hub/logic.py#L209)). Making `parent_id` authoritative must NOT narrow scan resolution — explicit edge-case-checklist item ("don't straight-dump the existing lookup").
3. **No nagging** — a relabel prompt fires only on a deliberate rename, never per-edit or on a migration. Reprints stay opt-in + batchable.

## Group build order

> ⚠️ **See the per-doc "Adversarial-review corrections (2026-07-07)" blocks** in the Phase-5 + add-redesign + config plans — they revise the specifics below (esp. re-point-don't-delete, don't-flip-strict, validate-only-changed-rows, suppress-Add-child-on-toolheads).
- **Phase 0 — shared spine** (from the Phase-5 plan's Phase 0): the `location_prefix()` split + re-point **all** load-bearing callers (4 matchers, synthesizer, migration guards, `immediate_parent_for` fallback, room-resolution fallback) byte-identically; `save_locations_list` write-time validation of **only the newly-changed rows** (whitelisting `None` + `PSEUDO_ROOM_PREFIXES`; Phase-1A/feeder_map check the save return); extract `buildLocationTree` / confirm `is_descendant`. Everything downstream consumes this.
- **Phase 1 — Phase-5 prefix-retirement** (its plan's Phases 1–4, as corrected): confine `strict` to the write-time cycle check (do NOT blanket-flip `_parent_of`), re-point the migration guards onto `location_prefix()`, delete the old NAME `derive_parent_id_from_prefix`, close the (scoped) grep-gate, verify/re-base the CI pins.
- **Phase 2 — sub-location add redesign** (its plan's Phases 1–5, as corrected): per-row Add-child (**suppressed on Printer/Tool Head/MMU Slot**) + inference → auto-gen id → tree picker → explicit grouping-row creation → tests.
- **Adjacent — Bulk Moves (L298)**: build per its own plan **any time** (not gated on Phase 0 — flat matcher exists today); fold in as a later phase or ship as its own follow-on — Derek's call.

## Verification / prod hygiene

- Verify each phase against the **live Docker container** (real Spoolman :7913) — unit tests alone don't hit the real topology ([[feedback_adversarial_review_runtime_lens]]).
- Backend touches safety-critical matchers → adversarial review with the runtime-topology lens; never swap a flat matcher to transitive `is_descendant`.
- The shelf-grouping migration change is a **prod data migration** (backup `locations.json` first; verify nesting + no re-typing after deploy).
- Full `RUN_INTEGRATION=1` sweep must stay green; the L271 CI pins (`test_l271_*`, `test_dryer_bindings.py`, `test_locations_json_integrity.py`) are updated deliberately, not just deleted.

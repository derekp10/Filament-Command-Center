# 📋 Epic Planning Sprint — Scope Remaining Epics, then Group by Commonality

> **Status:** IN PROGRESS (started 2026-07-07). **Self-contained handoff — a fresh chat needs no prior context.**
> **Kicked off by Derek:** *"I'd like to build out more plans and see if they all don't have a commonality so I could see if they can't be grouped together so that they can be done together."*
> **Prod state:** the cleanup sweep + empty-weight combine + Bulk Moves scoping were **RELEASED to `main` (`b49158b`, 2026-07-07)** — ⚠️ **PROD PULL PENDING Derek's TrueNAS play** (`update.sh` → `git reset --hard origin/main`). `dev` == `main`.

## The goal
Scope each remaining FCC epic into a **phased plan doc** (the model is [L298-bulk-moves-plan.md](L298-bulk-moves-plan.md)), THEN do a **cross-plan commonality pass** to find shared surfaces, so related epics can be batched into a **working group and built together** — a shared component built once and reused N×, instead of each epic re-inventing it.

## Method (per epic — no code during scoping)
1. Research fan-out (grounded, file:line) over the epic's subsystem — reuse the `Workflow` tool with ~4–6 parallel readers (see how the Bulk Moves scope was built: primitives / model / scan-flow / edge-cases / UX-undo).
2. Synthesize a plan doc under `docs/agent_docs/tasks/` with: **reuse map** (what to build ON, not reinvent), **design decisions** (surface the real forks for Derek via `AskUserQuestion`, like the Bulk Moves 4 decisions), **phased build order**, **edge-case/safety checklist**.
3. Lock the decisions with Derek, then the doc is build-ready.

## Epic inventory + status
| Epic | Status | Plan doc / groundwork |
|---|---|---|
| **Bulk Moves (L298)** | ✅ **SCOPED, 4 decisions locked** | [L298-bulk-moves-plan.md](L298-bulk-moves-plan.md) |
| **Sub-location add redesign** | ✅ **SCOPED + DECIDED 2026-07-07 (Full redesign)** | [sub-location-add-redesign-plan.md](sub-location-add-redesign-plan.md) |
| **L271 Phase-5 prefix-retirement** | ✅ **SCOPED + DECIDED 2026-07-07 (split helper)** | [L271-phase5-prefix-retirement-plan.md](L271-phase5-prefix-retirement-plan.md) |
| **Per-printer Config (N6) + L18 Phase 5** | ✅ **SCOPED + DECIDED 2026-07-07 → [Group 35](35-config-cluster.md)** | [config-cluster-plan.md](config-cluster-plan.md) |
| Make everything user-configurable | ✅ Effectively DONE by design — L18's declarative schema makes adding a setting a one-line `Field` edit; incremental as-needed, not an epic | — |
| Rename inventory hub → FCC | ⬜ NEEDS SCOPING (mechanical branding sweep) | — |
| Mobile (L315) | ⬜ NEEDS SCOPING (large, self-contained) | — |
| Project Color Loadout (L391) | separate SQLite add-on; blocked on a real ColorMix `.3mf` | `docs/Project-Color-Loadout/` |
| Amazon multi-pack / external parsers | small, **INPUT-GATED** (needs Derek decisions first) | — |

## 🌳 Location-tree cluster — COMMONALITY PASS RESULT (2026-07-07, grounded 6-reader workflow)

**Verdict: the preliminary "build a reusable location-tree PICKER once, use it 3×" thesis is REFUTED as framed — the true shared surface is the `parent_id` MODEL + the flat location-string enumeration + the write/validate path, NOT a widget.** Grounded reality (all file:line-verified):

- **Bulk Moves (L298)** is **scan-first by locked decision** (D1: `CMD:BULKMOVE` deck-QR + a "Move all →" button that arms a destination *scan*). It does **not** need a picker; its plan's picker-alignment note ([L298:73](L298-bulk-moves-plan.md)) is explicitly *aspirational*, not a dependency.
- **Sub-location add redesign** is the **only** epic with a genuine primary picker need (upgrade the flat `#edit-parent` `<select>` → tree).
- **L271 Phase-5 prefix-retirement** is **backend-only — no UI at all.**
- A widget "built once, used 3×" would in reality be **used ~1×** (sub-loc-add primary; Bulk Moves optional/secondary; Phase-5 never).

**What is GENUINELY shared (the real spine) — corrected 2026-07-07 after adversarial review:**
1. **`location_prefix()` first-segment helper** (Phase-5 splits it out of `derive_parent_id_from_prefix`). Phase-5 re-points the 4 `spoolman_api` matchers onto it, byte-identically. **The coupling is ONE-DIRECTIONAL** (corrected): Phase-5's *retirement* must keep `_build_location_match`/`get_spools_at_location_detailed` **FLAT** — if it naively swapped them to transitive `is_descendant` it would enlarge the destructive blast radius (room clear/delete sweeping a nested printer's live toolhead — the 2026-06-04 review bug) and break Bulk Moves' D2. But the matcher is **already flat today**, Bulk Moves is **unbuilt** ([spoolman_api.py:1320](../../../inventory-hub/spoolman_api.py#L1320)), and the split is byte-identical — so this is a **forward constraint on Phase-5's execution, NOT a Bulk-Moves prerequisite**. The add-redesign reuses the same segment vocabulary for id-generation.
2. **Write-time `parent_id` validation in `save_locations_list`** (shared **2×**, corrected — not 3×). Phase-5 adds it; the add-redesign *requires* it (deep chains must not silently orphan → float-to-root). *(Bulk Moves does NOT write through it — `perform_smart_move` writes SPOOL records via `update_spool`, never location rows.)*
3. **`is_descendant` / `build_parent_map` model primitives** ([locations_db.py:430](../../../inventory-hub/locations_db.py#L430)) — Phase-5 write-check cycle guard + add-redesign picker cycle guard + Bulk Moves self/descendant guard, all the same primitive.
4. **A shared `buildLocationTree(rows)` frontend helper** — the tree-walk is currently **duplicated 3×** (`_renderLocationsPayload` [inv_core.js:587](../../../inventory-hub/static/js/modules/inv_core.js#L587), `_locDescendants` [inv_loc_mgr.js:1518](../../../inventory-hub/static/js/modules/inv_loc_mgr.js#L1518), `_locBreadcrumbChain` [:1552](../../../inventory-hub/static/js/modules/inv_loc_mgr.js#L1552)). Extract once; the LM render, the add-redesign picker, and (optionally) a Bulk Moves click-alternative all consume it.

### → Proposed working group: **"🌳 Location-tree cluster"** (MODEL-framed)

- **Shared Phase 0 (the genuine build-once):** `location_prefix()` split + `save_locations_list` write-time `parent_id` validation + the `buildLocationTree`/`is_descendant` extraction. Every downstream epic consumes this.
- **Then Phase-5 prefix-retirement** (backend spine — retire the hierarchy fallbacks, rework migration guards, delete + grep-gate).
- **Then sub-location-add redesign** (UX on the now-authoritative explicit-`parent_id` model: add-child, auto-gen id, tree picker, explicit grouping-row creation).
- **Bulk Moves stays its own already-scoped build** ([L298 plan](L298-bulk-moves-plan.md), 4 locked decisions). **Corrected 2026-07-07:** it is NOT gated on Phase 0 — the flat matcher exists today, so Bulk Moves can ship independently on it. The only cross-link is the *forward constraint* that Phase-5's retirement keep that matcher flat (see pillar #1). Bulk Moves is the least-coupled of the three and could even go first.

### ✅ Cluster decisions locked (Derek 2026-07-07, via AskUserQuestion)
- **Q1 group shape → Model-framed, Bulk Moves adjacent.** ONE group = shared Phase 0 → Phase-5 retirement → sub-loc-add redesign; Bulk Moves adjacent with Phase 0 as a hard prerequisite.
- **Q2 Phase-5 → SPLIT the helper** (new `location_prefix()`; retire only the hierarchy fallbacks). The buglist's literal "delete it" is stale/unsafe.
- **Q3 add-redesign → FULL redesign** (add-child + auto-gen id + Type/Max inference + explicit grouping-row creation + tree picker).
- **Q4 sequencing → Phase-5 FIRST**, then the add-redesign on the clean explicit-`parent_id` model.

### 🚫 Cluster-wide hard invariant — NO FORCED RELABELING (Derek 2026-07-07)
Derek: *"avoid re-generating location labels as much as possible… I still have a lot that miss the `LOC:` prefix out there; if we just straight-dump the existing lookup for this new id system it'll cause problems."* Binds every epic in the cluster:
- Existing LocationIDs are **immutable**; auto-generation is **new-rows-only** (never rename/re-mint).
- The scan resolver must **keep landing every existing label form** — `LOC:<id>`, legacy `LEGACY:`/`LEG:`/`OLD:`, and **bare prefix-less ids** ([logic.py:209-228](../../../inventory-hub/logic.py#L209)). Making `parent_id` authoritative must not narrow scan resolution — an explicit edge-case-checklist item.
- Relabel prompts fire **only** on a deliberate rename (the one thing that changes printed identity), never per-edit or on the migration. Reprints stay opt-in + batchable.

*✅ Pre-filed as **[Group 34 — 🌳 Location-Tree Cluster](34-location-tree-cluster.md)** (2026-07-07). Build-ready pending Derek picking it up.*

### ⚙️ Config cluster — SCOPED 2026-07-07 → [Group 35](35-config-cluster.md)
Grounded 4-reader pass. **Reframing: L18 Config Phases 1–4 already shipped (2026-06-01)** — this is a small tail, not a greenfield epic.
- **N6 — per-printer settings** — a per-printer **map** field type + renderer. The Phase-3 `printer_map` type is **NOT** reusable (topology map vs per-printer-settings map); the real anchor is the per-printer **creds** grid. First customer `path_filament_g`'s reader is already map-ready.
- **L18 Phase 5 — action-tool co-location** — folded in (shares the section-host structure the buglist says to build once).
- **Make-everything-configurable** — dissolved: the declarative schema already makes adding a setting a one-line `Field` edit.
- → **Shared surface: `config_schema.SECTIONS` + the `inv_settings.js` per-section host.** Decisions: key by Name · `path_filament_g` only · fold Phase 5. Plan: [config-cluster-plan.md](config-cluster-plan.md).

### Standalone (no strong grouping — scope individually if/when picked up)
Rename→FCC, Mobile (L315), Project Color Loadout (L391), Amazon multi-pack + external parsers.

---

## ✅ SPRINT GROUPING COMPLETE (2026-07-07)
Both commonality clusters are scoped, decisions locked, and pre-filed as numbered working groups:
- **[Group 34 — 🌳 Location-Tree Cluster](34-location-tree-cluster.md)** (Phase-5 prefix-retirement + sub-loc-add redesign + Bulk Moves adjacent).
- **[Group 35 — ⚙️ Config Cluster](35-config-cluster.md)** (per-printer settings N6 + L18 Phase 5).

Plan docs written this sprint: [L298-bulk-moves-plan.md](L298-bulk-moves-plan.md) · [sub-location-add-redesign-plan.md](sub-location-add-redesign-plan.md) · [L271-phase5-prefix-retirement-plan.md](L271-phase5-prefix-retirement-plan.md) · [config-cluster-plan.md](config-cluster-plan.md). The remaining epics (Rename→FCC, Mobile L315, Color Loadout L391, Amazon/external parsers) are standalone with no strong shared surface — scope each individually when picked up.

## ▶ NEXT-CHAT KICKOFF — start here
- [x] **Scope the two unscoped Location-tree epics** → [sub-location-add-redesign-plan.md](sub-location-add-redesign-plan.md) + [L271-phase5-prefix-retirement-plan.md](L271-phase5-prefix-retirement-plan.md) (2026-07-07).
- [x] **Commonality pass** → done above (MODEL-framed, not picker-framed; proposed the "🌳 Location-tree cluster" group).
- [x] **Locked the Location-tree forks + filed [Group 34](34-location-tree-cluster.md)** (2026-07-07).
- [x] **Scoped + locked the Config cluster + filed [Group 35](35-config-cluster.md)** (2026-07-07).
- [x] **Sprint grouping COMPLETE** — see the "SPRINT GROUPING COMPLETE" section above. Groups 34 + 35 are build-ready pending Derek picking them up.
- [ ] (Future, if wanted) scope the standalone epics individually: Rename→FCC (mechanical branding sweep), Mobile (L315), Project Color Loadout (L391), Amazon/external parsers.

**Paste this into a fresh chat to resume (only if scoping the standalones):**
> The epic-planning-sprint grouping is complete (Groups 34 + 35 filed; see `docs/agent_docs/tasks/planning-sprint-epic-grouping.md`). Scope the next standalone epic — [Rename→FCC | Mobile L315 | Color Loadout L391 | Amazon parsers] — into a phased plan doc like the others.

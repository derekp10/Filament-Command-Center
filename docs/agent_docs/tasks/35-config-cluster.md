# Group 35: ⚙️ Config Cluster (Per-Printer Settings + Action-Tool Co-location)

**Branch name (when started):** `feature/group-35-config-cluster`
**Estimated effort:** SMALL–MEDIUM (~5–8 hrs). Renderer refactor ~1–2h · backend map type ~1–2h · per-printer renderer ~2h · Phase-5 co-location ~1–2h · tests ~1h.
**Risk:** **LOW–MEDIUM.** No prod data migration, no safety-critical matchers. Main hazards: the schema type + renderer must land together (else silent dict-stringify corruption), and the exact-equality config verify needs deterministic coercion. Phase-5 co-location is UI-only.

> **Status: 📋 TODO — SCOPED + DECISIONS LOCKED 2026-07-07.** Graduated from the epic planning sprint ([planning-sprint-epic-grouping.md](planning-sprint-epic-grouping.md)). Full phased plan + reuse map + risks live in **[config-cluster-plan.md](config-cluster-plan.md)** — this file is the orchestration brief.
>
> ⚠️ **2026-10-12 (`/refresh-groups`): re-decide G1 before building.** G1 keys the per-printer map by display printer **Name**. Its rationale was *"matches the shipped `_path_filament_g` reader + the creds editor"*, and half of that no longer holds:
> - The 2026-09-29 INDX hotfix (`main ab48e45`) moved the printer-connections grid to address Printer rows by **LocationID** ("display ≠ save ≠ lookup" was the bug).
> - The new buglist item *"Per-printer state is keyed by display Name"* says *"long term: key all of it by the Printer row's LocationID (revisit Group 35 decision G1)."*
> - [Group 44](44-printer-first-class.md) (Printer as a First-Class Object) will settle the stable printer id.
>
> Either build after 44's design pass, or put G1 back to Derek with that context first. The rest of the plan (G2–G4) is unaffected. The toolhead label display mode was considered here but placed in [Group 46](46-quick-fix-sweep-2026-10.md) 46.3 (global for now); its per-printer form would use this group's map type later.
>
> **🔄 2026-10-19 (`/refresh-groups`): G1 RE-DECIDED (Derek): key the per-printer map by the Printer row's Location ID now** (`XL`, `RCOI`: the key the printer-connections grid has used since the 2026-09-29 hotfix). This group no longer waits on [Group 44](44-printer-first-class.md): if 44's sit-down changes how printers are identified, its migration re-keys these values along with everything else. Read the build order's "one row per Name" below as one row per Printer row, labelled with its display name. Derek's wider point, for 44's sit-down: he needs one concrete id that carries the whole lineage (parents, children, grandparents) while keeping his naming conventions, with printers and toolheads joined properly.
>
> **New member, the first customer (2026-10-19):** the buglist's "Runout path filament per printer (and maybe per toolhead)". Derek: *"We may even want this to be per toolhead at some point. But I'm pretty sure that the sensor distance between the xl and the indx are probably not the same length. But I haven't confirmed this, it's just based on eyeballing the lengths."* Today `path_filament_g` is one float for every printer (`config_schema.py:83-91`, 0 = off), while `print_deduct._path_filament_g` already reads a `{printer_name: grams}` map with an optional `default` (`print_deduct.py:1376-1397`). So the reader maps the deduct's printer Name (the deduct is called with the display name) to its Printer row, and the map leaves room for an optional per-toolhead override keyed by the head's Location ID, on the same setting, without a new field type.
> _(Checked the same morning: since the 2026-09-29 hotfix, Settings → Toolheads creates the heads' Location rows itself, `ensure_toolhead_rows`, so they need not be made by hand in the Location Manager.)_

## What this group is

The **remaining tail** of the Config system (L18 Phases 1–4 already shipped 2026-06-01). Two open items the buglist folds together ([Feature-Buglist.md:7](../../../Feature-Buglist.md)):

| Item | Role |
|---|---|
| **N6 — Per-printer settings section** | The substantive item: a per-printer **map** field type + renderer in `config_schema.py`/`inv_settings.js`. First & only ready customer: `path_filament_g` (its reader already accepts a `{printer_name: grams}` map). |
| **L18 Phase 5 — action-tool co-location** | Optional UI-reorg (folded in per G3): mount the config-modal action cards into per-section hosts so the "clunky attributes" manager sits beside its prefs. No endpoint logic change. |
| **Runout path filament per printer (and maybe per toolhead)** (Derek, 2026-10-19) | N6's first customer, now with Derek's reason (the XL's and the INDX's sensor-to-nozzle tubes probably differ). Keyed by the Printer row's Location ID; a per-toolhead override can come later on the same setting. |

## Why one group (commonality)

N6's per-printer field needs a **per-section widget host**; Phase 5 introduces exactly a **section-keyed host registry**. Build the section-host once → it serves both the per-printer field placement AND the action-tool co-location. Shared surface = `config_schema.SECTIONS` + the `inv_settings.js` renderer + the per-section host pattern (already proven by the printer_map/creds block). The buglist itself says fold them together.

## Locked decisions (Derek 2026-07-07, via AskUserQuestion)

- **G1 → key the per-printer map by the Printer row's Location ID** (re-decided by Derek 2026-10-19; see the status note). It was "by display printer Name" on 2026-07-07, matching the shipped `_path_filament_g` reader + the creds editor, with a rename-orphan caveat.
- **G2 → build the mechanism + migrate `path_filament_g` only** (the sole value with a map-aware reader; offsets/path-length don't exist in code — no dead config).
- **G3 → fold in L18 Phase 5** (shared section-host structure; UI-only).
- **G4 (safe default, not separately asked)** → refactor the `inputFor()` if-ladder into the `WIDGETS {build,read}` table first (the L18 doc's promised design), then add the map as one entry. Behavior-preserving.

## Build order (from the plan doc)

1. **Renderer refactor** (G4) — `inputFor()` if-ladder + `save()` type-branches → a `WIDGETS = {type:{build,read}}` table. Behavior-preserving; existing config round-trip/E2E tests stay green.
2. **Backend map type** — `per_printer_map` + a `cell_type` `Field` attr; a dict branch in `coerce_and_validate` dispatching per-cell into the factored scalar coercer + `min`/`max`; extend `validate_payload`/`schema_for_ui`/export-import. Keep `config_schema.py` pure (validate cell VALUES only, not keys — no `locations_db` import). Fix the stale `Field.type` docstring.
3. **Per-printer renderer + name source** — a `WIDGETS['per_printer_map']` widget cloning `pcRowHtml`'s grid (one row per Name + a `default`/all-others row); source names from the `GET /api/printer_map` fetch already made on modal open (**de-dupe by Name** — `build_printer_map_from_rows` yields one entry per toolhead); collect rows → dict → PUT `/api/config`. Migrate `path_filament_g` `float` → `per_printer_map` (`cell_type='float'`, `min=0`, `max=50`). UI writes a `"default"` entry so the on-disk shape is uniform. _(2026-10-19: with G1 re-decided, one row per Printer row, keyed by its Location ID and labelled with its display name; de-dupe by Location ID.)_
4. **Action-tool co-location** (L18 Phase 5) — section-keyed host registry; refactor `configReconcileScan`/`configAttrsScan`/`configRestoreFieldOrder` to accept a passed host. **Preserve every fixed host id** (`#config-attrs-results`, `#config-restore-field-order-results`, `#config-printer-map`, `#config-build-info`) or the tools silently break.
5. **Tests + polish** — config round-trip byte-identity for the map, per-cell range reject, `test_runout_auto_split` stays green after the `path_filament_g` migration, visual check of the grid.

## ⚠️ Build-time notes

- **The L18 design doc lags the shipped code** — trust the source: no `WIDGETS` table (if-ladder), `schema_for_ui` not `schema_as_json`, no `CLIENT_PREF_KEYS`, secret masking in the route layer, `printer_map` off config.json. Full drift list in the plan doc.
- **Don't route `path_filament_g` through `/api/printer_map`** — it stays a plain config.json key saved by `save_config`. Don't fold creds into a config secret-map (they're correctly row-attached with a working masked editor).
- **Enumerate printers from Printer rows / `GET /api/printer_map`**, NEVER `config.json:printer_map` (vestigial seed).
- `config.json` is a single-file bind-mount (EBUSY → in-place fsync fallback, already handled) — don't disturb `_write_config_atomic`.

## Sequencing vs the other sprint groups
Independent of [Group 34 (Location-tree)](34-location-tree-cluster.md) — no shared surface, no ordering constraint. Lower-risk than Group 34; a good candidate to build first or interleave.

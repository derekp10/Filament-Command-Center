# Project Color Loadout — ColorMix Addendum (v1, 2026-07-02)

> **Why this exists:** ColorMix shipped in **PrusaSlicer 2.9.6** (after the original L391
> `roadmap.md` / `api_flow.md` / `database_schema.sql` were written). The original design assumes
> **one distinct real color per toolhead/slot**. ColorMix breaks that 1:1 assumption — it produces a
> *new apparent color* by alternating 2–3 already-loaded filaments layer-by-layer (halftoning). This
> addendum scopes what changes; it does **not** rewrite the roadmap. Pair with the buglist item
> "ColorMix support for Project Color Loadout".

## What ColorMix actually is (grounding)

- **Multi-material only** — toolchangers (Prusa XL, CORE One+ INDX) and MMU/AMS. Not single-extruder.
- Mixes by **alternating whole layers** between loaded filaments at discrete ratios: `1:1`, `1:3`,
  `3:1`, and `1:1:1` (three colors). No physical blending; the eye integrates adjacent layers.
- On a toolchanger it is emitted as ordinary **tool changes (`Tn`)** — *not* single-extruder
  `;COLOR_CHANGE`/M600. So the sliced output is standard multi-tool G-code with a per-tool
  `; filament used [g]` footer (verified shape: `; filament used [g] = 0.00, 6.35, 0.00, 0.00, 0.00`).

## Impact on the existing L391 design, by phase

| Phase | Original assumption | ColorMix change |
|-------|--------------------|-----------------|
| **1 — DB & core UI** | A loadout `slots` array = one filament per slot. | A slot may be a **mixed slot**: an ordered set of 2–3 constituent filaments + a ratio (`1:1` / `1:3` / `3:1` / `1:1:1`) that renders to one *apparent* hex. `loadout_data` JSON already flexible enough — add a `mix` sub-object; no column change. |
| **2 — .3mf parser / Smart Draft** | Extract per-object hex → Delta-E match to one Spoolman filament. | A ColorMix `.3mf` encodes **source filaments + a mix recipe**, not just a target hex. Parser must recognize the ColorMix recipe (which real filaments, what ratio) and map each constituent to inventory — not collapse it to a single hex. |
| **3 — Palettes / 4D swap** | A palette = N named single colors. | A **ColorMix recipe is a first-class palette entry** ("Sunset = Red+Yellow 1:1"). The 4D swap optimizer must treat a mixed slot as occupying **its constituent physical slots simultaneously** for the duration of that print. |
| **4 — Spoolman sync / Smart Cart** | One color consumes one spool; shortage = that spool low. | A ColorMix color consumes **N spools proportionally** (by the layer ratio). Smart-Cart shortage math must split the needed grams across constituents and flag *any* constituent low. See "Consumption math" below. |
| **5 — Reverse sync** | Inject one hex per object. | Inject the **recipe** (constituents + ratio + hidden `project_id`), not a single hex. |

## The killer synergy: Delta-E → suggest a *blend* when no single filament matches

The original Phase-4 "Delta-E Alternative Suggestion" only suggests the closest **single** in-stock
filament. ColorMix makes a strictly stronger move possible:

> **When no single owned filament is within tolerance of a requested color, search owned pairs/triples
> for a ColorMix ratio whose *integrated* color is within tolerance** — "You don't own Teal, but
> ColorMix of your Blue + Green at 1:1 lands ΔE 3.2."

This turns a limited real palette into a much larger *achievable* palette and is arguably the feature
ColorMix most enables for FCC. It reuses the Delta-E engine Phase 2/4 already needs; the new part is
searching combinations + ratios and computing the integrated (area-weighted) color.

## Consumption math (feeds Phase-4 Smart Cart AND FCC's deduct)

- A mixed slot at ratio `a:b` over a color region of total grams `G` charges roughly
  `G·a/(a+b)` to constituent A and `G·b/(a+b)` to constituent B (layer-count weighted, refined by the
  real per-tool footer once sliced).
- **FCC's completion deduct already handles the *print-time* reality**: ColorMix on a toolchanger is
  per-tool, so the per-tool `; filament used [g]` footer maps each constituent's grams to its bound
  spool with **no new deduct code** — the same mechanism any multi-tool XL print uses. L391's job is
  the *planning/shortage* side (before the print), not the deduct (after).

## What's machine-readable TODAY (checked 2026-07-02) vs. needs a real slice

| Data | Readable now? | Notes |
|------|--------------|-------|
| Per-tool total grams `; filament used [g] = …` | ✅ Yes | FCC parses it (`prusalink_api.parse_footer_usage`); includes that tool's own purge. |
| Per-tool total mm `; filament used [mm] = …` | ✅ Yes | Used for the g/mm ratio in the partial-deduct. |
| Wipe-tower **total** grams `; total filament used for wipe tower [g] = X` | 🟡 Likely | Documented config-summary line; **not present in the single-tool fixture** (no wipe tower). Confirm on a real multi-tool slice; FCC doesn't parse it yet but trivially could. |
| **Per-color / per-extruder purge** breakdown | ❌ Not confirmed | Docs show only a wipe-tower *total*, not a per-color split; the per-extruder flush weight looks like a **UI-sidebar computation**, not a machine-readable gcode line. A true "waste per color" metric may require deriving it, not reading it. |
| ColorMix **recipe** (constituents + ratio) from `.3mf` | ❓ Unknown | Needs a real ColorMix `.3mf` to inspect the XML/metadata representation. **Blocked on Derek slicing one.** |

## Blocked-on-data checklist (Derek's first ColorMix / material-swap XL print)

1. Keep the `.3mf` **and** the sliced `.bgcode`.
2. Decode the `.bgcode` (procedure proven on `tests/fixtures/sample.bgcode`) and capture the full
   config-summary footer — confirm the per-tool `; filament used [g]` array + whether
   `; total filament used for wipe tower [g]` appears, and whether any per-color purge line exists.
3. Note whether the ColorMix layers appear as `Tn` tool changes (expected) and whether any
   `;COLOR_CHANGE` markers appear at all (expected: none on a toolchanger).
4. Inspect the `.3mf` (it's a zip) for how the ColorMix recipe (constituent filaments + ratio) is
   stored — this is the Phase-2 parser input.
5. Weigh the real per-color result if feasible, to validate the consumption-split math.

This same capture also settles the **Group 22.3(b)** open question (does `;COLOR_CHANGE` survive the
decode for the *single-extruder* M600 case) — general comments already proven to survive
(`; prepare for purge` came through the decode intact).

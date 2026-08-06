# Group 37: 🌳 Location System Redesign

**Branch name (when started):** `feature/group-37-location-system-redesign`
**Estimated effort:** LARGE / multi-session — **do not start building until §Open forks are decided**
**Risk:** **HIGH.** Touches the location model that `/api/get_contents`, the bulk-move source
resolver, and the destructive clear/delete paths all read through. A `locations.json` backup is a
prerequisite for any data-touching phase.

> **Status: `TODO` — SCOPED, NOT STARTED.** Filed 2026-08-06 (`/refresh-groups`); scoped 2026-08-03.
> Derek's framing: *"I think we might need a refactor on how this whole location system works and
> displays… I feel like things need a re-design before we dig deep into developing a
> preserve-row-structure path."*
>
> **Full evidence + open forks → [location-system-redesign-scoping.md](location-system-redesign-scoping.md).**
> Related plan docs: [sub-location-add-redesign-plan.md](sub-location-add-redesign-plan.md),
> [L298-bulk-moves-plan.md](L298-bulk-moves-plan.md).

---

## Relationship to Group 34 (⚠️ read this first)

**[Group 34](34-location-tree-cluster.md) stays `PARTIAL` and keeps owning its two open slices** —
S5 (add-redesign phase 4) and the auto-gen-id refinement — per Derek's 2026-08-06 call. This group
**cross-references** them; it does not absorb them.

Practical consequence: **sequence 37 before finishing 34's leftovers.** Both of 34's open slices
build on semantics this redesign is expected to change, and S5's own plan mandates a
`locations.json` backup as step 1. Decide the model here first, then land S5 + auto-gen-id against
the settled model.

Group 34's shipped foundation is what this builds on: `location_prefix()` extracted (`55be529`),
the `derive_parent_id_from_prefix` alias retired (`2b16869`), per-row ➕ Add-child + tree picker
(`52990bd`), and all five Bulk Moves phases now merged to `dev`.

---

## 🔬 Root cause — PROVEN by source trace 2026-08-03

`locations_db.location_prefix` splits a LocationID on the **first dash only**
(`locations_db.py:487-492`), and that is the only non-exact match in
`spoolman_api._build_location_match` (`spoolman_api.py:1320`).

Since every descendant of room `CR` — `CR-CT-1`, `CR-CT-1-R1`, `CR-WLN-R1-SC1` — has first segment
`CR`, the granularity is **binary, not one-level**: a ROOM query reaches its whole subtree at any
depth, and **every other level is exact-match-only**. The prefix branch is effectively dead code for
Cart / Wall Shelf / Row / Section queries.

That single fact produces all three observed display symptoms, because `/api/get_contents`
(`routes_locations.py:648`), the bulk-move source resolver
(`get_spools_at_location_detailed_strict`), and the destructive clear/delete paths **all call the
same matcher** — one flat reader answering three different questions (*what is in here* / *what may
I move* / *what may I destroy*). **Only the third needs to stay flat.**

### ⚠️ Two hazards that fall out of this

- **Visible contradiction:** the `/api/locations` occupancy rollup IS transitive over `parent_id`
  (`routes_locations.py:127-140`), so cart `CR-CT-1` shows a **Total including its rows' spools**
  while opening that same cart lists **zero**.
- **The L298 D2 safety contract depends on NAMING, not structure.** A room query misses `XL-1` only
  because `location_prefix("XL-1") == "XL" != "LR"`. Nothing structural enforces it — **name a
  toolhead `LR-…` and a room-level clear sweeps a live print.** Any redesign must replace this with
  an explicit active-print/type guard rather than inherit the accident.

---

## Members (all filed separately in `Feature-Buglist.md`)

| # | Item | Notes |
|---|---|---|
| **37.1** | **Blank LocationID is accepted, then "already exists" on re-edit** — with no value visible on the field or in the Location List | ⚠️ **Derek's repro row is LIVE in `data/locations.json`** — index 0, `{"LocationID": "", "Name": "TestCart", "Type": "Cart", "Max Spools": "0", "parent_id": "CR"}`. **Do NOT delete it without asking.** It fails `test_locations_json_integrity` on every sweep and breaks the wizard's location combobox (it sorts to dropdown index 1). |
| **37.2** | **Unassigned list overflow on a new location's Manage view** — the list pushes UI elements off the visible screen | Wants: scrollable within the available viewport + easily collapsible from anywhere in the list, so the user can always reach the lower UI elements. |
| **37.3** | **Parent/child creation is still tedious** | The `+` on a parent doesn't autofill the child. Derek also wants **smart LocationID suggestions** and is openly questioning whether human-readable composite ids are still the right model (`CR-TC-R1` is hard to remember, set up, and track when each new row must be created from scratch). |
| **37.4** | **Cart-display fix** (a cart shows a transitive Total but lists zero contents) | ✅ **Decision 2026-08-03: folded in here rather than shipped as a point fix** — the redesign changes those semantics anyway. |
| _(x-ref)_ | Group 34 **auto-gen-id finickiness** — breadcrumb-id doesn't re-sync on parent change; numbering isn't topology-aware (always `R1`, never `R2`) | Owned by **Group 34**; land it after this group settles the model. |
| _(x-ref)_ | Group 34 **S5** (add-redesign phase 4 — "create missing levels" + demote the shelf-grouping boot migration) | Owned by **Group 34**; ⏸️ deferred, and its plan **mandates a `locations.json` backup as step 1**. |
| _(x-ref)_ | The older buglist item *"adding sub-locations is messy"* | Same surface as 37.3. |

---

## Constraints from the REAL dev topology

Read-only inspection of `data/locations.json`, 56 rows:

- **Per-row capacity is not tracked** — 27 rows have `Max Spools = ''`, including *every* cart and
  cart-row. So L298's D3 capacity pre-flight **cannot fire on a cart→cart move**.
- **No 1:1 row correspondence between carts** — `CR-CT-1` = `R1/R2/R3` vs `DR-CT-1` =
  `R1, R2-L, R2-R, R3-L, R3-R, R4-L, R4-R`.
- **`Type` cannot identify a row** — 26 rows are Type `Cart`, including the `R1/R2/R3` children. Any
  structure-aware feature must **walk `parent_id`**.

---

## ✅ Decisions already taken (Derek, 2026-08-03)

1. **Structure-preserving bulk move is DEFERRED, possibly dropped** — *"a feature I'm not 100% sure
   I'm going to use that often… might just make sense doing it using the existing bulk ability with
   the buffer and a location scan."* Do **not** build it before the redesign settles the model.
2. **The cart-display fix is folded into this redesign** (37.4) rather than shipped as a point fix.

## ❓ Open forks — need a decision BEFORE any build

1. **Is the human-readable composite LocationID still the right model?** *(the biggest fork — nearly
   every other pain point is downstream of it)* Alternatives: opaque id + display path; or keep
   composite ids but generate/maintain them entirely automatically from the tree.
2. **What should a subtree contents view show?** Derek's refinement: distinguish spools sitting
   **directly on the cart** ("unassigned at row level") from those filed into `R1/R2/R3`, rather than
   one undifferentiated list.
3. **Does bulk move gain subtree scope?** If yes, the naming-dependent guard above must be replaced
   with an explicit active-print/type check **first**.
4. **Does `Max Spools` become meaningful for carts/rows,** or stay unbounded there?

---

## 🟢 Interim recommendation (small, safe, survives whatever the redesign decides)

Do **not** widen bulk-move scope yet — that means re-adding per-toolhead active-print guards against
location semantics that are about to change.

Instead, kill the *silent no-op* that reads as a bug: when a bulk-move source has nested children,
have the preview panel say so explicitly — `"N spools sit in 3 sub-locations and will NOT move"`.
Small, touches only the preview text, leaves the locked D2 contract alone.

## 🔒 Invariants any redesign MUST preserve

- **NO FORCED RELABELING** (the Group 34 cluster-wide constraint, still binding): existing
  LocationIDs are immutable, scan stays `LOC:`/legacy/bare-compatible, no relabel-nag.
- A room-level clear/delete must **never** reach a live toolhead — but via an **explicit guard**, not
  the id-naming accident above.
- `location_prefix` must keep returning `None` for a dash-free id — the `/api/locations` synthesizer's
  virtual-row parent stamp depends on it, so a Spoolman-native name doesn't self-parent
  (`locations_db.py:484`).
- `slot_targets` is **plumbing, not contents** — never auto-cleared by a move (L298 Phase 4).
- Bulk/clear/move must keep delegating to `perform_smart_move`; never hand-roll spool writes
  (CLAUDE.md "Spool / Filament write surfaces").

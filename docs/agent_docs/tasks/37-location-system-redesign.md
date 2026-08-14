# Group 37: 🌳 Location System Redesign

**Branch name (when started):** `feature/group-37-location-system-redesign`
**Estimated effort:** LARGE / multi-session — **forks 2–4 are decided; do not start building until
§Fork 1 (the LocationID model) is settled**
**Risk:** **HIGH.** Touches the location model that `/api/get_contents`, the bulk-move source
resolver, and the destructive clear/delete paths all read through. A `locations.json` backup is a
prerequisite for any data-touching phase.

> **Status: `TODO` — SCOPED, NOT STARTED.** Filed 2026-08-06 (`/refresh-groups`); scoped 2026-08-03.
> **Forks 2, 3 and 4 were DECIDED 2026-08-07 (see below); only fork 1 remains open.**
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
(`locations_db.py:543-548`), and that is the only non-exact match in
`spoolman_api._build_location_match` (`spoolman_api.py:1467`).

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
| **37.1** | **Blank LocationID is accepted, then "already exists" on re-edit** — with no value visible on the field or in the Location List | ⚠️ **Derek's repro row is LIVE in `data/locations.json`** — index 0, `{"LocationID": "", "Name": "TestCart", "Type": "Cart", "Max Spools": "0", "parent_id": "CR"}`. **Do NOT delete it without asking.** It costs **TWO reds on every full sweep** (see below). |
| **37.2** | **Unassigned list overflow on a new location's Manage view** — the list pushes UI elements off the visible screen | Wants: scrollable within the available viewport + easily collapsible from anywhere in the list, so the user can always reach the lower UI elements. |
| **37.3** | **Parent/child creation is still tedious** | The `+` on a parent doesn't autofill the child. Derek also wants **smart LocationID suggestions** and is openly questioning whether human-readable composite ids are still the right model (`CR-TC-R1` is hard to remember, set up, and track when each new row must be created from scratch). |
| **37.4** | **Cart-display fix** (a cart shows a transitive Total but lists zero contents) | ✅ **Decision 2026-08-03: folded in here rather than shipped as a point fix** — the redesign changes those semantics anyway. |
| _(x-ref)_ | Group 34 **auto-gen-id finickiness** — breadcrumb-id doesn't re-sync on parent change; numbering isn't topology-aware (always `R1`, never `R2`) | Owned by **Group 34**; land it after this group settles the model. |
| _(x-ref)_ | Group 34 **S5** (add-redesign phase 4 — "create missing levels" + demote the shelf-grouping boot migration) | Owned by **Group 34**; ⏸️ deferred, and its plan **mandates a `locations.json` backup as step 1**. |
| _(x-ref)_ | The older buglist item *"adding sub-locations is messy"* | Same surface as 37.3. |

### 🧪 The two sweep reds 37.1 currently causes

Measured on the `RUN_INTEGRATION=1` sweep of 2026-08-06 (`2406 passed / 2 failed`) — **these
two ARE the entire red tail.** Both A/B-proven pre-existing (they fail identically with
`inventory-hub/` reverted to `70132aa`), so any sweep run while the repro row is live should
expect exactly these and nothing else:

1. `test_locations_json_integrity::test_every_row_is_a_dict_with_LocationID_and_Type` — the
   direct assertion (`row 0 missing LocationID`).
2. `test_wizard_group10_session_a::test_location_combobox_highlights_current_selection_on_focus`
   — **newly attributed 2026-08-06.** Deterministic, 5/5 in isolation. Chain: the blank row is
   served in `/api/locations` (verified live: 1 of 60 rows) → the helper
   `_pick_first_real_location` selects **dropdown index 1**, which is where the blank row sorts
   → its `data-value` is `""` → nothing matches the hidden input on re-focus, so
   `.autocomplete-option.active` counts **0**, not 1.

**Both should go green the moment 37.1 lands** — no separate test work needed. Worth
re-checking after the fix rather than editing either test.

---

## Constraints from the REAL dev topology

Read-only inspection of `data/locations.json`, 56 rows:

- **Per-row capacity is not tracked** — 27 rows have `Max Spools = ''`, including *every* cart and
  cart-row. So L298's D3 capacity pre-flight **cannot fire on a cart→cart move** — which
  fork 4 below has since confirmed is **CORRECT behaviour, not a gap**: blank means unbounded, on purpose.
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

## ✅ Forks 2–4 DECIDED (Derek, 2026-08-07)

### Fork 2 — contents view: TRANSITIVE at every level, GROUPED by child

Derek: *"Sub tree if target is for a specific row, should be that rows contents, if for the cart
should be the full cart (all rows) if for a location (CR) Full cart (with rows) — similar to how it
works currently when looking at a Room, where it's sub divided into Cart/box/wall locations, and
then those items within."*

So the rule is uniform, and **the existing Room view is the reference implementation** — not a new
pattern to invent:

| Query target | Returns |
|---|---|
| Row (`CR-CT-1-R1`) | that row's contents (it has no children) |
| Cart (`CR-CT-1`) | the whole cart — **every row**, grouped per row |
| Room (`CR`) | every cart/box/wall beneath it, each subdivided into its own rows/sections |

**This is the answer to the original "distinguish direct-vs-filed" framing:** yes, but by *grouping*
rather than by two separate lists. Spools sitting directly on the cart are simply the cart's own
group, alongside a group per row.

> 📌 **Why cart-level spools exist at all (Derek, 2026-08-13) — LEGACY, not corruption.** The cart
> labels were created *before* the rows existed, so spools filed then were assigned at the cart
> level and never moved down. Live dev today: `CR-CT-1` = 3 direct, `CR-CT-3` = 9, `CR-CT-4` = 2,
> while `CR-CT-2` = 0 direct with all 8 of its spools in `-R1/-R2/-R3`.
>
> Two consequences for whoever builds this:
> - **Do NOT "clean it up" as part of 37.4.** The grouped design above already renders it correctly
>   — it becomes the cart's own group. No migration is required for the view to be right.
> - **It is why the symptom looks inconsistent.** `CR-CT-2` scans as visibly *blank* (0 of 8), while
>   `CR-CT-1` returns 3 of 19 and reads as "worked" — the same defect wearing a less obvious face.
>   Use `CR-CT-2` when testing this, not `CR-CT-1`.
>
> Pushing those legacy spools down into real rows is a **separate, optional data-hygiene task** —
> Derek's call, and deliberately NOT a prerequisite for 37.4.

🔑 **It also dissolves the recorded contradiction.** The `/api/locations` occupancy rollup is ALREADY
transitive over `parent_id`, which is why a cart shows a Total including its rows while opening it
lists zero. Making contents transitive too means the number and the list finally describe the same
thing — so this fork is a bug fix, not just a preference.

### Fork 3 — bulk move DOES gain subtree scope, but it is the LAST thing to build

Derek: *"should be included, but we need to visualize this somehow in the UI so the user is aware
it's assigning across… This is such a rare instance… So very on the fence about this."*

Captured honestly, because the ambivalence is the useful part:

- **Include it** — but it is genuinely rare (cart→cart; section→section is likelier, e.g. wall
  storage where the destination section can't hold the exact count due to alignment).
- **It must be VISIBLE.** A move that silently reaches across sub-locations is not acceptable; the
  preview has to show the user it is assigning across.
- ⚠️ **Derek's own stated workflow probably supersedes it**: *"I'd probably just end up queueing
  everything in a section into the buffer, and just moving it into the location at that point."*
  The buffer already does this, today, with full visibility.

**Consequence for sequencing — build the visibility, then re-ask.** The
[🟢 interim recommendation](#-interim-recommendation-small-safe-survives-whatever-the-redesign-decides)
above (make the preview say `"N spools sit in 3 sub-locations and will NOT move"`) delivers most of
the value at a fraction of the risk. If the buffer flow is what actually gets used, full subtree
scope may never be worth its cost — so ship the visibility first and let real usage decide.

🚫 **HARD PREREQUISITE if it is built:** the L298 D2 safety contract currently depends on
LocationID **naming**, not structure. Widening bulk-move scope without first replacing it with an
explicit active-print/type guard means a room-level operation can reach a live toolhead.

⚠️ **Do not conflate this with the 2026-08-03 decision above.** They are separate:

- **Subtree SCOPE** (this fork, ✅ in) = the move *collects* spools sitting in sub-locations, instead
  of silently ignoring them. Everything lands at the single destination.
- **STRUCTURE-PRESERVING move** (2026-08-03, ⏸️ still deferred/possibly dropped) = also *mapping*
  each spool to the matching child at the destination, `R1`→`R1`, `R2`→`R2`.

Derek's wall-storage remark — *"sometimes you can't fit the exact number in a destination section,
just due to alignment"* — is precisely why structure-preservation stays deferred: there is often no
correct 1:1 mapping to preserve. The topology confirms it (`CR-CT-1` has `R1/R2/R3`; `DR-CT-1` has
`R1, R2-L, R2-R, R3-L, R3-R, R4-L, R4-R`).

### Fork 4 — `Max Spools`: blank/0 = unbounded; a real number is a real cap

Derek: *"shouldn't be meaningful if 0 or null/blank, if there's an actual number there then that's
probably a found good number and should be taken into consideration."*

**And its real purpose is slot integrity, not storage capacity.** Derek: *"Count is mostly there to
ensure that no more than X is in a given spot, so mostly to prevent a dryerbox from having 3 in it's
slot 1 (and to avoid conflicts with having 3 spools assigned to a slot that might be attached to a
toolhead."*

Why no pure-storage location sets it, in his words: capacity genuinely varies — *"it can vary on if
the spool is still in the box, or if mixed spool/brands, the spools themselves might vary enough to
cause a difference. (And if it's mixed 1kg & 250g, then that's a whole nother issue for counting.)"*

🔑 **This retroactively VALIDATES a finding filed as a gap.** The constraint note above says 27 rows
have `Max Spools = ''` — including every cart and cart-row — *"so L298's D3 capacity pre-flight
**cannot fire** on a cart→cart move."* That is now **correct behaviour, not a gap**: blank means
unbounded, and inventing a limit for storage rows would produce false blocks on exactly the
mixed-size inventory Derek describes. Do not "fix" it.

Treat `Max Spools` as: **absent / `''` / `0` → no cap enforced. Any positive integer → enforce it.**

---

## ❓ Fork 1 — STILL OPEN (the big one)

**Is the human-readable composite LocationID still the right model?** Nearly every remaining pain
point is downstream of it, and it deserves a worked comparison rather than a cold call.

⚠️ **Reframing to carry into that discussion:** the cluster-wide **NO FORCED RELABELING** invariant
constrains this far more than "opaque ids vs composite ids" suggests. Existing LocationIDs are
immutable and scanning stays `LOC:`/legacy/bare-compatible — so "opaque" cannot mean *replacing*
`CR-CT-1`. It can only mean **stop deriving structure from the string**: keep the composite as a
display label and scan alias, and let `parent_id` become the sole source of hierarchy. That is a
materially smaller and safer change than a model swap, and it is arguably what Group 34's Phase 0
already started. Put that option on the table before choosing.

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

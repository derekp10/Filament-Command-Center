# 🌳 Location System Redesign — Scoping & Evidence

> **Status:** 📋 SCOPING ONLY — nothing built, nothing decided beyond the two calls in §5.
> **Origin:** Derek, 2026-08-03, while driving the L298 Bulk Move panel on dev:
> *"I think we might need a refactor on how this whole location system works and displays the more I play around with it now… I feel like things need a re-design before we dig deep into developing a preserve-row-structure path."*
> **Standalone** — NOT nested under Group 34 or L298, both of which are complete. See
> [[feedback_standalone_followups_not_under_completed_epics]].

This doc exists so the evidence gathered on 2026-08-03 isn't lost. The *symptoms* are filed
individually in `Feature-Buglist.md`; what follows is the **shared root cause** underneath
several of them, plus the topology facts that constrain any redesign.

---

## 1. The one root cause behind the display + bulk-move symptoms

`locations_db.location_prefix` splits a LocationID on the **first dash only**
([locations_db.py:487-492](../../../inventory-hub/locations_db.py#L487)):

```python
return s.split('-', 1)[0].upper()      # "CR-CT-1-R1" -> "CR"
```

`spoolman_api._build_location_match` uses that as its only non-exact match
([spoolman_api.py:1320](../../../inventory-hub/spoolman_api.py#L1320)):

```python
elif locations_db.location_prefix(sloc) == target_loc_upper:
    match = True
```

Because **every** descendant of room `CR` — `CR-CT-1`, `CR-CT-1-R1`, `CR-WLN-R1-SC1` — has
first segment `CR`, the effective granularity is **binary**, not one-level:

| Query | Reaches |
|---|---|
| Room `CR` | its **entire subtree at any depth** (including 3-level `CR-WLN-R1-SC1`) |
| Cart `CR-CT-1` | **nothing** from its rows — exact matches only |
| Row `CR-CT-1-R1` | itself only |

⚠️ **The prefix branch is dead code for every non-room query.** Cart / Wall Shelf / Row /
Section queries are all exact-match-only. The docstring's framing ("a room query reaches its
cart-ROWS") undersells what it actually does and hides that nothing else gets subtree reach.

### 1a. Three symptoms, one cause

All three call the same matcher:

| Symptom | Call site |
|---|---|
| Opening/scanning a cart in the Location Manager lists nothing | `/api/get_contents` → `get_spools_at_location_detailed` ([routes_locations.py:648](../../../inventory-hub/routes_locations.py#L648)) |
| Bulk move with a cart source finds nothing movable | `get_spools_at_location_detailed_strict` ([spoolman_api.py:1486](../../../inventory-hub/spoolman_api.py#L1486)) |
| Clear / delete / deduct stay bounded | `get_spools_at_location` ([spoolman_api.py:1375](../../../inventory-hub/spoolman_api.py#L1375)) |

**One flat reader is answering three different questions** — *what is in here* (display),
*what may I move* (bulk), *what may I destroy* (clear/delete). Only the third needs to stay
flat. That conflation is the thing to fix structurally.

### 1b. The contradiction that's visible on screen

`/api/locations`' occupancy rollup is **transitive** over `parent_id` — distinct spool ids
across the whole subtree ([routes_locations.py:127-140](../../../inventory-hub/routes_locations.py#L127)).
So cart `CR-CT-1` displays a **Total that includes its rows' spools**, while opening that same
cart lists **zero**. Two different definitions of "what's in this cart", ~500 lines apart, on
the same screen. This is the concrete bug behind Derek's "seems like a bug".

### 1c. ⚠️ The D2 safety contract depends on NAMING, not structure

L298's locked **D2 = FLAT scope** decision is justified as "a room-level clear can't sweep an
actively-printing toolhead". That holds — but *only* because toolhead ids don't start with a
room prefix:

```
CORE1   Printer    parent=CR        XL     Printer    parent=LR
                                    XL-1..XL-5  Tool Head  parent=XL
```

A query for room `LR` misses `XL-1` because `location_prefix("XL-1") == "XL" != "LR"`. Nothing
structural enforces this. **Name a toolhead `LR-…` and a room-level clear sweeps a live print.**
Any redesign must replace this convention-dependent guard with a real one (an explicit
type/active-print check), not inherit it.

---

## 2. The pain-point cluster (all filed separately in `Feature-Buglist.md`)

1. **Blank LocationID accepted on save**, then "already exists" on re-edit with no value shown
   in either the edit window or the Location List. ✅ **Confirmed in live dev data** — row
   index 0 of `data/locations.json` is
   `{"LocationID": "", "Name": "TestCart", "Type": "Cart", "Max Spools": "0", "parent_id": "CR"}`.
   That is Derek's repro, **not test residue — do not delete it without asking.**
2. **Unassigned list on a new location** pushes UI elements off-screen; needs to be scrollable
   within the viewport and collapsible from anywhere in the list.
3. **Parent/child creation is tedious** — `+` on a parent doesn't autofill the child; no smart
   ID suggestions; and the human-readable-ID premise itself is in question
   (`CR-TC-R1` is hard to remember, set up, and keep sequential).
4. **Auto-generated IDs are finicky** (previously filed): changing a location's parent after
   creation doesn't update the generated id; numbering isn't topology-aware, so it proposes
   `R1` even when an `R1` exists instead of `R2`.
5. **Adding sub-locations is messy** (previously filed, older).
6. **Group 34 S5** — deliberately deferred; its plan mandates a `locations.json` backup as
   step 1.
7. **Display vs bulk-move scope** — §1 above.

---

## 3. What the real dev topology constrains

From `inventory-hub/data/locations.json` (56 rows, read-only inspection 2026-08-03):

- **Carts nest as `CR-CT-1` → `CR-CT-1-R1/R2/R3`.** Confirms the first-segment collapse in §1.
- **Per-row capacity is not tracked.** 27 rows have `Max Spools = ''`, including *every* cart
  and cart-row. Only dryer boxes and toolheads carry real numbers (`'4'`, `'1'`, `'6'`, `'2'`).
  → L298's **D3 capacity pre-flight cannot fire on a cart→cart move.**
- **No 1:1 row correspondence between real carts.** `CR-CT-1` has `R1/R2/R3`; `DR-CT-1` has
  `R1, R2-L, R2-R, R3-L, R3-R, R4-L, R4-R` (split rows). Three into seven — a structure-
  preserving mapper has **no automatic answer** on Derek's own furniture.
- **`Type` cannot identify a row.** 26 rows are Type `Cart`, including the `R1/R2/R3` children.
  Any structure-aware feature must walk `parent_id` and ignore `Type` entirely.

---

## 4. Decisions taken 2026-08-03 (Derek)

- **Structure-preserving bulk move (Cart A row1 → Cart B row1): DEFERRED, possibly dropped.**
  Derek: *"a feature I'm not 100% sure I'm going to use that often… might just make sense doing
  it using the existing bulk ability with the buffer and a location scan."* Combined with §3
  (no capacity data, no 1:1 correspondence) this is a large lift with an uncertain payoff.
  **Do not build it before the redesign settles the location model.**
- **The cart-display fix is folded into this redesign** rather than shipped as a point fix —
  Derek's call, because the display semantics are exactly what the redesign will change.

---

## 5. Open forks — need a decision before any build

1. **Is the human-readable composite LocationID still the right model?** Derek is questioning
   it directly (§2.3). Alternatives: opaque id + display path; or keep composite ids but
   generate/maintain them entirely automatically from the tree. This is the biggest fork —
   nearly every other pain point downstream of it.
2. **What should a subtree contents view show?** Derek's refinement: distinguish spools sitting
   **directly on the cart** ("unassigned at row level") from those filed into `R1/R2/R3`,
   rather than one undifferentiated list.
3. **Does bulk move gain subtree scope?** If yes, the §1c naming-dependent guard must be
   replaced with an explicit active-print/type check first.
4. **Does `Max Spools` become meaningful for carts/rows,** or stay unbounded there?

---

## 6. Interim recommendation (small, safe, survives the redesign)

Do **not** widen bulk-move scope yet — that means re-adding per-toolhead active-print guards
against location semantics that are about to change.

Instead, kill the *silent no-op* that reads as a bug: when a bulk-move source has nested
children, have the preview panel say so explicitly —
`"N spools sit in 3 sub-locations and will NOT move"`. Small, touches only the preview text,
leaves the locked D2 contract alone, and is still correct whatever the redesign decides.

---

## 7. Invariants any redesign must preserve

- A room-level clear/delete must **never** reach a live toolhead — but via an explicit guard,
  not the id-naming accident of §1c.
- `location_prefix` must keep returning `None` for a dash-free id — the `/api/locations`
  synthesizer's virtual-row parent stamp depends on it, so a Spoolman-native name doesn't
  self-parent ([locations_db.py:484](../../../inventory-hub/locations_db.py#L484)).
- `slot_targets` is **plumbing, not contents** — never auto-cleared by a move (L298 Phase 4).
- Bulk/clear/move must keep delegating to `perform_smart_move`; never hand-roll spool writes
  (CLAUDE.md "Spool / Filament write surfaces").

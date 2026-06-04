# Group 20: Toolhead Binding / Unbind-Propagation Cluster

**Branch name (when started):** `feature/toolhead-binding-cluster`
**Estimated effort:** ~6–10 hours (investigation-heavy; one sub-item needs a Derek decision)
**Risk:** **HIGH.** This touches `perform_smart_move` / `perform_smart_eject` / `perform_force_unassign` + the FilaBridge ↔ Spoolman one-spool-one-toolhead invariant — the exact subsystem behind the 2026-04-22 desync, 2026-04-27 outage, and a string of partial fixes (Group 13.6 → L204 → L206-still-open). Every change must be reproduced against the LIVE Docker container with real Spoolman (7913) + FilaBridge (5001) state, not just unit tests (see `[[feedback_adversarial_review_runtime_lens]]`).

> **Status: ✅ DONE 2026-06-04** on `feature/toolhead-binding-cluster` (branched off the L271 Phase-4 tip; pushed). **20.1 VERIFIED FIXED — no code change** (the cumulative L204 + Phase 3.5/4 work closed it). Live diagnostic (the doc's "reproduce first" rule) on BOTH an archived (#240) and non-archived (#225) spool came back CLEAN across all three scenarios: direct eject, auto-deploy cycle (box-slot→toolhead→eject), and cross-toolhead reassign (line 33) — eject/reassign always unmaps FilaBridge + clears Spoolman location & ghost-trail; already pinned by `test_smart_eject_clears_filabridge_and_unassigns_if_no_source` + `test_filabridge_move_ordering`. The L206 capture predates the fixes. **20.3 SHIPPED** (`daa31dc`): full toolhead-delete cascade (`logic.perform_toolhead_delete_cascade`) — direct spools→UNASSIGNED, ghost spools un-deployed (NOT yanked from their box — a latent bug in the old blanket `location=""`), FilaBridge unmapped, dryer `slot_targets` feeding it cleared, the entry pruned from the Printer row's `toolheads[]` (Phase-4 store), active-print gated, Activity-Log breadcrumb; 8 tests. **20.2 SHIPPED** (`c7c9847`): single-slot box (`Max Spools<=1`) auto-attach on assign / auto-detach on eject via `slot_targets` (lifecycle-driven; multi-slot boxes untouched); 9 unit tests + live-verified. **Decisions taken (Derek 2026-06-04):** orphan dest = UNASSIGNED+breadcrumb; 20.2 binding model = slot_targets reuse; new branch (Phase 4 ships independently first). **Open: PR/merge + the L271-Phase-4 prod deploy.** **Behavior note for review:** 20.2 makes single-slot box bindings lifecycle-driven, so a manual single-slot Feeds-editor binding now auto-clears on eject.
>
> **(original proposal below)** Triaged during the `feature/buglist-sweep-2026-06-03` autonomous sweep — bundled because all four items share the eject/assign/unbind code surface.

## Why these four are one group

They are all facets of the same architectural gap: **a spool's toolhead binding lives in three places that drift** — Spoolman `location`, Spoolman `extra.physical_source`/`container_slot` (ghost trail), and FilaBridge's toolhead→spool map — plus the dryer-box `slot_targets` binding. Moving/ejecting a spool must keep all of them consistent, and today some paths clear some-but-not-all.

## Items

### 20.1 — Eject/reassign doesn't fully clear the prior toolhead bind (buglist line 33 + L206)
**Buglist:** line 33 ("Changing a spool's location from a toolhead … should unload the filament from the toolhead on assignment to another location") + the L206 "continues to be inconsistency … ejecting doesn't fully clear all values, or only pulls it from the box, but not the toolhead" block (with the 10-minute Activity-Log capture as raw data).

**Current state of the code (read 2026-06-03):**
- `perform_smart_move` DRYER/GENERIC branches DO call `_fb_write(fb_origin[0], fb_origin[1], 0)` to unmap FilaBridge for the spool's prior toolhead (L204 fix, `logic.py:650`, `logic.py:691`) and pop `physical_source`/`physical_source_slot`.
- `perform_smart_eject` unmaps FilaBridge whether the spool is ON a toolhead (`logic.py:843`) or only FilaBridge-mapped (`logic.py:859`).
- So the FilaBridge side LOOKS covered. The L206 capture shows the symptom still recurs, so the remaining gap is elsewhere — **prime suspects:** (a) the **dryer-box `slot_targets` auto-deploy chain** (`logic.py:725-758`) re-deploys a spool onto the toolhead moments after an eject because the box slot is still bound, racing the unmap; (b) the **Spoolman `location` of the OTHER spool** in a shared box slot isn't updated; (c) the ghost-return loop (`perform_smart_eject` "saved_source"/slot-collision logic, `logic.py:893-921`) re-slots into a bound slot.
**Next step:** reproduce the L206 capture flow on the live container with DevTools + hub.log + a FilaBridge `/api/status` snapshot at each step; trace WHICH of the three stores is left stale. Do NOT patch blind — the capture says the obvious FilaBridge unmap is already there.

### 20.2 — Single-slot dryer-box auto-attach to toolhead (buglist line 37)
**Buglist:** line 37. **NEW feature, not a bug.** When a spool living in a **single-slot** box (`Max Spools <= 1`, e.g. PM Polymaker) is assigned to a toolhead, the box itself should be attached to that toolhead as a location, and detached when the spool is unloaded/ejected. Helps the Core One "missing box" notification for non-Core-One printers. **Restrict to `Max Spools <= 1` boxes only** (Core One by design runs box-less and takes loose spools).
**Doable, but** needs the binding model decided: is "box attached to toolhead" stored as a `slot_targets` entry on the single-slot box (slot "1" → toolhead LocationID), or a new field? Leaning `slot_targets` reuse (no schema change, matches the Phase 2/3 model in CLAUDE.md). Auto-attach on assign, auto-detach on eject — hook the same code points as 20.1 so they stay consistent.

### 20.3 — Propagate toolhead removal to Spoolman locations (buglist line 43)
**Buglist:** line 43. When toolhead rows are deleted via Location Manager, spools whose Spoolman `location` still references the deleted toolhead are orphaned (Derek hit this restructuring prod for the Core One). **NEEDS DECISION (Derek):** where do orphaned spools go — `UNASSIGNED`, `UNKNOWN` (the physically-lost bucket), or a prompt-the-user flow? Lean: `UNASSIGNED` with an Activity-Log breadcrumb naming the old toolhead (they're not lost, just unbound). Sibling of L271 Phase 4 (fold `printer_map` into `locations.json`) — doing Phase 4 first would make this fall out naturally (FK cascade). **Touches:** the `/api/locations` delete path + a migration sweep.

### 20.4 (implicit) — the architectural fix that dissolves all three
L271 (Location Manager redesign) Phases 3–4 give Toolheads a real `parent_id` and fold `printer_map` into `locations.json`. Once bindings are FK relationships instead of three drifting stores, 20.1/20.2/20.3 become trivial. **Consider whether to do L271 Phase 3–4 FIRST** rather than patch the symptoms again.

## Recommended order
1. Reproduce 20.1 live and nail the stale-store (cheap, diagnostic, unblocks understanding).
2. Get Derek's 20.3 orphan-destination decision.
3. Decide L271-Phase-3/4-first vs symptom-patch. If patch: ship 20.2 (most self-contained), then 20.3, then 20.1.

## Out of scope / do NOT do without live repro
- Any change to `_fb_write` / the FilaBridge unmap ordering — it's load-bearing and already patched multiple times.
- Multi-spool auto-deploy origin threading (`logic.py:744` note says multi-spool auto-deploy flows don't exist today).

# Group 21: New-Bug Sweep (2026-06-12) — card/modal + toolhead load/unload

**Branch name (when started):** `feature/new-bug-sweep-2026-06-12`
**Estimated effort:** ~4–6 hours (21.3 is the meaty one — backend smart-load; the rest are frontend/CSS/UX)
**Risk:** **MEDIUM.** 21.3 touches the one-spool-one-toolhead invariant (`perform_smart_move` auto-eject-resident) — the same load-bearing subsystem as Group 20, so reproduce against the LIVE Docker container before patching (see `[[feedback_adversarial_review_runtime_lens]]`). 21.1/21.2/21.4/21.5/21.6 are isolated card/modal/force-location UX and are low-risk.

> **Status: TODO** — filed 2026-06-12 by `/refresh-groups` (21.1–21.4). **21.5 + 21.6 added 2026-06-13** (two more small UX/state bugs). **⚠️ buglist line numbers below are stale:** 8 items were inserted at the top of `Feature-Buglist.md` on 2026-06-13, shifting everything +16 — 21.1–21.4 are now ~lines 19/21/23/25; 21.5 is line 9, 21.6 is line 13. Anchor by the quoted text, not the number.

## Why these are one group

A fresh batch of small bugs that cluster on shared surfaces, knockable out in one session:
- **Card / details-modal rendering + UX** — 21.1 (buffer-card badge overlap), 21.4 (details-modal stays open on queue), 21.5 (force-location double-click to assign). Touch `ui_builder.js` / `inv_details.js` + CSS.
- **Toolhead / buffer load-unload** — 21.2 (eject-from-dryerbox-slot-on-toolhead QR re-render), 21.3 (manual assign should auto-eject the resident), 21.6 (buffer spools return after scan-into-slot). Echo the now-DONE Group 20 cluster; 21.3 is the only one that reaches the backend move pipeline.

## Items

### 21.1 — Search badge covers the weight field on buffer-zone cards (buglist line 3)
**Buglist:** "Search badge (lower-right icon) now sometimes covers the weight field of a filament in the buffer zone. It was originally moved to prevent the weight QR code from being covered, so we need to re-evaluate its location again."
**Surface:** buffer-zone card layout — `static/js/modules/ui_builder.js` card render + the badge's CSS positioning.
**Direction:** the badge was relocated once already to clear the weight **QR**; the new spot now overlaps the weight **value text**. Find a position (or responsive rule) that clears BOTH the weight QR and the weight readout. Check the buffer-mode card specifically (vs search-mode), since the overlap is reported in the buffer zone. Verify visually at the 1600×1300 dev viewport (visual-regression baseline lives at `inventory-hub/tests/__screenshots__/chromium-1600x1300/`; recapture with `UPDATE_VISUAL_BASELINES=1` if the badge moves).

### 21.2 — Eject from a dryerbox-slot-on-toolhead (XL) refreshes the card but QR codes don't reload (buglist line 5)
**Buglist:** "Ejecting a spool from an attached dryerbox slot from the manage location on a toolhead (XL) causes the attached filament to refresh, but sometimes not reload the QR codes. This was done using the spool card's eject button."
**Surface:** the post-eject card re-render path + QR (re)generation. Likely `inv_details.js` / `ui_builder.js` re-render after the spool-card eject action.
**Direction:** **reproduce on the live container first.** Eject via the spool-card eject button on an XL toolhead whose dryerbox slot is attached; watch whether the re-render reruns QR generation or leaves the prior `<img>`/`<svg>` stale (async race — card HTML swapped before/without the QR pass). Likely a missing QR-regen call or a stale-node race in the silent-refresh path. **Related family:** L19 ("QR codes appear on the right side" of the in-progress modal) — both are QR re-render/layout issues; check whether they share a root before patching either.

### 21.3 — Manual interface assign to a toolhead should auto-eject the resident (buglist line 7)
**Buglist:** "Assigning a filament manually through the interface to a toolhead directly should auto-eject the currently loaded filament from the toolhead, not leave 2 filaments attached to the same toolhead. (This probably causes some sort of collision downstream in other code that might expect only a single filament in a toolhead. Which should always be the case, 1 spool per head.)"
**Current state of the code (read 2026-06-12):** `perform_smart_move` ALREADY has the auto-eject-resident path — `if is_printer or is_toolhead:` → `residents = spoolman_api.get_spools_at_location(target)` → Smart-Load eject ([logic.py:562-571](../../../inventory-hub/logic.py#L562)). The SCAN path enforces single-occupancy ([inv_cmd.js:714-723](../../../inventory-hub/static/js/modules/inv_cmd.js#L714)).
**Direction:** the gap is the **manual interface assign** path — find which UI action Derek means (Location Manager slot-click `_confirm…Assign`, Force-Location dialog, a details-modal "assign to toolhead", or Quick-Swap) and confirm whether it (a) routes through `perform_smart_move`'s toolhead branch at all, or (b) passes a flag/target shape that skips the resident eject. **Reproduce live** with two spools + one toolhead; check Spoolman `location` + FilaBridge map after the manual assign. Do NOT patch `_fb_write` / unmap ordering blind (load-bearing — Group 20 note).

### 21.4 — Queueing a label from the spool-details modal closes the modal (buglist line 9)
**Buglist:** "Queueing a label for a spool from the spool details modal shouldn't cancel out the modal, it should stay open."
**Surface:** `inv_details.js` spool-details queue-label handler.
**Direction:** the queue action currently dismisses the details modal (probably a refresh/close side-effect or an unintended `.hide()`); keep the modal open and just toast the outcome. **Precedent:** Group 17.2 (L146) made "Queue all active spools" stop auto-OPENING the Print Queue modal and toast instead — this is the sibling fix (stop auto-CLOSING the details modal). Mirror that pattern. Add a small E2E asserting the details modal is still `.show` after queueing.

### 21.5 — Double-click a force-location override entry should assign it without clicking Force (buglist line 9, added 2026-06-13)
**Buglist:** "Double clicking on a force location override entry should just assign that entry without having to click force."
**Surface:** the Force-Location dialog `window.promptEditLocation` ([inv_details.js:937](../../../inventory-hub/static/js/modules/inv_details.js#L937)).
**Direction:** add a `dblclick` handler on each location list entry that selects it AND triggers the same commit path the Force button runs (one gesture instead of click-then-Force). Keep the single-click + Force button working (don't break the deliberate two-step for keyboard users); double-click is a shortcut on top. Mind the keyboard-nav idiom (arrow + Enter already confirms — `dblclick` is the mouse equivalent).

### 21.6 — Buffer spools sometimes return to the buffer after being scanned into a slot (buglist line 13, added 2026-06-13)
**Buglist:** "Sometimes filaments that have been in the buffer for a bit (usually after a weigh update) after being scanned into a slot, return back into the buffer. (Could also be some weird issue with having FCC open on two PCs at the same time?)"
**Surface:** buffer ↔ scan-assign ↔ heartbeat-refresh state (`state.heldSpools` / `loadBuffer` / `liveRefreshBuffer` / the dashboard_pulse buffer renderer). **NEEDS LIVE REPRO.**
**Direction:** suspect a **stale-buffer race** — a spool is assigned out of the buffer, but a pulse/refresh that was in flight (carrying the pre-assign buffer) re-renders and re-adds it; the "after a weigh update" + "two PCs" hints point at a heartbeat carrying stale `heldSpools` (a second client's buffer, or a pre-assign snapshot) clobbering the post-assign state. Reproduce with DevTools: watch whether a `dashboard_pulse`/`loadBuffer` tick repopulates the buffer right after the successful slot-assign, and whether two open clients share/overwrite buffer state. Possibly related to the L28 in-flight-guard work (a pulse landing after a mutation) — check the buffer renderer honors the latest assign.

## Recommended order
1. **21.4** (most self-contained — one handler, clear precedent in 17.2).
2. **21.5** (small `dblclick` handler on the force-location list).
3. **21.1** (CSS/layout + a visual-baseline recapture).
4. **21.2** (needs live repro; may share a root with L19 — investigate together).
5. **21.6** (needs live repro; possible multi-client/stale-pulse race — pair the investigation with 21.2 since both are post-action refresh races).
6. **21.3** (live repro + backend; the meaty one — leave for last, or split to its own session if the manual-assign path turns out to need a real smart-move rework).

## Out of scope / do NOT do without live repro
- Any change to `_fb_write` / the FilaBridge unmap ordering (21.2/21.3) — load-bearing, patched multiple times (Group 20).
- Folding 21.3 into a broader "every assign path goes through one smart-move entry" refactor — flag it if the repro points that way, but don't start it under this sweep.
- A real multi-client sync transport for 21.6 — if the repro proves it's a genuine two-PC concurrency issue (not a single-client stale-pulse race), that's L302 (cross-browser sync, ON HOLD), not this sweep.

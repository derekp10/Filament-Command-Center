# Group 15: Canonical Overlay-Mount Helper

**Branch name:** `feature/canonical-overlay-mount`
**Estimated effort:** ~5–7 hours
**Risk:** Medium-High — touches every inline overlay surface in the app; regression-prone across many user flows

## Goal

Build **one canonical `mountOverlay()` helper** that every inline overlay uses, with a documented z-index ladder above Bootstrap's modal stack, a focus-guard pattern that doesn't depend on DOM-subtree mounting, and a uniform cleanup-on-host-close lifecycle. Replace every ad-hoc overlay implementation across the codebase with calls into this helper.

> 🩹 **"Fixed for good" charter.** Derek's note in [Feature-Buglist.md](Feature-Buglist.md#L17): every few weeks a new modal-on-modal or overlay-on-modal flow lands its top layer BELOW the host modal or backdrop. Most recent: 2026-05-11 Group 13.1 first attempted mount-inside-modal to defeat Bootstrap's `_enforceFocus`, inherited a worse z-index problem, reverted to focus-guard. We want a single source of truth so the next overlay author can't get this wrong.

## Items to Complete

### 15.1 — Build the helper
**What:** New module `inventory-hub/static/js/modules/overlay_mount.js` exporting `mountOverlay({ host, content, options }) → { element, cleanup }`.

**Required behaviors:**
- **Mount target:** Always `document.body` (avoids Bootstrap modal subtree z-index containment — lesson from 13.1's revert in commit `89c6f39`)
- **Z-index ladder:** Documented constants for every overlay tier:
  - `OVERLAY_Z.STANDARD` (e.g. 20000) — single overlay on top of any modal
  - `OVERLAY_Z.CONFIRM` (e.g. 20100) — confirm overlay on top of a standard overlay
  - `OVERLAY_Z.TOAST` (e.g. 30000) — toast layer above everything
- **Focus guard:** Capture-phase `focusin` listener on `document` that calls `stopPropagation` when target is inside the overlay, neutralizing Bootstrap's `_enforceFocus` without subtree mounting (the working pattern from `89c6f39`)
- **Bootstrap `data-bs-keyboard="false"`** awareness: if the host modal has it, the overlay can own Escape handling without double-handling races (lesson from Group 4 delete-overlay)
- **Cleanup hook tied to host-close:** if the host modal/offcanvas closes, the overlay is removed AND its `cleanup()` runs — no overlays outliving their parent
- **Backdrop occlusion handling:** when an overlay is open, any `<select>` or offcanvas-search underneath the host gets `pointer-events: none` until the overlay closes (lesson from `test_ui_details_modal_e2e` flake — buglist L233)
- **Idempotent cleanup:** calling `cleanup()` more than once is a no-op

**Files:**
- `inventory-hub/static/js/modules/overlay_mount.js` — new module
- `inventory-hub/static/css/overlays.css` — z-index ladder + occlusion CSS (or wherever overlay CSS lives today)
- `inventory-hub/tests/test_overlay_mount_helper.py` — new test file: mount/cleanup, focus-guard, z-index, host-close cascade

### 15.2 — Migrate existing overlay surfaces
**What:** Replace each ad-hoc overlay implementation with a `mountOverlay()` call.

**Surfaces to migrate (verify each is on the list; remove from migration plan only if confirmed using a different pattern):**
- `<WeightEntry>` overlay — [weight_entry.js](inventory-hub/static/js/modules/weight_entry.js)
- Force-location modal escape-confirm — `#fcc-escape-confirm-overlay`
- Quick-Swap confirm overlay — `#fcc-quickswap-confirm-overlay`
- Missing-tare prompt — Group 13.7's Skip/Provide/Cancel dialog
- Delete-confirm overlay — Group 4 delete-flow (`#fcc-delete-confirm-overlay`)
- Force-eject confirm — Group 13.8's confirm modal
- Duplicate picker — [duplicate_picker.js](inventory-hub/static/js/modules/duplicate_picker.js)
- Edit-slicer-profile pencil overlay — Group 5's `promptEditSlicerProfile`
- Vendor edit modal create/edit overlay — Group 6's `openVendorEditModal`

**For each surface:**
- [ ] Replace mount logic with `mountOverlay()` call
- [ ] Remove ad-hoc z-index CSS (defer to the ladder)
- [ ] Remove ad-hoc focus-guard / `_enforceFocus` workarounds
- [ ] Verify existing tests still pass; add a `mountOverlay()`-specific assertion if useful

### 15.3 — Documentation
**What:** Update `CLAUDE.md`'s "Project Conventions" section.

**Content:**
- Replace the existing "No nested `Swal.fire()`" + "inline overlay div pattern" subsection with a "Use `mountOverlay()` for any new inline overlay" rule
- Document the z-index ladder constants
- Document the focus-guard pattern (so future authors don't try to mount-inside-modal again)
- Cross-reference this group's task file as the definitive guide

**Files:**
- `CLAUDE.md`

## Symptom checklist for "is this another Z-order incident"

From Derek's buglist entry, these symptoms should all be impossible after the helper lands:
- Click triggered something, but I can't see it
- Overlay rendered behind sibling modal chrome
- Brief processing flash and then "nothing"
- Inline overlay's Escape closes BOTH the overlay and its host modal (double-handling)
- Overlay lingers after host modal closes
- `<select>` dropdown intercepts click events that should hit the overlay

Each symptom maps to a documented behavior in 15.1's required-behaviors list.

## Definition of Done

- [ ] `mountOverlay()` helper exists with full test coverage
- [ ] Every overlay surface listed in 15.2 routes through the helper
- [ ] Full regression sweep passes (anti-flake — coordinate with Group 14)
- [ ] `CLAUDE.md` documents the convention; symptom checklist is enforceable as a code review rubric
- [ ] At least one of the "would have been Z-order incident #N" symptom checklist items has a regression test

## Dependencies

- Independent. Can ship before, in parallel with, or after Group 14. Doing Group 15 first would shrink Group 14's scope (specifically 14.3) since the offcanvas-occlusion handling lives in `mountOverlay()`.
- Touches surfaces from Groups 4, 5, 6, 9, 13 — all `DONE` or covered by their respective task files. No active-group conflicts.

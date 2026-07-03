# Group 31: Weight-Entry Fixes & Unification

**Branch name (when started):** `feature/group-31-weight-entry-fixes-unification`
**Estimated effort:** ~5–9 hours (2 discrete bug fixes + a scoped WeightEntry-migration slice)
**Risk:** **MEDIUM.** Touches weight write surfaces — the same class behind the 2026-04 prod outages. Every write MUST follow the CLAUDE.md "Spool / Filament write surfaces" conventions (`compute_dirty_extras` + `SYSTEM_MANAGED_EXTRAS`, surface `LAST_SPOOLMAN_ERROR`, `update_spool`/`_or_raise`). ⚠️ Sending `initial_weight` through `/api/spool/update` runs `_auto_archive_on_empty`/`_auto_unarchive_on_refill` — mind the archive side-effects (that's exactly item 31.2).

> **Status: TODO** — filed 2026-07-03 by `/refresh-groups` (Derek's call: one Weight-Entry group). Three weight-surface items from Derek's 2026-07-03 buglist edits (`fdb3342`/`e2171e2`). Respects the CLAUDE.md rule "don't add new weight-entry UI before the unified `<WeightEntry>` migration — feed requirements into it" by making THIS group that migration slice: fix the two discrete bugs (31.2/31.3) now, and route 31.1's new input through the existing `<WeightEntry>` component rather than bolting on a fourth ad-hoc weight form.

## Why these are one group

All three are the fragmented weight-entry sub-system CLAUDE.md flags: the wizard weight fields (`inv_wizard.js`), the quick-update weight path, the bulk weigh-out modal (`inv_weigh_out.js`), and the `resolveEmptySpoolWeight` cascade (`weight_utils.js`). They share the `<WeightEntry>` component (`weight_entry.js`, built in Group 12) that the remaining surfaces still haven't fully adopted. Fixing them together (a) lets the discrete bugs land now instead of waiting on a full unification epic, and (b) advances the "every weight surface reuses `<WeightEntry>`" migration on the surfaces Derek is actively hitting.

## ⚠️ Deploy-gap context (verified 2026-07-03)

Derek's report bundled a "1000g restrictions still happening" complaint. **That half is a prod-deploy gap, not new work:** Group 24 (weight_is_default / kill hard-coded 1000g) is live + served on the **dev** container (verified: 7× `weight_is_default` in served `inv_wizard.js`) but **prod build `93d6d5be` (2026-06-29 10:54) predates the Group 24 merge** — prod never got it. **A `dev`→`main` release closes the 1000g complaint outright.** The work below is the residual that a deploy does NOT fix.

## Items

### 31.1 — (N2) Spool-weight data entry is confusing; quick-update lacks a total-weight input
> Derek: "had issues getting it to take the total weight from a scale, and properly deducting the known empty spool weight — I had to enter data in two different fields to get it to recalculate correctly … the quick update weight had no way to input total spool weight … it's like spool weight is being used to fill in the initial total used weight."

**In scope (the residual after the Group 24 deploy):**
- **Add a gross/total-weight input mode to the quick-update weight path.** Today the user can't enter a scale gross reading there and have tare auto-deducted — route the quick-update through the `<WeightEntry>` component's existing modes (`gross` / `net` / `additive` / `set_used`) so "put it on the scale, type the gross" works with `resolveEmptySpoolWeight` (`weight_utils.js`) doing the tare deduction. Do NOT build a new bespoke input.
- **Clarify the multi-field confusion** — Derek had to touch two fields to force a recalc. Surface the computed `used_weight`/remaining preview before submit (the `<WeightEntry>` design already calls for this) so one input recalculates everything.
- **Confirm the "spool_weight fills initial/used" smell** — trace whether the wizard is mis-mapping tare into `initial_weight`/`used_weight` and fix the mapping if so.

**Explicitly deferred:** the residual 1000g complaint → closed by deploying Group 24 (see deploy-gap note above); no code here.

### 31.2 — (N3) Setting remaining-weight in the add/edit wizard doesn't auto-assign unassign+archive flags
> Derek: "Setting remaining weight in add/edit filament wizard doesn't seem to auto assign the unassign and archive flags to the spool. Can't remember if this was by design or just a missed bug."

The generic `/api/spool/update` path runs `_auto_archive_on_empty` / `_auto_unarchive_on_refill`, but the **wizard** edit-spool save goes through `api_edit_spool_wizard` — verify whether that path triggers auto-archive/unassign when remaining hits 0, and wire it if not. **First decision:** is this by-design (the wizard deliberately doesn't auto-archive) or a gap? If a bug, mirror the auto-archive/unassign behavior, being careful with the `initial_weight` side-effects CLAUDE.md warns about (don't accidentally archive a loaded spool). Pin the chosen behavior with a test.

### 31.3 — (N4) Bulk weigh-out modal loses keyed-in text on per-item save redraw
> Derek: "Saving one line item resets the text box on other items in the list on re-draw. We should preserve the text, or provide a save-all function/button, or at least warn that we could lose data."

In the bulk weigh-out modal (`inv_weigh_out.js`), saving one row re-renders the list and blows away the other rows' un-submitted input values. **Preferred fix:** preserve the keyed-in values across the redraw (re-render only the saved row, or snapshot+restore sibling input values after re-render). **Alternative/also:** a "Save All" button. **Minimum:** warn before a redraw that would discard unsaved input. Preserve-text is the least surprising.

## Cross-references (do together if convenient)
- **Archived-spool empty-weight row** (buglist line 5, NOT-Grouped): same `<WeightEntry>` surface — (1) the empty-weight field only accepts the up/down scroller, no type-in; (2) combine the back-to-back spool-empty + filament-empty prompts; (3) offer to propagate the entered empty weight up to the vendor `empty_spool_weight`. Strong candidate to fold into this group's execution since it's the same component + `resolveEmptySpoolWeight` cascade. Cross-ref, not auto-folded (it's a separately tracked item — confirm with Derek before pulling it in).
- **Unified `<WeightEntry>` component** (`weight_entry.js`, Group 12) + `weight_utils.js` `resolveEmptySpoolWeight` — the canonical surfaces; route 31.1 through them.

## Recommended order
1. **31.3** first — self-contained frontend bug in one modal, no write-surface risk (it's a re-render/state bug), quick win.
2. **31.2** — decide by-design-vs-bug, then wire + pin; touches the archive side-effect, do it with the write-surface conventions open.
3. **31.1** — the WeightEntry-migration slice; the biggest lift. Land AFTER the Group 24 deploy so the 1000g half is already gone and you're only building the total-weight input + preview.

## Out of scope / do NOT do
- Building a NEW bespoke weight input for quick-update — reuse `<WeightEntry>` (CLAUDE.md convention).
- Any write that bypasses `compute_dirty_extras` / `update_spool` (sibling-wipe + silent-failure outage class).
- The 1000g complaint as code — it's a deploy gap (deploy Group 24). Don't re-implement what's already on dev.

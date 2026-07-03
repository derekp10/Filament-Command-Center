# Group 24: Weight Transparency & 1000g-Default Correctness

**Branch name (when started):** `feature/weight-transparency-1000g`
**Estimated effort:** ~3–5 hours (F ~1–2 hrs; K ~2–3 hrs)
**Risk:** **LOW-MEDIUM.** F is a purely additive Activity-Log line (the `pre` snapshot is already in hand). K touches the wizard create-path + the printer-status display + (read-only audit of) the Prusament L200 correction; the L200 *write* path is already hardened (don't change its used-preserving model without a Derek decision). Per CLAUDE.md "Weight-entry surfaces (known fragmentation hot-spot)" — keep changes on the existing funnels, do NOT add new weight-entry UI (that's gated behind the unified `<WeightEntry>` Phase 2).

> **Status: ✅ DONE 2026-07-01** (`feature/group-24-weight-transparency-1000g` → `dev`). Both items shipped. **24.F**: shared `_log_manual_weight_change` helper emits a before➔after Activity-Log breakdown, wired into BOTH manual funnels (`api_spool_update` + `api_edit_spool_wizard`). **24.K**: `weight_is_default` honored on the wizard create-path (`extractSpoolFieldsFromTemplate` + `applyFilamentFieldsFromTemplate` + calc-helper aborts), the Amazon/3DFP parsers, and the edit-filament import preview (`computeFilamentBackfillDiff`); printer-status bar scaled to the spool's own `initial_weight` (backend `_build_location_match` exposes it). L200 correction untouched; no new weight UI. Grounded (5-agent map) → 22-agent adversarial diff-review (4 of 18 findings confirmed + applied) → full `RUN_INTEGRATION=1` sweep 1759 passed / 21 pre-existing (zero regressions). The 21 pre-existing reds are filed as a standalone `## 🧪 Testing` cleanup row in `Feature-Buglist.md`. Original grounding below.
>
> _Original (filed 2026-06-15 by `/refresh-groups`, both items grounded against real code by a 7-agent triage workflow + a direct `1000` grep):_ Two items on the weight-write surface: **F** = manual weight changes leave no before→after trail; **K** = hard-coded 1000g spool logic that should be variable by size.

## Why these are one group

Both live on the **weight-write / Prusament-weight surface** CLAUDE.md flags as fragmented. F adds transparency to the manual-adjust funnel; K kills the silent 1000g assumptions on the same create/correct paths. A reviewer should see the weight-write changes together. **Cross-ref (NOT folded in):** the standalone NOT-Grouped row *"Archived-spool empty-weight entry — type-in + combine prompts + propagate to vendor"* is the same surface but is **gated behind the unified `<WeightEntry>` component** (new weight UI) — it stays deferred; only F (a log line) and K (a default-correctness audit, no new UI) are actionable now.

## Items

### 24.F — Manual weight adjustments should log before → after (buglist 2026-06-15, item F)
**Buglist:** "All manual weight adjustments should display what it was before, and what it is now. Basically give a breakdown."
**Grounded:** every manual surface funnels through `window.saveSpoolWeight` ([inv_weigh_out.js:317](../../../inventory-hub/static/js/modules/inv_weigh_out.js#L317)) → POST `/api/spool/update` → `api_spool_update` ([app.py:1122](../../../inventory-hub/app.py#L1122)). That handler **already fetches the pre-update spool** (`pre = spoolman_api.get_spool(spool_id)` at `app.py:1142`) but uses it only for the `pre_archived` flag — it writes **no** Activity-Log delta. `spoolman_api.update_spool` logs only auto-archive/unarchive transitions. The pre-submit overlay previews (`weight_entry.js:310`, `inv_weigh_out.js:252`) are ephemeral, nothing persists.
**Reference pattern to copy:** the deduct paths already log before→after — `_apply_usage_to_printer` ([app.py:4129](../../../inventory-hub/app.py#L4129)) writes `✔️ Auto-deducted {g}g … [{remaining}g at start ➔ {new}g remaining]`; cancel-deduct confirm at `app.py:5141`.
**Fix:** in `api_spool_update`, after a successful `update_spool` where weight changed, emit a `state.add_log_entry` with old (from `pre`) vs new `used_weight` + recomputed `remaining` (the `pre` snapshot is already there). **Scope gate (Derek):** fire only when `used_weight`/`remaining_weight`/`initial_weight` is in `updates` so location/extra-only edits don't spam the log.
**Surface:** `app.py:1122-1174` (`api_spool_update`); reference wording at `app.py:4129` / `5141`.

### 24.K — Audit + kill hard-coded 1000g spool logic; make weight variable by size (buglist 2026-06-15, item K)
**Buglist (Derek's reframe 2026-06-15):** "More an investigation into whether we have any hard-coded 1000g spool logic. All logic should be variable depending on size — and might be determinable if we weigh a new spool where the empty spool value is known." (Original symptom: correcting Prusament product-ids leaves a leftover REMAINING amount on some spools.)
**Grounded — three buckets of hard-coded 1000g (grep + agent):**
1. **Wizard create-path leak (the real bug).** `extractSpoolFieldsFromTemplate` ([inv_wizard.js:2511-2514](../../../inventory-hub/static/js/modules/inv_wizard.js#L2511)) sets `override.initial_weight = Number(temp.weight)` **without consulting `weight_is_default`** — and the Prusament parser emits `weight:1000.0` whenever the page omitted net weight, so a created spool bakes in a bogus 1000g initial. Plus the silent `|| 1000` form defaults at `inv_wizard.js:1099, 1116, 2440, 2665, 3157`.
2. **Parser fallbacks.** `external_parsers.py:178` (`net_weight = … else 1000`, tracked by the `weight_is_default` flag at `:193-194`), plus less-guarded hard `1000.0` at `external_parsers.py:339, 358, 456` in the other parsers.
3. **Printer-status bar display.** `inv_printer_status.js:211-212` hard-codes "1000g = full bar" — a 500g spool at 500g shows a 50% bar. Should scale to the spool's own `initial_weight`.
**Already correct (don't touch the model):** the L200 correction path REFUSES to propose the default — `_compute_prusament_spool_weight_diff` ([app.py:2414](../../../inventory-hub/app.py#L2414)) sets `scanned_net=None` when `weight_is_default`; the apply path writes only `initial_weight`/`spool_weight` and PRESERVES `used_weight` (the confirmed-with-Derek 2026-06-05 model). The "leftover remaining" is mostly **by design** (Spoolman derives `remaining = initial − used`, no scale reconciliation) — the actionable bug is the **legacy-1000 leak** (a spool already carrying a bogus 1000 initial is never corrected when the page still omits net).
**Fix:**
- (clear bug) make `extractSpoolFieldsFromTemplate` + the `|| 1000` sites **honor `weight_is_default`** — skip/require the weight instead of silently assuming 1kg.
- (display) scale the printer-status bar to `initial_weight`, not a fixed 1000.
- (audit) confirm the non-Prusament parser fallbacks are flagged/guarded the same way.
- (Derek's idea) **derive tare from a weigh-in:** when a NEW full spool is weighed and the net (filament) weight is known, `tare = measured_gross − known_net` — surface as an offer rather than assuming a constant.
**Open scope Q (Derek):** the used-preserving "leftover remaining" is partly by-design — a scale-based reconciliation step would be NEW weight-entry UI → feed it into the unified `<WeightEntry>` design, don't build ad-hoc here.
**Surface:** `inv_wizard.js:2511-2514` + `1099/1116/2440/2665/3157`; `external_parsers.py:177-194, 339, 456`; `inv_printer_status.js:211-212`; read-only ref `app.py:2373-2470` (`_compute_prusament_spool_weight_diff`) + `app.py:1177-1234` (`api_prusament_apply_weights`).

## Recommended order
1. **24.F** (small, low-risk, copy the deduct-path wording — quick transparency win).
2. **24.K** create-path `weight_is_default` guard + the printer-status-bar scaling (the two clear, uncontroversial fixes). Then surface the scale-derived-tare idea + assess the parser fallbacks; defer any scale-reconciliation to the unified `<WeightEntry>`.

## Out of scope / do NOT do
- New weight-entry UI (scale-reconcile dialogs, etc.) — gate behind the unified `<WeightEntry>` Phase 2 per CLAUDE.md; don't build ad-hoc.
- Changing the L200 used-preserving correction model (confirmed-with-Derek 2026-06-05) without an explicit decision.
- Raw Spoolman PATCH — route weight writes through `update_spool` / `compute_dirty_extras`.

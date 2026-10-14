# Group 43: 💸 Deduct Recovery & Attribution

**Branch name (when started):** `feature/group-43-deduct-recovery`
**Estimated effort:** MEDIUM (~8–12 h, 1–2 sessions). Double-deduct guard ~1 h · log wording ~0.5 h · pick-the-spool on reviews ~2–3 h · shortfall review ~3–4 h · 22.5 ~1–2 h · retry idempotency ~1–2 h · tests throughout.
**Risk:** **MEDIUM–HIGH.** Every item writes `used_weight` or the exactly-once ledger. There are two failure modes to design against: a **double-deduct** (grams charged twice) and a **silent loss** (grams charged to nobody). Each sub-task must name which one it could cause and pin it.

> **Status: `PARTIAL` — 43.1, 43.5, 43.3 and 43.6 shipped in the 2026-10-13 overnight run (merged to `dev`, `985aba8`; see `completed-archive.md`). 43.4 shipped with Group 39 (`c389e26`). Left: 43.2, answered by Derek on 2026-10-13 (a picked archived spool is charged and stays archived; see 43.2 below) and ready to build.**
> Grouped by Derek's call (2026-10-12). The unblocked deduct work stops waiting behind [Group 22](22-filabridge-phase2-detection-deduct-followups.md), whose only open item (the M600 multi-color split) is blocked on print data.
> It absorbs the "unblocked 22.5" that [Group 41's plan](41-honest-bulk-results.md) asked to file under Group 22 (it never landed there), and the standalone cancel-deduct retry row (Derek, 2026-10-12: "Into Group 43").
> Code anchors were read on `dev` @ `3949aba`. Line numbers drift, so re-grep the named function before editing.

---

## ⚠️ Read this first

- **The real loss that motivates this group** (prod, read-only, 2026-10-08):
  - Job **1104** `/usb/MAIN-B~1.BGC` on the Core One INDX needed **61.32 g**.
  - Spool #99 held 34.2 g, so the deduct clamped, zeroed #99 and auto-archived it.
  - **The other 27.12 g was charged to nothing.** The ledger entry has no `shortfall` field, so the only record is an Activity Log WARNING.
  - Jobs 1105/1106 (same file) were `no_spool` reviews that got dismissed. Job 1107 deducted cleanly.
- **Fix 43.1 before 43.2.** Today the latent double-deduct is only a wrong ledger number plus a WARNING. Once a shortfall becomes actionable (43.2), it generates real double-deducts.
- **Exactly-once is keyed `printer::job_id`**, with no position component:
  - `print_deduct_ledger._key` (`print_deduct_ledger.py:36`)
  - `cancel_review_store._key` (`cancel_review_store.py:29`)

  A job already in the ledger counts as "processed". That's why a naive follow-up is refused (see 43.2).
- **Drive the real deduct engine in tests.** Use a fake Spoolman that mirrors the real `update_spool` merge and the `used_weight ≤ initial_weight` cap ([[mocked engine hides chain bugs]]). `FakeSpoolman` / `WireSpoolman` in `tests/test_active_print_chain_confirm.py` is the pattern. Group 39 plans to extract it into `tests/move_engine_harness.py`; reuse that if it exists by then.
- **Prove each new test fails on the old code** (`git archive HEAD` into a scratch dir).
- **Container runtime is Python 3.9.**

---

## Items covered (quoted from `Feature-Buglist.md`)

| # | Buglist item | Direction |
|---|---|---|
| **43.1** | 🔴 **"Latent double-deduct: a spool with no `initial_weight` of its own."** `_apply_usage_to_printer` sets `initial = float(spool_data.get('initial_weight', 0) or 0)` (`print_deduct.py:332`). So `actual_g` (`:344`) is 0 and the ledger records **0 g**, while the write itself is unclamped and the full grams land on the spool. | Filed fix: mirror the inherit-weight fallback `_auto_archive_on_empty` already uses (`spoolman_api.py:201-205`), i.e. fall back to the filament's net weight. Filed note: *"Needs a Spoolman read to know whether any of Derek's loaded spools are currently in that shape."* Read-only, on dev AND prod. |
| **43.2** | 💸 **"A PARTIAL deduct with a leftover only WARNS — no review, and the ledger doesn't even record the shortfall."** Also the spool-join triage's piece (2): *"the follow-up vehicle Derek asked for."* | The filed design (2026-10-08) is summarised below. |
| **43.3** | Derek, on the two `no_spool` warnings for job 1104's file: *"This should have an option to select a different loaded spool, or any spool. Currently the bgcode directs to toolhead 1, but I've been printing from toolhead 2, which was done on the printer when selecting an existing file to print. If possible, we need to check for this scenario, and try to accommodate it. Or give an option to easily re-direct the deducts to the correct toolhead."* Also 22.5(b): *"A `no_spool` Review card never names a spool. Its Apply charges whatever is on the head at that moment, which can be a spool loaded after the print."* | A spool/toolhead picker on the review card (below). FCC probably can't detect a printer-side tool remap: PrusaLink exposes nothing per slot ([[reference_fcc_indx_hardware_and_gcode]]). So the picker is the vehicle. |
| **43.4** | 22.5(a), from *Found while briefing the six open decisions* item 6: *"A cancelled print's review silently drops an uncharged head. Its rows and total include only heads where it found a spool, and confirming records the ledger with no shortfall check."* | Carry every head in the usage map into the review, including heads with no spool, as a visible "no spool" row. Build it alongside [Group 39.4](39-confirm-on-every-door.md): D6 makes "a head emptied mid-print" an everyday confirmed action. |
| **43.5** | Derek: *"Because I'm running multiple printers with multiple toolheads we should probably change these log messages to report the toolhead/location and printer so it's clearer where the deduction occurred."* | Name the printer and toolhead on the per-spool line (`print_deduct.py:347`, where `printer_name` and `loc_id` are in scope), and the toolhead(s) on the summary line (`:830`). |
| **43.6** | ⚠️ *Deferred findings from the session-diff adversarial review (2026-08-05)*, last bullet: *"the cancel-deduct retry re-derives grams from CURRENT state rather than from the review record, which is what made a mis-reported write double-deduct. Raising the timeout to 15s narrows the window; making the retry idempotent closes it."* | The confirm-apply retry derives from the stored review record, not from the spool's current `used_weight`. |

### Excluded: these need print data first and stay standalone

- **SpoolJoin detection** (piece (1) of the spool-join triage). It needs a pollable signal for the printer's auto-switch. The ATTENTION-park and resume swap-diff logging added 2026-10-08 will show whether one exists on the next SpoolJoin print (⏸️ PENDING DEREK). Derek's 2026-10-13 idea of a toolhead-change history is recorded as a follow-up at the end of 43.2.
- **📉 The cancel-path prefix parser lands ~7% below the footer on a multi-tool INDX print.** It needs the INDX `.bgcode`. `tests/fixtures/` holds only `sample.bgcode`, so re-pull the file read-only or use the ⏸️ PENDING DEREK multi-slot capture.
- **Group 22's M600 multi-color split**: blocked on a real M600 print.

---

## Current behaviour (code anchors, `dev` @ `3949aba`)

| Function | Where | Relevance |
|---|---|---|
| `_apply_usage_to_printer` | `print_deduct.py:265` | The canonical per-toolhead loop: `initial` at `:332`, the `actual_g` clamp at `:344`, the per-spool log at `:347`. |
| `_record_applied_deduct` | `:373` | Records the ledger at `:401`, **then** computes the shortfall at `:403`. |
| `_is_sid_swap` | `:473` | Needs a spool on both sides, so an emptied head is not a "swap" (43.4). |
| `deduct_cancelled_print` | `:631` | Stashes a review only on `spools_updated == 0` (`:677`). |
| `deduct_completed_print` | `:701` | Same at `:811`; summary log at `:830`. |
| `_resolve_usage_to_spools` | `:1134` | Builds review rows and drops heads with no spool (43.4). |
| `_stash_unresolved_review` | `:1221` | Refuses once the job is in the ledger, which is why 43.2's ordering matters. |
| `_create_pending_cancel_review` | `:1353` | Stores only the resolved rows (43.4). |
| `_confirm_no_spool_review` | `:1467` | Re-resolves against whatever is on the head at Apply time (43.3). |
| `api_cancel_deduct_confirm` | `:1518` | Pops the record before any ledger check; ledger writes at `:1632` / `:1651` (the 43.2 hazard; 43.6). |
| Review card UI | `static/js/modules/cancel_review.js` | Where 43.3's picker and 43.4's "no spool" rows render. |

---

## Design, by sub-task

### 43.1 — Clamp against the effective initial weight

- In `_apply_usage_to_printer`, resolve `initial` as the spool's `initial_weight`, falling back to the filament's net `weight`. That's the same rule as `_auto_archive_on_empty` (`spoolman_api.py:201-205`), which is also how Spoolman computes `remaining_weight`.
- If neither weight exists, the remaining is unknown. Write the grams as today, record them as applied, and log that the spool has no known capacity.
- Before building, run a read-only count on dev AND prod of loaded spools whose `initial_weight` is null. That sizes the exposure.
- **Pin:** a spool with `initial_weight: null` and a 1000 g filament takes 50 g → the ledger records 50 g, with no shortfall WARNING. On HEAD it records 0 g.

### 43.2 — A shortfall becomes a recoverable review (filed design, 2026-10-08) — ✅ ANSWERED 2026-10-13: charge the picked archived spool, leave it archived

**Derek chose "charge it and leave it archived" (2026-10-13).** A picked archived spool is charged up to what it still has on record (the usual clamp) and stays archived where it is: it is never un-archived or moved, and a charge that takes a spool to 0 g archives it, as today. `_rows_from_charges` stops refusing archived picks, so today's review cards accept them too, and the shortfall card defaults to the spool that was on the head when the print ended, asking for another spool when that one is archived. Derek added that on small spools the recorded weight can be well off (job 1104: he thought #99 had enough to finish); his joined-spool idea is the follow-up note at the end of this section. Build it that way, on the filed design below, which still stands; the original question is kept for the record.

- **No ledger migration needed.** Stash the shortfall under a derived key, `"<job_id>#shortfall"`. `_key` is `f"{printer}::{job_id}"` and both stores stringify ids without parsing them, so the real-id poppers can never touch it.
- **Stash before `record_deduct`.** A crash then leaves the recoverable review rather than the terminal ledger key. Today `record_deduct` (`:401`) fires two lines before the shortfall is computed (`:403`). A naive "if shortfall: stash" afterwards is therefore a guaranteed silent no-op, because `_stash_unresolved_review` refuses once the job is in the ledger.
- **`api_cancel_deduct_confirm` pops the record before any ledger check.** A half-wired version would lose the grams a second time, silently. Pin it.
- **Threshold:** add a `shortfall_review_min_g` config value (~1.0 g), separate from the 0.05 g the log line uses. A 0.06 g card trains you to Discard without reading, which is how jobs 1105/1106 got dismissed.
- **Ledger:** record the shortfall on the entry too, so the record alone explains a discrepancy.
- ✅ **Answered 2026-10-13 (the bold line above); this was the open question for Derek:** when the clamped spool was **auto-archived** at 0 g (as #99 was), where should the top-up go, and how does he tell FCC which spool? 43.3's picker is the natural answer: the card asks which spool takes the remainder. The plain-language brief, with the job 1104 worked example and the code it was checked against, is "Where a print's uncharged grams go when the spool ran out and was archived" in [open-decisions-2026-10-13.md](open-decisions-2026-10-13.md).
- **Build notes from the answer** (code read on `dev` @ `f0d00f3`; re-grep before editing):
  - The refusal to remove is in `_rows_from_charges` (`print_deduct.py:1739-1741`, "Charging an archived spool is still an open question."), along with its docstring (`:1675-1676`). It covers a redirect target, a `no_spool` pick and a 43.4 uncharged-head pick; a kept archived row already goes on to the clamp.
  - The write already behaves: `_deduct_payload` (`:294`) sends `archived: True` for an archived spool, so a charge never trips `update_spool`'s auto-unarchive.
  - Picking a run-out spool such as #99 (0 g on record) charges 0 g, so the card still shows those grams as uncharged: pick another spool or discard.
  - Take the card's default spool from the deduct's own details. By the time the card is stashed, the auto-archive has already moved a run-out spool off its head, so a heads snapshot taken after the deduct won't show it.
  - The card's typed-#id lookup still says an archived spool "is archived — pick another spool" (`static/js/modules/cancel_review.js:596-597`); change it to match.
- 💡 **Follow-up idea, not a commitment (Derek, 2026-10-13):** have FCC catch a joined-spool (SpoolJoin) switch, where one head runs out and the printer carries on from another, if the printer exposes it. It would need a history of toolhead changes during a print and may get messy. Known so far: PrusaLink reports nothing per slot ([[reference_fcc_indx_hardware_and_gcode]]), and the swap-diff logging shipped 2026-10-08 will show what FCC can see on the next joined-spool runout (the SpoolJoin item in `Feature-Buglist.md`'s ⏸️ PENDING DEREK section). Revisit once that log exists. It belongs with "SpoolJoin detection" (Excluded, above), not with 43.2's build.

### 43.3 — Pick the spool on a review

- Store the expected spool on every review record when it's created: the spool on the head when the print ended. Apply then never silently charges a spool loaded afterwards.
- The card offers three choices:
  - the expected spool (the default);
  - any spool currently on one of that printer's heads;
  - a search for any spool.

  A head picker covers Derek's sliced-for-T1, printed-on-T2 case.
- Apply re-validates the chosen spool, clamps against its real remaining (43.1's rule), then records the ledger. How an **archived** spool is handled was part of the 43.2 question, answered 2026-10-13: it is charged and stays archived (see 43.2).
- The same picker serves 43.2's shortfall card and 43.4's "no spool" rows.

### 43.4 — 22.5: a cancel review keeps every head

- In `_create_pending_cancel_review` / `_resolve_usage_to_spools`, keep a row for every head in the usage map. A head that resolved to no spool gets `spool: null` plus its grams. The card shows it as "no spool on T<n>: pick one or discard" (43.3's picker).
- Confirm records the ledger with a shortfall check, like the completion path does.
- Why this pairs with Group 39.4:
  - A D6-confirmed move off a printing head records no swap event, because swap snapshots are taken only on a resume (`print_monitor.py`).
  - At completion, `_is_sid_swap` therefore sees no swap, and the head's grams become a shortfall. 43.2 makes that shortfall recoverable.
  - At cancel, the grams vanish with no warning at all until 43.4 lands.

### 43.5 — Deduct log lines name the printer and toolhead

- Per-spool line (`:347`): `✔️ {printer} {TOOLHEAD}: auto-deducted {g}g from Spool #{sid} ({label}) [...]`.
- Summary line (`:830`): list the toolheads charged, e.g. `✅ Completed-print deduct on 🦝 Core One INDX [RCOI-2]: 7.4g across 1 spool(s) (…)`.
- Before changing them, grep `tests/` for exact-string pins (`Auto-deducted`, `Completed-print deduct on`).

### 43.6 — The cancel-review retry is idempotent

- The confirm-apply charges the grams stored on the review record. It skips a spool the ledger already shows as charged for that job, instead of re-deriving from the spool's current `used_weight`.
- **Pin:** a first confirm whose write lands but is reported as failed (a timeout after commit), then a retry → the spool is charged exactly once.

---

## Build order

1. **43.1**, with its read-only exposure count.
2. **43.5**: tiny, and it gets the log lines right before new paths emit them.
3. **43.3**: the review record carries the expected spool, plus the picker. 43.2 and 43.4 both reuse it.
4. **43.2**: Derek answered the auto-archived top-up question on 2026-10-13 (charge it and leave it archived), so it's ready to build.
5. **43.4**, with or after Group 39.4.
6. **43.6**.

## Cross-group notes

- **[Group 22](22-filabridge-phase2-detection-deduct-followups.md)** stays `PARTIAL` with only the M600 split. 22.5 lives here now.
- **[Group 39](39-confirm-on-every-door.md) 39.4.** D6's "ask before moving a spool off a printing head" is what makes an emptied head an everyday case. Land 43.4 with it or after it.
- **[Group 42](42-single-slot-box-lifecycle.md) 42.3c.** The auto-unarchive redirect touches the same `_auto_archive_on_empty` / `_auto_unarchive_on_refill` pair that 43.1 reads. There's no conflict, but coordinate if both are open at once.
- **[Group 44](44-printer-first-class.md).** The ledger and review keys use the printer's display **Name**. If 44 re-keys per-printer state, it must migrate these stores too. Don't change the key here.
- **CLAUDE.md "Spool / Filament write surfaces".** Update the `_apply_usage_to_printer` and `api_cancel_deduct_confirm` rows when their contracts change. When 43.2 lands, the `api_cancel_deduct_confirm` row's "is refused until 43.2 settles where a top-up goes" becomes "is charged and stays archived".

## Verification

- Iterate hermetically from `inventory-hub/`: `"C:/Python314/python.exe" -m pytest tests/ -p no:cacheprovider -q --offline`.
- Keep the deduct-domain suites green: `test_runout_auto_split.py`, `test_spool_swap_22_3.py`, `test_deduct_followups_22_4.py`, and the cancel/completion deduct tests.
- Frontend changes (`cancel_review.js`) need the full E2E sweep before merging. It writes to shared dev data, so get Derek's OK first.

## Manual checks for Derek (add to the handoff)

- After the next print that runs a joined spool out: the shortfall review appears, and picking the joined spool charges the remainder to it.
- A `no_spool` review for an INDX print that ran on a different head than it was sliced for: pick the right head, and the deduct lands there.

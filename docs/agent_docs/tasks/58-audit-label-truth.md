# Group 58: 🔍 Audit & Label Truth

**Branch name (when started):** `feature/group-58-audit-label-truth`
**Estimated effort:** MEDIUM–LARGE (~6–12 h, 1–2 sessions), after Derek's decisions. 58.1 ~2–4 h · 58.2 ~1–2 h · 58.3 ~2–4 h (about ten small traps) · 58.4 ~1 h · 58.5 ~0.5–1 h · 58.6 depends on his pick (a scanning pass is his time, not code).
**Risk:** **MEDIUM.** Audit's Done moves spools, including off a head, with no undo today; any change to it is a write path. 58.6 touches prod data (read-only until Derek picks a repair).

> **Status: `TODO` — filed 2026-10-25 (`/refresh-groups`; Derek approved the grouping the same day: "Ok apply the grouping"). ⛔ Derek decides first what Done does (58.1); the rest of the audit work follows from it.** 58.5 (the false green tick) is ready now and needs no decision. 58.7 stays on hold.
> Derek's once-over relies on Audit, and labels are how FCC knows a spool is what it says: make Done safe, give Audit a notion of "no label", and make the label status honest (on the cards and in prod's data).
> **Until 58.1 ships: end audits with Cancel** (a full report, nothing moves).
> Code anchors were read on `dev` @ `d4b1ad7` (2026-10-25). Line numbers drift, so re-grep before editing.

## Items covered (quoted from `Feature-Buglist.md`)

| # | Buglist item | Direction |
|---|---|---|
| **58.1** | 🔍 *"Audit: Done moves unscanned spools with no confirm and no undo… `CMD:DONE` (the panel's Done & Auto-Park, the FINISH tile's QR, the Location Manager's Done QR) parks every expected-but-unscanned spool at UNKNOWN with no confirm, no undo and no check of where it is now, including a spool loaded on a printer that is expected at its home box (the head then reads empty)."* (Traced 2026-10-21, read-only, `wf_88cad35d-ac5`.) | Derek's decision below; then a confirm that lists them, an Undo, and never moving a spool that isn't at the audited place. |
| **58.2** | Same item: *"Audit has no notion of "no label": typing an id + Enter marks one found, but nothing says so, and there is no "needs a label" action; a label scan during an audit skips the label check."* | A "needs a label" action, and the label check during an audit. |
| **58.3** | Same item, *"Smaller traps: audit mode takes every device's scans; Hide is one-way; a printed CMD:AUDIT label cancels it; a hidden "Clear entire Buffer?" blocks scans; refusal toasts render under the panel; a rogue scan answers 500 on a Spoolman timeout; a second Done re-parks; auditing UNKNOWN / UNASSIGNED is destructive; a Spoolman blip at the location scan reads as 0 expected."* | Each a small fix (Claude's calls), one pin each. |
| **58.4** | Same item: *"Also wanted for the once-over: a list of spools filed only at a cart or room (each place's Location Manager shows its own under "Loose / Floating")."* *"One audit covers one place, and a cart expects only spools filed at the cart itself (the rollup is Group 37.6)."* | One list of every loose spool; the rollup stays Group 37.6. |
| **58.5** | 🏷️ *"search cards show the green "label confirmed" tick for a missing status (`spoolman_api` reads a missing flag as False)."* | Ready now: a missing status draws as unknown, not confirmed. |
| **58.6** | 🏷️ *"123 of prod's 267 spools have no label status at all (found 2026-10-21). `needs_label_print` is missing… on 123 in-stock prod spools, 96 of them from the first import (2026-02-11), so the 🏷️ Backlog can't see them; prod's #76 is one, with no label on it."* Derek: *"the check flag for needing a label might not have been applied, or it might have been lost"*. *"…a scanning pass sorts out the labelled ones and the rest could go to the backlog. Also… check whether an old bulk-loss path wiped the flag, and whether Spoolman's automatic backups still hold older values."* | Read-only first (where did the flag go?), then Derek's repair pick. |
| **58.7** _(on hold)_ | *"Check why FIL:58 wasn't marked as labeled when scanned… [ON HOLD — need to locate or reprint the FIL:58 physical label/swatch before repro can be attempted.]"* | Stays on hold; kept here because it is the same label-confirm path. |

## Decisions

- **For Derek, first: what Done does (58.1).** Today Done reports and then moves every unscanned spool to UNKNOWN, at once. Example: auditing `LR-MDB-1` while its slot 3 spool runs on XL-3 moves that spool off XL-3 to UNKNOWN, and XL-3 then reads empty.
  - (a) Done asks first: it lists each unscanned spool and where FCC has it now; Yes parks them at UNKNOWN, with one Undo for the batch.
  - (b) Done never moves anything: it reports; a separate "Park the missing" button does the move, with (a)'s confirm.
  - (c) Either way, a spool that isn't AT the audited place now (on a head, or moved meanwhile) is never parked, and the report says why.
  - Recommendation: (a) + (c). Default until he answers: nothing changes and Cancel stays the safe way to end an audit.
- **For Derek: a spool without a label during an audit (58.2).** (a) A "needs a label" action on the found spool (it joins the 🏷️ Backlog), from a key and a QR; (b) a typed id is marked found AND flagged automatically. Recommendation: (a), since a typed id isn't always a missing label. Default: (a).
- **For Derek: the prod repair (58.6), after the read-only look.** (a) A scanning pass: every `ID:` scan of a labelled spool turns a missing status into confirmed (that already works), then (b) for the rest; (b) send every spool still missing a status to the backlog. Recommendation: (a) then (b). Default: wait.
- **Claude's calls (for veto):** 58.3's fixes one by one (e.g. a second Done does nothing; auditing UNKNOWN / UNASSIGNED is refused; a location read that fails says "couldn't read" instead of "0 expected", Group 52's rule; refusal toasts above the panel through `mountOverlay`'s ladder). "Audit mode takes every device's scans" is a design question shared with [Group 60](60-phone-and-tags.md) (one scan buffer for every device, or one per device; step 3 plan, decision 3): note it there, don't decide it here.

## Today's code (anchors, `dev` @ `d4b1ad7`)

- **Done:** `CMD:DONE` parses at `logic.py:1018` and is shared with Bulk Move (`:3396`, `:3907`). `logic.process_audit_scan` (`logic.py:5019+`) builds the report (`:5030-5056`), then for `done` parks every missing spool at UNKNOWN with `fcc_pre_audit_location` set (`:5058-5095`; the loop `if cmd == 'done' and missing and expected_loc:` at `:5066`). No confirm, no undo record (`_push_undo` is not called), and no read of where each spool is now.
- **The label status:** `spoolman_api.format_spool_display` (`spoolman_api.py:1958+`) turns a missing `needs_label_print` into `False` (`:2032-2034`); the card draws the green "label confirmed" tick when `details.needs_label_print === false` (`ui_builder.js:122-126`). So a missing status draws as confirmed. The `ID:` label-verify scan already treats missing as unknown and confirms it (spool `routes_scan.py:1160-1182`; filament `:1248-1254`).
- **UNKNOWN:** a virtual bucket (`logic.py:1160`); `UNASSIGNED` / `UNKNOWN` are refused by several doors already (`logic.py:1294`, `:1574`).
- **The trace:** `review-samples/2026-10-21-audit/audit-trace-and-verify.json` (Derek's machine, git-ignored; the workflow `wf_88cad35d-ac5`).
- **Prod fact (read-only, 2026-10-21):** 123 of 267 in-stock prod spools carry no `needs_label_print` at all, 96 of them from the 2026-02-11 import.

## Design, by sub-task

### 58.1 — Done, safely (after Derek's pick)
- Before any write: strict-read each missing spool's record; keep only those still filed AT the audited location (or its slot); list the others in the report with where they are.
- (a)'s confirm through `requestConfirmation` / `window.confirmActivePrint`'s family (never a nested Swal; CLAUDE.md gating-dialog rule), naming each spool; its QRs under its buttons (`attachConfirmQRs({alignTo})`).
- One undo record for the batch (`_push_undo`), so "Undo Last Move" puts them back.

### 58.2 — "no label"
- A "needs a label" action on the audit panel's last found spool (sets `needs_label_print: true` through `update_spool`, which the backlog then lists); a label (`ID:`) scan during an audit also runs the label check it skips today.

### 58.3 — the small traps
- One fix and one pin each, listed in the commit. Group 52's honest-read rule for the location scan.

### 58.4 — loose spools
- A read-only list of spools filed at a cart or room itself (not a row, slot or head), reachable from the audit panel or the Location Manager, using the existing "Loose / Floating" rule.

### 58.5 — the false green tick
- `format_spool_display` keeps a missing flag missing (`None`); the card draws confirmed only for an explicit `False`, and a missing status as "label status unknown" (no tick, or a grey ?), with the backlog's wording. Check every reader of `details.needs_label_print` (the backlog's `_needs_label`, the wizard, the details window) for the tri-state.

### 58.6 — prod's 123 spools (read-only first)
- Read-only: which write paths could have dropped the flag (old bulk-loss paths: the pre-2026-05-19 partial-PATCH draft, the force_reset history of Group 36), and whether Spoolman's automatic backups on the NAS hold older values (prod read-only; never write to `:7912`). Then Derek's pick.

## Tests

- **Offline:** Done with a missing spool on a head parks nothing for it and says so; Done writes one undo record; a second Done re-parks nothing; `format_spool_display` on a record with no flag answers `None`; UNKNOWN / UNASSIGNED audits refused; a failed location read answers "couldn't read".
- **Browser:** the Done confirm lists the spools and its Yes / Undo work (stubbed data, `own_the_buffer` / `quiet_heartbeat` where the panel's polls own state); a search card with no status shows no green tick; the "needs a label" action adds the spool to the backlog; contrast and text-size guards on any new panel text.
- The full sweep before merging.

## Done when

- Done can't move a spool that isn't at the audited place, asks first (or never moves, per Derek), and can be undone; Audit can say "no label"; no card claims a label it can't know; prod's missing statuses have a repair Derek chose.

## Risks

- Audit and Bulk Move share `CMD:DONE` / `CMD:CANCEL`: change Audit's handler only.
- A confirm inside the audit panel must be reachable (the axis (b) class: confirms rendering behind `mountOverlay` panels).
- 58.6 must stay read-only against prod until Derek picks.

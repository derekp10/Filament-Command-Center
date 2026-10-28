# **New and Unsorted Features/Bugs**

* **🧪 The E2E suite is LOAD-SENSITIVE: a busy machine turns a 2-red sweep into a 13–16-red one, with a different set each time.** _(→ **Group 45.1**)_ _(Quantified 2026-10-08. Derek: "Not sure I can make the machine quiet… If it's a re-occurring issue, we may need to dig further.")_ Two full `RUN_INTEGRATION` sweeps of near-identical code, back to back: **13 failed** then **16 failed**, but only **5 tests failed in BOTH** — 8 were unique to the first, 11 unique to the second, so **19 of 24 distinct failures did not reproduce**. Of the 5 common ones, 2 are the standing Group 37.1 pair and the other 3 all passed when re-run in isolation. Both runs took **33:40** against **26:17** for the same suite on a quiet machine — a ~30% slowdown, with ambient load from ordinary desktop use (118 Chrome processes, which are Derek's browser, NOT orphaned Playwright chromium — those live under `ms-playwright`). **Signature:** almost every failure is a `wait_for_function` / `expect` hitting a hard **3000 ms** timeout, so a 30% slower machine trips proportionally more of them. Note the suite is SERIAL (no xdist/randomly), so test-vs-test contention is impossible — the pressure is external. **What this costs:** a sweep can no longer be read at a glance; "is this red real?" needs an isolation re-run every time, which is ~30 extra minutes per release. **Directions, cheapest first:** (a) raise the 3 s waits to ~8–10 s — they are not asserting on latency, so the tight bound buys nothing; (b) add a conftest-level default timeout so individual tests stop hardcoding one; (c) have the harness print total wall-clock and warn when a run exceeds the quiet-machine baseline, so a noisy run is self-labelling; (d) auto-retry a failed browser test once and report it as flaky rather than failed. **Do NOT "fix" this by running sweeps only on a quiet machine** — Derek has said he can't guarantee one, so the suite has to tolerate a working desktop. **Progress 2026-10-13/14 (Group 45, overnight run):** (b) shipped: Playwright's `expect` waits 10 s by default. (c) shipped: every run ends `⏱️ M:SS for N tests` with a load factor against this PC's own recent times, saying BUSY RUN at 1.25× or more, and a failed browser test's report lists its slow requests and the dev-Spoolman timeouts during it. The biggest load turned out to be FCC's own (45.8): the Printer Status widget re-read the whole spool list once per toolhead on every heartbeat. With that gone, full sweeps take ~21 min (was 33–38) and the second one had 1 red, a latent race since fixed. (d) hasn't been needed. **Left:** (a) triage a 3 s wait only where a red keeps coming back, and see a sweep on a genuinely busy desktop, which the load line now labels. **Standalone.**

## ⏸️ PENDING DEREK — deferred hands-on work (grep `PENDING DEREK`)

> Everything here is **blocked only on Derek doing something by hand**, not on code. It was pulled
> out of the release path on **2026-10-08** so ~100 commits of fixes — several of them data-loss
> fixes — could ship to prod instead of waiting behind it. **Nothing below blocks a release.**
> Derek's standing ask: *surface this section whenever he asks what's pending, even if he's asked
> about something else.* He'll get to it; he doesn't know when.

* **⏸️ PENDING DEREK — finish the 2026-10-26 release (Group 56; Claude removes this once (2) is done).**
  (1) ✅ Prod updated to `main` `1d9cae4` (Derek, 2026-10-26; prod's files checked the same evening). (2) After
  your next **completed** print and your next **cancelled** print (the first ones on firmware 8.0), tell Claude
  "check 56.7": it reads prod's deduct records itself; nothing for you to compare. (3) If the
  Activity Log ever shows "FCC's G-code walk of … came to … against the slicer's …", tell Claude: FCC may be
  misreading that file.
* **⏸️ PENDING DEREK — Bulk Moves (L298) hands-on pass.** Built, merged to `dev`, covered by the
  automated suite, and **shipped OFF behind `fcc.bulkMove.enabled`** (schema default `False`, so
  prod is dark; dev's own `config.json` has it `True`). Derek, 2026-10-08: *"I'm so unexcited about
  that whole thing that I keep putting it off. (And I doubt I'll even really use it much.)"* Flip it
  on in ⚙️ Settings → Behavior whenever the mood strikes — no release needed, prod unaffected.
  **The checks, with fixtures re-read 2026-10-08 so this is runnable cold:**
  | # | Check | Steps | Pass if |
  |---|---|---|---|
  | 1 | Undo | `CR-CT-2-R3` (#156, #194) → `CR-TC-2-R1` (empty), commit, then `CMD:UNDO` | One prompt first, naming the move ("Undo: put #156 back in CR-CT-2-R3 and #194 back in CR-CT-2-R3?"; since Group 41.4); Yes puts both back and the toast says so. Stronger: move `LR-MDB-1`'s spool out and undo — it returns to the same box AND slot |
  | 2 | Capacity block | `CR-CT-2-R1` (#42, #95, #126) → `LR-MDB-2` (**full**: #242@1, #230@2) | whole batch refused with a capacity message, nothing moves. ⚠️ the 2026-09-13 handoff said "2 free"; it is now 0 free |
  | 3 | Deployed-spool skip | ⚠️ **can't run as written** — `CR-MDB-1` is empty, so there's nothing to deploy. Put a spool in slot 1 first (dev spools are disposable), then bulk move `CR-MDB-1` → `CR-TC-2-R2` | the deployed spool is listed as skipped, with a reason |
  | 4 | Active print | while printing, a bulk move touching the loaded spool | a skip, not a prompt (bulk move refuses spools on a toolhead) |
  Optional sanity: source == destination blocked; a destination inside the source blocked; a toolhead
  destination blocked; reloading while armed brings the pill back. **Known, NOT a failure:** scanning
  a cart *parent* (e.g. `CR-CT-2`) finds only its direct spools (Group 37.4).
* **⏸️ PENDING DEREK — one session with a print running (mid-print checks; updated 2026-10-14).** Covers the
  active-print chain fix (2026-09-12) and Group 39 "Confirm on Every Door" (merged to `dev` 2026-10-13; **released
  2026-10-19, `main` `0140edf`**, so they run on prod or on dev, `http://localhost:8000`, which reads the same
  printers). Everything here
  has automated coverage too; these are what only a real printer, the real scanner and your eyes can check: does
  the wording read right, and does each move really ask once. **Setup:** start a multi-tool print on the XL; put a
  spare spool or two in the buffer. `LR-MDB-1` slots 1-3 feed XL-1 to XL-3 on dev.
  | # | Check | Steps | Pass if |
  |---|---|---|---|
  | 1 | Quick-Swap mid-print | Open XL-2 → tap its `LR-MDB-1` slot 2 tile | One confirm with the yellow "XL is PRINTING" banner. Yes → the new spool is on XL-2 and the old one is back in its box. No second prompt |
  | 2 | Return mid-print | Open XL-3 → ↩️ Return | The banner names the XL. Yes → the spool is back in its box slot. No second prompt |
  | 3 | Move off a printing head | Pick XL-3's spool into the buffer → scan `CR-CT-2-R1` | **One** prompt naming the spool, XL-3, `CR-CT-2-R1` and "stops charging this print to it". Cancel → nothing moves; again with Yes → it moves. **Does the wording read right to you?** |
  | 4 | Head to head asks once | Pick up XL-1's spool → scan XL-3's toolhead QR. Then the same from the Location Manager (open XL-3, assign it) | Exactly one prompt each time, naming both heads |
  | 5 | A bound slot is named | Pick XL-3's spool → scan the `LR-MDB-1` slot 2 label (it feeds XL-2) | One prompt that names XL-3 AND says the slot feeds XL-2 ("…so this also loads #N onto XL-2…"). Since Group 40 it has three buttons: **Load it instead** loads XL-2, **Just store it** (Enter) leaves the spool in slot 2 and XL-2 alone, Cancel moves nothing |
  | 6 | Slot label → toolhead | Scan a spare spool, then the `LR-MDB-1` slot 1 label | One prompt with three buttons. **Load it instead** (click, or scan its QR) puts the spool on XL-1; Enter means **Just store it** (the spool waits in slot 1, XL-1 untouched: your 2026-10-14 answer, a head isn't loaded mid-print by default). If XL-1 runs a spool from another box, the prompt names it too |
  | 7 | Force Location mid-print | Details of XL-3's spool → Force Location → `CR-CT-2-R1`; then again with "-- Unassigned --" | A confirm both times (not a red "failed" toast); Yes moves it |
  | 8 | Eject asks once | Eject a spool that has no saved home (put one on XL-2 with Force Location first) | **One** prompt beyond "Eject spool #N?", mentioning XL-2 and Unassigned. ⚠️ This INVERTS the old check ("the second prompt appears"): Group 39 merged the two prompts |
  | 9 | Deposit, three ways | XL-2's Quick-Swap grid → Deposit a buffered spool; answer once with a click on Load it instead, once by scanning its QR, once with Enter | One prompt each time (since Group 40, the three-button one). The click and the QR load; Enter stores (Just store it) |
  | 10 | Paused never asks | Pause the print → repeat check 3 | No prompt; the spool moves |
  | 11 | An emptied head keeps its grams | Mid-print, move one head's spool to a shelf (confirm). Then cancel the print | The cancel review lists that head as "no spool loaded" with its grams and a spool picker; Apply without a pick reports those grams as not charged |
  | 12 | Undo a mid-print move | Right after check 3's Yes (XL-3's spool moved to `CR-CT-2-R1`), tap UNDO MOVE | One prompt that says the XL is printing and this undo changes XL-3 mid-print, then "Undo: put #N back on XL-3?"; Yes puts the spool back on XL-3. **Does the wording read right?** (Group 41.4) |
  Still valid from the 2026-09-12 list: `CMD:EJECTALL` with no location open is refused with a message, so it's
  safe to try. (Its "Core One Return" check is dropped: it covered the one-head `CORE1` printer, which is now the
  INDX.) **With the
  Core One INDX switched off** (no print needed): in the Location Manager open `RCOI-1` and assign a buffered
  spool to it; then scan `RCOI-1`'s toolhead label with a spool in the buffer. Each time a "⏳ Checking 🦝 Core One
  INDX…" notice appears within about half a second (a pill at the top, or a label on the dimmed screen), and the
  move still goes through. **After the 2026-10-19 release (`main` `0140edf`, now past):** a tab left open across that
  update said "This FCC page is out of date … reload" when it confirmed a mid-print move; Ctrl+F5 fixed it. Only a tab
  opened before that update can show it, so skip this one unless such a tab is still open.
* **⏸️ PENDING DEREK — the "head already runs another spool" question on slot labels (Group 40.3; on dev since
  `d6fc8b2`, 2026-10-15; on prod since `main` `0140edf`, 2026-10-19).** Your everyday path: a slot-label scan into a bound
  `LR-MDB-1` slot now asks first when the head that slot feeds runs a spool from somewhere else (e.g. a PolyDryer),
  with three buttons, each with a scannable QR: **Load it instead** · **Just store it in LR-MDB-1 slot N** ·
  **Cancel**; Enter = Just store it. Automated tests cover all of it; these check the wording, your scanner and the
  feel. **Setup:** printer idle unless a row says otherwise; empty the buffer between rows.
  | # | Check | Steps | Pass if |
  |---|---|---|---|
  | S1 | Empty idle head (your path) | XL-2 empty. Buffer a spool, scan `LOC:LR-MDB-1:SLOT:2` | Loads onto XL-2 with no prompt |
  | S2 | The slot's own spool (your path) | XL-3 runs a spool that came from `LR-MDB-1` slot 3. Buffer a new spool, scan `LOC:LR-MDB-1:SLOT:3` | No prompt; the new spool is on XL-3, and the old one is in your scan buffer with a toast "✋ #N → your buffer (taken off XL-3)" (your 2026-10-15 answer, built in 40.2). Since Swap option C (2026-10-19) it is also filed back where it sat before that slot when FCC knows (the toast adds "filed back in CR-CT-2-R1"); a spool slotted before that build has no record, so it stays Unassigned until you scan it somewhere or weigh it out. `LR-MDB-1` no longer reads 5/4. A scanner's double-read of the label is ignored ("Ignored a second read"); scanning the same label again on purpose swaps the two straight back, so a wrong scan is fixed by re-scanning (your 2026-10-15 evening answer: no hard stop) |
  | S3 | Head fed from a PolyDryer | Load a `PM-DB-2` spool onto XL-1 (scan it, then XL-1's QR). Buffer another spool, scan `LOC:LR-MDB-1:SLOT:1` | One prompt naming the PolyDryer spool, with the three buttons. Just store it → the spool is in slot 1, XL-1 unchanged. Again with Load it instead → the PolyDryer spool is back in `PM-DB-2`, the new one on XL-1. **Does the wording read right?** |
  | S4 | Scan the choice | Repeat S3, but scan the on-screen QRs instead of clicking | Each QR does what its label says; Cancel writes nothing |
  | S5 | Printing: store by default | While the XL prints, XL-2 empty: scan a spool, then `LOC:LR-MDB-1:SLOT:2` | The prompt says the XL is printing; Enter stores the spool in slot 2 and leaves XL-2 alone |
  | S6 | Deposit onto a fed head | As in S3 (XL-1 runs the PolyDryer spool): open XL-1 → Quick-Swap grid → ⬇️ Deposit a buffered spool into `LR-MDB-1` slot 1. Then once more, tapping the tile twice quickly | The same prompt as S3, and only ONE prompt, even on the double tap |
  | S7 | Someone re-points the slot meanwhile (optional, two tabs) | Tab A: S3's scan; leave the prompt open. Tab B: Location Manager → `LR-MDB-1` → 🔗 Slot → Toolhead Feeds → slot 1 → XL-2, save. Tab A: Load it instead | FCC asks again: "LR-MDB-1 slot 1 now feeds XL-2 (it fed XL-1 when you were asked). Load #N onto XL-2?" Set slot 1 back to XL-1 afterwards |
* **⏸️ PENDING DEREK — the pickers and Swap option C (Group 40's last leg, built 2026-10-19; on dev since `8d0ff64`; on prod since
  `main` `0140edf`).**
  Automated tests cover all of it; these check the feel, the wording and your scanner.
  **Setup:** printer idle unless a row says otherwise; empty the buffer between rows. Spools slotted BEFORE this
  build carry no "where it sat before" record, so a Swap leaves those Unassigned (and buffered); the record starts
  with the next spool you put in a slot.
  | # | Check | Steps | Pass if |
  |---|---|---|---|
  | C1 | Swap files it back | Put a spare from `CR-CT-2-R1` into `LR-MDB-1` slot 4 (scan it, then the slot label). Buffer another spare, open `LR-MDB-1`, tap slot 4 → **Swap** | The new spool is in slot 4; the old one is in your buffer AND back on `CR-CT-2-R1` in FCC, toast "✋ #N → your buffer (filed back in CR-CT-2-R1)". The box label's picker says it before you choose ("#N → your buffer, filed back in CR-CT-2-R1") |
  | C2 | The same-slot swap, one rule | As S2, with a spool you put into `LR-MDB-1` slot 3 from a cart after this build | It comes off XL-3 into your buffer, filed back on that cart ("taken off XL-3; filed back in …"). **Does that read right** (your "I may have a more nuanced opinion once I run into it")? |
  | F1 | Force Location into a box | A spool's details → Force Location → `LR-MDB-2` | The slot picker opens (each slot's spool and the head it feeds, a ⭐); it lands in the slot you pick and loads that slot's head, asking first when needed. Escape: nothing moves |
  | F2 | Force Location onto an INDX head | Details → Force Location → `RCOI` | The Printer picker: RCOI-1…RCOI-8 with what each holds; pick an empty head and the spool lands on it (your "INDX heads without labels" item) |
  | P1 | `LOC:XL` with a buffer | Buffer a spool, scan `LOC:XL` | The Printer picker: XL-1…XL-5 (what each runs, which slots feed it) plus the Printer Pool slots; "Checking XL…" until the printer answers |
  | P2 | Load over a spool | In P1 pick a head that holds a spool | "Load #N onto XL-3? XL-3 holds #M (from …). Loading #N sends #M back to …": Load it instead / Cancel (no store: a head isn't storage), Cancel steps back to the picker. **Does the wording read right?** |
  | P3 | "Record it as coming from…" | In P1, with a spare from Unassigned, pick the empty head `XL-4` | Asks which slot feeding XL-4 is its home (`LR-MDB-2` slot 1 pre-selected when it's the only free one; scanning that slot's label picks it); toast "(recorded as from LR-MDB-2 slot 1)" |
  | P4 | Empty buffer | Empty buffer: scan `LOC:XL`; then `LOC:PM-DB-2` while its spool runs on a head | `LOC:XL` opens the XL view and grabs nothing; the PolyDryer label still grabs its spool (your answer 8) |
  | R1 | Return, one tap | Open a head whose spool came from `LR-MDB-1` slot 3 → ↩️ Return | One tap; the confirm names "LR-MDB-1 slot 3"; toast `↩️ #N → LR-MDB-1 slot 3` |
  | R2 | Return to a taken slot | Put another spool in that slot first, then Return | The return-mode picker opens with a ⭐; "No slot" says the box will read 5/4; no toast ever says `null` |
  | R3 | DEPLOYED ↩️ | `LR-MDB-1` grid → ↩️ on a DEPLOYED card | Same as R1/R2: the spool comes back into its slot and the head is emptied (asking first if the XL prints) |
  | W1 | Wizard Location → printer | Edit a spool, pick `XL` in Location | The Printer picker opens; the field then reads "XL-3 (via XL)"; Save puts it on XL-3. **If the picker gets in your way here, say so** (your veto point) |
  | W2 | Wizard Location → box | Edit a spool, pick `LR-MDB-1` | The slot picker opens; Save moves it into that slot and loads its head (asking first when needed); a refused move says so and your other edits stay saved |
* **⏸️ PENDING DEREK — the next INDX cancel review for a print you ran from a different head than it was sliced
  for.** Nothing to set up; it will happen on its own (your job 1104/1105 case). Open 🛑 Review, and on that
  T-line pick the spool on the head the print really used, then Apply. Pass if the deduct lands on that spool (the
  Activity Log names the printer and head) and nothing is charged on the sliced-for head. (The review-card spool
  picker, built 2026-10-13.)
* **⏸️ PENDING DEREK — weigh the spools before and after one multi-slot INDX print.** _(Shrunk 2026-10-25 from
  "capture one raw multi-slot `.bgcode` as a test fixture": the 3-slot raccoon capture answered the gcode questions
  (the footer is zero-padded 8-wide, and the INDX selects with bare `T<n>`), and the purge/parser gap turned out to
  be FCC's parser skipping arcs, fixed in Group 56.1 (2026-10-25). FCC downloads each job's file itself, so
  nothing needs capturing.)_ Weigh the spools on the slots a print uses (ideally ≥3 non-contiguous ones, e.g. 1, 4,
  8 → T0, T3, T7, which also exercises the index mapping) before and after, and paste the numbers here: that
  validates the multi-tool completion deduct against the scale the way job 1078 validated the runout split.
* **⏸️ PENDING DEREK — the next SpoolJoin print will answer the detection question by itself.** The
  ATTENTION-park and resume swap-diff logging shipped 2026-10-08, so the next time a joined slot runs
  out, the Activity Log will say either "parked at ATTENTION … recorded N swaps" or "no spool mapping
  change at any toolhead". Nothing to set up — just check the log afterwards and paste it here.
* **⏸️ PENDING DEREK — the next spool that runs out mid-print, now on firmware 8.0 (Group 56.7).** 8.0 added a
  Runout Reaction setting, and FCC's run-out split keys off the printer pausing. Nothing to set up. **In-slot
  swap:** when a spool runs out and the printer pauses, load the new roll into that slot and scan it onto that
  head in FCC before resuming; once the print ends, 🛑 Review should show a "spool changed mid-print" card with
  each spool's share (weighing both spools before and after makes it a scale check, optional). **Joined spool
  (SpoolJoin):** the item above. Either way, tell Claude what happened (or that the printer didn't pause).
* **⏸️ PENDING DEREK — branch cleanup session.** 11 branches are fully merged into `dev` and could be
  deleted (4 of them also on `origin`): `feature/bulk-move-panel-affordance`, `feature/bulk-moves-l298`,
  `feature/bulk-moves-l298-p1`, `feature/group-34-location-tree-cluster`,
  `feature/group-36-attribute-force-reset-data-loss`, `feature/group-38-hermeticity-residuals`,
  `fix/active-print-chain-confirm`, `fix/locations-json-write-lock`,
  `fix/scan-path-and-bindings-2026-08-03`, `fix/update-spool-request-timeout`,
  `hotfix/indx-printer-setup`. Derek, 2026-10-08: *"I didn't know we had gotten that many loose ends
  out there… one or two might be waiting on a few of the tests I need to do."* Wants its own pass so
  each is checked rather than swept.
  **Added 2026-10-19 (Group 40, merged into `dev` `8d0ff64`):** `feature/group-40-slot-picker`,
  `feature/group-40-engine-403`, `feature/g40-6-return-picker`, `feature/g40-7-wizard-server`, `fix/g40-6-review`,
  `fix/g40-7-review` (all on `origin`).
  **Added 2026-10-20 (the 2026-10-19 bundle, merged into `dev` `2ec9f46`):**
  `feature/group-51-move-archive-integrity`, `feature/groups-48-49-cards-restock`,
  `feature/group-49-find-and-restock`, `feature/group-52-spoolman-read-load`, `fix/bundle-reads-1`,
  `bundle/2026-10-19` (all on `origin`); and `fix/bundle-followups-2026-10-20` (merged `0bd0293`, on `origin`).
  **Added 2026-10-21 (merged into `dev` `e7699c4`):** `fix/low-stock-out-list-2026-10-20`,
  `feat/not-buying-again-2026-10-20`, `fix/extras-clear-spoolman-027-2026-10-21`, `bundle/2026-10-21` (all on
  `origin`).
  **Added 2026-10-25 (merged into `dev`, found by the refresh):** `feat/readability-2026-10-21` (merged `09b395a`,
  on `origin`), `fix/backlog-label-filter` (merged `afdd509`, on `origin`), and three overnight-run branches missing
  from this list: `feature/group-41-honest-bulk-results`, `feature/group-42-single-slot-box-lifecycle`,
  `feature/group-45-sweep-hygiene` (local only).
* **⏸️ PENDING DEREK — lay out and label the INDX spool holders (and the 8-spool box; maybe the XL's holders).**
  _(Derek, 2026-10-19, answering the refresh's holder question.)_ Setting them up in FCC as a box with one slot per
  holder (no code) is *"possibly the way to go"*, but it is his grunt work and design first:
  - **4 holders on each side** of the INDX, each holding nothing, a spool, or a **USS Prusa drybox** (it works like a
    PolyDryer, except it fits on a holder and has no drying unit yet);
  - a second option, an **8-spool dryer box** whose spools all feed by tube into the printer's filament sensor boxes
    (left / right on the printer, top / bottom rows in the box): still unlabelled while he decides the PTFE routing;
  - the **XL's holders** too: rarely used (boxes and PolyDryers), but maybe a USS drybox there later.
  **The no-code setup, when he's ready** (Location Manager, on prod; dev picks it up with Group 45.6's refresh): one
  location of Type **Dryer Box** per holder group (e.g. one per side of the INDX, under room `CR`), Max Spools = its
  holders. In its 🔗 Slot → Toolhead Feeds, set each slot to the head that holder feeds (e.g. slot n → `RCOI-n`),
  leaving a slot unbound where a dryer box feeds that head instead; then print its slot labels. **Its ID must not
  start with `RCOI-`**, or FCC's location matcher would show its spools as the printer's own. A USS drybox can be its
  own single-slot Dryer Box (Max Spools 1), like a PolyDryer. Then "scan the spool, scan the holder slot's label"
  loads that head (asking first if it runs another spool), Quick-Swap and Return work as on `LR-MDB-1`, and Printer
  Status drops its "🔗 no bound slot" placeholder on those heads. A proper "Spool Holder" type is Group 37's
  question. **Done when** the holders (and the box, if used) have rows, feeds and printed slot labels; that also
  lets his "INDX heads without labels" item close, once his F2 check passes.
* **⏸️ PENDING DEREK — the ⚠️ Low stock list: exclude what you can't get (nothing here blocks a release).**
  1. **After it ships, exclude the ones you can't get or won't restock.** On prod (read 2026-10-20), Out had Creality
     PETG Black and Kingroon PETG White, and now also lists the 11 filaments with no spool record (all from the
     2026-02-11 import): Anycubic PLA Red (Matte), Anycubic PLA Violet, Creator PETG Black (Carbon Fiber), Elegoo PC
     Black, IEMAI TPU Green, Jayo PA6 Black (Glass Fiber), Overture PC Black, Polymaker PC Clear (sample printed),
     Sunlu PETG Black, Sunlu PLA Clear, Sunlu TPU Green. 🔕 on a row (or Del), with why: Discontinued, Can't find it,
     One-off, Didn't like it, Other.
  _(Answered 2026-10-20/21: the never-stocked filaments are listed under Out, last, as "no spool on record" ("they are
  technically out"; built, `68a9b9d`); the One-off attribute idea gave way to marking from the list with a reason, then
  named **Excluded**, not "Not buying again" ("just because it's discontinued, or I can't find it from the
  manufacturer, doesn't mean I didn't like it"; built, `38dbdd2`, with a "Can't find it" reason); the tabs, filter and
  one-line rows are liked as they are ("I love the design"); "shippable once we have addressed the other two things"
  (the name and the text size); the bigger text is kept ("looks good, so I'd say its a keeper for now", 2026-10-21
  walkthrough); and an archived spool scanned onto a toolhead is un-archived and loaded when its record still has
  filament, refused at 0 g; built.)_ **Released to prod 2026-10-25 (`main` `97fcf7c`):** what's left is
  excluding the prod filaments he can't get, from the list's 🔕. Dev's long-list sample was put back (`low_stock_g`
  250, filaments 91 and 96 included again).
* **⏸️ PENDING DEREK — pick how the title bar's ⚠️ Low stock button reads (Group 57; built 2026-10-26 on
  `feature/group-57-low-stock-at-a-glance`, live on dev while that branch is checked out).** The title bar has a ⚠️
  button with a count of the filaments that are low or out (it opens the Low stock list), and the list's window keeps
  one size. Pictures: `review-samples/2026-10-26-low-stock/` (also sent to your phone the same night), numbered as
  below.
  1. **How it reads** (pictures 1a–1c, 5a, 5b). A: "⚠️ 12" (built). On your 1600 px window nothing else on the bar
     changes at Small / Standard; at Large ADD INVENTORY reads ADD, at Extra Large the version badge hides. The bar
     gives way only as far as it must, whatever the counts say: a bigger count tightens the spacing before it ever
     shortens the title. A's cost is in narrower windows: at 1280 px (the Framework 12 at 150%) the version badge
     hides at Small / Standard and the title shortens at Extra Large; at Extra Large between 992 and 1100 px
     (an iPad on its side) the title shrinks to its first letters ("F…" at 1024 px, picture 5a); below 992 px the
     buttons need one more line (Standard at 768 px, an iPad upright, picture 5b). B: "⚠️ Low stock (12)" in words,
     which tightens the bar sooner at every size. C: words at Small / Standard, and all three of Backlog, Queue and
     Low stock as icon + number at Large / Extra Large and in narrow windows: the answer to A's narrow-window costs
     (in 5a the title comes back, "Filament Co…" at 1024 px; in 5b the buttons fit one line). Claude's pick: A (the
     words are in its tooltip), and C if you use FCC at Extra Large or on a tablet.
  2. **What the number counts** (picture 2). (a) Low + Out as one number (built; Claude's pick: the list's tabs
     already split it), (b) both, "1 · 11" (wider: at Small / Standard on your window the bar tightens its spacing,
     the title stays whole), (c) Low only. Excluded never counts.
  3. Claude's call, veto it if you like: the 🔍 Search panel's own "⚠️ Low stock" button goes once 1 is settled.
  4. For your information, nothing to pick (picture 4): a count FCC couldn't refresh (Spoolman didn't answer) keeps
     its number with a "?" after it and a dashed border, "⚠️ 12?", and the 🏷️ Backlog count does the same, "(53)?";
     the tooltip says why. The "?" takes no room, so a blip never moves the bar. Before its first answer a count
     reads "–" ("(–)" on Backlog and Queue, which used to read a "(0)" nobody had read), and "?" if that read failed;
     a heartbeat FCC hasn't answered after 30 s counts as failed.
  If you never answer, A and (a) go to `dev` as built.
* **⏸️ PENDING DEREK — look again at the scale trade-off of your digits-only call, if you like (Group 57 review,
  2026-10-28; nothing here blocks a release).** A scanner's digits are now a scan, never a weight (your call). The one
  case that can't be told apart is a scale that types a bare whole number into the box ("645", no '.', unit or
  Space): FCC reads it as a scan, so no weight is saved from it, but the number is looked up as a spool id, so a spool
  with that id joins the scan buffer, and in the weigh-out list its box takes the focus (a reading typed next by hand
  would go to it). A scale's reading with a '.', a unit or a Space stays a weight. No scale that types into a box is in
  use, and the SpoolmanScale you're eyeing would talk to an API instead. If you never answer, it stays as built.
* **📐 Plan docs: named sizes and colors as the base for themes; alternative views (phone, wall tablet, printer pictures,
  the Location Manager) (Derek, 2026-10-21; written).** _(→ **Group 60.1**: Claude first rewrites step 3's order, phone first, then the decisions one at a time)_ "Themes" in his sense are whole alternative designs a user
  can choose ("what we have now, or future ones, possibly ones that focus on using images of the printers themselves"),
  with the classic look kept, as stepping stones toward the MOBILE item and the Project Color Loadout's screens. To go
  through with him one decision at a time, not to read cold:
  [step 2, named sizes and colors](docs/agent_docs/tasks/design-step2-named-sizes-colors-and-themes.md) (today 1,222
  hand-typed colors and 364 text sizes in 33 files; about 8 sessions to put them on names with nothing changing on
  screen, the first one session; 6 decisions) and
  [step 3, other views](docs/agent_docs/tasks/design-step3-alternative-views.md) (a wall-tablet station view first, as
  one mockup before any build; then the shared core, printer pictures, a phone view, the Location Manager; 10
  decisions). Its phone and tablet screenshots are in `review-samples/2026-10-21-views/` on Derek's machine.
  **Phone first** (decided 2026-10-21; see "📱 Phone view first" under 🗒️ Notes): step 3's milestone order is rewritten
  after the readability merge.
* **⏸️ PENDING DEREK — tap a tagged Bambu spool with Chrome's NFC test page (2026-10-21).** _(→ **Group 60.4**)_ On the Pixel, open
  https://googlechrome.github.io/samples/web-nfc/, press **Scan** only (never Write or Make Read-Only), and hold the
  phone flat on the side of a Bambu spool near the hub. A "Serial Number" line means the phone can link Bambu spools by
  their tag ID; "Cannot read data" every time means Bambu reading comes from the scale. Waiting on a spool with a tag:
  prod's #76 (Bambu PLA Green Matte, DR-CT-1) has none, #75 (Beige) isn't where FCC says, and a Bambu support spool may
  be in the to-be-labelled pile. (A Prusament OpenPrintTag spool passed this test on 2026-10-21: `Serial Number:
  6f:c4:ed:18:09:01:04:e0`, `Records: (2)`.)

## 🗒️ Notes and standalone items

> Ordinary backlog items, not hands-on work; most name the group that owns them. This heading was added on
> 2026-10-19 so they stop reading as part of ⏸️ PENDING DEREK above, which had no closing heading.

* **🖨️ Printer Status follow-ups (Derek, 2026-10-24).** _(→ **Group 50**, 2026-10-25: (a) **50.5**, (b) **50.6** with the ⌨️ Enter item, (c) **50.7**, (e) folded into **50.1**, sample first; (d) parked)_ Done before the merge: the printers step in under the title,
  each one's name comes first with its state and 🛑 count on an info line under it, the tiles lost their colour dot,
  and a printer named with an apostrophe gets its count. Left: (a) **a richer hover card for a tile** (a small spool
  card, easier to read, especially in collapsed mode), and **a tap that opens the same card on a touchscreen**, where
  there is no mouse to hover ("how a user who doesn't have a mouse could see that detail, that gets truncated"): design
  it with the phone view, sample first; (b) the scan accumulator in `scripts.html` cancels Enter on every focused
  dashboard button except the ▲▼; (c) on short windows (1280×800 at Large, 1366×768 at Small / Standard) the open
  widget scrolls inside itself; (d) long term, a customizable layout (tiles per row, style) for printers with many
  spools ("with AMS units on the bambu side, things could get crazy"). (e) **The collapsed strip needs the same clean-up
  (Derek, 2026-10-25, on prod):** "I know what is what, but it kind of reads as just a mess of toolheads. Because I
  follow a naming convention, I can tell what's what, but if anyone else doesn't, then it gets confusing fast." He
  found it when the Settings → This Browser "Printer Status toolhead labels" choice (XL-3 / 3 / Tool 3) changed only
  the expanded tiles: he expected the strip to follow it too (Group 46.3 kept the strip on the full id on purpose,
  so that is a decision to revisit). Give the strip a clear per-printer grouping like the expanded view's (the name
  first, its state and 🛑 count, then its heads), sample first. **Standalone.**
* **🐞 A print re-mapped to another head on the printer is charged to the wrong spool (found 2026-10-23).** _(→ **Group 56.6**, gated: a printer and a real print)_ FCC charges
  the file's tool N to head N (`print_deduct.py`, "the tool index IS the toolhead position"). Derek re-maps at print
  start (job 1104 was sliced for head 1 and run on head 2, Group 43.3), and firmware 7.0's sticky and Smart mapping
  make that more common; a SpoolJoin run-out switch is invisible too. The printer's metrics stream (`M334`, UDP) sends
  `active_extruder` every second, the PHYSICAL head on the INDX and XL, which could show both. Facts: metrics are OFF
  in production firmware; changing them asks "Allow the changes?" on the printer's screen; the setting survives a
  restart; a parked INDX reports no tool; plain UDP, so prod would need a UDP port on FCC's TrueNAS app. Next step when
  Derek wants it: a small listener on dev, then one short re-mapped print with metrics on (needs a printer and a real
  print). **Standalone.**
* **⚠️ After a printer moves to firmware 8.0, check FCC's first completed and first cancelled deduct (noted
  2026-10-23).** _(→ **Group 56.7**, gated: the first deducts after an upgrade)_ 8.0.0 (2026-10-22) also brings 7.0's changes to a printer that skipped it (the INDX was on 6.9.2 in
  October): PrusaLink file downloads keep long file names (FCC downloads each job's file by the path PrusaLink reports,
  and prod's ledger holds 8.3 names like `/usb/MAIN-B~1.BGC`), a Runout Reaction setting (FCC's run-out split keys off
  the pause) and tool-mapping changes. PrusaLink's own status looks unchanged in 8.0 (likely, not checked live); 8.0's
  new per-head usage data goes only to Prusa's cloud service, which has no public API. 8.0's OpenPrintTag reader is
  CORE One / L only for now; it adds to a tag's `consumed_weight` every 5 minutes and at print end (cancels too) and
  unload, so once a reader printer writes a tag, FCC's own tag writes must add deltas, never overwrite (an absolute
  write is fine while none of Derek's printers write tags). **Standalone.** **2026-10-26:** every printer is on 8.0 (Derek), and prod's last deducts (to 2026-10-24) still show 8.3 names, so the next completed and cancelled prints are the first on 8.0, and they run Group 56's code (released `main` `1d9cae4`). Claude reads prod's ledger afterwards (read-only); nothing for Derek to compare. The run-out half is the ⏸️ PENDING DEREK swap item.
* **📋 Other modules still put outside text into the Activity Log unescaped (found 2026-10-26 by Group 56's
  review).** Group 56.4 escaped every filename, exception and Spoolman error in the deduct and monitor lines
  (`print_deduct._esc`, an AST canary in `tests/test_deduct_accuracy_56.py`), but about 20 lines in
  `logic.py` (e.g. force-unassign, `:4627-4630`) log `{err}` = `spoolman_api.LAST_SPOOLMAN_ERROR` or `{why}`
  raw, and `routes_locations.py` / `routes_scan.py` / `routes_config_attrs.py` / `routes_inventory.py` log `{e}`
  / `{err}` raw. When Spoolman is down a connect error's `<urllib3.connection.HTTPConnection object at 0x…>`
  vanishes from the line as a bogus tag, and `routes_inventory.py:74` logs a typed filament name raw ('Silk
  <Gold>' shows as 'Silk '), against CLAUDE.md's own rule. Direction: move the escaper to `state` (e.g.
  `state.esc`) and widen the canary to every module. **Standalone.**
* **🔁 A `.bgcode` FCC can't decode is re-downloaded every 30 s for 72 hours (found 2026-10-26 by Group 56's
  review).** `prusalink_api.fetch_cancel_gcode` returns None for a failed download, an empty decode and a
  decode exception alike, so `_compute_cancel_usage` treats all three as "download failed" and the job is
  queued; the monitor then downloads the whole file again on every IDLE tick until the 72 h give-up (for the
  11 MB raccoon file, thousands of downloads). Rare (`decode_bgcode` skips bad blocks), and since Group 56.3 the
  give-up opens a "couldn't download or read its file" review. Direction: report a decode failure separately,
  carry it on the fetch record, and give up after a few attempts. **Standalone.**
* **🎨 Design follow-ups from the 2026-10-22 text-size walk (each one: a sample to Derek before any restyle).** _(→ **Group 59** for (a)–(d), one picture session first; (e) → **Group 57.3**: it is option C of the Group 57 sample, 2026-10-26, see ⏸️ PENDING DEREK)_
  (a) **The slot picker in printer mode:** "it just looks scattered, and it's hard to tell what is what"; its slots
  break onto a second row and leave a lot of empty space after the head list. Rethink the layout (his idea: a 3×3 grid
  for the heads). (b) **The slot picker's Swap / Overwrite / Back panel:** "the buttons are all over the place", their
  two-line labels make it hard to tell which QR does what ("Yellow to Yellow, but what does yellow button do again"):
  use the move questions' pattern, three short buttons each with its QR under it, and the details as one line of text.
  (c) **Settings as a side panel:** section names (This Browser, Connection, Behavior, …) on the left, the open
  section's settings on the right. (d) **Grey help text on black** "might need a re-think later" (the 2026-10-22 build
  only lifted it to pass the contrast guard): with step 2's named colours. (e) **The title bar at Extra Large:** if the
  squeeze ever bothers him, Backlog and Queue could shrink to their icon and count at that size. **Standalone.**
* **📱 Phone view first, with spool tags (Derek, 2026-10-21).** _(→ **Group 60**, an epic, design-first: the view **60.2**, tags **60.3**)_ The phone ("pocket") view comes before the tablet one:
  Android (a Pixel 11 Pro XL), Chrome, a web page (no app for now). Testing over plain http uses Chrome's "Insecure
  origins treated as secure" flag on the phone; real HTTPS comes later from a reverse-proxy container with a
  DNS-challenge certificate, on his network with no open ports. FCC itself stays plain http and platform-agnostic
  (Docker, TrueNAS or anything else). Tags: Prusa's OpenPrintTag first (Chrome on his Pixel read a factory Prusament
  tag); read-only first, then "tap a tag, FCC sees its weight is newer than the tag's and offers to rewrite it"; tag
  links in Spoolman 0.27's own tag table; an unknown Prusament spool opens the Add wizard filled from its tag (as the QR
  scan does); FCC's values stay and the tag fills blanks; Bambu next; OpenPrintTag for untagged spools too (he has ~40
  blank tags). Research: `review-samples/2026-10-21-phone-tags/`. Next: rewrite the step 3 plan doc's order.
  **Standalone.**
* **⚖️ SpoolmanScale that reads every tag and talks to FCC (Derek, 2026-10-21).** _(→ **Group 60.5**)_ His NFC scale project
  (github.com/Niko11111/SpoolmanScale; every part bought, case not printed): "set a spool on a scale, have it read out,
  and then put it away". Its PN532 can't read OpenPrintTag (ISO 15693), so Derek **ordered a PN5180** (Amazon
  B09G2KXPRL; no licence lock-in). Plan: our own copy of the scale's firmware with the new reader (its update check
  off), a hand test before printing the case, and an FCC "stand-in" for the scale's published server spec, so
  weigh-ins go through FCC's rules. Under study: two readers (the PN532 for Bambu-style tags with the stock code, the
  PN5180 for OpenPrintTag) and every brand's tags (research running). Research: `review-samples/2026-10-21-scale/`
  (`corrections.md` first). **Standalone.**
* **🎨 Filament colours aren't the most accurate available (Derek, 2026-10-21).** _(→ **Group 60.6**)_ The hex FCC stores feeds PrusaSlicer,
  on-screen colour picking and the printed swatch labels, so it should match the printed colour, and FCC should record
  where each colour came from. For one real Galaxy Red spool three sources disagree: its tag #bf1d2d, Prusament's spool
  page (what FCC's QR import takes) #8d2129, SpoolmanDB #d94a5a. Research `wf_43831b5c-daf`: each import path's
  source, which source is closest to the printed colour, recording the source, and fixing stored colours. A colour edit
  already asks to reprint the swatch label (when a sample was printed or its label confirmed). **Standalone.**
* **🏷️ 123 of prod's 267 spools have no label status at all (found 2026-10-21).** _(→ **Group 58.5**, the false green tick, ready; **58.6**, the prod repair, a decision)_ `needs_label_print` is missing
  (neither "needs printing" nor "confirmed") on 123 in-stock prod spools, 96 of them from the first import
  (2026-02-11), so the 🏷️ Backlog can't see them; prod's #76 is one, with no label on it. Derek: "the check flag for
  needing a label might not have been applied, or it might have been lost". A scanner-speed `ID:` scan outside an
  audit already turns a missing status into confirmed (`routes_scan.py`), so a scanning pass sorts out the labelled
  ones and the rest could go to the backlog. Also: search cards show the green "label confirmed" tick for a missing
  status (`spoolman_api` reads a missing flag as False); check whether an old bulk-loss path wiped the flag, and
  whether Spoolman's automatic backups still hold older values. **Standalone.**
* **🔍 Audit: Done moves unscanned spools with no confirm and no undo, and unlabelled spools read as lost (traced
  2026-10-21, read-only, `wf_88cad35d-ac5`).** _(→ **Group 58.1–58.4**; Derek decides first what Done does)_ Derek's once-over relies on Audit. `CMD:DONE` (the panel's Done &
  Auto-Park, the FINISH tile's QR, the Location Manager's Done QR) parks every expected-but-unscanned spool at UNKNOWN
  with no confirm, no undo and no check of where it is now, including a spool loaded on a printer that is expected at
  its home box (the head then reads empty). Audit has no notion of "no label": typing an id + Enter marks one found,
  but nothing says so, and there is no "needs a label" action; a label scan during an audit skips the label check.
  One audit covers one place, and a cart expects only spools filed at the cart itself (the rollup is Group 37.6).
  Smaller traps: audit mode takes every device's scans; Hide is one-way; a printed CMD:AUDIT label cancels it; a hidden
  "Clear entire Buffer?" blocks scans; refusal toasts render under the panel; a rogue scan answers 500 on a Spoolman
  timeout; a second Done re-parks; auditing UNKNOWN / UNASSIGNED is destructive; a Spoolman blip at the location scan
  reads as 0 expected. **Until fixed: end audits with Cancel** (full report, nothing moves). Also wanted for the
  once-over: a list of spools filed only at a cart or room (each place's Location Manager shows its own under
  "Loose / Floating"). Trace: `review-samples/2026-10-21-audit/`. **Standalone; a candidate group.**
* **🧪 `test_fab_no_overlap_with_cmd_deck.py` writes 7 spools into dev's shared buffer (found 2026-10-21 by the
  readability review).** _(→ **Group 45.10**; its second half, the spool-details visual skip, → **45.11**, with the duplicate entry under 🧪 Testing)_ It doesn't call `conftest.own_the_buffer`, so a run leaves dev's buffer changed (the reviewer
  put it back to []). Also: `test_baseline_spool_details_modal` always skips (no buffer cards after search closes), so
  its April baseline is never compared. **Standalone.**
* **Emptying a plain field in the wizard doesn't clear it (found 2026-10-21 by the extras-clear fix).** _(→ **Group 54.5**)_ The wizard
  drops a native field it reads as empty from its payload (`settings_extruder_temp`, `settings_bed_temp`, price, the
  spool's and the filament's empty weight), so erasing one and saving keeps the old value. Not an extra, so the
  sentinel doesn't cover it: an edit-mode clear would send `null` for these (Spoolman takes null for its own optional
  fields; check each on dev first). **Standalone.**
* **Partial PATCHes once Spoolman 0.26 is the minimum (Derek's call; noted 2026-10-21).** Dev and prod run 0.27.0,
  which merges a PATCH's `extra` key by key, so `update_spool` / `update_filament` / `update_vendor` could send only the
  keys they change. Today they still read the record's whole extras and re-send them (and refuse a write when that
  read fails, Group 36), the guard a Spoolman that replaces `extra` needs. Dropping it saves a read per write and
  removes a refusal, but only while no older Spoolman is ever pointed at FCC. **Standalone.**

* "[03:00:52] ⚠️ 🦝 Core One INDX: 27.12g of '/usb/MAIN-B~1.BGC' wasn't deducted (no bound spool, a failed write, or a near-empty spool) — weigh that spool to true up.
[03:00:52] ✅ Completed-print deduct on 🦝 Core One INDX: 34.2g across 1 spool(s) ('/usb/MAIN-B~1.BGC').
[03:00:52] ✔️ Auto-deducted 34.2g from Spool #99 (Complete): [34.2g at start ➔ 0.0g remaining]
[03:00:52] 📦 Auto-archived Spool #99 (remaining weight hit 0) — moved to UNASSIGNED" 
We should check to see if this worked as intended and deducted properly across both spools. the final message, abut needing to true up, I'm not sure if it was needed or not. It looks like everything was accounted for? by maybe not. This was a print where the spool was joined (T1 to T2) so that the print would use up a spool and move on to the next. I'm not sure if this complete properly. And if not, we should give a vehicle to allow the user to follow up porperly if possible? I think it wokred with an earlier print, but only because the first spool had more listed on it than it actually did have, so that might not have full deducted the proper amounts from each spool.

  **🔎 TRIAGE 2026-10-08 — confirmed: it did NOT deduct across both spools, and Derek's "only because the first spool was over-stated" hunch is right.** Read read-only from prod's `print_deduct_ledger.json`: job **1104** `/usb/MAIN-B~1.BGC` recorded **`grams: 34.2`** — the print needed **61.32 g**, spool #99 held 34.2 g, so the deduct clamped to the real remaining, zeroed the spool and auto-archived it; the other **27.12 g was charged to nothing**. Jobs **1105** and **1106** are the same file at `grams: 0, dismissed: true` (the two "couldn't be deducted" reviews). Job **1107** `/usb/MAIN-B~2.BGC` took the full 61.32 g cleanly. The ledger entry for 1104 carries no `shortfall` field, so the discrepancy isn't even recoverable from the record — only the Activity Log warning. **So the joined slot's spool is over-stated by 27.12 g.**
  **Mechanism (Derek's correction, 2026-10-08 — an earlier analysis had this wrong):** a "joined" spool is NOT a physical splice. It is a printer setting: when the filament sensor detects a runout on one slot, the printer AUTO-SWITCHES to the joined slot and keeps printing — effectively a tool swap the printer performs by itself. This is the key difference from a single-head runout, where the sensor PAUSES the printer into load-filament mode and the user swaps filament in the same feed. FCC's existing runout detection keys off that pause (the ATTENTION-park state poll), so **a multi-head spool join may produce no state transition at all** and nothing enters `swap_log`. Also note the slicer's view: a spool-join print is sliced for ONE tool, so the footer attributes 100% of the grams to that tool and the joined slot's share exists nowhere in the gcode — detection can only be runtime, never from the file. Whether the printer exposes ANY pollable signal for the switch is the open question.
  **Two separable pieces of work:** _(piece (2) → **Group 43.2, ✅ shipped 2026-10-14**: an uncharged remainder of 1 g or more now opens a 🛑 review card to pick the spool that took it, see `completed-archive.md`; piece (1), detecting the auto-switch, stays standalone and data-gated)_ (1) **detect** the auto-switch (needs a pollable signal — open); (2) **the follow-up vehicle Derek asked for** — today a PARTIAL deduct with a leftover only logs a WARNING, while the `spools_updated == 0` case stashes a recoverable review. Routing a non-zero shortfall into that same "Review / Discard" affordance is the smaller, independent half, and it would have caught this. ⚠️ Blocker to check first: the exactly-once ledger keys on `printer::job_id` with no position component, so job 1104 is already "processed" — a later top-up may be refused unless the design handles that. Related: the audit's partial-failure finding (one failed head of N burns the ledger) and the separate `📉 cancel-path parser ~7% below footer` item. **2026-10-13 (Derek, answering 43.2):** on small spools the recorded weight can be well off (job 1104: he thought #99 had enough to finish), so he'd like FCC to catch a joined-spool switch, one head used and then the printer moving to another, if the printer exposes it. That would need a history of toolhead changes and may get messy: a follow-up idea for piece (1), not a commitment. Known so far: PrusaLink reports nothing per slot, and the swap-diff logging shipped 2026-10-08 will show what FCC can see on the next joined-spool runout (the SpoolJoin item in ⏸️ PENDING DEREK). **Standalone.**

[03:59:40] ⚠️ 🦝 Core One INDX: print used ~61.32g ('/usb/MAIN-B~1.BGC') but it couldn't be deducted (no spool bound to the toolhead, or the write was rejected) — Review to apply once it's bound, or Discard.
[17:09:11] ⚠️ 🦝 Core One INDX: print used ~61.32g ('/usb/MAIN-B~1.BGC') but it couldn't be deducted (no spool bound to the toolhead, or the write was rejected) — Review to apply once it's bound, or Discard.
This should have an option to select a different loaded spool, or any spool. Currenlty the bgcode directs to toolhead 1, but I've been printing from toolhead 2, which was done on the printer when selecting an existing file to print. If possible, we need to check for this senerio, and try to accomidate it. Or give an option to easily re-direct the deductes to the correct toolhead. _(✅ **Group 43.3**, done 2026-10-13: every review line now has a spool picker — a spool that was on a head when FCC logged the print, one on a head now, or any spool by #id. See `completed-archive.md`.)_

* ✅ **Derek's INDX printer-setup report and its ✅ HOTFIXED 2026-09-29 triage** — archived 2026-10-12 (Group 47.14 + 47.29). `completed-archive.md` keeps both verbatim, including the refusals Group 44 must replace. The hotfix (`main ab48e45`) fixed the connection, stale-location and Settings→Location-list asks; the rest are Group 44 (44.0–44.4: one add/configure flow, renames, toolhead editing) and Group 46 (46.2 Type + "t" + Enter, 46.3 toolhead label display).

* Printers sometimes have on device filament storage, spool roll holders, etc. Perhaps we should make a new slot type, or virtual slot, to help track stuff on the actual printer. I noticed this while looking at the core one's extended info in the printer status section. Realized there was a warning about a slot not being selected, and realized, that we don't really acknolege the fact that the printer itself might have a storage location for filament. I'm not sure if this really makes sense to put in, but it's something to consider down the line to possibly help clean up some ambiguity. And in some instances, I might have a box attached and be using this "on device" storage for filament. So this might complicate things more. Either way, it should be evaluated and see if it's something we should implement. _(→ **Group 37.5**, with the pointer below; the no-code holder setup is the ⏸️ PENDING DEREK INDX-holders item.)_

* **On-device filament storage (Derek's second report above)** _(→ evaluate in **Group 37**; cross-referenced from Group 44)_ — where it would fit, from the 2026-09-29 investigation: a new storage Type (e.g. "Spool Holder") parented under the Printer row, NOT added to `TOOLHEAD_TYPES`; if it should feed toolheads, widen the Dryer-Box-only feeder checks (`== DRYER_BOX_TYPE`) to a feeder-type set and reuse `slot_targets`. Evaluate with the location-system redesign. **2026-10-19 (refresh):** now **Group 37.5**. The interim needs no code: a Dryer Box row per holder group with slot n → `RCOI-n` (an ID that must not start with `RCOI-`), which is Derek's layout and labelling to do first (the ⏸️ PENDING DEREK INDX-holders item, with his holder details). Whether holders get a proper "Spool Holder" type is Group 37's question: a USS Prusa drybox on a holder behaves like a PolyDryer, minus the drying unit.
* **Printer / toolhead LocationID rename cascade** _(→ **Group 44.1**)_ — the hotfix refuses changing the LocationID of a printer that owns toolheads, or of a toolhead on a printer's list, because nothing re-keys what hangs off it. A real rename needs one server operation under the write lock + active-print guard: the row id, children's `parent_id`, `toolheads[].location_id`, Dryer Box `slot_targets`, `PRINTER:<prefix>` sentinels (+ `PRINTER_ROOM_OVERRIDES`), every Spoolman `spool.location` including archived spools, and location ids inside spool extras (`physical_source(_slot)`, `fcc_pre_archive_location`, `fcc_pre_audit_location`), then a label-reprint flag. Derek: "this should be easier to change".
* **Per-printer state is keyed by display Name** _(→ **Group 44.2**)_ — renaming a printer mid-print drops the `_PRINT_TRACKER` latch / `print_tracker_latch.json`, strands `pending_cancel_fetches.json` (abandoned after 72 h with 0 g) and `no_spool` reviews, splits the deduct-ledger history, and orphans per-printer config values (`path_filament_g`, Group 35's planned per-printer map). Short term: refuse a Printer Name change while a print or pending review exists for the old name; long term: key all of it by the Printer row's LocationID (revisit Group 35 decision G1). _(2026-10-19: Group 35's G1 is re-decided: per-printer settings are keyed by the Printer row's Location ID.)_
* **Settings toolhead editor: one printer-name field per printer** _(→ **Group 44.3**)_ — the name lives on every toolhead row (the hotfix mirrors an edit across a printer's rows and fills new rows); a per-printer header row (name + connection + "add toolhead") would make the model obvious, and the Location Manager's Printer view could show the connection status with a jump to Settings.
* **Location Manager "Add child" on Printer rows can come back** _(→ **Group 44.4**)_ — dev's Group 34 add-redesign hides Add-child on printer topology because "a toolhead created via api_save_location would be invisible to Quick-Swap + print-deduct". Since the 2026-09-29 hotfix a Tool Head created under a printer as `<printer>-<n>` joins its toolhead list automatically, so Add-child could be offered on Printer rows with the next `<printer>-<n>` pre-filled.
* **🖨️ EPIC — make a printer a FIRST-CLASS object with a real add/configure flow, instead of a generic location married to its toolheads by name.** _(→ **Group 44**: the 44.0 design pass)_ _(Derek, 2026-10-08: "we should come back and fix this properly with a proper way to add/configure printers, instead of treating them as generic locations, and marrying them up to the toolheads in the settings based on name alone, which cannot be changed after the fact.")_ **This is the parent the surrounding printer items are all symptoms of** — file fixes under it rather than as new siblings. The shape of the problem: a printer is a `locations.json` row whose Type happens to be `Printer`, its heads are sibling rows joined by a LocationID prefix convention (`<printer>-<n>`), its tool indices live in a separate `toolheads[]` array, its connection lives on the row, and its per-print runtime state is keyed by the *display Name*. Nothing enforces that these four agree, and several can't be changed after creation. Concrete symptoms already filed separately, each of which this would subsume: the LocationID rename cascade (a printer that owns toolheads can't be renamed because nothing re-keys `toolheads[].location_id`, Dryer Box `slot_targets`, `PRINTER:<prefix>` sentinels, Spoolman `spool.location` and the location ids inside spool extras); per-printer state keyed by display Name (renaming mid-print drops the `_PRINT_TRACKER` latch and strands pending reviews); one printer-name field smeared across every toolhead row in Settings; "Add child" disabled on Printer rows; the removal guard over-counting on a dual-role → multi-head conversion; and Derek's original INDX report ("incredibly cumbersome… delete the printer from the location list first, then move to settings to change the name and API connection"). **Evidence this is structural, not cosmetic (2026-10-08):** `_derive_printer_room` has three arms — a `Location` column (pre-L271, no longer written), a dash-prefix parse, and a hardcoded `PRINTER_ROOM_OVERRIDES = {"XL": "LR", "CORE1": "CR"}` that still names the retired `CORE1` — and all three failed for `RCOI`, so the INDX rendered as a top-level root beside the rooms instead of inside Computer Room, with only a WARNING in `hub.log` that nobody reads (fixed by hand on dev + prod the same day). A printer created today is born mis-parented, and the only reason the XL isn't is an accident of the original CSV import. Related: the legacy-column relaxation below, which was the surface symptom that surfaced this. **Wants a design pass before any code** — at minimum: what identifies a printer (a stable id, not the Name and not the LocationID prefix), how heads are attached and re-ordered, where the connection lives, and a migration for the three existing printers. Probably folds in the Settings↔Location-Manager split that the 2026-09-29 hotfix papered over. **Still open (2026-10-13): "what identifies a printer" is for one design sit-down, together with Group 37's fork 1.** Derek's input, from his Room-delete answer: reorganise by renaming / re-ID'ing rather than deleting, with IDs that stay readable (where it is, what it is, which one); his words are on the 🌳 LOCATION SYSTEM REDESIGN item.
* ✅ **Legacy-column schema check relaxed 2026-10-08** — archived 2026-10-12 (Group 47.14, see `completed-archive.md`); the proper schema is Group 44's job.
* **Deleting a printer's last toolhead leaves `PRINTER:<prefix>` pool bindings dangling** _(→ **Group 44.6**)_ — the box's Feeds save then fails with a 400 (the Settings guard blocks the same removal). Drop the sentinel when the prefix disappears, or refuse the delete with the Settings guard's reason.
* **Dual-role printer → multi-head: the removal guard over-counts** _(→ **Group 44.5**)_ — once any `CORE1-n` head holds a spool, removing the `CORE1` self-entry is blocked by a prefix-matched "spools are stored there". Check removed keys with an exact-location spool lookup. (Prod moved the INDX to a new `RCOI` prefix, so this only bites a future in-place conversion.)
* **🔄 Refresh dev's data from prod (locations, Spoolman inventory, config) — and make it a repeatable operation.** _(→ **Group 45.6**)_ _(Derek, 2026-10-01: "we should also now consider updating dev to a more recent version of the data on prod". Explicitly NOT urgent — filed as the follow-up.)_ Dev's `locations.json` and dev Spoolman (`:7913`) have drifted from prod (`:7912`, files at `\\TRUENAS\App_Data\InventoryHub`): prod now carries the `RCOI` INDX printer with RCOI-1…RCOI-8, while dev still reflects the older fleet, and dev's locations carry test residue (e.g. the blank-`LocationID` "TestCart" row that is the standing Group 37.1 red pair). Consequences while it drifts: E2E fixtures encode a fleet prod no longer has, "does this repro on prod?" gets harder to answer, and the gap quietly grows. Wanted deciding: how much to copy (locations only, or Spoolman spools/filaments/vendors too), what dev-only state must survive a refresh (the fixed `DEV_BOX_BINDING_BASELINES` boxes PM-DB-1/2/4/5 at `{}`, the virtual test spools), and whether this becomes a scripted `--refresh-from-prod` alongside `--reset-dev` or stays a manual copy. ⚠️ Read-only against prod — a refresh must never write to `:7912`. Would also let the TestCart row be dropped and close the Group 37.1 pair. **Decided 2026-10-13 (Derek): script the full refresh:** locations plus the Spoolman inventory, prod read-only, the dev-only test fixtures re-applied and the reset snapshot retaken. Run it one evening when Derek is around to approve the prod reads; still not urgent. (The TestCart row was deleted separately on 2026-10-13, so that pair already passes. And since this was filed, dev's locations were copied from prod on 2026-10-08, so dev already has RCOI; dev's Spoolman inventory is still June's.) **Standalone.**

* **🔀 Bulk Move polish (while the feature flag is off).** _(Low priority. Bulk Moves (L298) is complete and ships dark behind `fcc.bulkMove.enabled` (default off, `config_schema.py:97`: prod dark, dev on), so none of this reaches prod until Derek turns it on after the ⏸️ PENDING DEREK hands-on pass. Merged 2026-10-12 (Group 47.11) from two of Derek's reports: the wrong/empty-source report (2026-08-13, filed 2026-09-12) and item 3 of the Bulk Move active-print testing report (2026-09-12). That report's items 1–2 shipped in `51d9a49` and are archived; its item 4, dev/prod data parity, is Group 45.6.)_ Build both parts together when the feature is turned on. The flag's own gate gap (three backend doors ignored it) was fixed 2026-10-13 and archived. **Standalone** — L298 is complete; don't nest this under it. **2026-10-19:** the multi-user awareness item's last door, the Bulk Move commit vs its preview (`logic.py:3824-3862`), rides with this; build it when Bulk Moves is turned on.
  1. **A wrong or empty SOURCE can only be escaped by cancelling the whole move.** Derek, driving the L298 panel on dev 2026-08-13: "once a destination is scanned, any other location scans updates the destination source only, so if the source has 0, and the destination has 0, you have to cancel the move entirely to re-assign a new source location… a little bit of push back from the UI for the user." Row→row moves themselves tested fine, e.g. `CR-CT-2-R3` ⇄ `CR-TC-2-R1`.
     - **Mechanism — deliberate, not a regression.** `process_bulk_move_scan` (`logic.py:1515`) takes the FIRST location scan as the source and unconditionally advances to `awaiting_dest` (`:1567-1572`); every later location scan RE-TARGETS the destination (`:1574+`, by design — "the user changed their mind before committing"). Nothing checks that the source holds anything, so an empty source still arms and the preview has nothing to move — and the only way to pick a different source is `CMD:CANCEL`.
     - **Suggested fix (small, no semantic change):** refuse a zero-spool source at the source-capture step — stay at `awaiting_source` and toast + log *"CR-TC-2 is empty — scan a different source"*. One extra read at scan time (the same `get_spools_at_location_detailed_strict` the planner already calls, `logic.py:1087`), and the re-target-the-destination behaviour is untouched.
     - **Build it together with the Location-redesign interim note below** (*"when a bulk-move source has nested children, the preview should say `N spools sit in 3 sub-locations and will NOT move`"* — confirmed still unbuilt 2026-09-12). The two collide on carts: `CR-CT-2` held 0 spools directly and 8 in its rows (2026-08-13), so a bare "is empty" would mislead there — the refusal should say *"no spools directly on CR-CT-2 — 8 sit in 3 sub-locations."* Once Group 37.4 makes contents transitive, the same check simply stops refusing it.
     - _Alternatives considered:_ a "change source" button in the preview panel; or letting `CMD:BULKMOVE` re-arm an active session instead of safe-bailing (the `/api/bulk_move_session` start action already accepts `replace: true`, `routes_scan.py:461`).
  2. **🟡 Discoverability and input while armed** (working as built, but unintuitive). Derek, 2026-09-12, testing during an active print: "I found that I couldn't key in a location manually (by typing the location LOC:XX-XX-X) to set it, I later realized that I could go to a location as source and start that way, which is good, but didn't know it was a feature… there didn't seem to be a way in there to set the destination… I thought if I scanned the barcode for the locaiton in the window that would add it, instead it created anotehr move source window… I also found that I couldn't type in a spool ide with the bulk move window open."
     - Typing `LOC:…` or a spool ID does nothing with the panel open: it mounts with `backdrop: true` (`inv_cmd.js:1005`), so the manual-entry field can't take focus, while a hardware scanner still works. By design, every scan during a session routes into the bulk move and spool scans are refused ("Scan a LOCATION during a bulk move (or CMD:CANCEL)", `logic.py:1599`), so nothing can join the buffer while armed.
     - There is no in-panel way to set the destination; it only comes from a location scan. Scanning a location label while the panel was hidden DID set the destination, but showed nothing until the panel was reopened via the 🔀 pill. (The 2026-09-12 triage didn't separately explain "it created another move source window" — check what that window was while doing this.)
     - "Move all →" in the Location Manager (starts a move with that location as the source) is an undocumented entry point.
     - Suggested polish: an in-panel location field for source and destination (typed/pasted `LOC:` or bare IDs), a toast when a hidden session captures a destination, and a short "how to" line in the empty panel.

* Add readme documentation and images to the readme file for the Filament Command Center project. _(→ **Group 55.1**: a short README written for Derek, with fresh screenshots.)_

* ✅ **Deferred findings from the 2026-08-05 session-diff review** — archived 2026-10-12 (Group 47.9, see `completed-archive.md`). Both of its open sub-bullets are done: the `slot_targets` reader migration (fixed 2026-10-13, archived) and the cancel-deduct retry idempotency (Group 43.6).

* ✅ **DATA LOSS when removing a filament-attribute choice** — fixed by Group 36 (`43389c6` + `a9a582d`); archived 2026-10-12 (Group 47.1, see `completed-archive.md`). Its three unfiled follow-ups are the "Group 36 follow-ups" item below.

* ✅ **When creating new locations, a blank Location ID was accepted, then "already exists" on re-edit** _(Group 46.5, was 37.1)_ — fixed and archived 2026-10-13 (see `completed-archive.md`): a blank LocationID is refused (client + 400), the editor won't open a blank row (it says to delete it and add it again), and 🗑️ on that row now removes it (`DELETE /api/locations?blank_id=1`). Dev's `TestCart` row and prod's `Unknown Location` row were still there when this was archived — Derek's call; deleting dev's clears the two standing sweep reds. **Decided 2026-10-13 (Derek): dev's row is gone.** Claude deleted it through that 🗑️ path (`DELETE /api/locations?blank_id=1`: 82 → 81 rows, no spool touched), and both sweep reds now pass. `CR-TC-1`, also named "TestCart" (with its row `CR-TC-R1`), is kept. Prod's `Unknown Location` row was not part of this.

* On a new location created, when hitting the manage button the unassigned list shows up and pushes the ui elements off the visible screen, the unassigned list should be scrollable within the view available, and should be easily collapsible reguardless where the user is in the list. So that the user can get to the lower UI elements. _(→ **Group 37.2**)_

* Creating parent child locations is still tedious and needs to be refactored so it's less work to do. Clicking the + button on a parent item, doesn't seem to help autofill the new child element when the window opens, leaving the user to have to fill in that data as well. Also smart suggestions for the location id might be a good idea. Originaly location id was ment to be human readable, but maybe we need to re-think this so it's less cumbersome for the user if they want a readible path. (CR-TC-R1, hard to remember, setup and keep track of when you have to exit and re-create each new row from scratch (with the 1, becoming a 2 in this case for a new row add.)) _(→ **Group 37.3**)_

* **🌳 LOCATION SYSTEM REDESIGN — the five items above share one root cause; scoped, not started.** _(→ **Group 37**; its 37.1 moved to Group 46.5)_ _(Derek's call, 2026-08-03, while driving the L298 Bulk Move panel: "I think we might need a refactor on how this whole location system works and displays… I feel like things need a re-design before we dig deep into developing a preserve-row-structure path.")_ **Full evidence + open forks → [docs/agent_docs/tasks/location-system-redesign-scoping.md](docs/agent_docs/tasks/location-system-redesign-scoping.md).** Members: the three items directly above (blank LocationID accepted then "already exists"; unassigned-list overflow on a new location; tedious parent/child creation + ID legibility), the auto-gen-id finickiness filed below, the older "adding sub-locations is messy", and Group 34 S5 (deferred — its plan mandates a `locations.json` backup as step 1). **Fork 1 (the LocationID model) is still open (2026-10-13), for one design sit-down together with Group 44's "what identifies a printer?".** Derek's input, from his Room-delete answer: reorganise by renaming / re-ID'ing, with IDs that stay readable: where it is, what it is, which one. In his words: *"But the ID system still needs some sort of work to get it in a better shape than what it currently is. (LR-MDB-1 to something else, but still maintains a readable Location, what it is, which it is based ID kinda system.)"*
  **🔬 ROOT CAUSE of the display + bulk-move half — PROVEN by source trace 2026-08-03.** `locations_db.location_prefix` splits a LocationID on the **first dash only** (`locations_db.py:543-548`), and that is the only non-exact match in `spoolman_api._build_location_match` (`spoolman_api.py:1467`). Since every descendant of room `CR` — `CR-CT-1`, `CR-CT-1-R1`, `CR-WLN-R1-SC1` — has first segment `CR`, the granularity is **binary, not one-level**: a ROOM query reaches its whole subtree at any depth, and **every other level is exact-match-only**. The prefix branch is effectively dead code for Cart / Wall Shelf / Row / Section queries. That single fact produces all three observed symptoms, because `/api/get_contents` (`routes_locations.py:648`), the bulk-move source resolver (`get_spools_at_location_detailed_strict`), and the destructive clear/delete paths **all call the same matcher** — one flat reader answering three different questions (*what is in here* / *what may I move* / *what may I destroy*). Only the third needs to stay flat.
  ⚠️ **Contradiction visible on screen:** the `/api/locations` occupancy rollup IS transitive over `parent_id` (`routes_locations.py:127-140`), so cart `CR-CT-1` shows a **Total including its rows' spools** while opening that same cart lists **zero**.
  ⚠️ **The L298 D2 safety contract depends on NAMING, not structure.** A room query misses `XL-1` only because `location_prefix("XL-1") == "XL" != "LR"`. Nothing structural enforces it — **name a toolhead `LR-…` and a room-level clear sweeps a live print.** Any redesign must replace this with an explicit active-print/type guard rather than inherit it.
  **Constraints from the REAL dev topology** (read-only inspection of `data/locations.json`, 56 rows): per-row capacity is **not tracked** — 27 rows have `Max Spools = ''`, including *every* cart and cart-row, so L298's D3 capacity pre-flight cannot fire on a cart→cart move; there is **no 1:1 row correspondence** between actual carts (`CR-CT-1` = `R1/R2/R3` vs `DR-CT-1` = `R1, R2-L, R2-R, R3-L, R3-R, R4-L, R4-R`); and **`Type` cannot identify a row** (26 rows are Type `Cart`, including the `R1/R2/R3` children), so any structure-aware feature must walk `parent_id`.
  **✅ Decisions 2026-08-03 (Derek):** (1) **structure-preserving bulk move DEFERRED, possibly dropped** — *"a feature I'm not 100% sure I'm going to use that often… might just make sense doing it using the existing bulk ability with the buffer and a location scan"*; do NOT build it before the redesign settles the model. (2) **The cart-display fix is folded into this redesign** rather than shipped as a point fix, since the redesign will change those semantics anyway.
  **Interim recommendation (small, survives the redesign):** don't widen bulk-move scope yet — that means replacing the naming-accident active-print guard against semantics about to change. Just kill the *silent no-op* that reads as a bug: when a bulk-move source has nested children, the preview should say `"N spools sit in 3 sub-locations and will NOT move"`. Leaves the locked D2 contract alone.
  ℹ️ **The blank-LocationID row in live dev data was Derek's own repro, NOT test residue** — `data/locations.json` row index 0 is `{"LocationID": "", "Name": "TestCart", "Type": "Cart", "Max Spools": "0", "parent_id": "CR"}`. **Do not delete it without asking**; it's the reproduction case for the first item above. **Deleted 2026-10-13**, per Derek's answer, once 46.5 had shipped the repair path (see the 46.5 item above).

* **🔎 CODEBASE-WIDE ADVERSARIAL REVIEW — stop finding the same CLASSES of bug one feature at a time.** _(Derek's ask, 2026-08-03.)_ _(→ axes **(d)** and **(e)**: **Group 53** (53.2, 53.3), as cheap source canaries instead of agent reviews (2026-10-19). Axes (b) and (c) stay parked: one idle window each, with Derek's OK on the axis and the window.)_ **The case for it, from evidence rather than vibes:** every per-diff review on L298 found real defects, but the most valuable ones were **cross-cutting patterns that exist all over the app and were only noticed because a new feature tripped over them** — (1) a focused `<input>` silently DISARMS the barcode scanner (the global handler's first line is `if (e.target.tagName === 'INPUT') return;`) — *every* modal/overlay with a text field has this property and nobody has audited which ones matter; (2) Bootstrap confirms render BEHIND `mountOverlay` panels (z ~1100 vs 20000) **and** set `state.activeModal`, swallowing scans — so any `requestConfirmation`/`promptSafety` called from inside an overlay is an unreachable dead end; (3) `scripts.html`'s load order silently no-ops `if (window.X)` guards for modules loaded before their provider; (4) a write endpoint that reports `success:false` into a caller that never checks (the `_restore` no-op that silently corrupted dev data for months). **None of these are feature bugs — they are house-wide invariants with no test and no lint.** **Recommended shape (NOT "review everything", which is unaffordable and low-yield):** pick the review axis by RISK SURFACE, one batched workflow per axis, findings verified in BATCHES (never one agent per finding — see the CLAUDE.md Workflow budget rule). Candidate axes, roughly in value order: **(a) scan-path integrity** — every `document` keydown listener + every focusable input vs the scan accumulator; ✅ **DONE 2026-08-03/05** — 11 distinct findings, all fixed or decided (`ef1e422` + `4f10e35` + `34d0fe3`); write-up [docs/agent_docs/tasks/scan-path-integrity-findings.md](docs/agent_docs/tasks/scan-path-integrity-findings.md), archived 2026-10-12 (Group 47.5); **(b) overlay/z-order + confirm reachability** — every `requestConfirmation`/`promptSafety`/`Swal` call site, is it reachable from where it is invoked?; **(c) silent-failure audit** — every caller of a function that can return `success:false`/`None` and doesn't check (the 2026-04-26/27 outage class, and the `_restore` bug); **(d) write-surface conformance** — the CLAUDE.md "Spool / Filament write surfaces" table vs reality; **(e) load-order/export guards** — `if (window.X)` patterns vs `scripts.html` ordering. **Estimate:** ~4–8 agents per axis, roughly 0.5–1M tokens each — so run them ONE AXIS AT A TIME in idle windows, never as one mega-sweep, and treat each as its own working group with its own fixes + pins. ⚠️ **Budget-sensitive** — shared subscription with paid work ([[feedback_agent_budget_and_windows]]); agree the axis and the window before launching.
  _Note for the record: L298 itself HAS been adversarially reviewed — twice on this branch (Phase 3: 8 agents / 1.37M tokens / 40 raw findings; Phase 4: 4 agents / 590K / 23 raw, 0 refuted), plus Phases 0–2 earlier. This item is about the codebase AROUND it, not about re-reviewing Bulk Moves._

* **🧪 Attribute-suite residuals: `/api/update_filament`'s generic rejection, and max-attribute coverage of the chip renderers.** _(filed 2026-08-03 as "`test_filament_attributes_bulk_api` mutates REAL dev inventory and wedges itself"; narrowed 2026-10-12, Group 47.7.)_ ✅ **Shipped and archived:** `6834b7f` makes the suite own its data (a `scratch_filament` record) and opt-in, and `_restore` now sends the real `{id, data}` shape and asserts the write took; `34d0fe3` pins max-attribute support (`tests/test_max_attributes_supported.py`: the label-CSV Type column, the report's counts, `sweep_unused`); the `sweep_unused` force_reset hazard went to Group 36. **Two small residuals, low priority:** _(→ **Group 54.1** and **54.2**, 2026-10-19)_
  **(1) A malformed payload still gets a generic answer.** A body without `data` (the old `_restore` shape, `{id, field, value}`) still returns `{"success": false, "msg": "No fields to update."}` (`routes_scan.py:175-178`). That generic message is what hid the `_restore` no-op for months. Reject an unrecognized payload shape loudly instead, naming the missing `data` key.
  **(2) Max-attribute coverage stops short of the UI.** Derek: *"Highly unlikely in reality, but we should make sure that having that many attributes doesn't break things like it might be doing right now, so we should probably put in some tests for this kind of thing, so that it's supported, even though it might not currently be possible."* Nothing pins the wizard/details chip renderers with every choice applied (28 chips: layout and overflow). Search and filtering get the same case once the "Adding attributes in search" item ships.

* **🟡 Group 36 follow-ups: three low-priority hardening items (all dormant on current data).** _(Recorded only in the Group 36 task file since 2026-08-06; filed 2026-10-12 by Group 47 at Derek's call. Group 36 itself is archived.)_ (1) **The pre-merge extras read has no retry.** Since Group 36, `_get_raw_extras` (`spoolman_api.py:442`) returns `None` on a read failure and its callers refuse the write rather than wipe siblings. That is correct, but a Spoolman blip now produces a false refusal. A retry would cut those, but it has to stay inside the `spoolman_api.requests` seam that eleven test files patch: routing it through `http_retry` was tried and reverted for exactly that reason. (2) **`_parse_filament_attrs_value` collapses a non-JSON string** such as `"Silk, Matte"` into one pseudo-tag, so real tags can read as zero-usage and therefore sweepable. (3) **`setup-and-rebuild/setup_fields.py:244-247` still sends a partial-`extra` spool PATCH** (`{"extra": {"container_slot": value}}`), the replace-the-whole-`extra` landmine, inside `migrate_container_slot_to_text`, the function CLAUDE.md names as the template for type migrations (dormant, guarded). Source: [docs/agent_docs/tasks/36-attribute-force-reset-data-loss.md](docs/agent_docs/tasks/36-attribute-force-reset-data-loss.md), "Follow-ups". _(→ (1) ✅ built by **Group 52.2** (2026-10-19: one more try 0.5 s later on a timeout, a 5xx or a garbled answer; archived); (2) **Group 54.3**; (3) **Group 54.4**; grouped 2026-10-19.)_

* Part of Group 34, I noticed that the auto id generate is a bit finicky. If you + on a base location (say room) and then decide you want to change it in the location section, it doesn't auto update the id to match the new location id breadcrum (CR-CT1-R1, vs just CR-XXN). Also the system isn't very aware of the numbering conventions, and looks like it would over write existing location types with R1 always, instead of being aware of the current location topology. If there was an R1, and I was trying to make another row, R2 should auto populate. This all might be part of the other half of 34 that is currently on hold. We need to look into this a bit more to try and make it either easier, or clearer to the user.

* **Per-printer settings section in the Config tool (refactor).** _(→ **Group 35**, N6)_ `config_schema.py` only supports FLAT scalar fields (bool/int/float/string/select) — one value per key. Genuinely per-printer values need a per-printer **map** field type + a UI renderer (the "per-printer settings" modularization). First customer: **`path_filament_g`** (the runout sensor→nozzle remnant, Group 22.3b) shipped 2026-07-03 as a **single value for all printers** (Config → Behavior) as an interim — the reader already accepts a `{printer_name: grams}` map for when this lands (Core One ~2 g, XL ~4 g). Other candidates that would move here: printer creds, nozzle offsets, per-printer path length. Overlaps the **L18 Phase 5** config-modal-reorg follow-up (fold together). _(Derek 2026-07-03: per-printer settings are worth modularizing; "the whole thing probably needs a bit of refactoring.")_ _(2026-10-19: keyed by the Printer row's Location ID, `XL` / `RCOI` (Derek's re-decision of G1); the runout path item below is its first customer.)_

* **Runout path filament per printer (and maybe per toolhead).** _(Derek, 2026-10-19; → **Group 35**, whose per-printer
  settings make it possible.)_ Settings → Behavior → "Runout path filament (g)" (`path_filament_g`) is ONE value for
  every printer today (0 = off). Derek: each printer can have a different tube length between the filament sensor and the
  toolhead; *"We may even want this to be per toolhead at some point. But I'm pretty sure that the sensor distance between
  the xl and the indx are probably not the same length. But I haven't confirmed this, it's just based on eyeballing the
  lengths."* The deduct already reads a `{printer_name: grams}` map (`print_deduct._path_filament_g`); Group 35 adds the
  per-printer settings UI. **Decided 2026-10-19 (Derek): key it by the Printer row's Location ID (`XL`, `RCOI`) now**,
  so it needn't wait for Group 44; if that sit-down changes how printers are identified, its migration re-keys these
  values. A per-toolhead override (keyed by the head's Location ID) can come later on the same setting.

* **ColorMix support for Project Color Loadout (L391) — design addendum (2026-07-02).** ColorMix (new in PrusaSlicer 2.9.6) breaks L391's one-color-per-slot assumption: it renders a NEW apparent color by alternating 2–3 loaded filaments per-layer (ratios 1:1 / 1:3 / 3:1 / 1:1:1) on a toolchanger (XL / Core One+ INDX) or MMU. Full scoping in [docs/Project-Color-Loadout/colormix-addendum.md](docs/Project-Color-Loadout/colormix-addendum.md): (1) the loadout model needs a **"mixed slot"** (constituents + ratio → one apparent hex); (2) the `.3mf` parser must read the ColorMix **recipe**, not collapse it to one hex; (3) **killer synergy** — extend the Phase-4 Delta-E suggestion to propose a ColorMix **blend** when no single owned filament matches ("no Teal, but Blue+Green 1:1 = ΔE 3.2"); (4) Smart-Cart shortage math splits a color's grams across its constituent spools. FCC's completion deduct already handles the print-time reality (per-tool footer — no new deduct code). **Blocked on Derek slicing a real ColorMix `.3mf`** to confirm the recipe representation (capture checklist in the addendum). Do when L391 is picked up; standalone — don't nest under a completed epic.

* **Filament waste / wipe-tower tracking (feature idea, 2026-07-02).** PrusaSlicer emits `; total filament used for wipe tower [g] = X` in multi-tool slices (confirmed via docs; NOT present in the single-tool `sample.bgcode` fixture — no wipe tower there). FCC parses per-tool `; filament used [g]` today but ignores the wipe-tower total. Opportunity: surface a **"waste vs. part"** figure per print — ColorMix is purge-heavy, so this quantifies the real cost of a multicolor job. ⚠️ A true **per-color** purge breakdown does NOT appear machine-readable from the gcode (only the wipe-tower *total* + per-tool totals; per-extruder flush looks like a slicer UI computation), so the feature is likely limited to a total-waste figure unless derived. Confirm the wipe-tower line on Derek's first real multi-tool slice (the single-tool fixture can't). Low priority; pairs with the ColorMix work above.

* Adding new locations, specifically shelve, row section locations is messy and needs a revision. infact any location that's a sub location isn't easy to add. This whole workflow needs to be re-designed. (Should check to see if we've finished the full refactor on location id and stuff yet.)

* **Mid-print spool swap / run-out apportionment: only the M600 single-extruder multi-color split is left (Group 22.3(b), blocked on data).** ✅ Shipped and released: (c) a completion whose toolhead spool changed between start and completion goes to a `spool_changed` review instead of dumping the full footer on the current spool (`e522d99`, 2026-06-14); (a) swap-event capture, which also catches A→B→A, plus the `parse_color_change_segments` segmentation primitive (merged `8592964`); (b) the runout / single-swap auto-split (`adc1e36`, 2026-07-03), validated on real Core One job 1078 to within 0.08 g of the scale (`print_deduct._compute_swap_split`, `prusalink_api.compute_segment_usage`, the `path_filament_g` remnant, `test_runout_auto_split.py`); and a swap on one head of a multi-head printer no longer drops the other heads (`4101884`, 2026-10-08).
  **Remaining:** the M600 single-extruder multi-color (A→B→A per-color) split. `_compute_swap_split` generalizes to it, but it needs a real M600 multi-color print for ground truth. Do the apportioned grams match the weighed spools, and does `;COLOR_CHANGE` survive the `.bgcode` decode (if not, the boundary moves to the `M600` line)? **💡 Derek's steering:** make the system genuinely SWAP-AWARE. A pause is NOT always a filament swap (magnets, inserts, an inspection, a clog clear), so segment on actual filament events (`;COLOR_CHANGE`/M600, the runout sensor, an explicit FCC eject-load), and ideally let the user confirm or annotate each pause's reason. ColorMix is NOT this case: its tool changes give a per-tool footer, which the completion deduct already handles. Design + capture checklist: §22.3(b) of `docs/agent_docs/tasks/22-filabridge-phase2-detection-deduct-followups.md`.

* **Retire the vestigial `fb_url` / `filabridge_url` plumbing (mechanical refactor, no product decision).** _(Its narrow slice ✅ **done in Group 56.5** (2026-10-25, `feature/group-56-deduct-accuracy`): the boot seed that GETs FilaBridge `/printers` is gone (replaced by a check that only names Printer rows with no PrusaLink IP), `prusalink_api.fetch_all_filabridge_printers` and `locations_db.seed_printer_credentials` were deleted (no callers left), and the shortfall card reads the heads on an explicit `read_heads=` flag. Nothing calls FilaBridge any more; the rest below, the dead `fb_url` / `filabridge_url` parameters, stays parked.)_ Spun off from the FilaBridge-artifacts cleanup part (3) once parts (1)+(2) shipped (2026-07-06). Post-decommission, `config_loader.get_api_urls()` still returns a dead `fb_url` (a `server_ip`-derived placeholder) purely to keep its `(sm_url, fb_url)` 2-tuple signature, and a `filabridge_url` positional param is still threaded through `prusalink_api` (`get_printer_state` / `_probe_printer_state` / `get_printer_job` / `get_printer_mmu_flag` / `fetch_printer_credentials`) and passed by ~7 callers (`print_deduct.py`, `print_monitor.py`, `routes_bindings.py`, `routes_state_pulse.py`, `logic.py`) plus ~12 test stubs, even though every one of them ignores it (creds now come from `locations_db.get_printer_credentials`; the last real deref, a fail-soft boot seed against the stopped FilaBridge, went in Group 56.5). Clean rip-out: collapse `get_api_urls()` to return `sm_url` only, drop the `filabridge_url` param everywhere (`fetch_all_filabridge_printers` is already gone, Group 56.5). Pure signature churn — verifiable offline by the existing prusalink/deduct tests. Low priority. **2026-10-19 (Claude's call, offered for veto; none):** leave the plumbing, except a narrow slice the next time `print_monitor` / `print_deduct` are touched: drop the boot seed that still GETs the retired FilaBridge `/printers` (`print_monitor.py:1040`, `:1067`; `prusalink_api.fetch_all_filabridge_printers`) and replace the `fb_url is not None` switch in the shortfall card (`print_deduct.py:666-668`) with an explicit flag. Keep `get_api_urls()`'s 2-tuple (`setup_fields.py` and ~131 test references use it).

* Rename inventory hub to Filament Command Center. _(→ **Group 55.2** for the leftover text only: the screen has said Filament Command Center since January (`dashboard.html:7`, `:19`); left are the "Inventory Hub" headers in `.env.example` and `config.json.example` and the old Jan-2026 "Inventory Hub - System Operator Manual". **The full rename of every reference to Filament Command Center (the `inventory-hub/` folder, the container, the TrueNAS app and the prod folder) stays on this list as eventual work** (Derek, 2026-10-19: *"unless of course the entire scope and abilities of the project change, like the color picker or project manager"*).)_

* 🚫 **SHELVED (Derek 2026-06-05)** — Prusament QR codes *as reusable labels*: using Prusament's manufacturer spool QR in place of FCC's own labels for re-spooled/rewound spools. Derek's call: "feels like it might be more of a nightmare to code out correctly … better to shelve reusing prusament QR codes." (The QR's identity is the *manufacturer's original* contents; once you rewind your own filament onto it, the QR lies — so it can't be trusted as a current-contents label the way an FCC label can.) The scan pipeline still *recognizes* Prusament URLs and uses them for the supported flows (match + temp/weight backfill on existing inventory — L198/L200); what's shelved is treating the manufacturer QR as a primary, reusable FCC label.
  _[**Data-model note + matcher follow-up (2026-06-05):** a Prusament URL is `prusament.com/spool/`**`<product-id>`**`/`**`<spool-hash>`**` — the numeric id identifies the **filament/product** (shared across every spool of that product), the trailing hash identifies the **unique physical spool**. FCC's scan matcher currently keys off the numeric id ONLY (`resolve_scan` parses the number; the matched-handler needle is `/spool/<id>/`) and ignores the hash, so when you own duplicates of a product (e.g. dev spools #196 & #197, both product 17705) a scan corrects the **first** one rather than the exact spool scanned. For spool-level ops (L200 weights) that can correct the wrong physical spool. **Follow-up — ✅ DONE 2026-06-05** (`feature/prusament-spool-hash-matcher`): the matcher now keys on the spool-unique hash (both path `/spool/<id>/<hash>` and query `?spoolId=<hash>` URL forms) so a scan resolves the exact physical spool; an unowned exact hash routes to onboard. See `completed-archive.md`.]_
  _[Original future-idea context (pre-shelving): load a spool into the buffer straight from the manufacturer QR (e.g. in the L315 mobile-first version, where a phone camera reads the spool QR reliably — one bench barcode scanner did not). Key caveat (Derek 2026-05-30): Prusament spools are reusable; after a re-spool the QR still resolves to the ORIGINAL filament, so it may not match the roll. If this is ever revisited it needs a real guard, not just fill-blanks-only + the matched-overlay name + conflict prompt.]_

* Keeping the screen on when afk, still causes the screen to blank out. Confirmed on laptop, not on desktop. _[ON HOLD — OS-level power management, not fixable in app code. Candidate mitigations if we care: Wake Lock API (`navigator.wakeLock.request('screen')`) gated behind a toggle in the nav bar; only works when the tab is foreground. Worth considering if we add a kiosk/shop-floor mode.]_

* Check why FIL:58 wasn't marked as labeled when scanned. _(→ **Group 58.7**, still on hold)_ The `label_printed` field was retired in M7 and replaced with `needs_label_print` (boolean) — barcode-scan path now updates this field at `app.py:921-922, 968-969`. The FIL:58 case specifically needs manual repro to see whether the update fires and why Activity Log was silent. Could be because FIL:58 is an old physical swatch with no prior spoolman state. _[ON HOLD — need to locate or reprint the FIL:58 physical label/swatch before repro can be attempted. When found: scan with DevTools open → Network tab → `/api/identify_scan` response + Activity Log ticker.]_

* 🔬 **If the dashboard ever freezes again** (scans stop registering until a hard refresh): **don't refresh first.** Press F12, screenshot the Console's FIRST red error and any failed or still-Pending Network rows (or right-click → "Save all as HAR"), note what you did in the last 30 seconds, then refresh and paste it all here. _(The L28 frontend lock-up and its modal-on-modal sub-bug are fixed and archived — 2026-10-12, Group 47.33, see `completed-archive.md`.)_

* 🚫 **SHELVED (Derek 2026-10-19)** — the Prusa metrics exporter as a data source. Checked twice (2026-06-10 and 2026-07-02): the printers' metrics carry no filament grams, and turning them on needs a touchscreen opt-in on each printer plus a network listener in FCC. Kept in mind for Project Color Loadout and the bigger project-tracking idea. Derek's original note: *"These seem interesting, and it would be great to find a way to use this in some fassion. Just putting this here as a future thing, or as something to keep in mind."*
https://github.com/pubeldev/prusa_exporter
https://github.com/prusa3d/Prusa-Firmware-Buddy/blob/master/doc%2Fmetrics.md
  _[**Investigated 2026-06-10 (8-agent workflow) for the cancelled-print feature — NO-GO as a MEASURED-filament source.** The Buddy metrics catalog (`app_metrics.cpp@master`) has NO `pos_e`/`filament_used`/`extruded_mm` — only X/Y/Z position, `sdpos` (SD byte position = same progress proxy FCC already derives), `active_extruder` (index), and a `filament` field that's the filament TYPE name STRING ("PLA"), not grams. The firmware-measured running total (`render.cpp`) is a lifetime LENGTH odometer (meters, EEPROM) emitted only to the Prusa Connect CLOUD. Transport IS plain UDP syslog (port 8514 — a Flask UDP thread could ingest it WITHOUT Prometheus/Grafana/InfluxDB), and enabling needs an on-printer touchscreen confirm (M334/M340, off-by-default, dev-flagged) — but there's no useful payload, so the cost/benefit is moot for measured filament. **This NO-GO is specific to "measured filament for cancel deduction"; the broader idea (metrics → printer-status dashboards / richer state) is untouched.** See `filabridge-absorption-scoping.md` §9.1.]_

# **Active Backlog (Organized by Feature Area)**

## 📋 Activity Log

## 🎨 UI & Theming
* Refactor the longer "strip" cards used in the Location Manager window. Merge the horizontal layout with modern grid card features without cramping the text or making the button layout look weird. _(→ **Group 59.5**, 2026-10-25)_ _(2026-10-19 refresh: still standalone. It needs Derek to pick from a mock-up, which Claude can build on a real cart, e.g. `CR-CT-2-R1`, whenever he wants to look: two variants, one row per spool with all three QR badges or with one, both keeping Group 40.6's ↩️ RETURN footer. Its double LABEL handler is tidied in Group 48.1.)_
* ✅ **High-Contrast Pop everywhere** — now a CLAUDE.md standing order (Derek, 2026-10-19): readable contrast in everything new, reusing looks he has approved, and never an app-wide restyle without showing him a sample first. Archived 2026-10-19 (see `completed-archive.md`).
* **Printer Status: with 8 toolheads in a small window, the toolhead list wraps to a second line.** _(Derek,
  2026-10-19.)_ It looks odd on the collapsed version, the small one meant to be read at a glance. Part of a Printer
  Status redesign Derek wants. _(→ **Group 50.1**. Derek, 2026-10-19: head numbers with a coloured ring (cyan fine,
  amber under 100 g, red empty; grams in the hover text), no pipe between printers; if it still doesn't fit, one row
  per printer when it's longer than the window, with sideways scrolling as the fallback he also likes.)_
* **Printer Status: an easier way to reach the spool on a toolhead.** _(Derek, 2026-10-19: "perhaps this just needs
  more time in the oven".)_ Clicking a toolhead tile opens that toolhead in the Location Manager (its assignments,
  `inv_printer_status.js` → `openManage`), the most useful default, which should stay. But sometimes you just want the
  spool loaded there, and getting to it is clunky. Ideas, none decided: a right-click or long-press, or a small spool
  button on the tile. _(→ **Group 50.2**, still in the oven: the group ships without it.)_

## ⌨️ Keyboard Navigation
* ✅ **Keyboard navigation everywhere** — now a CLAUDE.md standing order (Derek, 2026-10-19): keyboard navigation in everything new, where it makes sense, following the existing idiom. Archived 2026-10-19 (see `completed-archive.md`). Its one concrete gap, the Printer Status tiles, is **Group 50.3**.
* **Enter on a focused button inside a window does nothing (app-wide).** _(→ **Group 50.6**, with the Printer Status follow-ups' (b): the same root cause)_ _(Found 2026-10-19 while building Group
  48.2.)_ Tab to a button in the spool window (its ✏️ or 🖨️, or the new "(from the filament)" link) and press Enter:
  nothing happens; Space works. The scan accumulator in `templates/components/scripts.html` calls `preventDefault` on
  every Enter outside a text field, so a scanner's Enter never presses whatever has focus. Fix idea: let Enter through on
  a focused button or link unless `window.enterIsAScan()` says a scan is arriving (the rule the dialogs already use).

## 🗂️ Modals & Add Inventory Wizard
* Help button to provide information on how to use a modal, and to try and store information about how things work in the code. _(→ **Group 55.3**, as in-app help, not folded into the README. Derek, 2026-10-19: *"no one really reads documentation… keeping the information available at a quick click is important"*; part of an eventual documentation overhaul.)_
* ✅ **Pair legacy-ID spools with their Spoolman IDs** — closed 2026-10-19 (Derek): scanning a legacy label that several spools share opens the duplicate picker (✓ Use selected, 🖨️ Print new label, ➕ Add new spool). Archived (see `completed-archive.md`).
* **Slicer profiles: the next steps after Group 48.4.** _(Derek, 2026-10-19: "being able to determin this, would
  help later on if they decide to add more variants, and we could just have the system add and update based on what it
  finds … I'd ove for this to carry over for other look ups if we ever implement them.")_ Group 48.4 fills a blank
  Slicer Profile while a filament is made, from prusament.com's product line ("Prusament PLA Blend") only. Still open: (a) update existing filaments when Prusa adds or renames a
  variant (a pass over his Prusament filaments that asks first); (b) read the product page when a spool page doesn't
  name the variant; (c) other lookups returning `slicer_profile` (the wizard already takes it from any parser).
  **Derek's caveat (2026-10-19):** the names are PrusaSlicer's (its default profiles, or a custom one he makes when
  needed), because he runs Prusa printers; they don't line up with other brands and slicers. Build the Prusa case
  first, but don't assume one profile name fits every slicer (a later version might keep a profile per slicer).
  **Derek, 2026-10-20: "Don't guess."** The guess from his own filaments (brand + material) was removed the same day:
  "we can confirm with prusa because of the spool link, we have a confirmed name documented. I can't nessessarly
  garentee that the attributes for a spool are also present in its profile name in prusa slicer." What the field is
  for: a profile he confirmed prints well, a brand's own (Prusament, Sunlu) or one he researched with some
  confirmation (Jayo → the Sunlu profiles, as Jayo is Sunlu's off-brand; TPU, where Generic prints unreliably), else
  the slicer's Generic one; "This is why I write these things down in the filament information, so I don't have to
  remember it all." (d) **Parked idea he likes for later:** an attribute counts as part of a variant when one of his
  profile names contains it (Blend, Carbon Fiber, High Speed, "+"), so a PLA Blend would learn only from his PLA
  Blends. Not now: there is no concrete list of Prusa's profiles, and it varies by printer (the XL has custom profiles
  for more brands than the INDX).
* **A Buy More link template with `&` breaks in the spool and filament windows.** _(→ **Group 57.4**)_ _(Found 2026-10-19 by the Group 49
  builder.)_ The details windows read the `buy_more_url_template` setting through Jinja's auto-escaping inside a
  `<script>` tag, so an `&` in it arrives as `&amp;` in the links they build. The ⚠️ Low stock panel builds its links on
  the server and is fine. Pass the setting with `|tojson` instead. _[BUILT 2026-10-26 on
  `feature/group-57-low-stock-at-a-glance` (`a6d2f1b`): `|tojson`, so nothing in the setting can end the script either;
  a null setting no longer arrives as the text "None". Pinned by `tests/test_low_stock_glance_57.py`. Archived when the
  branch merges.]_

## 🔍 Search, Display & Filtering
* **⚠️ Low stock: a title-bar button with a count, and a window that keeps one size (Derek, 2026-10-25, on prod).** _(→ **Group 57**: (b) as **57.1** first, then (a) as **57.2** after a sample)_ _[BUILT 2026-10-26 on `feature/group-57-low-stock-at-a-glance`: (b) the window is `min(40rem, 86vh)` tall on every list and state; (a) "⚠️ N" beside Queue, counted on every heartbeat from the tick's own reads (the cost question settled: no Spoolman read of its own; not asked for while the backlog window is open), "?" before a count, and on a failed read the last count kept with a "?" after it and a dashed border (the 🏷️ Backlog count too, since the review). How it reads and what N counts wait on the ⏸️ PENDING DEREK pick above.]_
  (a) **Where the button lives: decided.** Today it sits in the 🔍 Search panel ("works, seems a bit odd. And doesn't
  really tell you anything at a glance"; 2026-10-20: "a bit fiddly"). Move it to the title bar beside 🏷️ Backlog and
  🛒 Queue, with a count, so it reads at a glance. Things to settle in the build: what the count shows (Low + Out, or
  both separately; Excluded never counts); its cost (`build_report` reads every spool and every filament strictly, too
  heavy for each heartbeat: compute it on a slower cadence or after a deduct, a weigh-in or an exclusion, and say
  "couldn't read" rather than 0, Group 52); and room in the title bar at Large / Extra Large, where it already
  tightens (the design follow-ups' "Backlog and Queue as icon + count" idea may be needed). (b) **One size for the
  window:** "It jumps in size depending on its content's length, which makes everything move around in a weird way.
  This is kind of contradictory to some of the other modal design decisions we've made in the past." Give it a fixed
  height (in rem, so it follows the Text size) with the filament list scrolling inside it ("If that means adding a
  scrollbar to the list of filaments, that's fine"), the tabs, filter and legend staying put whatever tab or filter
  is chosen. The list's come-back behaviour (2026-10-20) stays. **Standalone.**

## ⚡ Quick-Swap Enhancements
*(No open items — resolved entries archived in `completed-archive.md`.)*

## 📍 Location Management & Scanning
* **L271 — Make the Location Manager less brittle and more concrete: ✅ phases 1A–5 shipped** (first-class Printer rows, the `parent_id` tree, `printer_map` folded into Printer-row `toolheads[]`, prefix retirement `2b16869` via Group 34); archived 2026-10-12 (Group 47.21, see completed-archive.md). **Still open:** recommendation #3, *"Decouple the printed barcode from the hierarchy … A `PM` box can move rooms without re-printing"* → [Group 37](docs/agent_docs/tasks/37-location-system-redesign.md) fork 1 (still open 2026-10-13, for one sit-down with Group 44; Derek's input is on the 🌳 LOCATION SYSTEM REDESIGN item). Never built; Derek (2026-10-12) carried these into [Group 44](docs/agent_docs/tasks/44-printer-first-class.md)'s 44.0 design pass: a printer `model` field; the MMU fields `mmu_attached` / `mmu_routed` (dormant since the MMU Core One was retired, though the M0/M1 alias heuristic is still in `print_deduct.py:47-80`); and rejecting a row with no `Type` on write (only the orphan-`parent_id` half of recommendation #5 shipped).

* 🏷️ **Manage custom location Types (edit / rename / delete)** — _[BACKLOG, Derek 2026-06-05. Not needed yet; deferred from L271 Phase 5.]_ _(**Kept open (Derek, 2026-10-19):** to rename a type added by mistake, or rename one that no longer fits instead of re-typing many locations.)_ Phase 5 made the Type dropdown data-driven so you can **add** custom types (free-text input → persisted in `localStorage:fcc.locMgr.customTypes` + auto-derived from any Type already used on a row). What's missing is **edit/rename/delete** of an existing custom type. Deliberately deferred because:
  - The **built-in** types (Room / Wall Shelf / Row / Section / Tool Head / MMU Slot / Dryer Box / Printer / …) are load-bearing — code keys behavior off those exact strings — so edit/delete applies ONLY to custom types (zero exist today).
  - Doing it right is a real feature with data + referential concerns, NOT a localStorage tweak:
    - **Rename a type in use** → a backend pass that retypes every row carrying that Type (mirror the printer_map "can't rename a key still in use" guard shape).
    - **Delete a type in use** → either BLOCK with a referential guard (preferred — list the rows still using it) or cascade-retype them. Open decision.
    - A stale `localStorage` custom type that's NOT on any row is the only trivially-deletable case.
  - **Natural home = the Config system (L9)** — custom location types are exactly the kind of pref/registry that should migrate into Config (a small "Manage location types" panel), alongside the other `localStorage` prefs flagged in CLAUDE.md. The current add-only design is forward-compatible, so deferring costs nothing — a future manage panel reads the same two sources.

* ✅ **Bulk Moves** (L298) — built (all 5 phases merged 2026-08-03) and released dark behind `fcc.bulkMove.enabled` (default off; `71a1be9`, `main e5b3a82` 2026-10-08); archived 2026-10-12 (Group 47.19, see `completed-archive.md`). The hands-on pass is the ⏸️ PENDING DEREK item; open bulk-move work has its own items (the "🔀 Bulk Move polish" and Bulk Moves flag-gate items, and Group 41.5–41.7).
* Audit parent/child rollup — scanning all of a cart's shelves (or a printer's toolheads) should count toward auditing the parent location itself. Future enhancement on top of the completed L154 Audit-mode work; would need the audit session to span multiple locations. _[deferred 2026-05-16; re-homed here 2026-06-05 during the buglist cleanup — full L154 context in `completed-archive.md`.]_ _(→ **Group 37.6** (2026-10-19): built on 37.4's transitive contents; ask Derek then whether it is one audit for the whole cart, or one per row with a history.)_ _(2026-10-21: see "🔍 Audit: Done moves unscanned spools" under 🗒️ Notes.)_

* Location Manager not syncing status across browser instances? _[ON HOLD — requires a real-time transport (SSE / WebSocket) on the backend. Current architecture is pull-only via `/api/locations` polling. Non-trivial; revisit after mobile mode since that work will establish the multi-client baseline anyway.]_

* **🟡 A spool "just stored" in a bound slot mid-print leaves a load to remember after the print.** _(Derek,
  2026-10-14, while answering Group 40.3's questions.)_ Mid-print you can't load a toolhead, so a slot-label scan
  into a bound slot gets stored (Enter = Just store it). After the print you load the head physically (from the
  laptop at the XL), and must ALSO remember to tell FCC (scan the slot again or Quick-Swap). Forget either half and
  FCC and the printer disagree, and FCC can't warn the way the slicer does. Ideas, none decided: offer the pending
  load when the print ends; mark the slot "stored, waiting to load" on its Quick-Swap tile; or auto-load the head
  after the print. Needs a design pass with Derek. _(→ **Group 50.4**. Derek, 2026-10-19: no notice at every print
  end and no "Load now" that locks him in (*"I may have a few prints I'm trying to do before I might have a chance
  to load it"*); instead the head's tile quietly shows a spool is stored for it but not loaded, with a way to
  confirm "I loaded it". Open to other ideas, since the collapsed strip has little room.)_
* **🟡 Assigning spools to INDX heads (and printer spool holders) without printed labels is clunky.** _(Derek,
  2026-10-14.)_ Force Location is meant as a last resort, but without a label per INDX head it's often the easy way.
  Group 40.4 / 40.5's pickers (Force Location or `LOC:RCOI` → pick a head) cover part of it (built 2026-10-19:
  Force Location → `RCOI` opens the Printer picker; ⏸️ PENDING DEREK check F2); the spool holders on the printer are
  still being thought through (Derek). _(**Kept open (Derek, 2026-10-19)** until his F2 check and the holders setup
  (the ⏸️ PENDING DEREK INDX-holders item); the Printer picker half is built.)_
* **🟡 Group 40 leftovers (filed 2026-10-19 at Group 40's finish; none urgent).** _(Group 40 is archived. Items 1–3
  and 5's 40.0d slot compare were built by **Group 51** (51.1–51.4; archived 2026-10-19). 5's extra spool-list read per
  bound-slot scan was measured by **Group 52**: a scan that loads its head makes four strict whole-list reads, each
  guarding a different moment; the one possible saving is the standalone "chained deploy" item under ⚙️. 4 →
  **Group 37.7**; the rest of 5 stays parked.)_
  4. **A Return chooser spanning two boxes that feed one head** (the 40.6 builder's question 2) → Group 37.
  5. **Deferred notes from Group 40's first engine review** (`docs/agent_docs/tasks/40-slot-picker.md`, "Engine review
     (2026-10-14) … deferred notes", the ones without ✅): Bulk Move's skip of a spool filed on a head-less one-slot
     Printer row; the MMU Slot grid's 0-based first slot vs `'0'` meaning no slot; and the open test-hygiene notes
     listed there.

## 🎟️ Print Queue, Labels & Filament Usage

## 🧪 Testing
* **🧪 The recurring sweep reds, filed from the logs (2026-10-08 to 10-13).** _(→ **Group 45.8**; filed 2026-10-13 by the Group 45 reconcile, `wf_1a1ff135-1c6`)_ Five full `RUN_INTEGRATION` sweeps are on disk with tracebacks (13, 16, 28, 13 and 17 reds). With the TestCart pair gone (46.5) the same families recur, and only 17 of the 87 reds failed at a 3 s limit. The main mechanism is the sweep itself saturating dev Spoolman through FCC: `hub.log` has 8,577 five-second `get_all_spools` read timeouts on 2026-10-13, packed into the E2E windows, against 16–81 ms quiet reads. `/api/get_contents` re-reads the whole spool list and fails open to `[]`; `/api/filament_details` gives up after 3 s and returns null, so its window never opens. Families: **(A)** windows that open only after Spoolman answers (filament details, the add-spool wizard's pre-filled weight, Prusament onboarding, the spool modal): feed made-up data to every read those tests make; **(B)** the Location Manager open (`#manageModal` only after `/api/get_contents`): readiness waits and `open_manage_modal`, and capture the request log for `test_bind_picker_opens_from_quickswap_header` (red 5 of 5) before changing it; **(C)** the slot-scan error toast (`test_ui_slot_scan_bad_target_shows_error_toast`, red 5 of 5 even after Group 33 raised its limit): capture first, it may be a real product bug (a leaked audit or bulk-move session swallowing scans, or a modal gate); **(D)** `test_doassign_buffer_safety` races FCC's own 2 s buffer poll: make the injected buffer authoritative (today it can also persist its fake spools #42/#44/#99 to dev's server buffer). Done when three consecutive full sweeps on a normal desktop show none of these families, each labelled by 45.1(c)'s load line. **Progress 2026-10-13/14 (overnight run):** the request log showed the mechanism on a QUIET machine: every dashboard load and every 5 s heartbeat fired 13 parallel `/api/get_contents` (one per toolhead, each a full spool-list read, 2–3.4 s apiece), and each test's own requests queued behind them. The widget now renders from the heartbeat's own section (95 → 35 requests per idle 21 s, 52 → 0 `get_contents`). Families A and B's isolated reds then passed 5 of 5; C passes; D's tests own their buffer endpoint (and no longer write made-up spools into dev's buffer). The faster page exposed latent test races that had leaned on the slowness (wizard closes inside Bootstrap's show transition, Location Manager opens before the locations load, injected state overwritten by a real poll), fixed with shared helpers (`conftest.close_wizard` / `wait_modal_settled` / `quiet_heartbeat` / `own_the_buffer`), plus one product gap (an early tile click was dropped; `openManage` now waits for the first load). Sweeps: 15 reds in 21:44 (the races), then 1 red in 20:46 (the same race, fixed), then **0 reds: 3004 passed in 21:01**. **Left:** the done criterion, three consecutive clean full sweeps (1 of 3 so far). **✅ Met 2026-10-25 (`/refresh-groups`):** no full sweep since has had a red from families A–D, and the last three (2026-10-24) were 4841, 4843 and 4870 passed, 0 failed, at load 1.06×, 1.09× and 1.05× (none BUSY); 45.8 is done (Group 45's row and task file).
* **🧪 Host-side test imports run FCC's startup migrations against whichever `data/locations.json` the working directory resolves to.** _(Found 2026-10-13 by Group 45, while triaging a sweep red; filed, not changed.)_ `locations_db.JSON_FILE` is the relative `data/locations.json` and `state.py` opens a relative `hub.log`; 90 test files `import app` on the host, which runs `startup_migrations` at import. From `inventory-hub/` (the canonical run) that is dev's REAL `inventory-hub/data/locations.json`, migrated by the host process while the container uses it (idempotent and usually a no-op, but it can write backups and migrations). From the repo root it is a stray, git-ignored repo-root `data/locations.json` left by a 2026-06-05 run (two rows, `CORE1` + `XL`, plus a `.pre-toolheads-migration` backup), which `test_printers_are_first_class_on_disk` read on 2026-10-13 (fixed: it now reads the container's file by absolute path). The host's hold on `hub.log` is already gone (Group 45 review: it blocked the container's log rotation on Windows and dropped its records). Options: point `JSON_FILE` / `hub.log` at module-relative paths (the container's WORKDIR is `/app`, so prod resolves the same), or give host test runs their own data dir; and delete the stray repo-root `data/`. _(→ **Group 45.9**, 2026-10-19: a host-only data dir that conftest points at a temp copy, `RotatingFileHandler(..., delay=True)`, and the stray repo-root `data/` and `hub.log` deleted.)_
* **`test_baseline_spool_details_modal` skips when dev's buffer is empty.** _(**Duplicate** of the second half of the `test_fab_no_overlap_with_cmd_deck.py` item under 🗒️ Notes; both → **Group 45.11**, 2026-10-25.)_ _(Seen 2026-10-19 in the bundle run:
  "No spool cards visible after closing offcanvas".)_ The visual test opens the spool window from a buffer card, so on
  an empty buffer it never runs. Give it its own card (`conftest.own_the_buffer`) so it always judges the window.
* **Group 52's two read-notice contrast checks judge nothing.** _(→ **Group 45.12**)_ _(Found 2026-10-19 by the reads-1 fixer.)_
  `assert_contrast(root)` / `contrast_offenders(root)` score the root's descendants only, and
  `test_manage_read_notice_has_no_gray_on_gray_text` / `test_backlog_read_notice_has_no_gray_on_gray_text` pass the
  notice itself, which has no children. Its colours pass by eye (about 11:1). Re-root both on the notice's parent and
  prove the notice is scored with `contrast_offenders(parent, min_ratio=100)`, as reads-1's own checks do, or make the
  guard score the root too.

## ⚙️ App Flow, Architecture & Database
* **MOBILE** Make the entire app mobile friendly so NFC/Scanning works on phones. (Perhaps a desktop mode to utalize barcode scanners, and a mobile mode of mostly touch interface and scanning barcodes/QR codes and NFC tags). The main difference being that mobile mode won't relye on all the inlaid barcode/qr codes we currently have in the interface currently for interacting with the UI elements. _(2026-10-21: phone first, Android + Chrome; see "📱 Phone view first" under 🗒️ Notes, and `docs/agent_docs/tasks/design-step3-alternative-views.md`.)_ _(→ **Group 60.2**, 2026-10-25.)_
* **Frontend file-size pass (optional, low priority).** _(Narrowed 2026-10-12, Group 47.32, from "Refactor dashboard to be more modular if possible, and reduce token size/context requirements." The backend half shipped as L316 and is archived. Derek kept a frontend pass on the list, just in case.)_ The frontend is already split into 24 modules under `static/js/modules/`, but four files are big enough that changing one feature means loading a lot of unrelated code: `inv_wizard.js` (4,472 lines), `inv_details.js` (3,721), `inv_loc_mgr.js` (2,325) and `inv_cmd.js` (2,203), as of 2026-10-12. Split them along natural feature seams (e.g. the Bulk Move panel out of `inv_cmd.js`) so an agent can load one feature without the whole file. No bug behind it. **Standalone.** _(2026-10-19, Claude's call, offered for veto; none: split only when a group already rewrites that part, lowest risk first (the ~700-line Bulk Move panel out of `inv_cmd.js`), not `inv_loc_mgr.js` before the Group 37/44 sit-down, and only after Group 53's load-order canary.)_
* **🧹 One source for the frontend's toolhead-Type lists.** _(Left as "a separate DRY item" when the backend duplicate was collapsed, 2026-06-15 `19a4a5e`; filed 2026-10-12 by Group 47.)_ The backend has one canonical `locations_db.TOOLHEAD_TYPES` frozenset (`locations_db.py:73`), but the frontend hard-codes the Types itself: `TOOLHEAD_TYPES` at `inv_quickswap.js:17`, plus two lists in `inv_loc_mgr.js` that add `Printer` (`SINGLE_OCC` at `:81`, which hides "Move all →" where it would be a no-op, and `_isPrinterTopologyType` at `:2300`). They agree today, so nothing has drifted, but a new toolhead Type would have to be added in every copy. Fix: serve the toolhead set from the backend (e.g. in the dashboard bootstrap or alongside `/api/printer_map`), read it from one `window.` constant, and derive the with-`Printer` list from it. _(→ **Group 53.1**, 2026-10-19: the copies have grown to 8; one list in `inv_core.js`, pinned against the backend's.)_
* Make as much of Command Center user configurable as possible, using UI elements and a config import/export feature. _[→ **Group 35** for what's left. ✅ The Config system shipped 2026-06-01 (L18 Phases 1–4, main `6bd1f76`): the ⚙️ Admin / Config button opens a schema-driven Settings card, `GET`/`PUT /api/config`, a guarded toolhead editor, and import/export with redacted secrets and a dry-run diff. Adding a setting is now one `Field` in `config_schema.py`. Group 35 owns the tail: per-printer settings (the "Per-printer settings section in the Config tool" item) and L18 Phase 5 action-tool co-location. The "Config button … NEEDS DESIGN SESSION" item was archived 2026-10-12 (Group 47.20).]_
* Continue to support Spoolman's "Import from External" feature for filaments... _[Status of existing parsers + a gap list of unimplemented sources lives in the module docstring at the top of `inventory-hub/external_parsers.py` as of 2026-05-13 (Group 11). The audit + dropdown cleanup landed; the items below are the still-unimplemented sources.]_
    - open-filament-database
    - Open Print Tags (Initialize, Read, and Write) _(→ **Group 60.3**, read-only first; 2026-10-25)_
* Refactoring setup code to be dynamic. On brand new installs, maintain existing code to get it started.
* Add the ability to configure which extra fields should be bound and propagated to the other type of item. (Filament <-> Spool). _(**Kept, parked (Derek, 2026-10-19)**, with a new thought: maybe share fields freely as a Settings configuration; the slicer profile on the spool card (Group 48.2) is the current example. He may have forgotten its first purpose.)_

# **On Hold**
* Amazon Parser: Multi-pack spools with different colors (e.g. 4x1kg) currently calculate as a single 4000g spool instead of 4 individual 1000g spools.
* Check whether botasaurus (https://github.com/omkarcloud/botasaurus) is a viable alternative for Amazon / vendor-page parsing. _(Narrowed 2026-10-12, Group 47: the `test_amazon_parser_matching` failure this was filed under (4/15/2026) was fixed by Group 14.5 (`00e18d1`), which pinned `beautifulsoup4` in `requirements-dev.txt` so the test runs on the host. The prod image still ships without bs4 on purpose (`Dockerfile`: `pip install flask requests`), so Amazon import returns nothing inside the container by decision; the parser also needs `SCRAPER_API_KEY`.)_
* Continue to support Spoolman's "Import from External" feature... Purchase emails, or Amazon/Vendor product pages, Onlyspoolz.com.
* A way to compare the specs of two filaments side by side.

# **Overarching Issue**
I think we've inadvertently created 3 levels of logic/complexity here:
1. The physical, Scanning stuff and efficiently Moving it
2. A UI layer, for debugging, but should only really need to be looked at to confirm things
3. A full on interface that is easier to move spools around than having to use Spoolman's lackluster interface.
All 3 of these things are important and have value. We should table for now, and come back to once we've gotten more of the functionality in place.
* **🐢 The buffer cards' live refresh reads Spoolman once per buffered spool on every heartbeat.** _(→ **Group 57.5**)_ _(Group 52 builder's
  note, 2026-10-19.)_ `spools_refresh` (`logic.get_live_spools_data`) makes one GET per spool in the buffer each tick:
  ten buffered spools are ten reads every 5 s. It could use the tick's one spool-list read (`SpoolListRead`), as the
  other heartbeat sections do since Group 52. _[BUILT 2026-10-26 on `feature/group-57-low-stock-at-a-glance`
  (`a6d2f1b`): every spool the tick's list holds is answered from it; one GET only for a spool it lacks (an archived
  one), one per spool when the tick read no list, and when the list read failed one per spool until the first that
  gets no answer at all (the review: an outage tick took 5 s + 3 s per buffered spool; a record Spoolman can't send
  stops only itself). `/api/spools/refresh` is unchanged. Pinned by `tests/test_low_stock_glance_57.py`. Archived
  when the branch merges.]_
* **✅ FIXED (on `feature/group-57-low-stock-at-a-glance`, review round 5; goes to `dev` with Group 57): ⌨️ Space on
  any focused button leaves a space in the scan buffer for 2 s.** The accumulator skips a Space while it holds
  nothing (no label starts with one), processScan drops blanks around a scan, and `enterIsAScan` counts only keys
  that aren't blank; pinned by `tests/test_slow_scan_slash_js.py` and `tests/test_slow_scan_confirms_js.py`.
  _(Found 2026-10-26 by the Group 57 review, round 2.)_ The scan accumulator (`templates/components/scripts.html`) records every printable key outside a
  field, the Space that presses a focused button included. For the next 2 s a scan arrives with a leading space: a
  client-side command label (" CMD:WEIGH", " CMD:LOCATIONS", " CMD:DROP") misses its match and the server answers
  "Malformed Command", and an Enter in a list that reads Enter as "a scan is in flight" goes to the scan path as " ".
  Group 57 fixed it for the ⚠️ Low stock buttons only (`inv_stock.js` takes a lone space back out of the buffer when
  Space pressed them). The general fix is for the accumulator to skip a Space aimed at a button, which is its own
  change to the scan path and wants its own tests.
* **⌨️ Four older dialogs answer a scan's Enter as a person's.** _(Found 2026-10-27 by the Group 57 review, round 5,
  reproduced on dev, read-only; older than Group 57, so not fixed on its branch.)_ The standing order asks a handler
  that acts on an Enter to leave a scan's Enter to the scan accumulator (`window.enterIsAScan()`); these don't:
  - **The location editor's Enter-to-save** (`inv_loc_mgr.js`, Group 46.2). Off a text field it steps aside only for
    a scanner burst or a ':' / '/', so a slower scanner's bare-number label ("57"; "1024" from about 40 ms a key) on
    the Type select saves the form (POST /api/locations) and closes it, or presses a focused Cancel. In the Name
    field it opens on, a label typed slower than the field capture's 150 ms is saved as the location's name
    ("LOC:LR-MDB-1"). Careful: a person's typeahead on the Type select ("dr", then Enter) saving is 46.2's design,
    which `enterIsAScan`'s two-keys rule would break; a digits-only rule wouldn't, and the Name field needs its own.
  - **The legacy-ID duplicate picker** (`duplicate_picker.js`): its Enter answers every scan, aborting the picker or
    taking the spool clicked in it, and the scan itself never reaches the scan path; it stays in the buffer and is
    glued to the next scan for 2 s ("ID:57ID:58", an invalid id). The picker is opened by a scan, so the next scan is
    likely; what a scan should do while it is open is the design question.
  - **Smaller ones:** a focused wizard section header (`inv_wizard.js`: a scan's Enter collapses it and the scan
    stays in the buffer), the floating pills (`draggable_pill.js`: Enter on the focused 🔍 opens the search and the
    scan is processed too), the filament editor's "Close without saving?" with Close Anyway focused (a scan closes
    it unsaved; Keep Editing has the focus by default), and the parent tree picker (`inv_loc_mgr.js`: Enter picks
    the highlighted parent; read from the code).
* **✅ FIXED (on `feature/group-57-low-stock-at-a-glance`, in `11f77b4`, `cec4a65`, `a692e5d`, `dcb90be`, `66f2c44`, `229d325` and `9eaf28a`; goes
  to `dev` with Group 57, or alone: its code needs nothing else from the branch, its tests round 3's slow-scan
  harness): 🔴 a label scanned into a weight box was saved as the weight, and could archive the spool.** _(Found
  2026-10-27 by the Group 57 review, rounds 5 to 10, on dev, read-only; older than Group 57.)_ The Quick-Weigh window
  (`weight_entry.js`: a buffer card's weight, the wizard's weigh) answered every Enter with Save, and its weight field,
  focused when it opens, had no field scan capture. A number field (Gross, Net, Set Used) kept the digits of "ID:57"
  and Save stored 57 g; in Gross that is under the empty spool, so the spool read empty and Auto Archive archived it.
  A reading typed first got the digits appended (64557 g). Round 5 (`11f77b4`) judged the speed between keys, which
  left a burst scanner (its Enter a moment after the label), one slower than 150 ms a key, or one pause inside a
  label saving it. Round 6 found the same hole in the missing-tare prompt (a label became the spool's tare) and the
  post-archive empty-weight prompt (it would become the filament's empty weight); a scan lost with the focus on the
  Auto Archive switch (its Enter saved, its 'D' set the default mode); Enter on Cancel or × saving; the tare
  prompt's Enter running Save twice and its Escape cancelling the window under it; and the weigh-out list dropping the
  focus after a save and on every redraw, so the next reading went to the scan path as a spool id. Round 7 found what
  round 6's fixes left: kept in the box that had it, the focus put a scanned spool's reading on another spool (its
  row is drawn at the top; a 0 g reading archived the other spool and took it off its place), and a spool already
  listed, scanned to pick it, never got the focus (older); a redraw between a burst scanner's label and its Enter lost
  the scan and swallowed the next reading; a reading typed after a click on the Auto Archive switch, or on the
  empty-weight prompt's vendor box, went to the scan path as a spool id, which joined the buffer unseen; the focus
  fell to the page after the list's two prompts closed and after Set as default (mostly older); a unit or a stray
  letter typed before a scan joined its prefix ("gID:57"); a number box kept a label's E or dashes, and the next
  reading was refused; a kilogram, pound or ounce reading or a decimal comma was saved as grams; and a label typed
  by hand went as 'barcode', marking the spool's printed label verified. Round 8 found what round 7's fixes left,
  in the weigh-out list: a spool's own box, picked by its scan, selected the reading typed while the scan was
  answered, and a scan read off a box split the reading between another spool's box and the scanned one (both
  need a slow Spoolman), so a cut reading was saved, or the whole one to the other spool; a spool scanned over the
  empty-weight or missing-tare prompt never got the focus, and the prompt's close put it back in another spool's
  box (a reading typed into the prompt itself would be saved as an empty weight); a spool weighed this session,
  scanned again to weigh it again, left the focus in the next spool's box (older); a click on another row's name
  sent the reading to the box that had had the focus; a number box dropped a '.' across a redraw (645.5 saved as
  6455; older); another maker's label ("PID:57") was cut to an FCC one; and (found while fixing) a redraw
  between a label's first letters and its ':' lost the letters (":57", older). Round 9 found what round 8 left,
  each needing a slow Spoolman (most older than round 8): a prompt over a scan still being answered saved the
  scanned spool's reading as a tare or as the filament's empty weight (its Enter wasn't held, and it opened over
  the scan); a save that read its spool's details first took the focus from the box a scan had picked, and after
  the list's last save the focus fell to the page, where a reading went to the scan path as a spool id; a scan read
  while another was answered was queued, and until it went out the earlier answer moved the focus and took its
  reading; a reading left in a spool's own box joined the new one (300425); a key typed on another row's 💾, or
  after a scanner's second Enter, stayed in the wrong box; a held key ignored Backspace; a redraw during a save drew
  its row enabled, and the new reading typed after a scan of it vanished with the row; a label's first letters were
  moved as a reading, and its carry put the old box's reading in the new spool's box; and with no details any
  mode's reading was saved as what is left (Additive '+25' as 25 g left). Round 10 found what round 9's own changes
  brought: the save's redraw drew a saved row enabled while it faded, so a quick key and Enter saved that spool
  again with the digits joined (Set Used: archived); a save that waited for its details opened its missing-tare
  prompt over the next row's reading, which became its tare; a row waiting for its details left the page
  clickable, and a correction went to the next spool; and, older, a later scan that named no spool freed Enter
  while an earlier spool scan was still out, and a middle scan's keys were dropped from the reading. Now every
  weight box judges what was typed
  (class `fcc-weight-box`, `installWeightScanCapture` in `inv_core.js`): a ':' or '/' proves a label at any speed,
  from its prefix, and its keys never reach the box (a number box is cleared of the ones it took); anything else a
  weight can't hold is a scan only at scanner speed, and a weight in grams with its unit or a Space stays a weight; a
  label split by a focus move is put back together, its Enter too, across a redraw as well; 'barcode' only at scanner
  speed. A weight window marks itself `data-fcc-weight-keys`, so a weight key typed on its other controls goes into
  its weight box. The scan accumulator reads a checkbox's keys, the overlay on top owns Escape and its keys, Enter
  presses the button it is on, and the weigh-out list keeps a target, the spool whose reading is being entered (a
  scan, a click or Tab into a box, a click on a row, the save moving on): a scanned spool's box takes the focus
  (one weighed this session is drawn again) with what was typed while the scan was answered, wherever it went;
  Enter saves nothing until the answer, in the list or a prompt over it; a weight key on another control goes into
  the target's box (a row's 💾,
  that row's); the focus comes back to it when a dialog over the list closes; a spool scanned over a prompt closes
  it, and neither prompt opens while a scan is answered or once a spool scan has been answered since its Enter; a
  scan queued behind another counts from its read, and an earlier spool scan takes the focus when the later one
  names no spool, with the keys typed under the scans after it; Enter waits while any scan that may still take the
  focus is out; a saving or fading row stays disabled through a redraw, and a save moves the focus only from its own
  row; a save that reads its details first dims the page, and its tare prompt opens only where the person was left;
  with no details only a Net reading is saved. The list's boxes are text boxes, Net, Gross and Set Used read
  strictly as grams. Pinned by `tests/test_quick_weigh_scan_js.py`, `tests/test_weight_box_scan_js.py` and
  `tests/test_weigh_out_scan_focus_js.py` (the real scan router). Not covered: a label with no ':' typed slower than
  a scanner (an old bare location label), a stall of 2 s or more inside a label, and a reading typed by hand in kg,
  lb or oz or with a comma into the Quick-Weigh or a prompt (a number box keeps its digits, as before Group 57; the
  weigh-out list refuses it). **Derek's call (2026-10-28): a scan must never add to a weight.** Digits alone faster
  than a person types (3 keys or more, each within 40 ms of the last, an Enter as fast counted) are a scan, never a
  weight, so an old digits-only label goes to the scan path (in the weigh-out list too, also while it holds a
  reading for a scan it is answering); a reading with a '.', a grams unit or a padding Space stays a weight at any
  speed, as a scale that types its reading sends it. Only a scale typing a bare whole number can't be told from such
  a label: it reads as a scan, no weight is saved from it, and the scan path looks the number up as a spool id, so a
  spool with that id joins the buffer (in the weigh-out list it takes the focus): ⏸️ PENDING DEREK. Not caught: a digits-only label from
  a scanner slower than 40 ms a key, or one or two digits with its Enter a moment later.
* **⚖️ The post-archive empty-weight prompt takes the focus from a reading being typed.** _(Found 2026-10-27 while
  fixing the Group 57 review's round 6; older than Group 57.)_ When a weigh-out row's save archives its spool and its
  filament has no empty weight, "📦 Spool archived — record the empty weight?" (`inv_details.js`,
  `showArchiveEmptyWeightPrompt`) opens about half a second later and takes the focus. A person already typing the next
  row's reading types it into the prompt instead, and Enter saves that reading as the filament's empty weight, which
  every later spool of it inherits. A scanned label can't any more (its box is a weight box), a spool scanned while
  it is up closes it, and it doesn't open while a scan is being answered or once a spool has been scanned since
  the save (rounds 8 and 9). Still open: a
  reading being typed into the next row, with no scan, when it opens. Fix idea: leave the focus
  where the person is typing (focus the prompt only when nothing has the focus, or open it once the list closes); a
  call on where the prompt shows, since it is Derek's "one pre-filled confirm".
* **✅ FIXED (on `feature/group-57-low-stock-at-a-glance`, the commit after `1a1293b`; goes to `dev` with Group 57):
  🔴 A slower scanner's "Scan to Cancel" could confirm a Quick-Swap.** _(Found 2026-10-27 by the Group 57 review,
  round 3; reproduced on dev, read-only, in round 4.)_ `window.isScanInFlight` (inv_core.js) counts 500 ms from a
  scan's FIRST key. The Quick-Swap confirm overlay's Enter asked only that (`inv_quickswap.js`): its "Scan to Cancel"
  is about 30 characters, so on a scanner slower than about 17 ms a key its Enter pressed the focused YES, and during
  a print the cancel loaded the spool onto the printing head (POST /api/quickswap with the head confirmed). The
  deposit, the Return and the server's re-ask share that overlay. The slot grid's Enter after Q opened a swap nobody
  asked for, and the next slow scan answered it; the shared move question (`window.confirmActivePrint`) let a slow
  bare-number label ("1024") answer "Just store it"; Shift+B armed a bulk move on a slow label's 'B' and cut the scan
  to "-1"; the wizard's Shift+E / Shift+C toggled its sections on a label's capitals; the grid's Q kept its 'q' in
  the scan buffer (a label scanned within 2 s arrived as "qLOC:…") and jumped the focus on any 'q' inside a label.
  Each Enter now asks `window.enterIsAScan()` and each letter key `window.scanIsArriving()` (Q also keeps its 'q'
  out of the buffer, the standing order's idiom); `tests/test_slow_scan_confirms_js.py` drives
  them with the real accumulator on a fake clock (red on the old code from 18 ms a key for the cancel), and
  `tests/test_scan_path_integrity.py` pins the stronger guards. The '?' help key asks `window.scanIsArriving()` too
  (round 5): a legacy Google Sheets label is a URL with a '?' after its "https:", and a scanner slower than 120 ms a
  key, or one pausing after the '?', opened the shortcut list over the scan.
* **⏱️ The buffer's server sync still orders by the wall clock.** _(Found 2026-10-27 by the Group 57 review, round 3;
  older code, L28 and 21.6.)_ `loadBuffer`'s 3 s grace window (`inv_cmd.js`, `lastLocalBufferChange`) and the
  recently-assigned-out TTL (`_recentlyAssignedOut`) are stamped with `Date.now`. A clock stepped back just after a
  local buffer change (a time correction, a resume from sleep) makes the change look newer than every server read for
  as long as the step: the tab skips the server's buffer and writes its own over it, so a second device's buffer
  change is lost. Theoretical (it needs the step and a second device). The fix is `performance.now`, as Group 57's
  ordering stamps use, but about ten test files set `lastLocalBufferChange` with `Date.now` and change with it.
* **📶 When FCC itself doesn't answer, only the title-bar counts say so.** _(Group 57 review, round 3.)_ A heartbeat
  whose request fails (the network gone, FCC restarting, a proxy's error page), or hasn't answered after 30 s (round
  4), now marks the ⚠️ Low stock and 🏷️ Backlog counts stale ("FCC didn't answer just now"). Group 52's notices (the
  Location Manager, the Printer Status widget, the Locations table) still cover only a read FCC reports as failed, so
  on flaky Wi-Fi they keep looking current. And a request that hangs (a link dropped without closing the connection;
  the heartbeat's fetch has no timeout) holds every later tick back until it fails, so nothing on the dashboard
  refreshes meanwhile: an abort past the slowest real heartbeat (an offline printer's probes) would let the next tick
  go. Worth doing with the phone view (📱).
* **🐢 A bound-slot scan that loads its head lists the head's spools twice in the chained deploy.** _(Measured 2026-10-19
  by the Group 52 builder.)_ Such a scan makes four strict whole-list reads, each guarding a different moment; the
  chained deploy's step-4 resident list and its step-6 re-list of the same head could be one read when no printer probe
  ran between them. A move-engine change (`logic.py`), for an engine session.
* **The archive edge doesn't read `remaining_weight`.** _(→ **Group 54.6**)_ _(Group 51 review note, 2026-10-19.)_ Since the review, a
  `remaining_weight` write (the weigh-out row's fallback when the spool's details can't be read) un-archives a spool
  weighed back into stock, but weighing one to 0 g that way still doesn't archive it (it never did). Rare path: make
  `spoolman_api._auto_archive_on_empty` read it too.

## Stuff to watch ##

# **New related project to be integrated **

* [Feature] Build Project Color Loadout Add-on -> (See /docs/Project-Color-Loadout/) _(2026-10-19: the print-start check Derek loves, "#99 has ~34 g, this print needs ~61 g", belongs here, estimated from the `.3mf`'s data; he does it by hand while planning, and Group 49 builds only the low-stock list and warning. The April design is stale: refresh it at its own design sit-down before any build.)_

# Group 72: 🔄 Ask at the Mid-Print Change

**Branch name (when started):** `feature/group-72-ask-at-mid-print-change`
**Estimated effort:** LARGE (~16–24 h, 3 sessions), plus one review round and the full run (~70 min). The sample ~1.5–2.5 h · recording a change on the print ~4–6 h · the engine's report and the route ~3–4 h · the question on the page ~3–4 h · a finished print with no card (72b) ~4–7 h. The proposal's MEDIUM (~6–10 h) was set before grounding. Grounding found two things that cost more:
- FCC asks nothing at a pause today (13.8), so this question can't simply extend the printing question. It needs its own path.
- A finished print charged with no card is a new automatic charge path.

Estimates here have run about 30% low, so plan on the upper half. "Splitting" near the end offers two sittings.
**Risk:** **MEDIUM.** The question writes nothing to Spoolman: it writes FCC's own record of the running print (the latch). Two hazards:
- 72b charges real spools with no card. It runs only when every change on the print was answered and the figures line up; anything else opens the card, as today.
- The hooks sit in the move engine's head write (Groups 39–42, 51) and in the print monitor's latch. Each runs only after the write landed, under the latch's lock, and never fails a move.

> **Status: TODO, filed 2026-11-16** (/refresh-groups; Derek approved the grouping the same day: "otherwise this seems fine").
> **Place in the order:** 11th, after 64 🖨️ and 65 📡, which change the same files (`print_monitor.py`, `print_deduct.py`, `cancel_review.js`), and after 62 ⌨️, whose question rules this question uses. Re-ground against their merges before starting.
> **Starts with:** a sample of the question (pictures, Group 59's way, below), then Derek's three calls, asked with the pictures, cold and one at a time. Nothing else waits on him.
> **Grounded** read-only on `dev` @ `95531a6` (2026-11-17). The member is live. One claim in the item is only partly true: FCC's printing question asks only while the printer prints, never at a pause, which is where a run-out swap happens (see the item's row). Grounding also found two small items outside the group (last section). Line numbers drift, so re-grep before editing.

**Read first:** [64-print-end-hardening.md](64-print-end-hardening.md) and [65-print-watch-first-steps.md](65-print-watch-first-steps.md) (what 72 needs from each is below), and [62-questions-scans-double-clicks.md](62-questions-scans-double-clicks.md) 62.2–62.4 (a question's scan hold-off, its 700 ms arming and its keys).

## Items covered (quoted from `Feature-Buglist.md`)

| # | Buglist item | Direction |
|---|---|---|
| **72.1** ✨ | *"Ask at the time of a mid-print spool change: "did #42 run out, or was the assignment out of date?" (Derek, 2026-11-11). Since the print-end hotfix (`main` `102d234`, 2026-11-12), a head whose spool changed DURING a print always asks at the print's review: a recorded swap is split there for him to confirm, and a change no swap explains is held as a set to split by hand. Derek wants the question asked when the change is made instead, so the deduct can run with no review afterwards. The INDX's toolhead is one unit, so a change at a used head that no recorded swap explains is a change made in FCC during the print, a swap at a pause too short for the 10 s poll to see, or a stale assignment, never a reload of a parked tool. It would build on the move doors' printing question (Group 39's `active_prints`, `window.confirmActivePrint`), the swap record on the latch (`swap_log`, 22.3(b)) and the review's sets: for example, "it ran out" records a swap at that point, and "it was out of date" says the new spool had the head all along. Its own group."* | **Live; one claim partly true.**<br>**True:** a finished print with a changed head goes to the 🔁 card (`print_deduct.py:2187-2221`); a recorded swap is split there; a change no swap explains is a set (`:1501-1504`); a cancel FCC can measure always gets a card (one it can't measure keeps a 0 g ledger entry and a "weigh the spool" line, `print_deduct.py:3267-3287`). The swap log is written only at a resume the 10 s poll saw (`print_monitor.py:772-790`, `:1063`), so a change made in FCC while the printer prints records nothing until the end. (A fourth source of an unexplained change: any pause while `fcc_owns_completion_deduct` is off, since the capture is gated on it. On prod it's on.)<br>**Partly true:** the printing question fires only for PRINTING, PAUSING or RESUMING (`prusalink_api.py:507-515`, 13.8). At PAUSED, ATTENTION or BUSY a move asks nothing, so the run-out case has no question to build on.<br>**Direction:** ask right after the move (Derek's call 1), with three answers. "It ran out" records a swap there; "it was out of date" replaces FCC's record for that head. A finished print whose changes were all answered charges with no card (call 2). |

## The sample (first, before any build)

Group 59's way. Make before / after pictures in `review-samples/<date>-mid-print-change/` (git-ignored):
- **Data:** dev's real data (the 🦝 Core One INDX, RCOI-5, INBXX-1 slot 5, #42 and #229).
- **Sizes:** 1600×1300 at Standard and at Extra Large; the question also at a phone width (390 px).
- **Nothing is committed** but the eventual build.
- **How to draw them:**
  - The "after" questions: from a prototype, the real `window.confirmActivePrint` on an `isolated_page` with the new options added in a scratch copy.
  - The cards: from records the real code writes, as the hotfix's pictures were made.
- **Walk Derek through them** one at a time, with labelled crops, then ask his calls below.

What to draw:
1. **Before: a run-out at a pause, today.**
   - The INDX is paused at ~42% of a print. #229 is scanned into INBXX-1 slot 5.
   - FCC asks nothing. The toasts say #229 is on RCOI-5 and #42 went to the buffer.
   - At the end, the 🔁 "spool changed mid-print" card waits for Confirm, with RCOI-5 split ("start → 42%, ran out" / "42% → end").
2. **Before: a record fixed while printing, today.**
   - The yes / no: "⚠️ 🦝 Core One INDX is PRINTING … Loading #229 onto RCOI-5 unloads #42, so FCC stops charging this print to #42. Continue?"
   - At the end, the card's RCOI-5 set: two empty grams boxes and "FCC saw #42 when the print started and #229 when the print ended, but not when it changed: split the 84.3 g between them, or put it all on one."
3. **After: the question, look A (words only)**, right after the move of picture 1. It shows the title, the words, three buttons with a QR under each, the hint and the ?, with the first focus on Not sure.
4. **After: the question, look B (two colour tiles).** The same question, with "This print had" and "On RCOI-5 now" as colour tiles (`window.fccSpoolTileHtml`, Done's question's look).
5. **After: what each answer says** (its toast and Activity Log line). Then the print's end with no card (72b): the two ✔️ lines for RCOI-5 and the ✅ summary.
6. **The question at 390 px and at Extra Large** (look B).

Proposed words, built from the user's own data (Derek's to change):
- **Title:** "🔁 RCOI-5 changed mid-print".
- **Words, paused:** "🦝 Core One INDX is paused at ~42% of job 1142. This print had #42 on RCOI-5, and #229 is on it now. Did #42 come off here?"
- **Words, printing:** "… is printing (~42% of job 1142) …".
- **With contact lost (65.1):** "FCC last saw this print at ~30% (14:02)."
- **Buttons:**
  - "#42 came off here": the yes slot, amber;
  - "FCC had it wrong: #229 was on it all along": the store slot, cyan;
  - "Not sure": the cancel slot, grey, with the focus.
- **QR captions:** "📷 Scan: it came off here" · "📷 Scan: FCC had it wrong" · "📷 Scan: not sure".
- **Hint:** "Enter or Esc: not sure (its review asks when the print ends)".
- **After each answer:**
  - "🔁 RCOI-5: #42 came off at ~42% of job 1142, and #229 prints from there. FCC splits RCOI-5's grams there when the print ends."
  - "🔁 RCOI-5: #229 was on it all along in job 1142 (FCC had #42). FCC charges #229 for RCOI-5."
  - "🔁 RCOI-5 changed during job 1142. Not answered, so its review asks when the print ends."

## Decisions

### For Derek, with the sample (cold, one at a time)

**Call 1: when FCC asks.**
- **What it is.** You put a different spool on a toolhead while its printer is in the middle of a print. FCC can ask what that change means for the print's charge: did the old spool come off here (it ran out, or you swapped it), or was FCC's record wrong?
- **Where you'd see it.** On the dashboard, right after a move onto a head. That covers a spool scanned and then a slot or head label, a Quick-Swap tile, a drop on a head in the Location Manager, the Printer picker, and a Location change in the wizard.
- **A real example.**
  - Job 1142 prints on the 🦝 Core One INDX. At ~42%, RCOI-5's spool #42 runs out and the printer pauses.
  - You put #229 in INBXX-1 slot 5 and scan it in. FCC loads #229 onto RCOI-5 and takes #42 off into your scan buffer.
  - Today FCC asks nothing at a pause. When the print finishes, a 🔁 "spool changed mid-print" card waits in 🛑 Review for you to confirm RCOI-5's split.
  - Had you fixed FCC's record while it printed instead, that card would ask you to split RCOI-5's grams by hand.
- **Options.**
  - **(a) Right after the move.** The move goes through as it does today, and the question opens at once, with three answers. It has no Cancel, since the move is done: Undo Last Move takes the move back, and forgets the answer. While the printer prints, FCC's printing question still comes first, as today, and this one after it.
  - **(b) Before the move, inside the move's own question.**
    - The move waits for your answer, and Cancel moves nothing.
    - At a pause, where FCC asks nothing today, every load onto that printer's heads waits on a question first.
    - It changes the move questions every door shares (Groups 39–42).
    - Quick-Swap and the Printer picker would still ask their own question before it.
  - **(c) Keep asking only at the review**, as today. Nothing is built.
- **Recommendation: (a).**
  - The move never waits, and at a run-out you want FCC's record right away.
  - Nothing that guards a print goes away.
  - The move questions every door shares stay as they are.
- **If you don't answer:** (a).

**Call 2: a finished print whose changes you answered.**
- **What it is.** When the print finishes, FCC can charge each spool its share at once, with no card, provided you answered every change made during it.
- **Where.** 🛑 Review and the Activity Log.
- **A real example.**
  - You answered "#42 came off here" at ~42%. Job 1142 finishes, and RCOI-5 used 84.3 g.
  - FCC charges #42 30.1 g (start to ~42%) and #229 54.2 g (~42% to the end). The figures come from the print's one download.
  - FCC writes one Activity Log line for each spool.
- **Options.**
  - **(a) Charge it at once,** with one line per spool. FCC still opens the card whenever something doesn't line up:
    - the head held another spool at the end than the one you named;
    - a spool can't be read;
    - a change you didn't answer;
    - a spool weighed after it came off;
    - the old spool came off in a move of its own before the new one went on (an eject at the pause): FCC then kept no weight for it from that moment, so it can't rule out a weighing.
  - **(b) Always open the 🔁 card,** pre-filled from your answers, for a one-tap Confirm.
  - **(c) Split by when the change was made:** (a) for a change made at a pause, (b) for one made while the printer was printing.
- **Recommendation: (a).** It is what you asked for ("so the deduct can run with no review afterwards"), and FCC falls back to the card whenever the numbers don't agree.
- **If you don't answer:** (a). If he picks (b), 72b shrinks to a card note (see "Splitting").

**Call 3: the question's look (pictures 3 and 4).**
- **What it is.** The question names two spools: the one FCC had for the print, and the one on the head now.
- **Where you'd see it.** The question that opens right after the move (call 1).
- **A real example.** After the run-out above: look A says "This print had #42 on RCOI-5, and #229 is on it now" in words; look B draws #42 and #229 as two colour tiles under the words, each with its name and grams.
- **Options.**
  - **(A) Words only:** the move questions' look.
  - **(B) The two spools as colour tiles:** the look of Done's question in an audit, which you chose on 2026-11-03: "a vibrant list of data where an out of place color might spark a memory".
- **Recommendation: (B).** The colours tell #42 from #229 at a glance, and a wrong spool stands out.
- **If you don't answer:** (B), a look you already approved.
- **Also welcome, not waited on:** the buttons' words.

### Claude's calls (for veto)

1. **What asks.** A spool written onto a toolhead by an FCC move, when all of these hold:
   - that head's printer has a print latched (`print_monitor._PRINT_TRACKER`: a job id and a file, the printer not idle and not ended);
   - the latch has a start snapshot;
   - FCC's record for this print names another spool on that head.

   A park alone never asks. Prod's November log has four parks at ATTENTION, none with an FCC move. A tool change inside the print never asks either: the INDX's own tool changes move no spool in Spoolman.
2. **What doesn't ask.**
   - A spool only taken off a head (eject, Return, a move away, force-unassign). The load that follows asks, naming the spool FCC had for the print.
   - A head with no spool at the print's start: today's charge already gives its grams to the spool on it at the end.
   - A print with no start snapshot.
   - A re-scan of the spool already on the head.
   - A head whose spool before the move isn't FCC's record for the print (an earlier change went unanswered). FCC can't name the right "from" spool, so the review asks, as today, with one log line saying so.
3. **Which heads.** Every head of the printer, used by the print or not. FCC can't tell before the download which heads a print uses: prod's INDX latch holds no `file_meta` (see Prod facts). An answer about a head the print didn't use charges nothing.
4. **Where the cut goes.**
   - At a pause, the pause's progress: the resume capture's own rule, `max(progress, pause_progress)`.
   - While printing, the latch's progress at the move, at most one 10 s poll old.
   - `runout` as today: an ATTENTION was seen during that pause.
5. **What each answer records** (the table under Design):
   - "came off here" adds a swap event marked as answered;
   - "FCC had it wrong" replaces the stretch's spool (in the start snapshot, or in the last recorded swap);
   - "not sure" records nothing.
6. **The resume capture never records a change twice.**
   - Answered before the resume: the running record already names the new spool, so the capture's diff finds nothing.
   - Answered after it: "came off here" marks the event the capture added, and "FCC had it wrong" removes it.
7. **No answer, late answer.**
   - Escape, Enter on no button, or the page closing counts as not sure.
   - An answer that reaches FCC after the print ended records nothing, and its words say the review asks.
8. **Several changes.** Each change asks, in order: the question holds scans, so the next move waits.
   - "Came off here" adds a cut.
   - "FCC had it wrong" replaces the spool of the stretch since that head's last change.
   - `_compute_swap_split` already splits a head at several cuts.
9. **Undo** takes back what the move recorded (an unanswered change, or the answer) while the same print is latched, and its question says so.
10. **Lost contact** (65.1). The question says when FCC last saw the print. "Came off here" still records which spool is which, but marks the cut as unplaced, so a finished print keeps its card.
11. **Cancels and ❓ ends keep their card:** FCC never charges a cancel by itself. The answers pre-fill it (a split, or a plain row), never a set.
12. **The run-out spool weighed before the charge** (64's Decision 1, extended). The swap event keeps the old spool's used weight from when it came off, and the charge compares against it, as 64's end read does for a spool still on its head.
13. **The question's look and keys.**
    - It is `window.confirmActivePrint`'s three-way, with new options: the first focus and Enter on Not sure (the answer that changes nothing), a caption for the store QR, its icon, and the store button's own words where the question names it today as "Just store it" / "stores it".
    - Its two record answers take no click for 700 ms (62.3's default). Not sure takes a click at once.
    - Scans are held off while it is open, its QRs answer it, and a ? opens its help.
    - One helper, `window.askPrintChange(answer)`, in inv_core.js beside `noteUnarchived`. `takeIntoBuffer` calls it, so every door that completes a move does, and so does Quick-Swap's tap.
14. **Where the code lives.**
    - The latch functions go in `print_monitor.py`, which owns `_PRINT_TRACKER`.
    - The route goes in `routes_bindings.py`: `POST /api/print_change`.
    - The engine calls `print_monitor` through a deferred import, as it already calls `prusalink_api`. A module-level import would cycle: logic → print_monitor → print_deduct → logic.
15. **Answers live inside the records that already go everywhere.**
    - A "came off" answer is a `swap_log` event; a "had it wrong" answer is a corrected `start_spools`. Both already ride the edge, the fetch queue, restart recovery and the review, so 65's recompute keeps them too.
    - The latch is saved at once after an answer, not only at the next tick, so a restart keeps it.

## What 72 needs from 64 and 65 (and 62)

**From 64:**
- **64.3 (2), the start snapshot whatever `fcc_owns_completion_deduct` says** (the resume capture too). Without a snapshot there is no "FCC's record for this print", so no question. On prod the flag is on (job 1142's latch held a snapshot), so 72 works there either way. A new install, whose flag defaults off, waits on 64.3 (2).
- **64.2 (9), one rule for an end read that disagrees with the last recorded swap** (hold the head). 72b's no-card check uses the same rule.
- **64.2 (10), a cancel's progress is at least its last swap's point.** A change answered at a pause, then a cancel from that same pause (ATTENTION → STOPPED), must split, not refuse as `unmeasured`.
- **64.3 (4), the park read.** An end straight from a park uses the park read as its end read. So when a change is answered during that park, 72 updates the park read's entry for that head. Otherwise the end read names the old spool, disagrees with the answered swap, and the head becomes a set. This is the "hook 72 asks from" in 64's file. If 64.3 (4) isn't built, there is nothing to update.
- **64.3 (1), one spool-list read per edge.** The end read keeps each head spool's used weight, and every deduct test moves to that new seam; 72's deduct tests use it too.
- **64's Decision 1, a spool weighed between its print's end and the charge.** 72 extends the detection to a spool that came off during the print (Claude's call 12), whose weight the end read never sees.
- **64.3 (7):** if the start snapshot also keeps `{alias: sid}`, an answer updates both forms.
- **64.1, the one-position fold.** On a printer whose heads share one position (MMU aliases; none here today, 64's file says so), a change splits through that fold, so 72b's no-card charge there relies on 64.1. The XL's and the INDX's heads each have a position of their own and don't need it.

**From 65:**
- **65.1 (1), the latch's last-seen and lost-contact stamps:** the question's lost-contact words, and Claude's call 10.
- **65.1 (1)'s recompute** rebuilds a ❓ card from the start snapshot and the swap log. 72's answers live inside them, so the rebuild must copy an event whole, its `asked` mark included.
- **65.3's call 12 ("isn't charged yet").** A spool that came off a running print is in the latch, not in the fetch queue or a review, so 65.3's check misses it. 72 extends the check to the latch's swap events and pending changes, or that spool's weighing reads as drift.

**From 62** (first in the order): 62.2 (every question holds scans), 62.3 (700 ms arming on a yes and a store) and 62.4 (a question's keys heard on the document while it is on top). This question is a three-way, which already holds scans. It uses 62.3's and 62.4's defaults if they have landed, else passes `armAfterMs: 700` itself and arms its store slot too.

## Today's code (anchors, `dev` @ `95531a6`)

### Where FCC sees a change during a print
- **The latch.** `print_monitor._PRINT_TRACKER` and `_PRINT_TRACKER_LOCK` (`print_monitor.py:59-61`), filled by `_track_print_edge` (`:647-1038`).
  - The monitor probes every 10 s while anything is busy and every 30 s when all is idle (`:1063-1064`; the tick `:1084-1159`).
  - It saves the latch each tick (`:1136`), through `print_tracker_store.save` (`print_tracker_store.py:35-47`, `data/print_tracker_latch.json`).
- **The start snapshot,** once per job at its first PRINTING tick (`:757-764`). It is stored only `if need_snapshot and _fcc_owns_completion_deduct()` (`:797-809`). The flag defaults to False (`config_schema.py:77`, `config_loader.py:92`). Dev's root `config.json:57` has it True, and prod's latch held a snapshot (Prod facts).
- **The swap log (22.3(b)).**
  - It is written only at a resume into PRINTING from a pause condition (`_PAUSED_CONDITION_STATES`, `:73`; the flag `:772-790`), under the same gate (`:820`).
  - `print_deduct._record_swap_events` (`print_deduct.py:1666-1707`) diffs a fresh read against the start snapshot advanced by earlier swaps. Each clean 1→1 change appends `{seq, position, progress, from_sid, to_sid, runout}`.
  - The cut is `max(progress, pause_progress)` (`print_monitor.py:788-789`). `runout` means an ATTENTION was seen (`:790`).
  - `pause_progress` is sampled at ATTENTION (`:903-910`, `:994-1011`; the "⏸️ parked at ATTENTION" line `:1002-1007`). The resume lines are `:838-854`.
  - So a change made in FCC while the printer prints records nothing until the end, and neither does a pause the poll never sees.
- **The edge.**
  - The fire dict carries `start_spools`, `snapshot_job` and `swap_log` (`:962-983`), the latch resets (`:985`), and the handlers get them through `_validated_start_spools` and `_validated_swap_log` (`print_deduct.py:1628-1650`; the dispatch `print_monitor.py:1020-1038`).
  - They ride the fetch record (`_hold_edge_fetch` `:214-234`, `_hold_end_heads` `:237-271`).
  - They ride restart recovery too (`_recover_one_print_latch` `:1554-1684`, which restores the whole entry for a print still running, `:1591-1593`, `:1682-1683`).
- **`file_meta`** is also latched (`:749-753`), but nothing reads it (see the last section).

### What the review does with it today
- **`_held_heads`** (`print_deduct.py:1179-1202`) holds a used head that FCC can't vouch for:
  - `swapped`: a swap was recorded there;
  - `two_spools`: two spools at the end;
  - `changed`: the start advanced by the swaps (`_start_mapping` `:1158-1165`) disagrees with the end read.
- **A finished print:** `deduct_completed_print` (`:2043-2289`).
  - `changed` is the start-vs-end diff plus any swap at a used position (`:2187-2211`). Any change → `_route_completion_to_review` (`:2212-2221`; the function `:2552-2774`).
  - A recorded swap is split from the one download (`_compute_swap_split` `:2340-2420`, rows `_split_to_review_rows` `:2447-2507`, `auto_split`).
  - A `changed` head with no swap is a set (`_held_sets` `:1414-1433`; its note `:1501-1504`).
  - The card is the 🔁 "spool changed mid-print" (`kind: spool_changed`, `:2725-2743`; log line `:2766-2772`).
  - Nothing changed → the print auto-applies through `_apply_usage_to_printer` (`:371-556`; its one `update_spool` at `:487`; `_spool_lock` `:335`, `_write_landed` `:345`, `_deduct_payload` `:357`; the ledger `_record_applied_deduct` `:570`).
- **A cancel or a ❓ end always gets a card:** `_create_pending_cancel_review` (`:3186-3364`) → `_stash_cancel_review_from_heads` (`:3367-3442`).
  - A recorded swap is split from the cancel's own download (`_split_held_swaps` `:1273-1313`). The split is refused, and the head held, as `end_differs`, `end_empty` or `end_two`.
  - A `changed` head is a set.
- **The card** (`cancel_review.js`):
  - `cardHtml` (`:1023-1132`; the spool_changed banners `:1071-1092`);
  - split rows grouped as "split at the swaps FCC recorded" (`rowsHtml` `:153-173`, `:169`);
  - each row's stretch, "start → 42%, ran out" (`segmentHtml` `:77-89`);
  - a set (`heldSetHtml` `:209-232`).

### The move doors' printing question
- **When it fires.** `logic._active_print_info_for_location` (`logic.py:17-62`) asks `prusalink_api.get_printer_state`, whose `is_active` is true only for PRINTING, PAUSING or RESUMING (`prusalink_api.py:507-515`, 13.8). That is pinned by `tests/test_printer_state_api.py:133-163`, which this grounding ran offline: 17 passed, 1 skipped. At PAUSED, ATTENTION or BUSY a move asks nothing.
- **Step 5** (`logic.py:2540-2640`). The touched heads (source, destination, feeds) go through `_uncovered_active_heads` (`:160-188`), and one answer comes back (`_requires_confirm_answer` `:274-293`, in the D6 words of `_active_print_message` `:197-271`; the destination sentence `:264-268`). The pre-write contract is the comment at `:2017-2051`; this group changes nothing before the writes.
- **The head writes.**
  - Smart Load unloads the resident (`:2718-2806`), reading its record at `:2737`.
  - The PRINTER MOVE branch (`:3037-3170`) writes at `:3145`.
  - A Tool Head row the printer map doesn't list goes through the GENERIC branch (`:3192-3224`), writing at `:3215`. Such a head belongs to no printer, so no print's start snapshot can name it: the snapshot reads only the printer map's heads (`print_deduct._snapshot_active_spools`, `print_deduct.py:931-964`).
  - The undo record (`:2653`) is pushed at `:3260`.
  - The chain into a bound head (`:3262-3375`) folds the chained answer's `to_buffer` and `unarchived` into the outer answer (`:3360-3362`). It also deletes the chained move's own undo records from the stack and folds them into the outer record (`:3348-3358`), copying only `ejections`, `ejection_extras`, `ejection_released` and `buffered`.
- **Undo:** `perform_undo` (`:5198`), `_push_undo` (`:1706`), `describe_undo` (`:5101`).
- **The doors pass the engine's answer to the page:**
  - `manage_contents add` returns it whole (`routes_scan.py:512-541`);
  - `/api/smart_move` returns it whole (`print_deduct.py:274-311`);
  - the slot scan (its engine call `routes_scan.py:1680-1693`) relays every key of a question (`:1709-1730`) and sends a landed move's answer as `smart_move` (`:1783-1797`);
  - `/api/quickswap` sends it as `smart_move` (`routes_bindings.py:1498-1548`);
  - the wizard: `_wizard_move` (`routes_inventory.py:519`, its engine call `:545`) gives an edit's `location_result` (`:1392`), and a create answers each spool's engine answer in `location_results`, keyed by spool id (`:827`), which the page reads in `wizardSettleCreatePlacements` (`inv_wizard.js:4085-4090`, its `takeIntoBuffer(d)`).
- **The page:**
  - `window.confirmActivePrint` (`inv_core.js:387-665`): the three-way's options (`:387-393`); its first focus on the store (`:520`); Enter stores when there is a store (`:583-591`); the QR captions (`:610-632`; the store's is fixed at 'Scan to Store', `:626`); the scan hold-off for the three-way (`:636-663`).
  - `askMoveConfirm` (`:874-916`).
  - `noteUnarchived` and `takeIntoBuffer` (`:829-866`). Every move door calls `takeIntoBuffer`, pinned by `tests/test_door_to_buffer_canary.py`.
  - Quick-Swap's tap posts in `performSwap` (`inv_quickswap.js:826-869`) and calls `noteUnarchived` on success (`:838`). Its own confirm's PRINTING banner is `:574-578`.
- **Help:** the 'move-question' entry (`help_texts.js:162-175`).

### Tests' homes
- **The resume capture:** `tests/test_spool_swap_22_3b.py` (`_latch` `:155`; the resume cases `:164-231`).
- **The hotfix's split and sets:** `tests/test_swap_split_sets_hotfix.py` and `tests/test_print_end_heads_hotfix.py`, on `tests/deduct_wire_harness.py`.
- **The real engine:** `tests/move_engine_harness.py`.
- **Both halves of a move question:** `tests/roundtrip_harness.py` with `tests/roundtrip_bridge.py`, which has `ctl('printing')` (`:64`) and no latch yet.
- **The three-way's twin:** `tests/test_head_load_confirm_js.py`.
- **The registries:**
  - the write canary's `_apply_usage_to_printer` row (`tests/test_spoolman_write_sites.py:404`);
  - the route pin (`tests/test_route_table_pin.py`'s `EXPECTED_ROUTES`, sorted by path: the new row goes beside `/api/print_batch_csv`, `:80`; `/api/quickswap`'s rows are `:90-91`).

## Design

### (0) The sample
As above, before anything is built. Derek's three calls are asked with it.

### What each answer does

| Answer | What FCC records on the print | A finished print | A cancelled or ❓ print |
|---|---|---|---|
| **#42 came off here** (it ran out, or you swapped it) | A swap at ~42%, #42 → #229, marked as answered, with #42's used weight when it came off | Call 2 (a): each spool its share, no card. (b): the 🔁 card, pre-filled | The 🛑 card, RCOI-5's rows pre-filled at ~42%, as a recorded swap's are today |
| **FCC had it wrong** (#229 was on it all along) | #229 in place of #42 for this print, since that head's last change | #229 the head's share, no card. Nothing changed now, so today's auto-apply does it | A plain row for #229 |
| **Not sure** (also Enter, Esc, the page closing) | Nothing (one log line) | Today's 🔁 card: a swap seen at a pause is split for you to confirm, and a change made while it printed is a set to split by hand | Today's card |

### (1) Recording a change on the print (`print_monitor.py`)

Everything here runs under `_PRINT_TRACKER_LOCK` and never raises into a caller.

New latch keys:
- **`pending_changes`:** a list of unanswered changes, each `{key, job_id, position, toolhead, from_sid, to_sid, progress, paused, runout, from_used, lost, at}`.
- **`print_answers`:** `{key: what an answer replaced}`, kept only for Undo.
- **On a swap event:** `asked: "came_off"`, `asked_at`, `from_used` and `unplaced`. Old readers ignore unknown keys.

**`note_head_change(printer, toolhead, position, to_sid, resident_sid, resident_used)`** (the engine calls it after a head write landed):
- Needs a latched job: a `job_id` and `filename`, a state that isn't idle or ended, and a start snapshot that `_validated_start_spools` accepts. Otherwise None.
- `from_sid` is FCC's record for that head: `print_deduct._start_mapping(start, swap_log)[position]`.
- Returns None, noting nothing, for every case of Claude's call 2.
- Otherwise appends a pending change, with the cut of call 4 and `lost` from 65.1's stamps, saves the latch, and returns the facts the page shows.

**`answer_head_change(printer, job_id, key, answer)`** (the route calls it):
- Refuses when the job is no longer latched (`ended`) or the key is unknown (`stale`). Answering the same key twice is idempotent.
- **`came_off`:** if the resume capture already added this change (same position, `from_sid`, `to_sid`), marks that event; else appends one at the pending change's cut, in progress order with `seq` renumbered.
- **`out_of_date`:** removes a capture-added event for this change, if there is one. Then sets the stretch's spool: the last event at that position's `to_sid` if there is one, else `start_spools[position]` (and its alias form, after 64.3 (7)). What it replaced goes in `print_answers[key]`.
- **During a park:** after 64.3 (4), the park read's entry for that head becomes `to_sid`.
- **`not_sure`:** drops the pending change.
- Each answer writes one escaped Activity Log line (the words of the sample), and the latch is saved at once.

**`take_back_head_change(printer, job_id, key)`** (Undo): drops a pending change, or reverses an answer from `print_answers`. It does nothing once the job is no longer latched.

The edge's latch reset drops `pending_changes` and `print_answers`. The answers themselves ride on inside `start_spools` and `swap_log`.

### (2) The engine reports the change (`logic.py`)
- **The hook.** After `_move_write` lands in the PRINTER MOVE branch (`:3145`), `_note_print_change(...)` does a deferred `import print_monitor` and calls `note_head_change` with the head's printer and position from `printer_map[target]`. The GENERIC branch's head write (`:3215`) needs no hook: a Tool Head row no printer lists has no printer, so no latched print can name it (see Today's code).
- **The resident.** Smart Load's unloaded resident (the `before` read at `:2737`) gives `resident_sid` and `resident_used`; with no resident, the head was empty.
  - An empty head counts as FCC's record (Claude's call 2: its spool was taken off by an earlier move, often an eject at the run-out pause), so the load still asks, naming the spool FCC had.
  - That event has no `from_used`: the spool came off in another move, which noted nothing, and a read at the load could already include a weighing made since. 72b's check then opens the card for that head, because 64's Decision 1 can't tell a weighing from the print's charge without it. Keeping each head spool's used weight in the start snapshot (cheap once 64.3 (1) reads the list once) would give such a spool its baseline: a builder's call.
- **Best-effort.** Any raise is one hub.log line and never fails the move. Nothing changes before the writes, so the pre-write contract stays as it is.
- **The answer** gains `print_changes: [facts]`. The chain folds `chained.get('print_changes')` as it folds `to_buffer` (`:3360-3362`). The undo record gains `print_changes: [{printer, job_id, key}]`.
  - The head write of a slot scan happens inside the chained move, whose own undo record is folded into the outer one (`:3348-3358`). That fold copies `print_changes` too, or Undo of the scan would put the spools back and leave the answer on the print.
- **The D6 printing question stays as it is.** It guards the print, and it fires only while the printer prints.
- **If engine-only tests trip on the deferred import** (print_monitor pulls in print_deduct and the Flask app), use a hook instead: print_monitor sets `logic._head_change_hook` at its import, and logic calls it when set. Prefer the deferred import.

### (3) The route (`routes_bindings.py`)
- **The request.** `POST /api/print_change` takes `{printer, job_id, key, answer}`, with `answer` one of `came_off`, `out_of_date` or `not_sure`.
- **The answers.**
  - `{success: true, recorded, msg}`;
  - `{success: false, why: "ended"}` with 409: "Job 1142 ended before your answer reached FCC, so its review asks about RCOI-5.";
  - `{success: false, why: "stale"}` with 409;
  - 400 for a malformed body.
- **No Spoolman write.**
- **Registration:** `tests/test_route_table_pin.py` and app.py's `routes_bindings` re-export block, on purpose.

### (4) The question on the page
- **`window.askPrintChange(answer)`** (inv_core.js):
  - reads `print_changes` from the answer itself, its `smart_move` or its `location_result`, as `noteUnarchived` does, and from each entry of a wizard create's `location_results` (`noteUnarchived` doesn't read those: a new spool is never un-archived onto a head, but it can be loaded onto one through the Printer picker or a bound slot);
  - asks once per answer (a marker on the answer object, like `__fccUnarchivedNoted`);
  - shows one question per change, the next after the last is answered;
  - keeps one queue for the page: a second answer's changes wait behind the question on screen. `confirmActivePrint` settles an unanswered question on the same overlay id as superseded (`_openMoveConfirms`, `inv_core.js:513-514`), which here would drop a change unanswered.
- **The question.** `confirmActivePrint` with:
  - the title, words and buttons of the sample;
  - `printing` from the change's state (orange while printing, cyan when paused);
  - for look B, one `tiles: true` section per spool.
- **New `confirmActivePrint` options,** which change nothing when left out:
  - the first focus and a plain Enter on the cancel slot, even with a store;
  - a caption for the store QR (today fixed);
  - the header's icon (today ⚠️ while printing, else 🔁, `inv_core.js:447-448`);
  - the store button's verb in the hint (today "stores it", `:461`, `:546`) and its name in a held-off scan's words (today "Just store it" whatever its label, `:643`; or pass the existing `hint`).
- **Arming.** The two record answers take no click for 700 ms; Not sure takes one at once. Enter and the QRs never wait.
- **Its overlay id** is `fcc-print-change-question`, with no `host`, so it outlives the window the move came from. Pass it as a literal (`ids: { overlay: 'fcc-print-change-question' }`): `tests/test_help_texts_55.py` finds a question's overlay, and that it draws its ?, only by the id written out in a script (`overlay: '<id>'`), never through a constant.
- **Posting.** Each answer, Not sure included (for its one log line), posts through `window.fetchT`. The answer's `msg` is toasted: 4 s for a success, 7 s for a refusal. With no answer from FCC: a 7 s "FCC didn't answer, so your answer about RCOI-5 wasn't recorded: its review asks when the print ends." and a `logClientEvent` line.
- **Who calls it:** `takeIntoBuffer` (`inv_core.js:845`), and Quick-Swap's `performSwap` beside `noteUnarchived` (`inv_quickswap.js:838`).
- **Help.**
  - A `registerHelp` entry (`print-change-question`, matched by the overlay id): plain lines with made-up examples (HEAD-1, #42, #57) and no scan code, drawn as a ? in the question.
  - Its keys get `window.registerShortcut` (←/→, Enter, Esc, in a new scope).
- **Look rules:** named text sizes only; the contrast guard on every new word.

### (5) 72b: a finished print whose changes were all answered
- **The check.** In `deduct_completed_print`, before `_route_completion_to_review` (`print_deduct.py:2212`), a new check passes a changed head only when:
  - every event at it is `asked` and none is `unplaced`;
  - the end read names the last event's `to_sid` (64.2 (9)'s rule);
  - `_compute_swap_split` gives its segments from the one download;
  - every segment's spool can be read, and none also has a plain row;
  - 64's Decision 1 check passes on each spool: the event's `from_used` for the swapped-out spool (an event with none fails it), the end read's used weight for the rest.
- **When every changed head passes, charge.**
  - The plain heads charge through `_apply_usage_to_printer`, as now.
  - Each split row charges through one per-spool helper factored out of that loop's body (`_charge_spool`: the lock, the read, the clamp, `_deduct_payload`, `update_spool`, `_write_landed`, the ✔️ line, `details` / `failed_out`), so there is still one `update_spool` site.
  - A run-out spool that left its head, archived or not, is charged as `_deduct_payload` already handles it.
- **The words:** "✔️ 🦝 Core One INDX RCOI-5: auto-deducted 30.1g from Spool #42 (Complete; up to ~42%, where you said it came off) [...]" and "… from Spool #229 (Complete; from ~42%) [...]"; the ✅ summary as now.
- **The ledger** goes through `_record_applied_deduct`. A clamp opens 43.2's uncharged-grams card, as now.
- **Otherwise** today's card opens, with the answered heads pre-filled.
- **If Derek picks call 2 (b),** none of this is built: the card opens as today, with one line on it, "You answered at the change (~42%)".

### (6) Cancels and ❓ ends
No deduct change is expected. `_split_held_swaps` already splits a recorded swap, an answered one included, and a corrected start is a plain row. Tests prove it (below).

### (7) Undo
- **Taking back.** `perform_undo` takes back the record's `print_changes` through `print_monitor.take_back_head_change`, once the restore that puts that head back has landed.
- **Its question** (`describe_undo`) adds "(and forgets what you told FCC about RCOI-5 for job 1142)" while that job is latched.

## Tests

Every new test is shown red on `95531a6` first (`git archive` into a scratch folder), and each deduct test file starts with a plain print, one spool per head and no change, charged exactly as before.

- **Recording (backend, offline).** A new `tests/test_print_change_latch_72.py`, on the real `print_monitor` functions, with `_PRINT_TRACKER` set by the test (the shape of `test_spool_swap_22_3b.py`'s `_latch`).
  - A change is noted at a pause and while printing, with its cut, `paused` and `runout`.
  - Nothing is noted with no latched job, an ended state, no snapshot, a head empty at the start, the same spool, or a resident that isn't the record's spool.
  - "came off" appends one `asked` event, and after a resume capture marks that event instead (no second one).
  - "had it wrong" rewrites `start_spools`, or the last event's `to_sid`, and removes a capture-added event for the same change.
  - "not sure" leaves the latch as it was.
  - The resume capture after an answer records nothing (`_track_print_edge` with a stand-in probe and read, as in 22_3b).
  - A late answer and a stale key are refused with words, and nothing is written.
  - Answers survive `print_tracker_store` save / load and `_recover_one_print_latch`'s restore, and take-back reverses each one.
  - Every new Activity Log line puts outside text (a file name, an exception) through `print_deduct._esc`. `tests/test_deduct_accuracy_56.py`'s escape canary already reads print_monitor.py (`test_every_deduct_and_monitor_log_line_escapes_its_outside_text`), but it checks file names, exceptions and Spoolman's error words only, not a printer's name, so the new lines' words get a pin of their own.
- **The engine (offline).** A new `tests/test_print_change_engine_72.py`, with the real `logic.perform_smart_move` on `tests/move_engine_harness.py` plus a latch.
  - A slot scan into a bound slot at a pause notes one change through the chain: `print_changes` is on the outer answer, with Smart Load's resident and its used weight.
  - A load onto a printing head after the D6 yes / no notes one too.
  - An eject at the pause, then a load onto the emptied head, notes one change from FCC's record, with no `from_used`.
  - A failed write, a refused Smart Load and a removal note nothing.
  - The undo record carries the key, a chained deploy's too (folded into the outer record), and `perform_undo` takes it back.
  - A raise inside the note never fails the move.
- **The route (offline).** Through the Flask test client: each answer, and each refusal's status and words. `tests/test_route_table_pin.py` changes on purpose.
- **72b (offline).** A new `tests/test_print_change_deduct_72.py`, on the deduct wire harness (`tests/deduct_wire_harness.py`, or the seam 64.3 (1) leaves).
  - A finished print whose only change was answered "came off" charges each spool its segment, with no card, and the ledger records the sum.
  - "had it wrong" charges the new spool the whole head, with no card.
  - An unanswered change gets today's card; the hotfix's pins stay green.
  - An answered change whose end read names another spool gets the card.
  - A run-out spool weighed after it came off gets the card, never a charge on top (call 2 (a)'s list), and so does a swap event with no `from_used` (the eject-then-load case).
  - A mixed print gets the card, with the answered head pre-filled.
  - A cancel with an answered change gets the card, with split rows pre-filled.
  - An `unplaced` cut keeps the card.
- **The write canary.** In `tests/test_spoolman_write_sites.py`, the `update_spool` site moves into the per-spool helper: its row at `:404` changes, and the helper's name goes into CLAUDE.md's write-surface section as the anchor. If the helper reports a failed write only through what it returns, it also goes in `WRAPPER_WRITERS` (CLAUDE.md's rule), so its two callers are registered sites and neither may throw its result away.
- **The page (hermetic).** A new `tests/test_print_change_question_72_js.py` on the round-trip harness. Give `tests/roundtrip_bridge.py` a `ctl('latch', {printer, job_id, state, progress, start_spools})` and PAUSED / ATTENTION probe states. Scenarios:
  - an INBXX-style slot scan at a pause → the question → each answer → the latch as expected;
  - a Quick-Swap tap → its own "Yes, swap" → then this question;
  - while printing: the yes / no, then this question;
  - Escape → not sure;
  - a scan while it is open is held off with words on the question, and its own QRs answer it;
  - a double click on the button that made the move answers nothing (700 ms);
  - a late answer is toasted;
  - a page that never calls the helper asks nothing.

  Beside `tests/test_head_load_confirm_js.py`, a node test of the helper's words (paused, printing, lost contact) and options (focus and Enter on Not sure, the captions).
- **Canaries and guards.**
  - A twin of `tests/test_door_to_buffer_canary.py`: `takeIntoBuffer` and Quick-Swap's `performSwap` call `askPrintChange`.
  - `tests/test_help_texts_55.py` and `tests/test_help_buttons_55_js.py`: the new entry, its ?, no scan code.
  - `tests/test_text_size_floor.py`.
  - The toolhead-type canary: no head Type string.
  - The load-order canary: no new script file is planned.
- **Needs the dev container:**
  - `tests/test_contrast_guard.py`'s case for the question;
  - one E2E look at 1600×1300 and 390 px, with every non-GET answered in the browser, so nothing reaches dev.
- **The full run before merging** (frontend changes). Then one review round with the checklist's lenses (`docs/agent_docs/review-checklist.md`): a scanner is a keyboard, a double click's second press, stacked overlays, honest reads and writes, ordering and staleness.

## Done when
- FCC asks about a spool put on a toolhead in FCC during a print right after the move (call 1), at a pause as well as while printing. It never asks for a park alone, a removal or a tool change.
- Each answer is recorded on the print, survives a restart, is never recorded twice by the resume capture, and is taken back by Undo.
- "FCC had it wrong" leaves a finished print nothing to ask, and "came off here" splits the head where it came off.
- With call 2 (a), a finished print whose changes were all answered and line up charges each spool its share with no card. Anything else asks at the review, as today.
- A cancelled or ❓ print's card is pre-filled from the answers.
- Derek has seen the sample, and his look and words are built.
- CLAUDE.md and the PENDING DEREK checks say what the code does.

## Risks
- **A wrong answer charges wrong with no card (72b).** Not sure has the first focus and Enter, the two record answers wait 700 ms, and each charge line names the split, so a weighing trues it up. Call 2 (b) is the cautious alternative.
- **The engine's head write is the busiest code here.** The hook runs only after a landed write, is best-effort, and adds nothing before the writes.
- **The latch belongs to the monitor.** Every new key is written under `_PRINT_TRACKER_LOCK`, and a resume capture racing an answer for the same change ends as one event.
- **Two saves of the latch.** The tick copies the latch under the lock and writes the copy after it (`print_monitor.py:1131-1136`). An answer saved in between is then overwritten by the tick's older copy until the next tick, and a restart in those seconds loses it. Save in one order (a sequence number on the copy, or the answer's save taking the tick's place) and pin it.
- **Two questions while printing (call 1 (a)):** the D6 yes / no, then this one. That is rare on the INDX, where a change during printing is a record fix.
- **Stale tabs.** A page from before the release never calls the helper, so its moves get today's review at the end. That is safe.
- **Dev watches the real printers (68.6).** Dev's FCC asks too when a dev move touches a head of a printer that is really printing.
- **Same files as 62, 64 and 65.** Build after their merges and re-ground.

## Splitting (if the group is too big for its slot)
- **72a, the question and its record (~12–17 h):** the sample, the recording, the engine's report, the route, the page, Undo and the card pre-fill.
  - After 72a alone, "FCC had it wrong" already needs no card: the corrected record leaves the head unchanged, so today's completion auto-applies.
  - "Came off here" gives the 🔁 card a pre-filled split, also for a change made while printing, which is a set today.
- **72b, a finished print with no card (~4–7 h):** the per-spool charge, its checks, 64's Decision 1 for the swapped-out spool, and the write registration. If Derek picks call 2 (b), 72b is the card's one line only.

## Owed at the merge (CLAUDE.md and the buglist)
- **CLAUDE.md:**
  - a paragraph after "Move confirms name their heads (Group 39)": when this question asks, its three answers and what each records, `window.askPrintChange`, the route and its refusals, Undo's take-back, and 72b's rule;
  - the module map rows: `print_monitor.py` (the latch's change record and its three functions) and `routes_bindings.py` (`/api/print_change`);
  - the write-surface table's `_apply_usage_to_printer` row: 72b's charge, with the per-spool helper's name as its anchor.
- **Feature-Buglist.md, ⏸️ PENDING DEREK:**
  - **The mid-print session (`:120-151`).** Checks 1, 4, 5, 6 and 9 load a head, so this question now follows their prompt ("No second prompt" and "Exactly one prompt" change). Checks 2, 3, 7, 8, 10 and 11 take spools off a head, and 12 puts one back through Undo, which never asks, so those stand as written. Add one check: at a pause, load a spool onto a head and answer each of the three, then let the print finish.
  - **56.7's run-out item (`:214-219`):** "once the print ends, 🛑 Review should show a 'spool changed mid-print' card" changes per call 2.
  - **Group 22's M600 item (`:327-330`):** each colour change now asks; answer "came off here".
- **The ✨ item** is archived.

## Prod facts (read-only, optional)
- **Already known, from a local copy (no new read).** The hotfix session's capture of prod, 2026-11-12 16:07 (that session's scratchpad, `live_update/20261112-160726_before.json`; scratchpads can be cleared):
  - **The latch.** Prod's INDX latch for job 1142 held `filename`, `job_id`, `progress` 0.69, `snapshot_job`, `start_spools` (a spool on all 8 heads) and `state` PRINTING. It had no `file_meta` and no `swap_log`. So the flag is on there, and FCC can't tell which heads a print uses before its download.
  - **The parks.** The capture's hub.log lines show the INDX parked at ATTENTION during jobs 1137 (~0%), 1138 (~0% and ~37%) and 1141 (~19%). Each resume logged "no spool mapping change at any toolhead". Parks happen with no FCC move, so a park alone must never ask.
- **Optional, with Derek's OK (GETs only):**
  - prod's hub.log since 2026-11-12, for "spool changed mid-print" and "recorded N spool swap(s)" lines: how often the review has asked;
  - prod's `data/pending_cancel_deducts.json`, for `spool_changed` cards.

  Nothing in the build depends on them.

## Found while grounding (not in this group's items; for the refresh to file)

> **Filed 2026-11-17 by the refresh:** both joined 64.3's item, for its (4).
- **The latch keeps `file_meta`, and nothing reads it.**
  - Its comment says it is "latched for slice 5's preview UX" (`print_monitor.py:749-753`; also `:59`, `:731`, `:1611`; parsed at `prusalink_api.py:584`). Prod's INDX latch has none.
  - Drop it, or make the comment true.
  - Fits 64.3 (4), which adds `park_heads` to the same latch (64.3 (9)'s hygiene is about the tests only).
- **The resume capture's line for a park with no FCC move** (`print_monitor.py:849-854`) ends "so no swap was recorded and the full footer will be billed as-is."
  - That is wrong for a print then cancelled (FCC charges only the part printed up to the cancel, on a card) or ended unseen (a ❓ review asks).
  - Its raw `before={…}, after={…}` dicts sit in an Activity Log line a person reads.
  - On prod it was written at each of the four November parks.
  - Fits 64.3 (4), which rewrites the resume's comparison (a resume compares with the park read), or this group, whose answers change what that line means.

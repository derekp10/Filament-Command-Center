# Open decisions, explained (2026-10-13)

Written for Derek on the morning of 2026-10-13, after the overnight run, because the short versions in
[session-handoff-2026-10-13.md](session-handoff-2026-10-13.md) assumed you remembered each group's context.
Each explanation was drafted from the task files and **checked against the code on `dev` after Group 39 merged**
(5 readers + 1 fact-checker, workflow `wf_e72fb6df-441`). The numbers in brackets are the handoff's Question
numbers; the internal refs at the bottom of each item are for the next session, not for you.

**How to answer:** reply per section, e.g. "Your call: loop, refuse, keep moves-only, later. OK: yes to all.
Decide: fine." Anything you skip keeps its stated default.

## Derek's answers (2026-10-13, afternoon)

Answered one at a time after the overnight run. Until the task files are updated from this list, it wins over the "If you don't answer" lines below.

1. **Several spools in hand when you scan a whole box's (or printer's) label** → **Loop**: the slot chooser opens once per spool you're carrying (Enter, Enter, Enter fills the box); Escape stops and the rest stay in the buffer. _(Group 40 Q1 (handoff Q6))_
2. **Deleting a Room that still has locations in it** → **Refuse until it's empty.** Derek: deleting a room with stuff in it is a bad idea to begin with; a rename and re-ID is the right tool for a reorganisation. The ID system needs work, but IDs should stay readable (where it is, what it is, which one: LR-MDB-1 becomes something else that still reads that way). That part is input for the location-ID sit-down (Group 37 fork 1, paired with Group 44). _(Group 41 Q4 / 41.3 (handoff Q4))_
3. **Should Undo also undo a weight change?** → **Undo stays moves-only and is renamed "Undo Last Move"** (or "UNDO MOVE" if the tile is too narrow); the problem was that it never said what it does. It **always asks first, naming the move** it will reverse, printing or not (a printing head is called out like on any move). The toast says what it put back, and the Activity Log line is reworded so it can't be read backwards (today: "↩️ Undid: moved #57 from LR-MDB-1 -> XL-2"; new: "#57 is back in LR-MDB-1 (it had been moved to XL-2)"), so a user can fix things by hand. **No weight-undo**: it gets complicated once a print deduct or a review lands; other undos wait until they make sense elsewhere. **Redo**: undecided, a maybe-later (the command deck is already crowded). _(standalone Undo item, Feature-Buglist.md (handoff Q10))_
4. **Refresh dev's data from prod** → **Script the full refresh**: locations plus the Spoolman inventory, prod read-only, the dev-only test pieces re-applied, the reset snapshot retaken. Run it one evening when Derek is around to approve the prod reads. Not urgent. _(Group 45.6 (handoff Q14))_
5. **A print's uncharged grams when its spool ran out and was archived** → **Charge the picked spool and leave it archived**: it doesn't move, and a charge that takes a spool to 0 g archives it, as today. Today's review cards stop refusing archived picks too. Derek's notes: on small spools the recorded weight can be well off (job 1104: he thought #99 had enough to finish); he'd like FCC to catch a joined-spool switch (one head used, the printer moves to another) if the printer exposes it, which would need a history of toolhead changes and may get messy. Known so far: PrusaLink reports nothing per slot; the swap-diff logging shipped 2026-10-08 will show what FCC can see on the next joined-spool runout (the SpoolJoin item in PENDING DEREK). _(Group 43.2 (handoff Q2))_
6. **Delete dev's blank-ID "TestCart" row** → **Done 2026-10-13 by Claude** through the app's own delete path (`DELETE /api/locations?blank_id=1`): 82 → 81 rows, no blank-ID rows left, no spool touched (backup in the session scratchpad, `locations.pre-testcart-delete-20261013.json`). The two standing sweep reds (`test_locations_json_integrity.py`, `test_location_combobox_highlights_current_selection_on_focus`) now pass. **`CR-TC-1` (also named "TestCart") is kept**, per Derek. _(Group 46.5 follow-up (handoff Q15))_
7. **Is TST-MDB-1 just a test box?** → **Yes.** Empty becomes its protected starting state (its old `{"1": "PRINTER:XL"}` leftover is dropped from the reset snapshot); the Printer Status widget test gets made-up data instead of clearing every box; the shared Quick-Swap helper uses a test box holding a test spool instead of Derek's real boxes. No change to dev data. _(Group 45.5 (handoff Q13))_
8. **The never-run Feeds test (slot 1 linked, slot 2 left empty)** → **Point it at TST-MDB-1** (6 slots, empty) instead of widening PM-DB-1, which stays a one-slot PolyDryer. Depends on the answer above. _(Group 45.4 (handoff Q12))_
9. **Claude's calls; Derek reviewed them and didn't object** → **A.** A full box in the slot chooser works like the Location Manager grid (tap an occupied slot → Swap / Overwrite; the incoming spool always gets a real slot). **B.** A PolyDryer remembers where its spool lived before it went in (a separate "before the box" note, shown as a "(system)" field in Spoolman like the existing breadcrumbs), built together with "the PolyDryer follows its spool". **C.** Bulk Move's dead "source is printing" check is removed, with its fake test. **D.** Printer Status's tool-name option counts from 1 ("Tool 1"). **E.** The OFFLINE printer label goes from 45% to 50% white, landed with the contrast-guard fix. _(A: Group 40 Q2 (handoff Q7) · B: Group 42 Q-A caveat / 42.6 (Q5) · C: Group 41 Q3 / 41.7 (Q3) · D: Group 46.3 (Q1) · E: Group 45.3 (Q11))_
10. **Still for a sit-down** → What permanently identifies a printer, and whether a location's ID should still decide where it sits. Derek's input from the Room-delete answer: reorganise by renaming / re-ID'ing, with IDs that stay readable (where it is, what it is, which one). _(Group 44 (handoff Q8), Group 37 fork 1 (Q9))_

## Your call

Product behaviour only you can decide. Each has my recommendation.

### Carrying several spools when you scan a whole box's or printer's label: place them one after another, or only the top one?

_(your call)_

**What it is.** First, the slot chooser. It is planned, not built. Today, if you scan a multi-slot dryer box's own label while spools are in your buffer (the strip of spools you've scanned and are carrying to a location), FCC decides for you. The box's own label is its box QR, e.g. LOC:LR-MDB-2, as opposed to a per-slot label like LOC:LR-MDB-2:SLOT:1.
- With one spool, FCC takes the lowest free slot. If that slot feeds a toolhead and the printer is idle, the spool goes straight onto that toolhead, and whatever the head was running is unloaded without asking.
- With two or more spools, it drops them all into the box with no slot (floating loose), and the toast just says 'Assigned 3 items!'. If you carry more spools than the box has slots, its count overflows too (e.g. 3/2).
- Scanning a printer's own label (LOC:XL, LOC:RCOI) with spools in the buffer files them all on the printer itself, not on any toolhead.

The planned chooser is a pop-up showing every slot of the box: the spool in it, which toolhead it feeds, and a star on the recommended slot. A slot can also be a Printer Pool slot: one wired to the printer as a whole, used for staging, which never loads a head. You pick by tapping a slot, using the arrow keys and Enter, pressing its number, or scanning its slot label. Escape cancels and the spool stays in the buffer. A printer version lists the heads (XL-1 to XL-5, with what each holds) plus the Printer Pool slots. PolyDryers never get the chooser: their box label stays a single scan.

The question: the chooser places one spool, so what should happen when you're carrying several?

**Where you'd see it.** Only when you scan a multi-slot box's own label (LR-MDB-1, LR-MDB-2) or a printer's own label (LOC:XL, LOC:RCOI) with two or more spools in the buffer. You normally place spools with slot labels and toolhead QRs, so you'd rarely see it. Scanning slot labels one after another already places a full buffer one spool per scan. A PolyDryer label or a toolhead QR already takes only the top spool (normally the one you scanned last).

**Example.** You carry #150, #151 and #152, with #150 on top. LR-MDB-2 is empty (slot 1 feeds XL-4, slot 2 feeds XL-5), XL-4 and XL-5 are empty, the XL is idle, and you scan LOC:LR-MDB-2.
- (a) Loop: the chooser opens for #150 and recommends slot 1. Press Enter, and #150 goes into slot 1 and onto XL-4. It reopens for #151 and recommends slot 2. Press Enter, and #151 goes onto XL-5. For #152 the box is full, so you can swap it into an occupied slot or press Escape; #152 stays in the buffer.
- (b) Top only: #150 goes wherever you pick. #151 and #152 stay in the buffer until you scan LOC:LR-MDB-2 again, once for each.
- Today: all three go into LR-MDB-2 with no slot (it shows 3/2), and nothing loads onto XL-4 or XL-5.

**Options:**

- **(a) Loop: one chooser per spool (recommended).** One scan of a box or printer label walks you through every spool you're carrying, one chooser at a time: Enter, Enter, Enter fills a box. Each spool still gets the usual questions when its slot feeds a toolhead that is printing or is already running a spool from somewhere else (a PolyDryer, say). Escape stops at any point, and the rest stay in the buffer. For a printer label, you pick a head or a Printer Pool slot for each spool in turn.
- **(b) Top spool only.** Only the top spool is placed. The rest stay in the buffer, and you scan the box or printer label again for each one. A PolyDryer label, a toolhead QR and a slot label already work this way when you carry several spools.
- **(c) Keep today's behaviour when carrying several.** With two or more spools in hand, they all go into the box with no slot: the floating state you said reads as 'what went wrong' (and the count overflows, 5/4-style, when there are more spools than slots). The chooser opens only when you carry exactly one spool. For a printer label this would simply be refused, because the same work stops spools being filed on the printer itself.

**My recommendation.** (a): someone without slot labels can fill a box from one scan, every spool still gets a slot and every load question, and Escape loses nothing. It hardly touches your own scanning (you place spools with slot labels and toolhead QRs), so one word is enough.

**If you don't answer.** (b) is built: only the top spool is placed and the rest stay in the buffer (the documented default). Nothing changes until the chooser itself is built, and it is planned after the PolyDryer work.

<details><summary>What was checked (for the next session)</summary>

Internal ref: Group 40 Q1, handoff Question 6 (docs/agent_docs/tasks/40-slot-picker.md, 'Open questions' Q1; shapes 40.2 box-label door and 40.5 printer door)

Read on dev after the confirm-on-every-door merge (c389e26). Paths are from the repo root.
- inventory-hub/static/js/modules/inv_cmd.js:1712-1745, a location scan with a buffer. Only toolhead types and Max-1 boxes are trimmed to the top spool (:1730-1740). A multi-slot box or a Printer row gets the whole buffer via performContextAssign (:1864-1929): POST /api/smart_move with slot null, then 'Assigned N items!' at :1909.
- inventory-hub/print_deduct.py:254-268 api_smart_move: no Printer-row refusal yet.
- inventory-hub/logic.py:851-882: auto-slot still fires only for a single spool (:858), and still after the confirm step (:842-844), even though the pre-write contract comment (:699-719) reserves an earlier step for it. Several spools land with container_slot '' (:1018-1021).
- logic.py:738-746 (the 2026-09-29 INDX hotfix): XL and RCOI (Max 0, owning other heads) are not single-occupancy. The generic branch (:1120-1144) files every buffered spool on the printer row. _active_print_info_for_location (:13-31) returns None for 'XL', so the destination itself never raises a printing question.
- inventory-hub/routes_scan.py:1229-1266 and :1334: a slot-label scan places only the first buffered spool and answers 'N still in buffer'.
- The merge reserved fed_heads / can_store / target_slot in _requires_confirm_answer (logic.py:216-231) but built none of the chooser, so the question is unchanged.
Stale in 40-slot-picker.md:
- The door table says Smart Load treats LOC:XL as single-occupancy. That has been false since the hotfix.
- The dev topology is out of date. Dev's inventory-hub/data/locations.json now has RCOI (RCOI-1..8, Max 0) instead of CORE1, CR-MDB-1 with no bindings, TST-MDB-1 reading {}, and PM-DB-1..10.
- Line refs have drifted: auto-slot was 553-578 and is now 851-882; the single-spool check was logic.py:554 and is now :858.
Second pass (fact-check, read-only on dev): every code reference above re-read and holds; the auto-deploy chain passes no confirm for an auto-picked slot, so mid-print the one-spool case stays in the slot with a warning instead of loading. Corrected three things: a multi-spool drop always floats the spools but overflows the count only when there are more spools than slots; option (a)'s extra question is for a head fed from somewhere else, per the planned rule in 40-slot-picker.md 40.0c (the slot's own spool swaps with no prompt); decision_type moved from agent_can_decide to opinion, because loop-versus-top-spool is a product behaviour and the recommended (a) differs from the documented default (b), which the old text contradicted.

</details>

### Deleting a Room that still has boxes and shelves in it: refuse, or empty them?

_(your call)_

**What it is.** Every row in the Locations list has a 🗑️, Rooms included. Deleting a Room removes only the Room's own row, but it also sets to Unassigned every spool FCC counts as "in" that Room:
- spools filed on the Room itself;
- everything in any location whose ID starts with the Room's code (for LR: the dryer boxes LR-MDB-1 and LR-MDB-2, and the drawers LR-SD-1 and LR-SD-2);
- the spools on XL-1 to XL-5 that came out of those boxes, because the delete also follows each spool's "came from" link (the box it was loaded from).

Nothing checks for a running print. The boxes, the drawers and the XL printer row are not deleted. They stay, emptied, still listing LR as their parent, and from the code the list then shows a stand-in "LR (Room)" where LR was. The prompt is only "Delete LR?". Failures go only to the server log, the delete always reports success, and it has no Undo.

Some fixes are already planned whatever you answer. A delete will never touch a spool loaded on a toolhead, it will clear the box links it leaves behind, and if any spool can't be updated the location is kept and a toast names the spools. The open question is what happens to the spools in the Room's boxes and drawers.

**Where you'd see it.** The LOCATIONS tile on the dashboard deck → the Locations list → the 🗑️ on a Room row (LR, CR or DR) → "Delete LR?".

**Example.** You reorganise the living room and delete LR. LR-MDB-1 has a spare in slot 4, the drawer LR-SD-1 holds two spools, and each XL head has a spool loaded from LR-MDB-1 or LR-MDB-2. Today all eight spools become Unassigned, including the five on the XL heads, even mid-print. LR-MDB-1, LR-MDB-2, LR-SD-1, LR-SD-2 and XL all survive, pointing at a Room that's gone. There is no Undo, so you re-place all eight by hand.

**Options:**

- **A. Today's reach, minus toolheads (what gets built if you don't answer).** Deleting LR empties its boxes and drawers. The three box and drawer spools become Unassigned with their box links cleared, and the five loaded XL spools stay on their heads. LR-MDB-1, LR-SD-1 and the rest stay as empty rows, still naming LR as their parent. If any spool can't be updated, LR isn't deleted and a toast names the spool. There's no Undo, so you re-place the emptied spools by hand.
- **B. Only spools filed on the Room itself.** Deleting LR unassigns only spools whose location is exactly LR (loose spools in the room). The box and drawer spools stay where they are, and so do the loaded XL spools. The boxes, drawers and XL still point at a Room that no longer exists.
- **C. Refuse while the Room still has locations inside it (recommended).** Deleting LR while it still has locations inside it is refused with a message like "LR still contains LR-MDB-1, LR-MDB-2, LR-SD-1, LR-SD-2 and XL — move or delete them first", and nothing changes. To retire a Room you first give each of those a new Parent (✏️ → Parent) or delete it, then delete the empty Room. Any loose spools filed on the Room itself then become Unassigned, and toolheads are untouched. Nothing is ever emptied by accident.

**My recommendation.** C. Deleting a Room that still has boxes inside is almost always a reorganisation, and a delete has no Undo, so every emptied spool would be re-placed by hand. A or B would also leave the boxes and the XL pointing at a Room that's gone.

**If you don't answer.** Option A gets built (the documented default). Deleting a Room still empties its boxes and drawers, but never touches a spool loaded on a toolhead, and failures are reported.

<details><summary>What was checked (for the next session)</summary>

Internal ref: Handoff Q4 = Group 41 Q4 / sub-task 41.3 (docs/agent_docs/tasks/41-honest-bulk-results.md 'Q4' and 'Found while writing this plan'); Group 37 invariant (37-location-system-redesign.md:261-262)

Delete route: routes_locations.py:api_delete_location (:538-645). A Room takes the non-toolhead branch (:617-645), which:
- reads with the fail-open spoolman_api.get_spools_at_location, which returns direct, first-segment and ghost (physical_source) matches;
- sends a location-only update_spool(sid, {'location': ''}) per spool (:626), leaving container_slot and physical_source behind;
- logs failures only to hub.log (:627-630);
- ignores save_locations_list's result (:643) and always answers success: true (:645);
- has no active-print check and no child-location check.

Ghost reach: the ghost branch of spoolman_api.py:_build_location_match (:1494-1503) matches physical_source LR-MDB-1 (first segment LR). logic.py:_ghost_trail_from (:553-569) writes the box as physical_source on a box → head move.

Bindings (read-only; prod and dev agree): LR-MDB-1 slots 1-3 → XL-1..XL-3, slot 4 → PRINTER:XL; LR-MDB-2 slots 1-2 → XL-4, XL-5. Tree (prod and dev): LR's parent_id children are LR-MDB-1, LR-MDB-2, LR-SD-1, LR-SD-2 (Sliding Drawers) and the Printer row XL; CR's include RCOI.

Stand-in row: the /api/locations synthesizer (routes_locations.py:153-219), with locations_db.ancestors_of (:739-755), makes a 'Virtual Room' for a parent id that has occupancy (including a stale physical_source trail) but no row. This is a code trace; I did not run it.

No Undo: only logic.py:_perform_smart_move_impl pushes the undo stack (:958, :1146). Both delete paths write through update_spool directly (perform_toolhead_delete_cascade, logic.py:2240-2358, likewise).

Frontend:
- 🗑️ on every non-'Virtual' row (static/js/modules/inv_core.js:1219-1221).
- Prompt 'Delete LR?' (inv_loc_mgr.js:_deleteLocRequest :2426-2433); deleteLoc is at :2435-2453.
- Parent dropdown in the editor (templates/components/modals_loc_mgr.html:88).

The location redesign's invariant (37-location-system-redesign.md:261-262) says a room-level clear or delete must never reach a live toolhead, via an explicit guard. On dev, cart rows (CR-CT-2-R1..R3) hang off their cart by parent_id, so a parent-based refusal would naturally cover carts too. Today a cart delete reaches only spools filed directly on the cart.

Stale in the task file:
- deleteLoc now reads the answer and toasts a refusal (hotfix 2026-09-29); the task file says it 'never reads the answer'.
- Deleting the Printer row XL is now refused with 409 while it has heads (routes_locations.py:556-575), so 'deleting XL would unassign every XL head' no longer applies.
- Line refs drifted: the non-toolhead branch was :449-477.
- Its example refusal message omits XL, but XL's parent is LR on prod and dev, so a parent-based refusal would name it.

Today's confirm-on-every-door merge did not touch the non-toolhead delete path.
Second pass: the code claims re-read and hold; the synthetic row's Name is '<id> (Room)', the ✏️/🗑️ are hidden only for Type exactly 'Virtual', and an explicit Parent save accepts any existing row (routes_locations.py:400-428). Corrected option C, which said 'while it still holds anything' yet let loose spools through; the refusal is about child locations. Prod could not be re-read (this session's permission check refused it). The 2026-10-08 copy of prod's configuration (inventory-hub/data/locations.json.pre-cart-restore-20261008-164132.bak) has the same LR children and bindings, with RCOI unparented, which 44-printer-first-class.md:47 says was fixed by hand on dev and prod that day.

</details>

### Should Undo also undo a weight change, or stay moves-only?

_(your call)_

**What it is.** FCC's Undo (the UNDO tile on the dashboard's command deck, or scanning the CMD:UNDO QR) reverses spool moves only. Changing a spool's weight (in the weigh-out list, the weight-entry overlay, the edit wizard or the details window) records nothing Undo can reverse.

So if you weigh a spool, spot a typo and press Undo, FCC doesn't put the old weight back. It reverses the most recent move instead: the last move made from any tab since FCC last restarted, however old and unrelated. When nothing is left, the server answers "Nothing to undo (Undo reverts spool moves only).", but the dashboard currently throws that answer away, so you never see it. Undo work that is already planned will show it, and will also show what was undone.

Making Undo cover weights means three things. Every weight-changing screen has to save a "before" snapshot. Undo has to know whether your last action was a move or a weigh. And it must not wipe out a print charge that landed after the weigh (FCC charges filament to spools automatically when a print finishes or is cancelled).

**Where you'd see it.** The UNDO tile on the dashboard's bottom command deck and the CMD:UNDO QR, right after any weight change: the WEIGH QR / weigh-out list, the weight-entry overlay, the wizard's weight fields, or the details window.

**Example.** You weigh #88 in the weigh-out list, type 812 g instead of 821 g, and press UNDO. The weight stays 812 g. If the last move anyone made was this morning's Quick-Swap on XL-2, that is what gets reversed: the old spool goes back on XL-2 and the new one back into LR-MDB-1 slot 2, and the Activity Log says "↩️ Undid: moved …". Today that happens without asking, even if the XL is printing (a print check for Undo is planned). You fix the weight by weighing or typing it again, which simply replaces the number. With weight-undo, if a print had finished between the weigh and the Undo, putting the old weight back would also erase that print's charge, unless Undo knew about it.

**Options:**

- **A. Keep Undo for moves only (recommended).** Undo works as it does now, and you fix a wrong weight by weighing or typing it again. The Undo work already planned makes Undo say on screen what it reversed, or "Nothing to undo (Undo reverts spool moves only)".
- **B. Build weight-undo.** Pressing Undo right after a weigh puts the previous weight back. If that weigh emptied and archived the spool, Undo also un-archives it and puts it back where it was. This means changes to about six weight-entry places, a second kind of undo record, and rules for a print charge that lands in between. It is several sessions of work, and should be designed together with the planned single weight-entry component.
- **C. Moves only, but Undo names the move and asks first.** Pressing Undo shows something like "Undo: put #57 back in LR-MDB-1 slot 2 and #196 back on XL-2?" and waits for a Yes. That is one extra tap per Undo, but a press after a weigh can no longer quietly reverse an older, unrelated move. It is small and could ride along with the Undo work already planned. This is my suggestion; it isn't in the existing plan.

**My recommendation.** A. A wrong weight is already fixed by weighing again (each weigh replaces the number), whereas weight-undo is a multi-screen feature that has to fit around the automatic print charges. If the surprise of Undo moving something else worries you, add C's confirm when Undo is reworked.

**If you don't answer.** Nothing is built until you answer, so Undo stays moves-only and the buglist item stays open.

<details><summary>What was checked (for the next session)</summary>

Internal ref: Handoff Q10 = standalone 🟡 'Undo reverts moves only — wire weight-undo, or keep it move-only? (decide first)' (Feature-Buglist.md:363; docs/agent_docs/working-groups.md:246; origin completed-archive.md:247, 2026-06-15 19a4a5e). Related: Group 41.4 honest Undo.

Where it is recorded:
- Feature-Buglist.md:363: standalone 🟡 'Undo reverts moves only — wire weight-undo, or keep it move-only? (decide first)', filed 2026-10-12 by the buglist reconciliation.
- docs/agent_docs/working-groups.md:246: 'OPEN — standalone, needs Derek's decision first'.
- Origin, completed-archive.md:247 (2026-06-15, 19a4a5e): 'Weight-undo intentionally NOT wired'.

Code:
- logic.py:perform_undo (:2397-2525) restores only location, the slot/source extras, Smart-Load ejections and buffer membership, never a weight field. The empty answer is at :2398, and perform_undo never probes the printer, so it writes to a printing head without asking.
- logic.py:_push_undo (:612) is called only from _perform_smart_move_impl (:958, :1146).
- state.py:7 UNDO_STACK is a plain in-memory list under 'GLOBAL STATE': no cap, cleared only by a restart, shared by every tab.
- Weigh-out posts /api/spool/update (static/js/modules/inv_weigh_out.js:432). When the spool empties it also posts force_unassign (:490 → logic.py:perform_force_unassign :2361-2395). Neither records an undo.

Stale or inaccurate in the docs:
- The buglist's line refs logic.py:690, :878 and :2091 are now :958, :1146 and :2398.
- 'Its empty message says so' is true only in the API JSON. triggerUndo (static/js/modules/inv_cmd.js:1931) discards the response, perform_undo writes no Activity Log line for the empty case, and no frontend code reads the pulse's undo_available (routes_state_pulse.py:238), so the UNDO tile never dims.

The honest-bulk-results task file's Undo sub-task already plans the toast, the log line and a print-check ask. Weight surfaces are as listed in CLAUDE.md 'Weight-entry surfaces'. Print charges write used_weight via print_deduct._apply_usage_to_printer.
Second pass: every claim re-read and holds (perform_undo restores the Smart Load ejection, so a Quick-Swap undo puts both spools back; the UNDO tile is templates/dashboard.html:180; only a comment in inv_core.js mentions undo_available). No changes.

</details>

### Refresh dev's data from prod as a repeatable one-step copy (not urgent)

_(your call)_

**What it is.** FCC runs in two places with completely separate data. Prod is the copy on the TrueNAS you use day to day, with prod Spoolman on port 7912. Dev is the Docker copy on your desktop at localhost:8000, with its own Spoolman on 7913. The two drift apart. Dev's Spoolman inventory (spools, filaments, brands, weights) is essentially June's snapshot (238 spools, 177 filaments, 40 vendors), churned by months of automated tests. Prod has your real purchases, prints and weigh-ins since then. Dev's location list was already copied from prod once, by hand, on 2026-10-08; that's how dev got the INDX. Printer logins were left out of that copy (dev has them again now), and your CR-TC test carts and the TestCart repro row were put back afterwards. The proposal is to turn that into a scripted refresh. It would read prod without changing anything there, copy both the location list and the Spoolman inventory into dev, and re-apply the dev-only pieces: your test carts, the empty test boxes the tests rely on, the virtual test spools, and a deliberate choice about printer logins. Along the way it would count, read-only, any spools on either side that still remember a 'came from' box slot after leaving the printer.

**Where you'd see it.** Only on dev (localhost:8000): its spools, weights and filaments would match your real inventory as of the copy. Nothing changes on prod. You'd mostly notice it when you ask me to reproduce a prod problem on dev, or when you try something by hand on dev and want realistic data.

**Example.** An example of the drift that bites: dev's saved reset snapshot dates from 2026-06-02, before the INDX. Running reset-dev today would bring back the old single-head Core One (CORE1) and drop the INDX heads RCOI-1 to RCOI-8 from dev. A refresh would finish by re-taking that snapshot from the refreshed data. A second example: four dev filaments (#4, #121, #157, #175) lost some extra fields to an old bug on dev, and a Spoolman copy from prod would put them back.

**Options:**

- **Script the full refresh: locations plus the Spoolman inventory (recommended, whenever convenient).** One command refreshes dev, and prod is only read. You'd need to be around to approve the prod reads, because the session's safety check blocks prod access without you. Copying Spoolman with the same spool numbers as your labels probably means copying prod Spoolman's database file into dev's Spoolman on the NAS while dev's Spoolman app is stopped, which may need you in TrueNAS. Copying through Spoolman's API instead would renumber every spool. Tests that lean on particular dev spools may need a one-time touch-up.
- **Locations only, by hand when needed (as on 2026-10-08).** Dev's location list stays close to prod's. Dev's spools and weights stay June's snapshot plus test churn.
- **Not now.** Nothing changes. Dev keeps drifting, and the June reset snapshot remains a trap: a reset would undo the INDX on dev.

**My recommendation.** Script the full refresh, in a quiet window when you're around to approve the prod reads. It's the only option that lets 'does this happen on prod?' be answered on dev, and it fixes the out-of-date reset snapshot along the way; there's no rush.

**If you don't answer.** Nothing is built until you answer. Dev keeps June's Spoolman inventory and the 2026-10-08 location copy, and the reset snapshot stays out of date.

<details><summary>What was checked (for the next session)</summary>

Internal ref: Handoff Q14 / Group 45.6 (refresh dev from prod; absorbs 45.7 drift count and the Group 36 prod-to-dev sibling-extras restore)

setup-and-rebuild/reset_dev.py:222-244 restore_locations overwrites the whole dev locations.json with seeds/locations-seed.json: 53 rows, captured 2026-06-02 in efc82fd, with no Printer rows, CORE1 present and no RCOI. Dev inventory-hub/data/locations.json has 82 rows, including Printer rows XL (XL-1..5) and RCOI (RCOI-1..8). The reset_dev.py docstring (:52-56) notes that Spoolman assigns ids on create; hence the renumbering point. Seed counts come from seeds/spoolman-dev-seed.json (40/177/238). The 2026-10-08 copy is recorded in commit 92abc12 ('Dev's locations.json was synced to prod's configuration on 2026-10-08 ... the sync deliberately stripped printer credentials') and visible in inventory-hub/data/ backups. pre-prod-sync had CORE1, the TestCart blank row and the CR-TC carts. Right after the copy, prod's blank 'Unknown Location' Virtual Room row was present and the CR-TC carts were gone; they were restored at 16:41, and the TestCart row replaced 'Unknown Location' later. So a future locations copy brings in prod's own blank-ID row, and the script must handle it or the two standing sweep reds return. Stale: Feature-Buglist.md:121 and the 'Interactions' section of docs/agent_docs/tasks/45-sweep-load-tolerance-test-hygiene.md say dev still reflects the older fleet, but dev has had RCOI since 2026-10-08. Prod reads need Derek's approval (memory feedback_prod_data_is_gold_standard; the overnight read-only prod GET was denied, handoff lines 143-149). The filament ids come from the same task file. Outside this question: the handoff's two 'Checking… (offline printer)' manual checks still say 'Open CORE1'. Dev, copied from prod's configuration, has no CORE1 row, only RCOI.
Second pass: the reset-dev and seed claims re-read and hold. Corrected 'printer logins were left out' and the plan's 'no printer logins' dev-only piece: the 10-08 copy stripped them (the 14:31 post-copy backup has empty printer_creds), but dev's locations.json carries a LAN IP and API key on XL and RCOI again (back by the 18:47 backup), so the refresh has to decide what dev should hold rather than assume none. This session's own read of the prod share was refused by the permission check, which bears out option 1's note.

</details>

## Just needs your OK

Low-risk; I'll do the recommended thing once you say yes.

### Where a print's uncharged grams go when the spool ran out and was archived

_(needs your OK)_

**What it is.** When a print finishes, FCC charges each head's grams (from the slicer's numbers) to the spool loaded on that head. It never charges a spool more than FCC's records say is left on it. So if a spool's recorded filament runs out partway through, FCC charges what's left and the rest of the print's grams go to no spool. That leftover is a shortfall, and today the only trace is one warning line in the Activity Log. A spool whose recorded remaining hits 0 g is auto-archived: it's hidden from your active spools and moved to UNASSIGNED, off the head or box slot it was in (FCC remembers where it was). The planned fix: when about 1 g or more goes uncharged, FCC adds a shortfall card to the review list, the same place cancelled-print reviews go. The card asks which spool took the rest, using the spool picker added last night (spools on the printer's heads when the print ended, spools on them now, or any spool by #id). It would suggest the spool that was on the head at the end. If that spool is the one that just got archived, it would ask you to pick instead. The open part: what should happen if you pick an archived spool? Today's review cards refuse one while they wait for this answer, so whatever you decide applies to them too. Worth knowing: picking the run-out spool itself charges nothing under any option (0 g, or a refusal), because it has nothing left on record. The choice only matters for an archived spool that still has grams on record, such as one you archived by hand. One limit: the card only appears when the first spool's record actually runs out. If that record was too high, everything is charged to it and nothing flags it; that is the separate detection question your next SpoolJoin print should answer.

**Where you'd see it.** The 🛑 review window ("🛑 Cancelled-Print Reviews"), opened from the 🛑 chip on a printer's name in Printer Status, the "🛑 N reviews" pill on the Activity Log header, or the "🛑 Review" button on a log line. After a finished print FCC couldn't fully charge, the new shortfall card would appear there. Today you only get the Activity Log warning.

**Example.** Job 1104 on the Core One INDX: the file MAIN-B was sliced for head 1 (RCOI-1) and needed 61.32 g. RCOI-1's spool #99 had 34.2 g on record. You had head 1 joined to head 2 ("joined (T1 to T2)" in your note), so when #99 ran dry the printer switched to head 2's spool by itself and finished. FCC can't see that switch. It charged #99 its last 34.2 g; #99 hit 0 g and was auto-archived and moved off RCOI-1. The other 27.12 g went to nobody, so head 2's spool still reads 27.12 g heavier than it really is. With the shortfall card, a 🛑 card would say that 27.12 g of MAIN-B weren't charged. It wouldn't suggest #99 (archived and empty). You'd pick RCOI-2's spool from "On this printer's heads now", press Apply, and the 27.12 g lands there. That part is the same under every option below; they only differ if you pick an archived spool.

**Options:**

- **Charge it and leave it archived.** An archived spool you pick is charged whatever it still has on record, then stays archived and doesn't move. For #99 that's 0 g, so the card reports the 27.12 g as still uncharged, and you pick again or discard. FCC already follows this rule when an automatic deduct, or a review row you keep, lands on an archived spool. Today's review cards would stop refusing archived spools too.
- **Un-archive it, then charge it.** A picked archived spool comes back into your active spools. For #99, with nothing left on record, there's still nothing to charge, so you'd just get an empty spool back in your list. FCC's current un-archive rule also sends a spool back to where it was before it was archived. For a spool that came off a toolhead, that's the head, which may hold another spool by now. Two spools on one head make FCC skip that head's next deduct as "ambiguous", so a build would have to work around this.
- **Keep refusing archived spools (as today).** The shortfall card and today's review cards keep saying "spool #N is archived — refill it (weigh it) or pick another spool". To use an archived spool you weigh it first: a weight that leaves grams un-archives it automatically and puts it back where it was. For a spool that came off a toolhead, that's the head, which can leave two spools on it (the same catch as the option above, until a planned fix sends it to the printer's room instead). Then you Apply. It's the most cautious option for the charge itself, but it costs an extra step in the rare case it comes up.

**My recommendation.** Charge it and leave it archived, as the handoff suggests. FCC already applies this rule when an automatic deduct or a kept review row hits an archived spool, and it never moves a spool. In the real job-1104 case you'd pick head 2's live spool anyway, so the choice only matters for an archived spool that still has grams on record.

**If you don't answer.** Nothing is built until you answer; the plan schedules this item after your reply. Until then, a shortfall on a finished print stays a single Activity Log warning ("27.12g of '/usb/MAIN-B~1.BGC' wasn't deducted … weigh that spool to true up"), and the review cards keep refusing an archived spool with "Charging an archived spool is still an open question." Only the archived-spool rule needs your answer: the card itself could be built now with today's refusal (the third option) as a stopgap and switched later.

<details><summary>What was checked (for the next session)</summary>

Internal ref: 43.2 (Group 43 'A shortfall becomes a recoverable review'; handoff Questions for Derek #2; buglist 'A PARTIAL deduct with a leftover only WARNS' + the spool-join triage piece (2))

Not built yet. print_deduct.py:_record_applied_deduct (:455-491) records the ledger (:483) before it computes the shortfall (:485), and only logs a WARNING (:486-490). deduct_completed_print auto-applies and then calls it (:921-948). config_schema.py has no shortfall_review_min_g. The open question is live in code: _rows_from_charges (:1739-1741) refuses an archived redirect or no_spool pick with "Charging an archived spool is still an open question." A kept archived row passes (`kept`) and goes to the clamp, which matches the CLAUDE.md api_cancel_deduct_confirm row. Option A's rule already exists: _deduct_payload (:294-301) sends archived: True for an archived spool, so a charge never un-archives it; it is used by the auto-deduct (:390) and by the confirm loop (:2019). The clamp: the confirm loop caps grams at the spool's remaining (:2004-2013), a spool at 0 g records 0 g ("Spool already empty", :2014-2017), and the job's shortfall_g plus a WARNING report the rest (:2113-2122). spoolman_api._auto_archive_on_empty (:192-263), at remaining ≤ 0, archives the spool, sets its location to '' (UNASSIGNED), saves fcc_pre_archive_location and clears container_slot/physical_source. _auto_unarchive_on_refill (:266-311) un-archives when a write leaves remaining > 0 and restores the saved location. update_spool (:341-370) logs both. Two spools on one head: select_deduct_targets (spoolman_api.py:1550-1591) returns ambiguous, and _apply_usage_to_printer skips that head with a WARNING (print_deduct.py:358-366). Frontend: the "On this printer's heads now" group hides archived spools (cancel_review.js:105), and a typed archived #id shows "is archived — pick another spool" (:596-597). The "When FCC logged the print" group (:84-86) doesn't filter archived spools; the server refuses them at Apply. The job 1104 numbers come from the 2026-10-08 read-only triage of prod's ledger (buglist spool-join item; 43-deduct-recovery.md "Read this first"); I did not re-read prod. Stale or loose wording: the handoff's "Picking an archived spool charges it anyway" reads as if #99 could absorb the 27.12 g, but the clamp stops at 0 g. Also, by the time a shortfall card is stashed, the auto-archive has already moved #99 off RCOI-1, so a heads snapshot taken after the deduct won't show it; the card's suggested spool must come from the deduct's own details. Today's merges (the spool picker a3533b4, every-head-kept 795529c) didn't change the question: the uncharged-head picks go through the same archived refusal.
Second pass: the code claims re-read and hold (exact refusal text at print_deduct.py:1740-1741; the ~1.0 g threshold is 43-deduct-recovery.md:84; Derek's 'joined (T1 to T2)' is Feature-Buglist.md:88). Corrected: 'charges 0 g under every option' (the refuse option charges nothing because it refuses); option 3 no longer calls itself plainly the safest, because its weigh-first route runs today's un-archive rule, which restores fcc_pre_archive_location even onto an occupied head, the same catch as option 2, until the planned occupancy redirect (42-single-slot-box-lifecycle.md 42.3c) lands.

</details>

### Delete the blank-ID 'TestCart' location you made to reproduce the blank-ID bug

_(needs your OK)_

**What it is.** In August you found that FCC accepted a location with an empty Location ID, then got stuck with 'already exists' when you tried to fix it. Your reproduction case is still in dev's location list: a cart named TestCart with no Location ID. That bug is now fixed. A blank ID is refused on save, the editor won't open a blank row (it tells you to delete it and add it again), and 🗑️ on that row now actually deletes it. The row is the only cause of the two test failures that turn up in every run. One test checks that every location has an ID. The other is a location-picker test that selects the first location after 'Unassigned'; the blank row sorts first and shares Unassigned's empty value. Deleting the row clears both, so every red in a test run means something again.

**Where you'd see it.** Dev's Location Manager location list: a 'TestCart' cart under CR (the computer room) with an empty ID. Prod is unaffected. Prod has its own, separate blank-ID row called 'Unknown Location', which this doesn't touch.

**Example.** Location Manager → the TestCart row's 🗑️ → 'Delete the location with a blank Location ID ("TestCart")?' → Yes, and only that row goes. Your other test carts stay: CR-TC-1, also named 'TestCart' (probably the copy the bug made when you tried to give the blank row an ID), with its row CR-TC-R1, and CR-TC-2 with rows R1 to R3. No spool is touched. This delete deliberately skips the usual 'unassign everything inside it' step: an empty location is how Spoolman spells 'Unassigned', so that step could otherwise reach every unassigned spool.

**Options:**

- **Let Claude delete it now through the app (recommended).** I send the same request the 🗑️ button sends, on dev only, while no test run is going. You do nothing, and the two standing failures disappear from the next run. A delete has no Undo, and a blank row can no longer be created through the app (that's the fix).
- **Delete it yourself with the 🗑️ button.** Same result. It also covers the 'delete dev's TestCart row' manual check in the handoff, though an automated test already pins that prompt.
- **Keep it.** Every test run keeps carrying the same two known failures.

**My recommendation.** Let me delete it through the app's own delete path. You said you'd rather lean on me for things I can handle; this touches no spools, and the button's prompt is already covered by an automated test, so the manual check adds little. If CR-TC-1 was only part of the repro too, say so and I'll remove that the same way.

**If you don't answer.** The row stays (the docs say to leave it until you decide), and the two standing failures stay in every run.

<details><summary>What was checked (for the next session)</summary>

Internal ref: Handoff Q15 / Group 46.5 follow-up (dev blank-LocationID 'TestCart' row; formerly 37.1)

Dev inventory-hub/data/locations.json row 0 = {"LocationID": "", "Name": "TestCart", "Type": "Cart", "Max Spools": "0", "parent_id": "CR"}. A second row, CR-TC-1, also named 'TestCart' (otherwise identical; child row CR-TC-R1), is mentioned in no doc. It matches the bug's documented effect ('giving the blank row a real id appends a second row', docs/agent_docs/tasks/46-quick-fix-sweep-2026-10.md). tests/test_locations_json_integrity.py:95-102 test_every_row_is_a_dict_with_LocationID_and_Type fails on row 0; it reads the real dev file and runs under --offline. tests/test_wizard_group10_session_a.py:61-76 and :127-143 select option index 1, which is the blank row. The delete path is routes_locations.py:509-546 _delete_blank_id_rows (DELETE /api/locations?blank_id=1): it removes every blank-ID row under the write lock, logs to the Activity Log, and deliberately makes no Spoolman call. That is pinned by tests/test_blank_location_id.py (_no_spoolman fails on any Spoolman call). The frontend prompt is built at static/js/modules/inv_loc_mgr.js:2426-2433 and pinned with a faked answer by test_loc_editor_enter_to_save_e2e.py:303. The rooms CR, DR and LR have parent_id null (top level), and nothing is parented under the blank row. Feature-Buglist.md:273 and the overnight plan say not to delete the row without asking, hence the question. The only change to routes_locations.py in the recent merges is the blank-ID fix itself (0d2cd8d).
Second pass: re-read the delete path, both standing-red tests (the wizard's '-- Unassigned --' option has value '' like the blank row, inv_wizard.js:1523), and the prompt test. All hold. Corrected only a detail here: the rooms' parent_id is null in dev's file, not "".

</details>

### Stop three tests from temporarily rewiring your real dev dryer boxes

_(needs your OK)_

**What it is.** Some automated tests need a dryer-box slot that feeds a toolhead. Three of them 'borrow' your real dev boxes: they change a box's slot → toolhead bindings for the length of the test, then write back whatever they saw at the start. If a run is killed partway through, the temporary setting stays. Every later run then 'restores' that leftover as if it were yours. A run was killed like that at 03:18 in the overnight run, when a broken command started the whole suite (that time it left nothing behind). A stray PM-DB-1 slot 1 → XL-1 binding that sat on dev until September was most likely left this way, though that was never proven. Most tests already use a safe pattern. Only boxes on a short list can be borrowed. A test refuses to start unless the box is in its known starting state, and it always puts back that known state, never whatever it saw. Three tests still use the old pattern:
1. The Printer Pool test borrows TST-MDB-1. The Printer Pool is the '🏭 Printer Pool' row in the Quick-Swap grid (the tiles you get when you open a toolhead): box slots set aside as staging for a whole printer rather than one head.
2. A shared helper behind seven Quick-Swap overlay tests hunts through your boxes for the first slot holding a spool and, if needed, binds it to a toolhead for the test. On dev that can mean CR-MDB-1, LR-MDB-1 or LR-MDB-2.
3. One Printer Status test wipes the bindings on every dryer box, including your LR-MDB-1 and LR-MDB-2 setup, to check how the bar looks with nothing bound, then writes them back.
Two answers unlock the fix. Was TST-MDB-1's old 'slot 1 → the whole XL' (PRINTER:XL) binding deliberate? And may the Printer Status test use made-up data instead of wiping your boxes?

**Where you'd see it.** Nothing changes in the app. What changes on dev: test runs stop rewiring your boxes, even for a few seconds, and an interrupted run can no longer leave LR-MDB-1, LR-MDB-2 or CR-MDB-1 with wrong or missing bindings.

**Example.** On dev, TST-MDB-1 had slot 1 → PRINTER:XL from at least early June (the oldest copy on disk) until the 2026-10-08 copy from prod, which brought it in empty, so your live setup very likely has it empty too. It has been empty on dev since then, and nothing has broken. The old value now survives only in the saved reset snapshot, so running reset-dev would put it back and add a TST-MDB-1 tile to the XL's Printer Pool row on dev.

**Options:**

- **TST-MDB-1 is just a test box, and the Printer Status test uses made-up data (recommended).** No change to your dev data. TST-MDB-1 joins the list of boxes tests may borrow, with 'empty' (what dev has today) as its starting state, and the reset snapshot's leftover binding is dropped. The shared Quick-Swap helper uses a test box holding one of the virtual dev spools instead of hunting through your real boxes. The Printer Status test feeds the bar a made-up 'nothing is bound' answer, as its two neighbouring tests already do.
- **The TST-MDB-1 pool binding was deliberate; keep it.** Slot 1 → PRINTER:XL becomes TST-MDB-1's protected starting state, so I'd write it back onto dev (an edit to your dev locations). TST-MDB-1 slot 1 shows up in the XL's Printer Pool row on dev again.
- **Keep the Printer Status test on real data, checked against a recorded copy of every box.** The test still wipes all your dev boxes for a few seconds, but only when each one matches a recorded copy, and it writes the recorded copy back. Whenever you rebind a dev box by hand, the test refuses to run until someone updates the copy.
- **Leave all three as they are.** Nothing changes, and the risk stays that an interrupted run makes a temporary binding on your real dev boxes permanent.

**My recommendation.** Treat TST-MDB-1 as a test box and give the Printer Status test made-up data. The box came from your original spreadsheet as 'Test Filament Dryer', the one test that uses it calls it 'baseline-empty', the 2026-10-08 copy of your live setup brought it in empty, dev has had it empty since, and the server half of the Printer Status check is already tested without touching dev. The same answer also unblocks the Feeds test in the previous question.

**If you don't answer.** Nothing is built until you answer, and the three tests keep borrowing your real dev boxes.

<details><summary>What was checked (for the next session)</summary>

Internal ref: Handoff Q13 / Group 45.5 (dev-data borrowers: test_quickswap_printer_pool.pool_binding, conftest.bound_loaded_slot, test_printer_status_widget::test_widget_shows_unbound_printers_with_placeholder)

tests/test_quickswap_printer_pool.py:16-40: pool_binding writes {"1":"XL-1","4":"PRINTER:XL"} to TST-MDB-1 and PUTs back the observed snapshot; its comment says "baseline-empty bindings". tests/conftest.py:539-621 bound_loaded_slot sorts /api/dryer_boxes/slots, takes the first box with a slotted spool, binds a non-toolhead slot to real_toolheads[0], and restores the observed original. It is used by 7 tests: 4 in test_quickswap_ui_e2e.py, 2 in test_quickswap_visual.py, 1 in test_return_text_and_overlay_close.py. tests/test_printer_status_widget.py:158-236 clears every box and restores the observed bindings in finally; it is the only allowlist entry in tests/test_box_binding_loans.py:260-266. Neighbouring tests already inject payloads through window.refreshPrinterStatusWidgetFromAggregate (test_printer_status_widget.py:239-322). The server half (rows for unbound printers; the unbound flag independent of occupancy) is pinned hermetically by tests/test_printer_status_box_bounding.py against routes_state_pulse.py:302 _pulse_section_printer_status. TST-MDB-1 history from the dev backups in inventory-hub/data/: {"1":"PRINTER:XL"} in the 06-04, 06-10 and 10-01 files; {} from the 2026-10-08 copy onward and today. The seed (setup-and-rebuild/seeds/locations-seed.json, captured 2026-06-02 in efc82fd) still holds it. TST-MDB-1 appears in Derek's original import, 'inventory-hub/3D Print Supplies - Locations_BACKUP.csv' line 51. The Feeds printer-sentinel test always used PM-DB-1, so it is not the source; the repo can't say who set the binding. Stale docs: Feature-Buglist.md:219 says both the seed and dev hold {"1": "PRINTER:XL"} (dev no longer does), and docs/agent_docs/tasks/40-slot-picker.md:63/186/278 still use TST-MDB-1 1 → PRINTER:XL as dev topology. Dev today: LR-MDB-1 {1:XL-1, 2:XL-2, 3:XL-3, 4:PRINTER:XL}, LR-MDB-2 {1:XL-4, 2:XL-5}, CR-MDB-1 {}. None of these files changed in today's merges.
Second pass: the test and fixture claims re-read and hold. Corrected: (1) the 03:18 killed run left nothing behind (session-handoff-2026-10-13.md:136-141), now said; (2) the September PM-DB-1 → XL-1 leftover was never proven to be test residue (open-decisions-2026-09-13.md:102-106 lists a second possible cause), so 'this way' became 'most likely'; (3) 'from at least May' had no evidence (the oldest copies are the 2026-06-02 seed and the 06-04 backup); (4) added that locations.json.pre-cart-restore-20261008-164132.bak, written straight after the copy from prod, already reads TST-MDB-1 {}, so prod's own box was very likely empty then (prod itself couldn't be re-read: this session's permission check refused it).

</details>

### Let the 'some slots bound, some left empty' Feeds test actually run

_(needs your OK)_

**What it is.** One browser test has never actually run. It checks a case you asked for, in the Feeds editor. That's the 'Slot → Toolhead Feeds' section of the Location Manager, the window that opens on a location, where you choose which toolhead each dryer-box slot feeds. The test saves a box with slot 1 feeding a toolhead and slot 2 left empty, then confirms slot 2 is stored as 'not feeding anything'. It uses dev's PM-DB-1, a one-slot PolyDryer, so it finds only one slot and skips itself on every run. The server side of the same rule is already tested without a browser; only the browser half is missing. The filed fix is to turn dev's PM-DB-1 into a 2-slot box. Having read the code, I'd rather point this one test at TST-MDB-1, the 6-slot 'Test Filament Dryer' from your original spreadsheet. Its bindings on dev have been empty since 2026-10-08, so that route doesn't touch your dev data. It does depend on the next question: whether TST-MDB-1's old binding meant anything.

**Where you'd see it.** Nowhere in normal use; it's a test that quietly skips. Only the widening route would show anything: PM-DB-1 with two slots in dev's Location Manager.

**Example.** Dev's dryer boxes today: LR-MDB-1 (4 slots feeding XL-1, XL-2, XL-3 and the XL pool), LR-MDB-2 (2 slots feeding XL-4 and XL-5), CR-MDB-1 (4 slots, nothing bound), ten one-slot PolyDryers PM-DB-1 to PM-DB-10, and TST-MDB-1 (6 slots, nothing bound). On TST-MDB-1 the test would set slot 1 → XL-1 and leave slot 2 empty, save, check that slot 2 came back unassigned, then set the box back to empty.

**Options:**

- **Point the test at TST-MDB-1, the existing 6-slot test box (recommended).** Nothing changes in your dev locations, and the test starts running. TST-MDB-1 joins the short list of boxes tests may borrow, with 'empty' as its starting state: a test refuses to start unless the box is empty, and always sets it back to empty afterwards. The only other change is in a repo file: the saved reset snapshot loses its stale TST-MDB-1 binding.
- **Widen dev's PM-DB-1 to 2 slots (the filed plan).** PM-DB-1 shows two slots in dev. FCC automatically binds a one-slot box to whichever toolhead its spool is loaded onto (the PolyDryer behaviour), so PM-DB-1 would stop doing that in dev. The screenshot test of PM-DB-1's Feeds section needs re-capturing, seven other test files that borrow PM-DB-1 slot 1 would see an extra empty slot, and the reset snapshot has to change too.
- **Leave it skipped.** Nothing changes, and the browser side of the 'some bound, some empty' case stays untested.

**My recommendation.** Point the test at TST-MDB-1: it's already a multi-slot test box, it needs no edit to your dev data, and PM-DB-1 keeps behaving like the real PolyDryer it stands for. If the next question shows TST-MDB-1's old binding was deliberate, I'd fall back to widening PM-DB-1.

**If you don't answer.** Nothing is built until you answer, and the test keeps skipping.

<details><summary>What was checked (for the next session)</summary>

Internal ref: Handoff Q12 / Group 45.4 (test_feeds_section_save_with_some_slots_none permanently skipped; PM-DB-1 Max Spools 1)

tests/test_loc_mgr_bindings_ui_e2e.py:14 has TEST_BOX = "PM-DB-1" (git history shows it always has), and :76-83 skips when fewer than 2 select.feeds-select elements render. Dev inventory-hub/data/locations.json: PM-DB-1 has Max Spools "1", Device Type "Single", slot_targets {}; TST-MDB-1 has Max Spools "6", slot_targets {}. PM-DB-1 is already in DEV_BOX_BINDING_BASELINES (tests/conftest.py:392-397), so the filed 'register it' step is already done and only the slot count would change. locations_db._is_single_slot_dryer_box (locations_db.py:1877) treats Max Spools <= 1 as an auto-managed single-slot box (auto-attach/detach, tests/test_l271_single_slot_autoattach.py:1-6), so widening changes PM-DB-1's behaviour in dev. Live tests that borrow PM-DB-1: test_contrast_guard, test_feeds_section_visual (screenshots PM-DB-1's Feeds section), test_loc_mgr_bindings_api_e2e, test_printer_status_widget, test_quickswap_ui_e2e, test_return_and_breadcrumb, test_bind_slot_picker. tests/test_box_binding_loans.py:229 pins each baseline box's bindings (not its slot count) to setup-and-rebuild/seeds/locations-seed.json. Either route therefore edits that seed: widening PM-DB-1 there, or clearing TST-MDB-1's stale {"1": "PRINTER:XL"}. The server accepts a mix of bound and empty slots (tests/test_dryer_bindings.py:169). Stale doc: Feature-Buglist.md:118 lists TST-MDB-1 among boxes that 'carry Derek's real bindings'. That was true of the seed and of dev before 2026-10-08; dev's copy has been empty since. None of these files changed in today's merges.
Second pass: re-read the test, the baselines dict, the seed (TST-MDB-1 Max 6 with {"1": "PRINTER:XL"}; PM-DB-1 {}), and the seven borrowing files (each sets TEST_BOX = "PM-DB-1"). All hold; no changes. The recommendation departs from the filed plan with its reason stated, which the code supports.

</details>

## I'll decide these unless you object

Calls I can make myself (you asked me to lean on that); listed so you can veto any of them.

### The box you scanned is full: what should the slot chooser offer?

_(Claude can decide)_

**What it is.** This is about the same planned slot chooser, which isn't built yet. It is a pop-up that opens when you put a spool into a multi-slot dryer box without naming a slot. That happens when you scan the box's own label (LOC:LR-MDB-1, not a per-slot label) or use Force Location (the override in a spool's details that puts it somewhere directly). The chooser shows each slot, what's in it, which toolhead it feeds, and a star on the recommended slot.

The open part is what it offers when every slot already holds a spool. Today FCC silently drops the spool into a full box with no slot, and the box shows 5/4, the count you said reads as 'what went wrong'. The Location Manager (the window that opens on a location and lists its slots) already handles this case: tap a full slot while carrying a spool and it asks 'swap or overwrite?'.

**Where you'd see it.** Scanning a full multi-slot box's own label while carrying a spool, or using Force Location to put a spool into a full multi-slot box. Slot labels and toolhead QRs aren't affected, because they already name the slot.

**Example.** All four slots of LR-MDB-1 hold spools. Slots 1 to 3 feed XL-1 to XL-3; slot 4 is the XL's Printer Pool, staging that never loads a head. You carry #160 and scan LOC:LR-MDB-1.
- (a) The chooser shows the box as full, with no star. You tap slot 4 (or scan its label) and get 'swap or overwrite?'. With Swap, #160 takes slot 4 and slot 4's old spool goes into your buffer, ready to scan somewhere else. Picking slot 1 instead would also load #160 onto XL-1 and unload what XL-1 is running; the planned load question comes up only if the XL is printing or XL-1 is being fed from somewhere else (a PolyDryer, say).
- (b) The same, plus a dimmed 'Store without a slot' tile. It drops #160 in loose after warning that the box will read 5/4.
- (c) FCC says 'LR-MDB-1 is full — take a spool out first', and #160 stays in your buffer.
- Today: #160 goes in loose and the box shows 5/4.

**Options:**

- **(a) Same as the Location Manager grid (recommended).** You get the 'swap or overwrite?' question you already know.
- Swap: the new spool takes the slot and the old one goes into your buffer. FCC keeps listing the old spool in the box, with no slot, until you scan it somewhere.
- Overwrite: the new spool takes the slot and the old one stays in the box with no slot.
Either way, the incoming spool always gets a slot.
- **(b) Grid choices plus 'Store without a slot'.** Everything in (a), plus a deliberate way to drop the new spool in loose, after a warning that the box will read 5/4.
- **(c) Refuse.** Nothing moves. FCC says the box is full and the spool stays in your buffer. You open the box and take a spool out first.

**My recommendation.** (a): it reuses the question you already answer in the Location Manager, and the incoming spool never goes in without a slot; you only get a loose spool if you choose Overwrite. Claude can make this call: it is the documented default and adds nothing new.

**If you don't answer.** (a) is built (the documented default).

<details><summary>What was checked (for the next session)</summary>

Internal ref: Group 40 Q2, handoff Question 7 (docs/agent_docs/tasks/40-slot-picker.md, 'Open questions' Q2; shapes 40.2 and 40.4)

Read on dev after c389e26.
- inventory-hub/static/js/modules/inv_loc_mgr.js:1254-1301 handleSlotInteraction: carrying a spool and tapping a full slot asks 'Slot Occupied — Put #N into Slot S: swap or overwrite?' (:1269-1285; the task file's :1212-1228 has drifted).
- Swap and Overwrite send the same /api/manage_contents add with the slot (_doAssignFinalize :1411-1453, then routes_scan.py:389-401). Swap only adds the displaced spool to the buffer after success (:1490-1498).
- inventory-hub/logic.py:997-1021: the engine clears the old occupant's container_slot and leaves its location as the box. That is what Overwrite leaves, and what Swap leaves until the displaced spool is placed. So the task file's '(a) … no unslotted option is offered' is true for the incoming spool only.
- Today's path: Force Location's payload has no slot (inv_details.js:1217-1224), and a box-label scan sends slot null. With every slot taken, auto-slot finds nothing (logic.py:858-882), and the dryer branch (:1100-1118) writes the spool in loose.
- logic.py:1148-1177: a slot wired to a toolhead chains the spool onto it, and a PRINTER: pool slot never deploys (:1173-1176).
- The merge didn't touch any of this, so the question is still open.
Stale: the task file's worked example uses CR-MDB-1 slot 1 → CORE1. Dev's CR-MDB-1 has no bindings and CORE1 is now RCOI, so this brief uses LR-MDB-1 (1→XL-1, 2→XL-2, 3→XL-3, 4→PRINTER:XL), read-only from inventory-hub/data/locations.json.
Second pass: the code claims re-read and hold; auto-slot treats a deployed spool's slot as taken because the matcher reports its saved slot (spoolman_api.py _build_location_match, :1455-1528). Corrected the example's 'so the usual load questions come first': on an idle printer, loading the swapped-in spool onto XL-1 asks nothing today, and the planned load prompt (40-slot-picker.md 40.0c / 40.3) fires only when the printer is printing or the head is fed from somewhere else.

</details>

### Remember where a spool sat before it went into a PolyDryer, so ejecting it out of the box sends it back there

_(Claude can decide)_

**What it is.** A PolyDryer is Polymaker's one-spool heated dryer. In FCC each one is a Dryer Box location with room for one spool (PM-DB-1 to PM-DB-10).
- A multi-slot box like LR-MDB-1 has its slots wired to toolheads by hand in the Feeds editor (the slot-to-toolhead wiring section of the Location Manager, the window that opens on a location and lists its slots), and that wiring never changes on its own.
- A PolyDryer is wired automatically. When you load its spool onto a toolhead, FCC 'attaches' the PolyDryer to that head, meaning it records that the dryer now feeds it. FCC also remembers the PolyDryer as the spool's home, so ⏏️ Eject puts the spool back into it.

You already decided that the PolyDryer 'follows its spool'. When that spool moves from one toolhead straight to another, the PolyDryer lets go of the old head and attaches to the new one, and the spool keeps the PolyDryer as its home. Physically, you carry the dryer along with the spool.

You added a condition: FCC shouldn't forget where the spool was before it went into the PolyDryer (a cart, say), so that unloading it from the box can send it back there. Today it can't. Each spool has a single 'home' note. FCC writes it when the spool goes onto a toolhead and wipes it the moment the spool lands anywhere else. So the cart is lost as soon as the spool goes into the PolyDryer, even if it never leaves the box, and ejecting it out of the PolyDryer just asks 'unassign?'.

The question: how should FCC keep that second place?

**Where you'd see it.** Ejecting a spool that sits in a PolyDryer (⏏️ Eject on its card, or eject mode and then scanning the spool). This is also the last thing holding up 'the PolyDryer follows its spool between toolheads', e.g. picking a PolyDryer-fed spool up from one XL head and scanning another head's QR.

**Example.** #50 sits on cart CR-CT-2-R1. You put it into PolyDryer PM-DB-2 (scan #50, then PM-DB-2's label), load it onto XL-2 (scan #50, then XL-2's QR), and later move it straight to XL-4.
- With the recommended note: PM-DB-2 follows #50 to XL-4. Ejecting #50 from XL-4 puts it back in PM-DB-2. Ejecting it again, out of the dryer, puts it back on CR-CT-2-R1.
- Today: CR-CT-2-R1 is forgotten the moment #50 goes into PM-DB-2, so even straight out of the dryer, Eject asks 'unassign?'. The XL-2 → XL-4 move also loses PM-DB-2: #50's home becomes LR-MDB-2 slot 1 (the slot wired to XL-4, if it's free), and PM-DB-2 stays attached to XL-2.

**Options:**

- **1. A separate 'before the box' note (recommended).** When a spool goes into a PolyDryer, FCC writes down where it came from in a second note. FCC doesn't display it; Spoolman's own spool page lists it as one more '(system)' field, like the two FCC already keeps for archived and audit-parked spools. The note rides along onto toolheads, between them, and back into the PolyDryer. Ejecting the spool out of the PolyDryer then sends it back to that place instead of asking 'unassign?'. Moving the spool somewhere yourself drops the note. Multi-slot boxes and every other move behave exactly as today.
- **2. Remember the last cart or shelf on every move.** Every move notes the last ordinary place (cart, shelf) a spool left. Ejecting from any box, or from a toolhead the spool was loaded onto straight from a cart, can then send it back there. This reaches further and surprises more: a spool that has lived in LR-MDB-1 for months would go back to whatever cart it last sat on. It also changes every move path, which is the busiest code in FCC.
- **3. Build 'the PolyDryer follows' now, add the note later.** PolyDryer spools moved between toolheads get the follow behaviour sooner. Ejecting a spool out of a PolyDryer keeps asking 'unassign?' until the note is added. The two pieces don't depend on each other in the code, so splitting them is safe; spools that went into a PolyDryer before the note existed simply won't have one.

**My recommendation.** Option 1, built together with the follow behaviour: it does exactly what you asked and nothing more, using the same kind of one-job note FCC already keeps for auto-archived and audit-parked spools. Claude can make this call unless you also want multi-slot boxes, or spools loaded straight from a cart, to remember their cart.

**If you don't answer.** There's no documented default for the note itself. Until it's settled, the 'PolyDryer follows its spool' step waits, and the rest of the PolyDryer work (queued behind the work that makes bulk actions report honestly anyway) is built with the task file's fallback, 'release only': a move between toolheads lets the PolyDryer go from the old head without attaching it to the new one (today it doesn't even let go). Ejecting a spool out of a PolyDryer keeps asking 'unassign?'.

<details><summary>What was checked (for the next session)</summary>

Internal ref: Group 42 Q-A caveat, handoff Question 5; blocks 42.6 (head→head: the single-slot box follows its spool). Sources: 42-single-slot-box-lifecycle.md Q-A (:563-578) and 42.6 (:391-403); open-decisions-2026-09-13.md:134-140

Read on dev after c389e26.
- inventory-hub/logic.py:1100-1118 (dryer branch): entering any Dryer Box writes physical_source '' (the generic branch :1120-1144 does the same for shelves and carts). So the pre-box place is lost at box entry, not later.
- logic.py:553-569 _ghost_trail_from plus PRINTER MOVE :1023-1076: a head-to-head move starts with no trail. The reverse-binding fallback (_find_box_slot_feeding_toolhead :252-281) then records the new head's first free wired slot (LR-MDB-2:1 for XL-4 on dev).
- The attach (:1083-1088) is a no-op when the spool comes from a head. No move detaches; only perform_smart_eject does (:2142-2158), keyed on the toolhead.
- logic.py:2029-2100 _eject_destination: a spool sitting in PM-DB-2 has no saved home, and get_room_from_location (:2005-2027) returns '' for the PM pseudo-room (locations_db.py:641). That sets needs_unassign_confirm, i.e. the 'unassign?' prompt; open-decisions-2026-09-13.md:131 calls it 'the prompt a PolyDryer spool already gets'.
- inventory-hub/spoolman_api.py:511-522: SYSTEM_MANAGED_EXTRAS already holds two one-job breadcrumbs (fcc_pre_archive_location, fcc_pre_audit_location), registered in setup-and-rebuild/setup_fields.py:322-334. A 'before the box' note would add one more entry to each, i.e. one new empty text field on every spool in Spoolman's own page, prod included.
- logic.py:995 copies the whole extra dict, so a new key rides through every move branch untouched. That is why option 3's split is clean.
- locations_db.py:1877-1890 _is_single_slot_dryer_box (a Dryer Box with Max Spools ≤ 1); attach is at :1893-1929.
- Dev inventory-hub/data/locations.json: PM-DB-1..PM-DB-10 (the task file says 1..8), each a Dryer Box with Max 1, parent PM, and no bindings at rest.
- The merge changed none of this, so the question is still open. No doc expands the recommendation beyond session-handoff-2026-10-13.md:178-184.
Details Claude would settle without asking: never remember a bare Room or Unassigned (matching Derek's 'no new Room-only spools' answer), and fall back to today's prompt if the remembered place has since been deleted.
Second pass: the code claims re-read and hold, including the claimed-slot check that keeps the reverse-binding off an occupied slot (logic.py:1054-1075). Corrected: (1) 'hidden note' — the existing breadcrumbs are registered as visible Spoolman extra fields ('Pre-Archive Location (system)', 'Pre-Audit Location (system)'), so a third would show on Spoolman's spool page too; (2) if_unanswered — 42-single-slot-box-lifecycle.md:397 gives the head-to-head step a fallback ('Default until answered: release only'), so the brief now says what gets built meanwhile; (3) the Location Manager is explained where the Feeds editor first appears. decision_type kept: Derek already stated the behaviour (open-decisions-2026-09-13.md:136), and option 1 implements exactly that.

</details>

### Bulk Move's "source is printing" warning can never appear. Remove it?

_(Claude can decide)_

**What it is.** Bulk Move moves everything from one location to another in one go. You open a location in the Location Manager (the window that opens on a location and lists its slots and spools) and press 🔀 Move all →, or scan the BULK MOVE QR and then the location you're emptying; either way you then scan where it all goes. It is switched off on your live FCC (⚙️ Settings → Behavior → Enable Bulk Moves) and switched on only in dev.

Bulk Move never moves a spool that is loaded on a toolhead. A spool on a head, or a box spool currently feeding one, is listed as "left in place". Bulk Move also has a separate warning, meant for when the location you are emptying is itself a toolhead on a printer that is printing. That warning is checked only after the loaded spools have been set aside, so by the time it runs there is nothing left to move, and it never shows.

On both your live and dev data, every toolhead ID has a dash in it (XL-1 to XL-5, RCOI-1 to RCOI-8). For an ID like that, FCC only ever finds spools that Bulk Move already refuses, so the warning cannot appear. Its only tests pretend a dryer box is printing, which the real printer check never reports.

**Where you'd see it.** Nowhere today, which is the problem. If it could fire, it would be a yellow "⚠️ ACTIVE PRINT" strip in the Bulk Move preview panel, with an "I understand a print is active — move anyway" tick box. You reach Bulk Move from 🔀 Move all → in the Location Manager's title bar (hidden on toolheads and printers), or from the BULK MOVE deck tile or a CMD:BULKMOVE scan. Dev only.

**Example.** The XL is printing, and you bulk-move LR-MDB-1 (your 4-slot living-room dryer box) into the drawer LR-SD-1. The spools in slots 1–3 are feeding XL-1 to XL-3, so the preview lists them as "left in place: deployed to a live toolhead". Slot 4's XL spare moves, and nothing asks, because nothing feeding the print moves. You can't start a bulk move from XL-3 with the button, and if you scan XL-3 as the source you get "Nothing to move from XL-3 (1 left in place)". To take a loaded spool off a printing head you use a normal single move, which since today's update asks first: "#42 is loaded on XL-3. Moving it to CR-CT-2-R1 means FCC stops charging this print to it. Continue?"

**Options:**

- **A. Remove it (recommended).** Nothing you'd notice. The warning that can't fire, its tick-box strip in the panel, and the two tests that fake a printing dryer box are deleted. Bulk Move still never moves a loaded spool, and taking a spool off a printing head is still a single move that asks first.
- **B. Make it cover box slots wired to a printing head.** Bulk-moving a box such as LR-MDB-1 while the XL prints would show the yellow strip, and you'd need to tick the box, whenever a slot wired to XL-1, XL-2 or XL-3 holds a spool other than the one on the head (say a spare in slot 2 while XL-2 runs off a PolyDryer). That spare isn't feeding the print, so the warning only matters when FCC's records disagree with the printer. The panel already shows a blue note for this case ("This move empties a slot wired to XL-2 … The wiring stays"), without asking.
- **C. Leave it.** Nothing changes. The dead check and its fake tests stay, and anyone reading the code keeps believing Bulk Move has a mid-print prompt that can never show.

**My recommendation.** A. The warning has never been able to appear on your live or dev data, Bulk Move already refuses loaded spools, and a real mid-print move off a head now asks through the normal single move. I'd count this as housekeeping I can decide myself, because A changes nothing you'd see; B adds a prompt for spools that don't affect the print, in a feature you've said you'll rarely use.

**If you don't answer.** There is no documented default. Nothing is built until you answer, so the dead check stays (in effect option C). It holds up only this one cleanup, not the rest of the work on honest bulk results.

<details><summary>What was checked (for the next session)</summary>

Internal ref: Handoff Q3 = Group 41 Q3 / sub-task 41.7 (docs/agent_docs/tasks/41-honest-bulk-results.md 'Q3'; Feature-Buglist.md:167-170, the 'Bulk-move tally and slot unseat' item 3)

logic.py:plan_bulk_move (:1279-1478). The skip loop (:1382-1411) sets aside ghosts as 'deployed to a live toolhead' (:1391-1393), plus every spool whose own location is a printer_map key or a Tool Head / MMU Slot / No MMU Direct Load / Printer row (:1403-1410). The source-print check (pre-flight 4, :1452-1470) runs only after that, and probes only the source id. logic.py:_active_print_info_for_location (:13-49) answers only for a printer_map key. The matcher, spoolman_api.py:_build_location_match (:1455-1528) with locations_db.location_prefix (:584-606), adds first-segment matches only for a dash-less target, so a dashed head id matches exactly plus ghosts, and both are skipped.

Read-only check of prod's locations.json on the TrueNAS share and dev's inventory-hub/data/locations.json (2026-10-13): printer_map keys are XL-1..XL-5 and RCOI-1..RCOI-8 on both. Neither has a dash-less head or a CORE1 row. The check could fire only with a dash-less head id that is also the first segment of another location holding spools (e.g. an old-style CORE1 plus a CORE1-SHELF).

The fake tests are tests/test_bulk_move.py:376-387 and :390-400, which patch the probe to call box PM-DB-A printing.

Flag: routes_scan.py:_bulk_moves_enabled (:463-476). /api/bulk_move has been gated since 2026-10-13 (:428-433). Dev config.json has fcc.bulkMove.enabled=true; prod config.json has no such key, so it is off. Derek, 2026-10-08 (buglist PENDING DEREK entry): 'I doubt I'll even really use it much'.

UI: Move all → is hidden on single-occupancy types (static/js/modules/inv_loc_mgr.js:84, :108). The yellow strip is inv_cmd.js:812-823, and the commit handler's confirm branch is :447-461. The blue feeds note is inv_cmd.js:824-837, fed by logic.py:_bound_feeds_for_move (:1497-1547). A scanned toolhead source is accepted (logic.py:process_bulk_move_scan :1845-1851) and then plans 'Nothing to move' (:1421-1424). Single-move source confirm wording: logic.py:_active_print_message (:154-213).

Stale in the task file:
- Line refs drifted: pre-flight 4 was :1168-1186, the test :362-386.
- Its CORE1 examples (Eject All block, check 41-c) name a row that exists on neither prod nor dev.
- Its reason to keep the bulk-move confirm plumbing under A ('a destination confirm can still come back from the engine') no longer holds. Today's confirm-on-every-door merge made execute_bulk_move call the engine with a blanket confirm_active_print=True (logic.py:1568-1577), and the engine's only confirm is logic.py:842-844. So the rest of that plumbing (routes_scan.py:444-448, logic.py:_apply_plan_to_session :1684, the panel strip) is unreachable too, and can be removed or kept as a labelled backstop.
Second pass: the code claims re-read and hold (including config_schema.py:97 'Enable Bulk Moves' under ⚙️ Behavior, and dev's repo-root config.json with fcc.bulkMove.enabled true). Corrected the BULK MOVE QR flow: after the QR you scan the source, then the destination. The prod half of the data check could not be re-confirmed: this session's permission check refused a read of the TrueNAS share. Dev's locations.json.pre-cart-restore-20261008-164132.bak, prod's configuration as copied on 2026-10-08, shows the same dashed head ids and no dash-less head.

</details>

### How Printer Status should number a toolhead: "Tool 1" or "T0"

_(Claude can decide)_

**What it is.** Printer Status is the dashboard panel with one row per printer and a coloured tile per toolhead. Today every tile, and every chip in the collapsed one-line strip, is labelled with the head's full location id: XL-1 to XL-5 on the XL row, RCOI-1 to RCOI-8 on the Core One INDX row. In your INDX setup report you asked to be able to show just the number instead: "(XL-1, vs just 1 (Or Tool 1))". The plan is a per-browser setting with three choices: the full id (today's look, which I'd keep as the default), a bare number, or a tool name. Only the visible text changes: clicking a tile still opens that head, and hovering still shows the full id. The open part is how the tool name counts. FCC stores each head's position starting from 0 (XL-1 is position 0, RCOI-8 is position 7), which is how the gcode numbers tools (T0, T1, ...). "Tool 1" counts from 1, like the head's own id and FCC's Feeds dropdown (the slot-to-toolhead picker on a dryer box, which reads "XL-1 — Toolhead 1 on 🦝 XL"). The task file says the printers' own screens count from 1 too. "T0" counts from 0, like the gcode. One gap in the plan: the collapsed strip shows no printer names, only a divider and a PRINTING/IDLE/OFFLINE badge per printer. With a short label, the XL's first head and the INDX's first head would read the same there, so the build should keep the full id in that strip or put the printer's name in front of each group.

**Where you'd see it.** The Printer Status panel on the dashboard: the name on each head's coloured tile (expanded view) and on each chip in the collapsed one-line strip. The setting would sit in the ⚙️ button's Admin / Config window, under ⚙️ Settings → 🖥️ This Browser, next to "Default weigh-in mode".

**Example.** On the INDX row, the tile that says RCOI-8 today would say "Tool 8" with "Tool 1" numbering, or "T7" with "T0" numbering: the gcode's number, but one less than the head's own name. On the XL: "Tool 1" to "Tool 5", versus "T0" to "T4", where XL-3's tile would read "T2".

**Options:**

- **"Tool 1" (counts from 1).** Tiles read Tool 1 to Tool 5 on the XL and Tool 1 to Tool 8 on the INDX. The number always matches the head's own id (XL-3 → Tool 3) and the Feeds and Quick-Swap pickers ("Toolhead 3"). The deduct review card (the 🛑 card for a print FCC couldn't charge on its own) keeps its gcode-style line labels such as "T0 · RCOI-1", so a review card numbers the same head one lower; the id printed next to it keeps that readable.
- **"T0" (counts from 0, like the gcode).** Tiles read T0 to T4 on the XL and T0 to T7 on the INDX. That matches the gcode and the review card's "T0 · RCOI-1" lines, but every tile's number is one less than the head's own name, so "T1" on the dashboard means your second head (XL-2 / RCOI-2).
- **Offer both.** The setting gets four choices (XL-1 / 1 / Tool 1 / T0) and you pick per browser. The menu is slightly bigger; nothing else changes.

**My recommendation.** "Tool 1". It's what your own setup report asked for ("XL-1, vs just 1 (Or Tool 1)"), its number always matches the head's id and FCC's Feeds dropdown, and you count heads from 1 yourself ("the bgcode directs to toolhead 1, but I've been printing from toolhead 2").

**If you don't answer.** Nothing is built until you answer. Printer Status keeps showing the full id (XL-1, RCOI-3) exactly as it does today.

<details><summary>What was checked (for the next session)</summary>

Internal ref: 46.3 (Group 46 'Toolhead label display mode'; handoff Questions for Derek #1; buglist line 'Toolhead label display mode (Derek's aside in the INDX report)')

Why agent_can_decide: Derek's original aside, kept verbatim in completed-archive.md (his 2026-09-29 INDX setup report), already says "(XL-1, vs just 1 (Or Tool 1))". T0 was added later as an alternative in triage. The change is display-only, per-browser and opt-in, with today's look as the default, so it is easy to reverse. Today's rendering: inv_printer_status.js puts `${th.id}` (the full LocationID) in the tile label at :184, :200 and :248 and in the collapsed chip at :272, :284 and :309. data-toolhead (:166) and every title attribute use th.id. `_fingerprint` (:133-153) has no label mode yet. The collapsed strip (:428-438, plus global.css :1655-1660 and :1735-1746) renders a state chip and the chips per printer group, with no printer name. Positions are 0-based: in dev data/locations.json the Printer rows have XL-1..XL-5 at 0..4 and RCOI-1..RCOI-8 at 0..7, and the INDX memory note says prod matches (prod not re-read). The Feeds dropdown says "Toolhead ${e.position + 1}" (inv_loc_mgr.js:473, :527), as does the Quick-Swap toolhead picker (inv_quickswap.js:1237). The review card already uses gcode style "T${pos} · ${toolhead}" (cancel_review.js:201, :233), and so does a deduct log tail (print_deduct.py:1162, "on T{p}"). config_schema.py:61 defines the "🖥️ This Browser" section, and :93-96 is the client-scope select pattern to copy. `git grep` finds no toolheadLabel or _thLabel, so nothing has been built. inv_printer_status.js last changed in fbdd5f7 (the 2026-09-29 hotfix), so today's merges don't affect this question. Slightly stale docs: the handoff says "Tool 1" matches the Feeds dropdown, but the dropdown actually says "Toolhead 1" (same number, different word). The printer-screen claim can't be checked from the repo. The filed plan doesn't say whether the bare number comes from the id suffix or from position+1; on both of Derek's printers they agree.
Second pass: re-read the tile/chip lines, the collapsed-strip code, the Feeds and review-card labels, the 'Admin / Config' and '⚙️ Settings' names in modals_config.html, and Derek's quote at completed-archive.md:103. All hold; no changes.

</details>

### Brighten the grey OFFLINE printer label a little so the readability test can be fixed

_(Claude can decide)_

**What it is.** FCC's test suite has a readability check that scans parts of the screen for text too faint to read against what's behind it. That's the grey-on-grey problem that keeps coming back. The check is a test helper only; you never see it. It has a blind spot: when the text colour itself is see-through (say, 45% white), it scores the text as if it were solid white, so faint text passes. Closing the blind spot takes two lines. But as soon as it's closed, the check correctly flags one real thing in the app: the OFFLINE label in the Printer Status bar measures 4.41:1, under the 4.5:1 minimum (the usual accessibility bar for normal-size text). So the check fix can't go in alone without turning the test suite red. The proposal is to land it together with a tiny style change: the OFFLINE text goes from 45% white to 50% white, which measures about 5.3:1.

**Where you'd see it.** The Printer Status bar across the top of the dashboard. Each printer has a small state label: green PRINTING, amber PAUSED, grey IDLE, red when it needs attention, and a dimmer grey OFFLINE when FCC can't reach the printer (switched off, network trouble, or no login saved). The label sits under the printer's name when the bar is expanded, and at the start of that printer's row of toolhead chips when it's collapsed. You'd see it, for example, whenever the Core One INDX is powered off.

**Example.** Today the word OFFLINE is drawn at about grey level 115 (out of 255) on a near-black chip. After the change it would be about 128. IDLE stays brighter at 60% white (about 153), so OFFLINE is still the dimmest state, and side by side the difference is hard to see. An example of what the fixed check catches that it misses today: 25%-white text on a faint white tint actually shows at 2.24:1, which is unreadable, but the check currently scores it 18.36:1 and passes it.

**Options:**

- **Fix the check and brighten OFFLINE to 50% white (recommended).** The OFFLINE label gets very slightly brighter, and nothing else in the app changes. From then on the check also catches faint see-through text on the screens it covers: the Printer Status bar, the Quick-Swap grid and its confirm box, the Feeds editor, the bind-a-slot picker and the keyboard-shortcut overlay.
- **Fix the check but give OFFLINE a permanent exception.** Nothing you'd see changes. The label stays at 4.41:1, just under the bar, and the test carries a carve-out that someone has to remember.
- **Leave both as they are.** Nothing changes. The check stays blind to see-through text, so a future faint label could pass unnoticed.

**My recommendation.** Fix the check and brighten OFFLINE to 50% white. The change is too small to notice, OFFLINE stays dimmer than IDLE, and the check can then catch the grey-on-grey text it exists to catch. I can make this call myself: it was routed to you only because style changes are normally yours, the only visible effect is a barely-there brightness bump on one label, and it goes the way of your standing 'no similar colour on similar colour' rule.

**If you don't answer.** Nothing is built until you answer. The check stays blind to see-through text, and the label stays at 45% white.

<details><summary>What was checked (for the next session)</summary>

Internal ref: Handoff Q11 / Group 45.3 (CONTRAST_GUARD_JS ignores foreground alpha; .fcc-ps-state-offline 4.41:1)

inventory-hub/tests/conftest.py:1235-1318 (CONTRAST_GUARD_JS): the offender loop scores relLum(fg.r, fg.g, fg.b) and never uses fg.a. The over() helper the fix needs is already at :1260. The comment at :1228-1231 says foreground alpha is ignored on purpose because compositing it flags the OFFLINE chip. inventory-hub/static/css/global.css:1531 `.fcc-ps-state-offline { background: rgba(0,0,0,0.35); color: rgba(255,255,255,0.45) }`; IDLE at :1529 is 0.6. The widget is a direct child of <body> (templates/dashboard.html:132; body #000 at global.css:46-47), and .fcc-ps-widget's gradient counts as transparent to the check. My recomputed figures: 0.45 gives 4.41:1 and 0.50 gives 5.28:1 (the docs' 5.29 is rounding); against the real gradient paint, about 4.44-4.50 and 5.30-5.33. Other see-through text in the widget still passes with the fix: IDLE 7.12, header hint at 0.55 6.27, material line 7.37. tests/test_contrast_guard_compositing.py renders all five state chips, OFFLINE included, against the real global.css under --offline, so the check fix alone would fail it on every run. The live widget contrast tests are test_contrast_guard.py:114 and :127. Inside modals Bootstrap text-muted is overridden to opaque #aaa (global.css:226-239), and reading the code turned up no second offender. I could not re-measure the other covered screens in a browser (read-only task). OFFLINE renders when the state probe returns null (static/js/modules/inv_printer_status.js:322-329). Neither conftest.py nor global.css has changed since e818d0c, so today's merges don't affect this.
Second pass: recomputed 4.41:1 and 5.28:1 over black, and the 2.24 vs 18.36 example matches 25% white on an 8% white tint (45-sweep-load-tolerance-test-hygiene.md:38); the covered screens are exactly test_contrast_guard.py's seven tests. Corrected a stale claim that dev always shows OFFLINE because the 2026-10-08 copy stripped the printer logins: the copy did strip them (92abc12; the 14:31 post-copy backup has empty printer_creds), but dev's locations.json has a LAN IP and API key on both XL and RCOI again (already back in the 18:47 backup). decision_type kept as agent_can_decide, with the reason now stated: it raises contrast in line with Derek's standing rule against similar-colour-on-similar-colour text (memory feedback_ui_dark_contrast_no_reflow).

</details>

## Needs a sit-down later

Design questions; nothing to answer in one word.

### What should permanently identify a printer in FCC: its display name, its Location ID, or a new hidden ID?

_(design session)_

**What it is.** Today a printer in FCC isn't one record. It's four separate things that are kept in step by habit:
1. A row in the location list with Type 'Printer' (XL, RCOI).
2. Its heads, which belong to it mainly because their IDs start with the printer's ID and a dash (XL-1…XL-5, RCOI-1…RCOI-8). Settings groups heads this way, and FCC checks a dryer-box slot's Printer Pool binding (staging for the whole printer, written PRINTER:XL) against those same ID prefixes.
3. A list of heads and their tool numbers, stored on the printer row. Print charging bills by tool number. (Charging means FCC subtracting the grams a print used from the spool on that head.)
4. Everything FCC remembers about prints, filed under the printer's display name ('🦝 XL', '🦝 Core One INDX'). That covers:
   - the tracker for the print that's running;
   - review cards waiting for you (cards where you pick which spool to charge);
   - cancels waiting to download their gcode;
   - the record of prints already charged, which stops double charges;
   - the lookup of the printer's PrusaLink login.

Nothing forces these four to agree, and some of them can't be changed after setup. The September INDX hotfix added refusals so you can't break things. You can't change the Location ID of a printer or of a listed head, you can't delete a printer that still has heads, and two printers can't share a name. Those refusals are guard rails, not a way to do the job.

The design session would decide:
- what permanently identifies a printer;
- how heads are attached and re-ordered (a head's tool number must stay the slicer's tool index);
- where the PrusaLink connection lives;
- one add/configure-printer screen, instead of half the job in Settings and half in the Location Manager;
- the one-time conversion of existing records for XL and RCOI (the retired CORE1 is still named in a hard-coded printer-to-room table);
- whether three printer features planned in June but never built are still worth building: a model field, 'MMU attached' / 'MMU-routed head' flags, and refusing a location saved without a Type.

It's paired with the location-ID question (the next brief) because both ask the same thing: does the text of an ID mean something, or is it only a label? Printers are where ID text carries the most meaning today, so the two answers need to match. The planned per-printer settings, which would be keyed by display name, also wait on this answer.

**Where you'd see it.** ⚙️ Settings → Toolheads:
- You type the printer name on every head row.
- The help text says 'A printer's toolheads share its ID prefix … Existing LocationIDs can't be renamed'.
- Printer Connections holds each printer's IP and API key.

The Location Manager (the window that opens on a location and lists what's in it):
- Saving a new Location ID for a printer or one of its heads is refused.
- '➕ Add child' isn't offered on printers.
- Deleting a printer that still has heads is refused.

The display name appears on Printer Status (the bar showing each printer and its heads), in Activity Log charge lines ('🦝 Core One INDX RCOI-2: auto-deducted 7.4g'), on print review cards and in the mid-print warnings.

**Example.** Three things that happen today with your printers:
1. When the INDX was set up, FCC put the RCOI printer at the top level, next to Living Room and Computer Room, instead of inside the Computer Room. It was fixed by hand the same day. A printer added through Settings is created with no room, and FCC's room guesser has nothing to go on for a new one: its fallback table only knows XL and the retired CORE1. The next printer you add will land outside its room the same way.
2. If you add a ninth INDX head in Settings and call it 'INDX-9' instead of 'RCOI-9', the save is refused with 'printer name … would be shared by RCOI and INDX'. FCC reads the 'INDX-' spelling as a second printer.
3. If you rename '🦝 XL' to 'Prusa XL' in the middle of a print (nothing stops this yet):
   - At the next check FCC drops what it knew about the running print and starts a new record under the new name. A spool swap or run-out from earlier in that print is no longer seen.
   - A cancel waiting to download its gcode stays filed under the old name. FCC gives up on it after 72 hours with 0 g charged.
   - Review cards filed under '🦝 XL' can no longer find the XL's heads on their own.
   On dev you can see stranded history already: the old Core One's charge records are still filed under '🦝 Core One Upgraded', a name no printer has now.

**Options:**

- **The printer's Location ID (XL, RCOI) is its permanent identity; the name is only a label.** Renaming '🦝 XL' becomes safe at any time, even mid-print. The print tracker, review cards, waiting cancels, charge history, PrusaLink login and per-printer settings all stay with the printer. FCC converts its saved records once ('🦝 XL::690' becomes 'XL::690'). A head belongs to a printer because it's listed under it, not because of its spelling, so 'INDX-9' could join RCOI. The Location ID itself stays fixed: it's printed on the QR label and stored in Spoolman, and your July rule says existing IDs never change unless you deliberately rename one. A deliberate rename would remain a rare, heavy job.
- **Give each printer a new hidden ID, separate from both its name and its Location ID.** Renames behave as in the first option, and FCC's own records would also survive a later change to the printer's Location ID. The cost is a third identifier that has to stay in step with the other two. It also doesn't make changing a head's ID cheap. Spoolman stores each spool's location as plain text ('XL-1'), so renaming heads still means rewriting every spool record that points at them, archived spools included.
- **Keep today's model and add only the missing guards.** Setting up or changing a printer stays the way your INDX report described it: half in Settings and half in the Location Manager, heads joined by their spelling, and new printers created outside their room. FCC would add a refusal to rename a printer while it's printing or has a review card open. It's the smallest change, but the 'can't change it after setup' problem stays.

**My recommendation.** The first option (the Location ID as the permanent identity), decided in the same sitting as the location-ID question. It's the printer version of the recommended location answer, where the ID is the permanent key and the tree says what belongs where. It also matches what's already keyed by ID: the Printer Connections editor, which saves each login against the printer's Location ID since the September hotfix (FCC still looks the login up by name when it checks a printer), and today's mid-print warnings, which name heads by ID. The task file doesn't pick between these options, so this choice is mine. The refusal to rename a printer mid-print can ship before the session.

**If you don't answer.** Nothing in the printer redesign gets built until you answer: no add/configure screen, no renames, no 'Add child' on printers. The task file marks one piece as safe to build now: refusing a printer rename while it's printing or has a review card open. The per-printer settings section also waits, because it was going to key settings by display name.

<details><summary>What was checked (for the next session)</summary>

Internal ref: Group 44 (44.0 design pass, covering 44.1-44.6). Decide with Group 37 fork 1; the answer also settles Group 35 G1. Handoff 'Questions for Derek' #8.

Checked read-only on dev @ d96b6ef, after today's merges. git log shows that neither the spoolman_api matcher nor the printer helpers changed in them, so the question stands as filed.

State keyed by display Name:
- print_monitor._cancel_monitor_tick (print_monitor.py:678-724) walks printers by printer_name and prunes _PRINT_TRACKER entries for names that are gone. _track_print_edge (:264+) then re-latches under the new name via setdefault, with a fresh start-spool snapshot.
- _process_pending_cancel_fetches looks the printer up by name (states.get(printer), ~:812) and gives up after 72 h with grams=0 (:673, :789-805).
- cancel_fetch_store._key (:37-38), cancel_review_store._key (:29-30) and print_deduct_ledger._key (:36-37) all build '<Name>::<job_id>'. print_tracker_store saves {printer_name: entry}.
- locations_db.get_printer_credentials (:1076-1110) matches on Name.
- print_deduct._resolve_active_locs_for_printer (:42-85) picks heads by printer_name; the dormant M0/M1 alias heuristic is at :70-85. _confirm_no_spool_review (:1773-1800) resolves through it, so a review filed under an old name answers 'still_no_spool'.
- /api/printer_map groups by Name (routes_bindings.py:160-239); its printer_rows view has been keyed by LocationID since the hotfix. /api/machine/<printer_name>/toolhead_slots is at :1037-1051.
- Today's confirms key on head ids (logic.confirmed_heads :75-87) but find the printer through its Name (logic._active_print_info_for_location :13-49). That is consistent with a LocationID answer.

Joins by spelling:
- locations_db._known_printer_prefixes (:789-798) validates PRINTER:<id> (:1792-1803).
- The toolheads[] fold groups by prefix (:973-982).
- ensure_toolhead_rows parents a new head to its prefix (:1283, :1299).
- register_toolhead_on_printer requires '<printer>-<n>' (:1349-1395).
- get_bindings_for_machine (:2083-2088).
- routes_bindings._pm_prefix (:328-332) feeds the Settings removal guard (:381-412).
- PUT /api/printer_map syncs names by prefix and refuses a shared name (:494-517). That is the 'INDX-9' refusal.
- Return's legacy '<id>-' fan-out (:684-686).
- inv_settings.js pmPrefixOf (:251-255) and its help text (:313-318); inv_quickswap.js legacy branch (:60-67).

Room:
- migrate_printers_to_rows_if_needed appends a new Printer row with parent_id None (locations_db.py:902-908). It is called from PUT /api/printer_map (routes_bindings.py:486).
- _derive_printer_room (:1442-1467) falls back to PRINTER_ROOM_OVERRIDES = {'XL':'LR','CORE1':'CR'} (:1403).
- migrate_immediate_parent_ids_if_needed then only logs a warning (:1516-1529).

Current refusals:
- routes_locations.py:355-381 (ID change on a printer with heads or on a listed head; re-typing a printer), :383-398 (shared name), :556-575 (deleting a printer with heads).
- routes_bindings.py:365-424 and :505-517.
- tests/test_indx_printer_setup_hotfix.py has 51 tests.

Not built: the short-term 'no rename while printing or with a pending review' refusal. There is no such check in routes_locations.py or routes_bindings.py.

path_filament_g is a single float in Settings today (config_schema.py:83). Its reader accepts a {printer_name: g} map (print_deduct.py:1067-1088), so name-keyed per-printer config is planned, not live.

Dev data (read-only; dev only, not prod):
- Printer rows XL (parent LR, XL-1..5) and RCOI (parent CR, RCOI-1..8), both with creds.
- LR-MDB-1 slot 4 = 'PRINTER:XL'.
- Ledger keys like '🦝 XL::690' and '🦝 Core One Upgraded::1043'; latch keys '🦝 XL' and '🦝 Core One INDX'.

Prod having XL + RCOI with CORE1 retired comes from the docs' 2026-10-12 read-only check; I did not re-read prod.

Stale in the task file: line numbers only (_derive_printer_room :1401 → :1442; PRINTER_ROOM_OVERRIDES :1362 → :1403; alias heuristic print_deduct.py:47-80 → :42-85). The substance holds.
Second pass: re-read the prune (:719-724), the 72 h give-up, the Name-based login lookup, the 'would be shared by RCOI and INDX' order (list order, routes_bindings.py:505-517), the 51 hotfix tests, and dev's ledger (51 '🦝 Core One Upgraded' entries). Corrected: (1) PRINTER:XL is the Printer Pool staging binding, not an 'any head' binding; (2) _derive_printer_room's other two arms read a 'Location' column FCC no longer writes and the heads' Location fields (44-printer-first-class.md:41-47), so a new printer falls through to the XL/CORE1 table; (3) 'Printer Connections keyed by ID' now says it's the editor's save that is keyed by LocationID, while the runtime login lookup is still by Name.

</details>

### Should a location's ID still decide what it sits inside, or should only the tree?

_(design session)_

**What it is.** Every location has a readable Location ID printed on its QR label: CR-CT-2-R1 reads 'Computer Room, Cart 2, Row 1'. Since June every location also stores its parent, the location it sits inside. The parent is what draws the Location Manager tree, adds up the totals, and works out a spool's room when you eject it.

Some places still read the structure out of the ID text instead:
- The check for 'which spools are in here?' treats a room's letters as a wildcard. Opening CR finds every spool whose location starts with 'CR-', however deep it sits. Opening a cart finds only the spools filed directly on the cart, never those in its rows. That's why a cart's total can count its rows' spools while its list is empty. You already decided the fix (a cart lists all its rows' spools, grouped by row), and it's waiting on this question.
- Clearing or deleting a room follows the same letters.
- The rule that a room clear never touches a printing head holds only by accident of naming. The XL sits in the Living Room, but 'XL-1' doesn't start with 'LR-'. A head whose ID started with 'LR-' would be swept. (Deleting a room already gets past it through each spool's 'came from' link; see the question about deleting a Room.)
- '➕ Add Location' guesses the parent from the ID you type ('Auto (derive from ID)').
- Your PolyDryers PM-DB-1…10 sit in a 'PM' group that exists only because of their first two letters.
- A start-up clean-up builds the Wall Shelf and Row levels by reading IDs like CR-WLN-R1-SC1.

You originally asked whether readable IDs are still worth it, because they're tedious to create. The recommended answer keeps every ID and label exactly as it is (your July rule: no forced relabeling) and stops reading structure from the text. The parent becomes the only source of 'what's inside what', and the ID becomes a name you scan. FCC can suggest IDs so you don't have to work them out: the ➕ on a row already pre-fills one, but it always proposes R1 and doesn't follow a parent change, and that fix waits on this answer. In June you chose to keep readable labels while the hierarchy moved to the parent; this would finish that move.

How big it is, checked in today's code: most of FCC already reads the tree. About 30 spots in the server code and 3 in the page code still read the ID text. The big piece is the one 'which spools are in here?' function. It has about 30 callers, but most of them ask about a single head or box, where nothing changes. It would split into three answers (what to show, what may be moved, what may be deleted) plus an explicit 'never touch a printing head' rule. The rest is small:
- fallbacks for spools at a location that has no row;
- the Add Location guess;
- the start-up clean-ups;
- the printer links, which belong to the printer question.

**Where you'd see it.** The Location Manager (the window that opens on a location and lists what's in it):
- Opening a cart shows only the spools filed directly on it, while its line in the list shows a total that includes its rows.
- '➕ Add Location' starts with Parent set to 'Auto (derive from ID)'.

Also affected: clearing or deleting a room, and the Bulk Move source (switched off on prod).

Scanning a LOC: label (the QR you scan to say where a spool goes) works the same under every option.

**Example.** Today:
- Open Cart 2 (CR-CT-2). Its list can be empty even though its total counts the spools in CR-CT-2-R1…R3.
- Use the Parent picker to move PolyDryer PM-DB-3 into the Living Room. The tree and the room's total both show it there, but opening the Living Room still won't list its spool, because its ID starts with 'PM'.
- On dev, CR-TC-R1 (your example of an ID that's 'hard to remember, setup and keep track of') sits under CR-TC-1 in the tree, even though its ID doesn't mention CR-TC-1.

With the recommended answer:
- CR-CT-2 lists its rows' spools, grouped by row.
- A PolyDryer or cart moved to another room shows up there everywhere, and its label stays valid.
- To add a fourth row under CR-CT-2 you pick the parent, and FCC can suggest 'CR-CT-2-R4' for you to accept or retype.

**Options:**

- **Keep every ID and label; only the tree says what's inside what (recommended).** No label gets reprinted, and every scan works as it does now. Opening a cart lists its rows' spools, grouped by row (your earlier decision, unblocked). Moving a PolyDryer or a cart to another room is just a parent change, and every list and total agrees with it. An odd or mistyped ID can't misfile anything. '➕ Add Location' asks for the parent and suggests the next ID. Clearing or deleting a room follows the tree, and an explicit 'never touch a printing head' rule replaces today's naming accident. Effort: one deep change plus small clean-ups.
- **Keep reading structure from the ID text where FCC does today.** Nothing changes in how you name or scan. The pending fixes (the cart list, easier sub-location adds, room deletes) would each be built on spelling rules, for example teaching the contents check that CR-CT-2-R1 belongs to CR-CT-2 because of how it's spelled. The tree and the spelling remain two definitions of 'inside' that can disagree, so a PolyDryer moved into the Living Room still wouldn't be listed there. The printing-head safety rule keeps depending on how heads are named.
- **Let FCC generate and maintain the IDs from the tree.** You'd never type an ID; FCC would build it from where you put the location. But moving a cart or a PolyDryer to another room would change its ID, and its QR label would need reprinting. That breaks your July rule that existing IDs never change, so this only works if you drop that rule. Generating an ID once, when a location is created, is already part of the first option.
- **Switch to hidden internal IDs, keeping today's IDs as scan names.** On the surface it's the same as the first option: labels and scans don't change. Underneath it's a model swap. Every stored reference to a location would either move to the hidden ID or keep today's text. That includes Spoolman's spool records, box-to-head feeds and the 'came from' trail on spools. Moving them means Spoolman's own screens would show the hidden IDs. Keeping the text brings you back to the first option. It's the largest effort, with no visible gain over the first option.

**My recommendation.** The first option: keep every ID and label, and let only the tree say what's inside what. The code backs the task file: the tree already drives the Location Manager, the totals and room lookups, so this is the smaller, safer change, and it finishes what you chose in June. One condition: the protection that a room clear never touches a printing head has to become an explicit rule before the contents check changes.

**If you don't answer.** Nothing in the location redesign gets built. The task file says not to start until this is settled. That keeps several things parked: the cart view you already decided on (a cart lists its rows' spools, grouped), easier sub-location adds with suggested IDs, and two smaller clean-ups (creating missing levels, and keeping ID suggestions right when a parent changes). Until then, a cart can show an empty list while its total counts its rows.

<details><summary>What was checked (for the next session)</summary>

Internal ref: Group 37 fork 1 (the LocationID model). It gates 37.3 (smart IDs), 37.4 (cart display) and forks 2-3, plus Group 34's S5 and the auto-gen-id refinement. It is also L271 recommendation #3. Handoff 'Questions for Derek' #9.

Checked read-only on dev @ d96b6ef. The matcher's last semantic change is 55be529; today's merges didn't touch it, so the question stands.

Still reading the ID text:
- location_prefix (locations_db.py:584-606) has 15 production call sites:
   - 10 in locations_db: _canonical_parent_id :321, _find_new_orphans :377, resolve_parent :632-633, _parent_of :678, migrate_parent_ids_if_needed :780, immediate_parent_for :1439, migrate_immediate_parent_ids_if_needed :1531/:1533, migrate_shelf_grouping_rows_if_needed :1759;
   - 4 in spoolman_api: _build_location_match :1491 (location) and :1499 (ghost trail), get_spools_at_location_strict :1652-1653;
   - 1 in routes_locations: the Spoolman-native synthesizer stamp, :70.
- 15 inline dash-split or startswith(id+'-') sites: locations_db ×12 (including _immediate_parent_from_rows :1416, the shelf-grouping parser :1660/:1668/:1752, and the printer helpers) and routes_bindings ×3.
- 3 frontend sites: inv_loc_mgr.js _locAutoDeriveParent :1774-1784 (the 'Auto (derive from ID)' preview), inv_settings.js :251-255, inv_quickswap.js :60-67.
- Also text rules: PSEUDO_ROOM_PREFIXES {TST, TEST, PM, PJ} (locations_db.py:641, 6 uses) and get_room_from_location's dash check (logic.py:2009-2010).

The get_spools_at_location* family has 31 production callers in 6 modules: logic 14, print_deduct 8, routes_bindings 3, routes_locations 2, routes_scan 2, routes_state_pulse 2. They include /api/get_contents (routes_locations.py:843-846) and the non-toolhead delete cascade (:620-632).

Already tree-driven:
- window.buildLocationTree (inv_core.js:936-958; parent_id only);
- the transitive rollup in /api/locations (routes_locations.py:127-176, via ancestors_of);
- resolve_room (locations_db.py:711-736), used by eject and Smart Load (logic.py:585, :2020);
- is_descendant (logic.py:1327, :2067);
- the cycle check (routes_locations.py:406-428);
- the write-time orphan guard (locations_db.py:405-423).

Tripwires that would be retired on purpose: tests/test_l271_phase5_prefix_retirement.py:303-375 pins that a room query must NOT reach a nested printer's head, and bans is_descendant( and build_parent_map( from spoolman_api.py. 19 test files reference these helpers.

Derek's 2026-06-03 call to keep readable labels while the hierarchy moves to parent_id is recorded at line 190 of the June location-model plan (refs). His 2026-07-07 rule that existing IDs are immutable, with no forced relabeling, is at lines 43-48 of the location-tree task file (refs). His 'hard to remember, setup and keep track of' remark about CR-TC-R1 is at Feature-Buglist.md:264.

Dev data (read-only): 82 rows and two printers (XL, RCOI). Only 3 rows' parent differs from what the ID text implies: CR-TC-R1 → CR-TC-1, XL → LR, RCOI → CR. PM-DB-1..10 have parent 'PM', which has no row of its own.

Stale in the docs:
- line refs: location_prefix 543-548 → 584-606; _build_location_match :1467 → :1455/:1491; /api/get_contents :648 → :843-846; the synthesizer stamp is at routes_locations.py:70, not locations_db.py:484;
- the 56-row dev topology (now 82);
- the scoping doc's diagram still shows the retired CORE1, and its list still has the three other location questions as open, though they were decided 2026-08-07.

The small interim bulk-move preview notice is still unbuilt. No tests were run and Spoolman was not read.
Second pass: counts re-checked and hold (15 location_prefix production call sites; 31 contents-reader callers when the family includes select_deduct_targets and bucket_spools_by_location; the three frontend sites). Corrected: (1) besides those 3 rows, the blank-ID TestCart row also has a parent (CR) the ID can't imply; (2) the ➕ Add-child already pre-fills an auto-generated ID (Group 34 S1-S4, 52990bd), which the text implied didn't exist; its finickiness is the refinement 34-location-tree-cluster.md:14 parks behind this question; (3) a room clear and a room delete are no longer conflated: clear_location skips ghosts (routes_scan.py:272-292), but the delete cascade reaches head spools through the ghost (physical_source) match (routes_locations.py:620-632).

</details>

## What the fact-checker corrected

- **Group 40 Q1, handoff Question 6**: what_it_is said a multi-spool box-label scan always leaves the box showing more spools than slots; it always floats them, but the count only overflows when there are more spools than slots. Option (a)'s extra question now applies to a head fed from somewhere else, matching the planned rule (the slot's own spool swaps with no prompt). Option (c)'s '5/4' wording got the same fix. decision_type changed from agent_can_decide to opinion: loop-versus-top-spool is a product behaviour, and the recommended (a) differs from the documented default (b). The old 'Claude can make this call' contradicted if_unanswered, which builds (b), so the recommendation no longer says it.
- **Group 40 Q2, handoff Question 7**: The example said picking slot 1 means 'the usual load questions come first'. Today, on an idle printer, loading the swapped-in spool onto XL-1 asks nothing. The planned load prompt fires only when the XL is printing or XL-1 is being fed from somewhere else, and the example now says that.
- **Group 42 Q-A caveat, handoff Question 5**: The Location Manager is now explained where the Feeds editor first appears. Option 1 called the note 'hidden', but FCC's two existing breadcrumbs are registered as visible '(system)' fields on Spoolman's own spool page, so a third would show there too. if_unanswered said only 'no documented default'. The task file gives the head-to-head step a fallback ('release only'), and the brief now says what gets built meanwhile.
- **Handoff Q3 = Group 41 Q3**: Fixed the BULK MOVE QR flow: after the QR you scan the location you're emptying, then the destination. The brief said you scan only where everything goes. verified now notes that this session couldn't re-confirm the prod half of the data check (the permission check refused a read of the prod share). It also notes that dev's backup taken right after the 2026-10-08 copy of prod shows the same dashed head IDs.
- **Handoff Q4 = Group 41 Q4**: Option C said a Room delete is refused 'while it still holds anything', then let loose spools on the Room become Unassigned. It now says 'while it still has locations inside it', which is the actual proposal. verified adds the same prod caveat: in the 10-08 copy RCOI had no parent, and the printer task file says it was fixed by hand that day.
- **43.2**: 'Picking the run-out spool charges 0 g under every option' became 'charges nothing under any option (0 g, or a refusal)'. Option 3 no longer calls itself plainly the safest. Its weigh-first route runs today's un-archive rule, which puts the spool back on its old toolhead even if another spool is there now, the same catch as option 2. That stays true until the planned fix lands, which sends it to the printer's room instead.
- **Group 44 (44.0 design pass)**: PRINTER:XL is now described correctly, as the Printer Pool staging binding for the whole printer (FCC checks it against the head ID prefixes). The brief had called it an 'any head of this printer' binding. The room-guesser sentence now says a new printer falls through to the fallback table that knows only XL and CORE1, because the other clues come from a Location field FCC no longer writes. The recommendation's 'Printer Connections is keyed by ID' now says it's the editor's save that is keyed by Location ID, while FCC still looks the login up by name when it checks a printer.
- **Group 37 fork 1**: The text no longer mixes up clearing a room with deleting one. A room clear skips spools that are on heads, but a room delete already reaches head spools through their 'came from' link, with a pointer to the Room-delete question. The text also implied FCC can't suggest IDs yet. In fact ➕ Add child already fills one in, but it always proposes R1 and doesn't follow a parent change, and that fix waits on this answer. verified now counts the blank-ID TestCart row as a fourth row whose parent differs from its ID text.
- **Handoff Q11 / Group 45.3**: Removed a stale claim: that dev always shows OFFLINE because the 2026-10-08 copy stripped the printer logins. The copy did strip them, but dev's locations.json has a LAN IP and API key on both XL and RCOI again (they were back by that evening's 18:47 backup). where_you_see_it now uses a powered-off Core One INDX as the example. decision_type stays agent_can_decide, and the reason is now stated: the change raises contrast, which fits Derek's standing rule against similar-colour-on-similar-colour text.
- **Handoff Q13 / Group 45.5**: The brief now says the 03:18 killed overnight run left nothing behind. The September PM-DB-1 → XL-1 leftover is now 'most likely' test residue: it was never proven, and the decisions record lists a second possible cause. 'From at least May' had no evidence and became 'from at least early June' (the oldest copies on disk). Added supporting evidence: the backup written straight after the 10-08 copy from prod already shows TST-MDB-1 empty, so the live box was very likely empty then.
- **Handoff Q14 / Group 45.6**: The brief said printer logins were left out of the 2026-10-08 copy; that's true, but dev has them again now, and the brief says so. Among the dev-only pieces a refresh re-applies, 'no printer logins' became 'a deliberate choice about printer logins', because dev currently holds them.
- **Handoff Q15 / Group 46.5 follow-up**: verified only: the rooms' parent_id is null in dev's locations.json, not "". No change to the text Derek reads.
- **Handoff Q10 (Undo), 46.3 (Tool 1 vs T0), Handoff Q12 / Group 45.4 (Feeds test)**: No changes. Every claim was re-checked against dev and holds; each verified field has a 'Second pass' line recording what was re-read.

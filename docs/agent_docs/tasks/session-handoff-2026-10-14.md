# Session handoff — overnight run, night of 2026-10-13 → 14

Plan and rules: [overnight-run-2026-10-14.md](overnight-run-2026-10-14.md). This file is the running log;
it is updated after every milestone and committed (and pushed) on `dev` at every merge.

## Morning summary

_Run in progress. Started from `dev` @ `4203ffe` (= `origin/dev`) at ~18:15 on 2026-10-13._

- Queue (Derek's pick): 43.2 + 46.3 → Group 45 → Group 41 → Group 42 → Group 40.
- Evening prep done: Derek's go-ahead for all-night full test runs, a push after each merge, and read-only prod
  counts (taken ~18:25; table in the plan file).

## Landed

_Nothing yet._

## Parked

_Nothing yet._

## Questions for Derek

Asked before Derek went to bed, from the pre-flight reconcile (`wf_1a1ff135-1c6`, read-only). Recorded as
answered; the builders follow these over the task files until the task files are updated.

**Round 1 (~19:00, Groups 41 and 42):**

1. **A used-up spool weighed back above 0 g whose old toolhead now holds another spool** → **Unassigned, with a
   7 s warning toast and an Activity Log WARNING** naming the spool that holds the head ("#99 is back in stock
   (40 g), but RCOI-1 now holds #299, so it is Unassigned — scan it to where you put it"). An empty head still
   gets it back, as today. Real on prod now: #99 → RCOI-1 (holds #299), #95 → RCOI-5 (holds #301).
   _(Group 42.3c; reader g42-q1)_
2. **Deleting a cart, shelf or row that still has locations inside it** → **refused, like a Room**: one rule
   for every location ("CR-CT-2 still contains CR-CT-2-R1, CR-CT-2-R2 and CR-CT-2-R3 — move or delete them
   first"). Printers keep their existing toolhead refusal. _(Group 41.3; reader g41-q2)_
3. **Eject All's refusal text on a Room or Printer view** → **follows the Bulk Moves switch**: with Bulk Moves
   on, a room points to 🔀 Move all → (with the preview warning); with it off (prod today), it says to eject
   from the room's boxes, drawers and shelves, or card by card. Printers point to each card's EJECT or the
   head (XL-1 … XL-5 / RCOI-1 … RCOI-8), "FCC asks first if XL is printing". Activity Log WARNING "Eject All
   refused on LR (a room): nothing was moved." _(Group 41.1; reader g41-q1; replaces manual check 41-b)_
4. **Eject feedback** → **short arrows in the toast** ("⏏️ #50 → back in PM-DB-2 (PM-DB-2 detached from
   XL-2)"; tile "🔗 attached — follows #50" / "🔗 attached, but its spool isn't on XL-2" + Unbind), **and a
   full sentence in the Activity Log** (Derek: "short arrows for toast. And a full sentence in the activity
   log", e.g. "Ejected #50 from XL-2 back into PM-DB-2; PM-DB-2 is no longer attached to XL-2.").
   _(Group 42.5a / 42.5c; reader g42-q2)_

**Round 2 (~19:10, Group 40):**

5. **The "XL-1 is already running another spool" dialog on a slot-label scan** → **Enter stores** ("Just store it"
   is highlighted). Wording as proposed: "Load #57 onto XL-1?" / "LR-MDB-1 slot 1 feeds XL-1, and XL-1 is
   running #1 (from PM-DB-3). Loading #57 sends #1 back to PM-DB-3." / [Load it instead] [Just store it in
   LR-MDB-1 slot 1] [Cancel], each with a scan QR. _(Group 40.3 / 40.0c; reader g40-q1)_
6. **Return when the spool has no recorded slot** → **one tap when the answer is obvious** (exactly one free slot
   feeds that head; the confirm still names it); the chooser otherwise. Derek: "the only time this might get
   tricky is if I've swapped something out for a dryerbox, but we probably already took care of that scenario."
   Builder note: a PolyDryer-fed spool HAS a recorded origin (its trail names the box), so Return sends it back
   there; and count an attached single-slot box as a second feed of that head, so a spool with no trail on a
   head a PolyDryer feeds gets the chooser, never a silent guess. _(Group 40.6, manual check R4; reader g40-q2)_
7. **A Location change in the Add/Edit Spool wizard** → **behaves like Force Location** (slot chooser for a
   multi-slot box, the toolhead chooser for XL/RCOI, Save moves the spool through the engine and loads the
   head a slot feeds, asking first when printing or busy; a refused move says so and the other edits stay
   saved). _(Group 40.7, manual check W1; reader g40-q3)_
8. **An empty-buffer scan of a location label** → **a single-spool dryer box still grabs its spool**, even when
   that spool is loaded on a head; printers, rooms, sections and rows open their view instead. Derek: **"also
   other single spool dryboxes"** — he has new Prusa dry boxes to add, and one of his scanners can't read a
   spool's barcode through their smoked plastic, so the box label is how he grabs the spool. Key the rule on
   Type "Dryer Box" with Max Spools 1 (Group 42.7), never on the PM prefix. _(Group 40.5 item F; reader g40-q4)_

## Manual checks for Derek

_None yet._

## Budget log

| Workflow | Unit | Agents | Tokens | Notes |
|---|---|---|---|---|
| `wf_1a1ff135-1c6` preflight-questions-tonight | Groups 45/41/42/40 | 5 (4 readers + 1 batched fact-checker) | _running_ | read-only reconcile + question harvest; started ~18:15 |

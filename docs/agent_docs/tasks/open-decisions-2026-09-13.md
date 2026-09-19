# Open decisions from the active-print fix — Derek's answers (2026-09-13)

> Working record for the six "Decide" items filed on 2026-09-12 under `fix/active-print-chain-confirm`
> (`51d9a49`). Background briefs came from read-only research (6 agents, plus 2 batched checkers
> that verified every brief against the code: 1 accurate, 5 with minor corrections applied).
> Decisions are copied into `Feature-Buglist.md` once all six are answered.

## Sweep before merge (2026-09-13, `RUN_INTEGRATION=1`, HEAD `51d9a49`)

**6 failed / 2517 passed / 23 skipped in 27:07. None is caused by the branch.**

| Test | Cause | Evidence |
|---|---|---|
| `test_locations_json_integrity::test_every_row_is_a_dict_with_LocationID_and_Type` | Known: Group 37.1's blank-LocationID `TestCart` row | `37-location-system-redesign.md` § "The two sweep reds" |
| `test_wizard_group10_session_a::test_location_combobox_highlights_current_selection_on_focus` | Known: the same row sorts to dropdown index 1 | Same section; deterministic in an isolated re-run |
| `test_contrast_guard::test_printer_status_widget_{expanded,collapsed}_has_no_gray_on_gray_text` | **Harness bug.** `firstOpaqueBg` (`tests/conftest.py` `_JS_CONTRAST`) takes the first background with alpha > 0.01 and uses its RGB as if opaque. `.fcc-ps-state-printing` is `rgba(16,185,129,0.18)` behind `#4ade80`, reported as 1.46:1; composited over the dark panel it is ≈ 6.7:1. The chip only carries that class while a printer is PRINTING, so earlier sweeps (idle printers) never hit it. Flaky with live state: on the re-run, collapsed passed and expanded failed. | CSS rule unchanged on the branch (`global.css` diff only adds the fading-dialog `pointer-events` rule) |
| `test_quickswap_visual::test_visual_quickswap_{grid,kb_active}` | **Dev-data dependency.** Height 680 → 762 px. In the May baseline, XL-1's Printer Pool slots (LR-MDB-1 slot 4, TST-MDB-1 slot 1) were empty short cards; now they hold #99 and #123 as full spool cards. The layout is unchanged. | Current and baseline images compared side by side (the baselines were restored from git afterwards); deterministic in an isolated re-run |

**Follow-ups to file:** make the contrast guard composite semi-transparent backgrounds over their ancestors; make the Quick-Swap grid snapshot hermetic (stub or mask the tile contents, or pin the pool slots) instead of recapturing a baseline that drifts with dev data.

## D1 — Quick-Swap and Return trust their overlay (R2-06, with R2-08) — ✅ DECIDED

**Choice: the server re-checks.** When no active-print banner was shown, `/api/quickswap` and `/api/quickswap/return` probe the printer themselves and answer `requires_confirm`; the UI re-confirms with the banner. Return probes the head it empties (not the box it lands in). Every confirm names the toolhead it was about, which closes R2-08 for Deposit and the confirmed slot-QR replay. Build it as a follow-up branch after the merge. Derek confirmed this pick after a worked-example re-explanation.

**Derek's steering (verbatim intent):**
- Quick-Swap should be printer-status aware. It is meant for non-active states (idle, stopped, paused — a pause may be a filament swap or runout). The realistic mid-print use is correcting FCC when it has drifted from the physical world after a print was started, e.g. syncing dev to live on 2026-09-12. So: allowed mid-print, but deliberate.
- **New UX requirement (all printer probes): show that FCC is waiting on a printer/server response**, so a slow or offline printer never looks like a lock-up or a click that did nothing. He expects to hit this when printers are offline and to forget that a printer ping is involved.

## D2 — Slotless move into a bound multi-slot box (guard gaps item 1) — ✅ DECIDED (Derek's own design)

1. **A box-label scan into a multi-slot box opens a slot picker** instead of FCC silently taking the lowest free slot. The picker shows the box's current loadout: each slot's spool and which toolhead (if any) it feeds. It recommends a slot (e.g. the next empty one) without assuming one exists. The user selects by touch or by scanning a slot QR. Possibly allow re-mapping slots from there (optional; may be out of scope).
2. **Before loading the toolhead a chosen slot feeds, confirm when:**
   - that printer is actively printing, or
   - the head is already fed from somewhere else, even when idle (e.g. XL-1 runs off the PolyDryer while slot 1 is being prepped for a later switch-out). Offer "load it instead" or "just store it in the slot".
   - An empty head on an idle printer loads without an extra prompt.
3. **Slot-label scans get the same "already fed from another box" confirm** (Derek: "Yes, slot labels too").
4. **Force Location into a dryer box behaves exactly like a box-label scan**: the picker, then the same load confirms.
5. **Out of scope, for the Location Manager overhaul (Group 37):** a wizard-style onboarding when assigning boxes to printers/rooms, where slots are mapped to toolheads as part of setup.

## Outcomes of the same session

- **Merged** `fix/active-print-chain-confirm` → `dev` as `f35d5e3` (`--no-ff`, Derek's OK), and pushed `dev` and the branch. `dev` → `main` stays held for the manual checks.
- **Dev spool #99's stale trail was already clear** when re-read (location `LR-MDB-1`, `container_slot 4`, empty `physical_source` and `physical_source_slot`), so no write was needed. The sweep's tests had rewritten it. `CR-MDB-1` no longer shows a ghost, so Bulk Move check 3 needs a spool genuinely deployed from `CR-MDB-1`.
- **Derek's standing rule:** dev spools are virtual test constructs. Any dev spool that no active test or open issue is using may be moved or cleared without asking.

## D3 — Spool placement on a Printer row — ✅ DECIDED

**Confirmed flow:**
1. Scanning `LOC:XL`, or picking "XL" in Force Location or the wizard, opens a picker. It lists XL-1…XL-5, with what is on each and which box slots feed each, plus the XL's Printer Pool slots.
2. Picking a head runs the normal load with the D2 confirms (printer printing, or head already fed from elsewhere).
3. It then asks "record it as coming from…": the box slots bound to that head, or no box. One is pre-selected only when exactly one free option exists.
4. Picking a pool slot only stages the spool.
5. Underneath, the server refuses a spool placed on the Printer row itself.

**Derek's context — it lowers the priority:** he never scans `LOC:XL` or a multi-slot box's own label (`LOC:LR-MDB-1`) to place a spool. The one exception is single-slot boxes (Polymaker). He uses slot labels and toolhead QRs, and has no printer-as-storage QR. D2's box-label picker and D3's printer picker are therefore "shoring up an oversight" for other users, who won't want to print a slot label for every bay.

**Single-slot box release rule — ✅ DECIDED (Recommended):**
- A single-slot box stays bound to a toolhead until ITS OWN spool leaves that head, by any path (eject, Return, Quick-Swap, any move).
- Ejecting a different spool from the head no longer unbinds it.
- **Derek's principle, restated:** "a toolhead should never have two spools attached to it directly… If looking at the toolhead, I should only ever see one in there." Showing loaded vs assigned/feeding as separate statuses is acceptable, but a head never shows two loaded spools.
- **Dev observation (Derek):** dev XL-1 shows an empty PM-DB-1 bound to it, while live shows no PM-DB bindings. Suspected stale test residue; under investigation.

**Derek's choice: a picker, not a refusal**, plus a confirm for the dryer-slot side. His words: "if I scan the printer, select toolhead 1, it should also then confirm if I want to add it to the assigned dryerbox in the assigned slot for that toolhead." He flagged transient single-slot boxes (PolyDryers, and other dryers coming soon) as the tricky part, and asked how they integrate.

**Integration, confirmed in code** (`locations_db.py` `_is_single_slot_dryer_box` / `attach_single_slot_box_to_toolhead` / `detach_single_slot_boxes_from_toolhead`; `logic.py` PRINTER MOVE branch and `perform_smart_eject`):
- FCC keys on `Max Spools`. For 2+ slots, `slot_targets` are user config and are never auto-changed. For a Dryer Box with ≤ 1 slot, slot `1`'s binding is lifecycle-driven:
  - **attach** when a spool moves onto a toolhead FROM that box;
  - **detach** of EVERY single-slot box bound to a toolhead when any spool is ejected from it.
- A toolhead may be fed by a multi-slot slot and a single-slot box at once (split feed); Quick-Swap shows both.
- Gaps:
  - The detach is toolhead-keyed, not spool-keyed (already filed).
  - Quick-Swap Return never detaches (filed 2026-09-13).
  - A non-eject move off the head (`perform_smart_move`) never detaches (to file).
- The 13.6 reverse-binding already silently records a free bound feed slot as `physical_source` when a spool lands on a head with no meaningful source. Derek's addition turns that into a visible choice.
## D4 — Room-level "Eject all" — ✅ DECIDED

**Choice: block Eject All on Room and Printer views.** On those views it moves nothing and says to use Move all → instead. Boxes, carts, shelves and toolheads keep it, with honest per-spool results, a refusal when no location is open, and no sweeping of a printer's heads mid-print.
- Derek: "an eject all on a room would be catastrophic… I don't think I would ever want to blindly unassign filaments assigned to locations in a room to that scale."
- **Principle:** a spool whose location is only a Room is a pain to find ("assuming it's even still in the room and somehow didn't get a location update"). Bulk filament still in its purchase boxes is the tolerated exception, because it is easy to spot.
  - **Implication to check:** the eject fallback sends a box/cart/shelf spool with no saved home UP to its Room's loose pile, which creates exactly these Room-only spools.
- **Usage:** "I may have used it once or twice, but I don't recall the last time… A case could be made for removing it." Removal is NOT decided; don't remove it without asking.
## D5 — Return with no recorded slot — ✅ DECIDED

**Choice: a slot picker (Recommended).** It is shown only when Return has no usable slot (none recorded, or the recorded one is taken).
- It lists the box's slots, with what each holds and which toolhead it feeds.
- It pre-selects this head's free slot, else a pool/spare slot, else "no slot".
- It is chosen by touch or slot QR.
- A known, free recorded slot keeps Return one tap.
- It reuses the D2 picker, so it is built after D2.
- The confirm preview and toast name the slot actually used (no more `SLOT:null`).

**Derek's context:** "an odd scenario that might happen with legacy data."
- He always assigns a spool to a slot, because the slot drives the auto-deploy to the toolhead and the Bowden tubes are already routed.
- A Return into a slot feeding a totally different head would be rare.
- A floating spool in a box should return to the box's floating pool. Floating spools are an annoyance, though: a "5/4" count in the Location Manager reads as "what went wrong".

**His question, answered:** yes, FCC has an auto-assign.
- Since 2026-04-23 (`dc19165`), a one-spool move into a multi-slot box that names no slot takes the lowest free slot (the D2 subject).
- Return falls back to that pick, which is how it can land in another head's feed slot.
- A spool landing with no slot in a full box is what shows as "5/4".

**Dev PM-DB-1 → XL-1 binding (Derek's observation under D3).** Not proven which of two causes:
- **Test residue.** Five E2E fixtures temporarily bind exactly PM-DB-1 slot 1 → XL-1 and restore the state they OBSERVED at start: `test_quickswap_visual`, `test_contrast_guard`, `test_bind_slot_picker`, `test_deployed_flag_preservation`, `test_feeds_section_visual`. One interrupted run makes the binding permanent.
- **The non-eject detach gap** (buglist findings item 9).

`inventory-hub/data/locations.json` is git-ignored, so there is no history to check.
## D6 — Guard moving a spool OFF a printing toolhead (omitted from the 2026-09-12 handoff's list) — ✅ DECIDED

**Choice: ask first, like Eject (Recommended).**

**When it asks:** before a move writes anything, if a moving spool's own location is a toolhead whose printer is PRINTING, PAUSING or RESUMING. Never while PAUSED.

**What it says:** the real consequence, not "will disrupt the print": "#42 is loaded on XL-3. Moving it to SHELF-A means FCC stops charging this print to it. Continue?"

**Scope:**
- Share the printer probe with the destination check, so a same-printer move asks once.
- A multi-spool move asks once, before anything is written.

**Build notes:**
- Build it together with guard-gap item 2 (Force Location's missing yes-path). Otherwise Force Location becomes a dead-end error.
- Build it with or after D1, so Quick-Swap isn't the one door left open.
- The Printer-row Eject All door is closed by D4's block.
- Tests must drive the real move engine ([[mocked engine hides chain bugs]]).

## Group-level questions — Derek's answers (2026-09-18)

Asked once the plan docs existed; each had background and a worked example.

| Q | Answer |
|---|---|
| **41 Q1** — where an ejected spool with no saved home goes | **Unassigned, after one "unassign?" prompt** (the prompt a PolyDryer spool already gets). Eject All asks once for the whole batch. This stops new Room-only spools. Smart Load's homeless resident keeps the 2026-09-12 rule (the printer's Room). |
| **39 Q1** — how deliberate a mid-print Quick-Swap confirm must be | **Keep today's overlay:** Yes stays focused, and Enter, a click or the CONFIRM QR all confirm. Only the consequence wording is new. |
| **42 Q-B** — what a LOCATION scan means in eject mode | **Eject that head's one loaded spool**, with the eject button's confirms. On a box, shelf or room, or a head holding 0 or 2 spools, warn and do nothing. |
| **42 Q-A** — does a single-slot box follow its spool head→head | **Yes, it follows** — with a caveat (below). |

**⚠️ Derek's caveat on Q-A, which needs a design answer before 42.6 is built.** In his words: "we shouldn't overwrite the spool location before the box load. (Say it was on a cart or something, so that if we unload it from the box, we know where it was before and move it back to that location.)"
- Today `physical_source` holds ONE level: the box (and slot) a spool was deployed from. A spool that came from a cart into a PolyDryer and then onto a head has no record of the cart.
- He wants that pre-box location kept, so that unloading the spool from the box can send it back to the cart.
- **Options to put to him:** a home chain (`physical_source` for the box, plus a separate "before the box" field), or a general "last non-container location" recorded on every move.
- **Where it lands:** Group 42 (release/attach rules) and Group 40 (the "record it as coming from" prompt, which is where a second level would be captured or shown).

## Housekeeping done after the decisions
- Dev PM-DB-1 slot 1 → XL-1 binding cleared with Derek's OK (`PUT /api/dryer_box/PM-DB-1/bindings/1 {"target": null}`). The test-fixture fix is filed under the sweep-triage follow-ups, item 3.

# Group 50: 🖨️ Printer Status Polish

**Branch name (when started):** `feature/group-50-printer-status-polish`
**Estimated effort:** MEDIUM (~6–11 h, 1–1.5 sessions). 50.1 ~1–3 h · 50.3 ~1–2 h · 50.4 ~3–6 h · tests and baselines throughout. 50.2 is not built yet (Derek: "more time in the oven").
**Risk:** **LOW–MEDIUM.** Mostly display (the widget's renderers, its one delegated click handler, the strip CSS). Two real hazards: a key handler on a tile must never swallow scanner input, and 50.4's "I loaded it" runs a real load, so it goes through an existing door with its questions intact.

> **Status: `TODO` — filed 2026-10-19 (`/refresh-groups`). Derek's decisions are in (2026-10-19); 50.2 waits in the oven and the group ships without it.** Not in the 48 + 49 + 51 + 52 bundle; it can start any time.
> The first slice of the Printer Status redesign Derek wants: the collapsed strip fits both printers, the tiles work by keyboard, and a head shows quietly when a spool is stored for it but not loaded. Every decision and his exact answers: [refresh-2026-10-19.md](refresh-2026-10-19.md).
> Code anchors were read on `dev` @ `c5c5aa6` (the refresh's grounding) and spot-checked at `08c4b10`. Line numbers drift, so re-grep before editing.

## Items covered (quoted from `Feature-Buglist.md`)

| # | Buglist item | Direction |
|---|---|---|
| **50.1** | Derek, 2026-10-19: *"with 8 toolheads in a small window, the toolhead list wraps to a second line. It looks odd on the collapsed version, the small one meant to be read at a glance."* Part of a Printer Status redesign he wants. | **Head numbers with a coloured ring, no pipe between printers; one row per printer if it still doesn't fit** (Derek's answer). |
| **50.2** | Derek, 2026-10-19: *"perhaps this just needs more time in the oven."* Clicking a toolhead tile opens that toolhead in the Location Manager, "the most useful default, which should stay. But sometimes you just want the spool loaded there, and getting to it is clunky. Ideas, none decided: a right-click or long-press, or a small spool button on the tile." | **Not built yet.** Kept here so the redesign remembers it; the gesture is still Derek's to pick. |
| **50.3** | The one concrete gap left by the old "Keyboard navigation everywhere" item (Group 8.1's 2026-05-12 audit; the item became a CLAUDE.md standing order on 2026-10-19 and was archived): the Printer Status tiles can't be reached by keyboard. Plus the tile tooltip, which says "click to Quick-Swap" while the click opens the head in the Location Manager. | Tiles and strip numbers reachable by Tab, Enter / Space opens the head, a tooltip that says what the click does. |
| **50.4** | Derek, 2026-10-14 ("🟡 A spool 'just stored' in a bound slot mid-print leaves a load to remember after the print"): *"Mid-print you can't load a toolhead, so a slot-label scan into a bound slot gets stored (Enter = Just store it). After the print you load the head physically (from the laptop at the XL), and must ALSO remember to tell FCC (scan the slot again or Quick-Swap). Forget either half and FCC and the printer disagree, and FCC can't warn the way the slicer does."* | **A quiet "stored, not loaded" marker on the head's tile, with an "I loaded it" confirm. No notice at print end** (Derek's answer). |

## Decisions

- **Derek (2026-10-19):**
  - **50.1, the collapsed strip:** head **numbers with a coloured ring** (cyan fine, amber under 100 g, red empty; the grams move to the hover text), **no pipe** between printers. If it still doesn't fit, **grow a little: one row per printer** when it's longer than the window; **scrolling sideways** is the fallback he also likes.
  - **50.4, "stored, not loaded":** *no* notice at every print end, and *no* "Load now" that locks him in (*"I may have a few prints I'm trying to do before I might have a chance to load it"*). Instead the head's tile **quietly shows that a spool is stored for it but not loaded, with a way to confirm "I loaded it"**. He is open to other ideas, since the collapsed strip has little room.
  - **50.2:** the "reach the spool on a head" gesture stays in the oven.
  - **50.3:** covered by his keyboard standing order (CLAUDE.md, 2026-10-19).
- **Claude's calls (for veto when the screenshots go to Derek):**
  - each printer's group in the strip starts with its short name (the Printer row's Location ID, `XL` / `RCOI`; the full name goes in the hover text), since numbers alone repeat across printers;
  - the strip always shows head numbers (position + 1, the "3" of the 46.3 setting); the expanded tiles keep the 46.3 Tool-label setting;
  - 50.4's marker is derived from data FCC already has (below), not from a new record.

## Today's code (anchors, `dev` @ `c5c5aa6`)

- **The collapsed strip:** one chip strip, `.fcc-ps-header-chips d-flex flex-wrap` (`dashboard.html:142`), filled in `_render` (`inv_printer_status.js:~480-495`). Each printer is a `.fcc-ps-printer-group` that doesn't wrap inside, led by a state chip with no printer name (`_renderStateChip`, `inv_printer_status.js:423`). **The "pipe" is that group's left border** (`border-left: 2px solid rgba(255,255,255,0.45)`, `global.css:1743-1755`).
- **Pills** come from `_renderToolheadCompact` (`inv_printer_status.js:315-370`): a colour swatch, the full head id and the grams (pill CSS `global.css:1695-1739`); unbound heads get a dashed yellow border and a 🔗; a head with two loaded spools gets "⚠️2".
- **Weight colours:** `_weightPalette` (`inv_printer_status.js:196-200`): red at 0, amber under 100 g, cyan otherwise. The ring reuses these thresholds.
- **The 46.3 Tool-label setting** (`_labelMode` / `_thLabel`, `inv_printer_status.js:154-165`) is deliberately not applied to the strip (comment `:146-153`), pinned by `tests/test_printer_status_widget.py:538-539` ("the collapsed strip keeps the full id"). That pin flips here, deliberately.
- **Width:** about 1,900–2,000 px for 13 pills plus badges (CSS arithmetic, not measured), so it wraps at 1,600 px and runs off below ~1,150 px. The expanded view wraps at 8 tiles too (168 px tiles + a 200 px name column; `global.css:1495-1500`, `:1576-1579`; `inv_printer_status.js:455`); probably fine, leave it.
- **Clicks:** one delegated handler: a tile or pill opens the head in the Location Manager (`_wireDelegation`, `inv_printer_status.js:509-518`; delegated because per-render listeners lost clicks during re-renders, L361). Loaded tiles carry `data-spool-id` (`:294`); pills don't (`:362-369`). Tooltips say "click to Quick-Swap" (`:296`, `:366`); the click opens the head's Location Manager view, where its Quick-Swap grid is.
- **Keyboard:** tiles are plain `div`s with no `tabindex`, role or key handling (`:293-296`).
- The tile's spool chip is passive by design (`ui_builder.js:266-272`).
- Every RCOI head shows "🔗 no bound slot" (`inv_printer_status.js:226-239`, `:287-304`) while no box slot feeds it; that goes away when Derek sets up his INDX holders (the ⏸️ PENDING DEREK item).
- **The data:** the widget renders from the heartbeat's `printer_status` section (Group 45.8), built in `routes_state_pulse.py` (~`:340-400`): ONE spool-list read bucketed by toolhead (`bucket_spools_by_location`, `:354`) plus each machine's bindings (`locations_db.get_bindings_for_machine`). Box-slot occupants aren't in it today.
- **50.4's gap:** "Just store it" replays with `auto_deploy: false`, the engine then binds no head (`logic.py:~2258-2262`) and only writes the box slot; nothing records a pending load. The print-end edge runs only the deduct (`_on_completion_edge`, `print_monitor.py:168-185`). Afterwards the user must re-scan the slot label or tap the slot in the head's Quick-Swap grid. If he forgets and FCC still has the old spool on the head (a PolyDryer spool, say), the next print charges that old spool; if FCC has nothing there, the deduct opens a no-spool review.

## Design, by sub-task

### 50.1 — the strip fits on one line
- Each printer's group: its short name once (Claude's call above), its state chip, then one **numbered dot per head**: the head's number on the filament-colour swatch (`.text-pop` for readability over the colour), **ringed** in the weight colour (`_weightPalette`); an empty head is a hollow ring with its number. Grams, the full head id and the spool go in the hover text.
- **No divider** between groups: drop the group's `border-left`; spacing plus the leading printer name separates them.
- Keep the unbound and doubled-head hints readable without stealing the ring's colour language (e.g. a tiny 🔗 / ⚠️ glyph beside the number; amber is already "under 100 g"). Show Derek before merging.
- **Overflow (Derek):** when the strip is wider than the window, switch to **one row per printer** (each group on its own line, names aligned) rather than a ragged wrap; if one printer's row is still too wide, that row **scrolls sideways**.
- `data-toolhead` stays the full id, so clicks and every test that selects by it are unaffected.
- Measure the real width at 1600×1300 before and after (bounding boxes), not by arithmetic.

### 50.3 — tiles by keyboard (standing order)
- `tabindex="0"` and `role="button"` on tiles and strip numbers; a visible focus ring.
- Enter / Space opens the head, through ONE delegated `keydown` on the widget root that acts only when a tile or number itself has focus (never per-render listeners: the L361 click-loss lesson).
- **Scanner input must never be swallowed:** a barcode scanner types characters and Enter. Before acting on Enter, ask `window.enterIsAScan()` (`inv_core.js:86`: two or more characters in the scan buffer, one in flight, a scanner burst, or a payload-like buffer); use `stopImmediatePropagation` and a deferred `scanBuffer` clear only when acting (the L298 / 46.2 lesson).
- Tooltip: "click to open XL-3 (its assignments and Quick-Swap)".

### 50.4 — "stored, not loaded", quietly
- **What counts (derived; no new record, no move-engine change):** a multi-slot Dryer Box slot whose binding is this head holds a spool that is not on any head. Exclude single-slot boxes (their slot-1 binding is the lifecycle attachment: their spool IS on the head) and Printer Pool slots (they feed no one head). Several such slots for one head: show the count and list them in the hover text.
- **Where:** the expanded tile gets a quiet line, e.g. "📦 #57 waits in LR-MDB-1 slot 2 · I loaded it". The collapsed strip has little room (Derek): a small mark on the head's number (a dot or 📦), its details in the hover text; show Derek a screenshot and take his pick.
- **"I loaded it":** runs the normal load of that slot's spool onto the head, the Quick-Swap tap's door (`/api/quickswap`, with Group 51.5's `expected_spool` once it exists), so it asks exactly as a Quick-Swap tap does (a printing head, a head running another spool) and Undo covers it. Never a load without his tap: FCC can't see what is physically on the head.
- **No print-end notice, no Activity Log line, no "Load now" prompt** (Derek). The mark simply disappears when the spool is loaded by any path or leaves the slot.
- **No extra Spoolman read:** extend the `printer_status` section's one bucketing read to the bound boxes' ids (the bindings are already in hand) and add the stored slot occupants per head.
- If the derived mark turns out noisy (a slot prepped for later while the head runs a PolyDryer spool for days also shows it), the alternative is a small record set only when "Just store it" answers a printing question; that is the open question below.

### 50.2 — not built (in the oven)
- When Derek picks a gesture: handle it inside the ONE delegated handler (`e.target.closest` on the new button before the tile branch), add `data-spool-id` to the strip numbers if right-click or long-press is chosen, open the spool window (`openSpoolDetails`), and update the chip's "no actions" comment (`ui_builder.js:266-272`). The grounding's default was a small 🔍 on loaded tiles.

## Tests (each proven red on the base first)

- Flip `tests/test_printer_status_widget.py:538-539` deliberately (the strip now shows numbers) and recapture `printer-status-widget-collapsed.png`.
- New: 5 XL + 8 INDX stubbed heads fit on one line at 1600 px (bounding boxes), stubbed through `window.refreshPrinterStatusWidgetFromAggregate` as the neighbouring tests do; no divider between groups; a narrow window gives one row per printer.
- The ring colours: cyan / amber under 100 g / red at 0; grams in the hover text; the contrast guard (`tests/test_contrast_guard.py`) on the numbers and the printer names.
- 50.3: Tab reaches a tile, Enter opens the head; a scan typed while a tile has focus still reaches the scan buffer and is processed as a scan.
- 50.4: a stored spool in a slot bound to XL-2 marks XL-2's tile; a single-slot box's spool and a Printer Pool slot don't; a spool on a head doesn't; "I loaded it" loads it (asks first when the XL prints, stubbed) and the mark disappears; no extra Spoolman GET per heartbeat; nothing logged at a print's end.

## Risks

- Click loss on re-render if a listener is added per render: keep the delegation.
- New key handlers vs scanner input (above).
- 50.4's "I loaded it" is a real move: route it through the existing door and its questions, never a shortcut write.
- Visual churn: the collapsed and expanded widget baselines.

## Open questions

- **50.4, derived mark vs a record:** show the mark for every stored-but-not-loaded slot (derived, the default above), or only after a mid-print "Just store it" (a small record)? Decide from how it looks with his real data; ask Derek with a screenshot if the derived mark shows on slots he prepped on purpose.
- **50.4 on the collapsed strip:** what the small mark looks like (Derek: "open to other ideas, since the collapsed strip has little room").
- **50.2:** the gesture (right-click / long-press, a small spool button, or both); still in the oven.
- **The rest of the redesign:** what else Derek wants from Printer Status. The refresh asked (for example print progress
  or time left); no answer is recorded yet. FCC reads only `printer.state` and the job's file, id and progress today
  (`prusalink_api.py:466-473`, `:509-528`); whether his firmware's `/api/v1/status` also gives time left and
  temperatures is unverified.

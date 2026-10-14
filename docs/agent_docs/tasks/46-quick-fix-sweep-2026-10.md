# Group 46: 🐞 Quick-Fix Sweep (2026-10)

**Branch name (when started):** `feature/group-46-quick-fix-sweep`
**Estimated effort:** SMALL–MEDIUM (~4–7 h, 1 session).
**Risk:** **LOW–MEDIUM.** Each item is small and already specified. 46.1 is on Derek's daily path and writes spool locations, so it needs a reproduction and an E2E pin.

> **Status: `DONE` — 46.1, 46.2, 46.4 and 46.5 shipped in the 2026-10-13 overnight run (merged to `dev`, `36d7318`); 46.3 ("Tool 1") shipped in the 2026-10-13/14 overnight run on `feature/finish-groups-43-46` with Group 43.2. See `completed-archive.md`. The 46.5 follow-up, deleting dev's blank-ID TestCart row, was done 2026-10-13.**
> Small, specified fixes that shouldn't wait behind the large design-blocked groups (37, 39–42, 44). It has the Option-B standalone-sweep shape.
> 46.5 (37.1) was pulled out of [Group 37](37-location-system-redesign.md) by Derek's call on 2026-10-12: it's root-caused and doesn't depend on fork 1.
> Code anchors were read on `dev` @ `3949aba`. Re-grep before editing.

## Items covered (quoted from `Feature-Buglist.md`)

| # | Buglist item | Direction |
|---|---|---|
| **46.1** | Derek, on prod: *"the carousel when selecting filaments in the buffer on a toolhead (or any location I assume) take a few seconds to update the deposit button… It would take forever to update the deposit button, so it kept re-assigning the filament that was top of the list on load or that was the last filament used… if you're too fast, you end up assigning the spool you were previously on, instead of the spool you actively have in the center of the carousel. We'll need to look into this one."* | See the code trace below. **It writes the wrong spool, so do it first.** |
| **46.2** | **"Location Manager: Type dropdown + 't' + Enter → error instead of saving"** (root-caused 2026-09-29). | The filed fix, below. |
| **46.3** | **"Toolhead label display mode."** Printer Status would show a toolhead as `XL-1`, as `1`, or as `Tool 1` / `T0`. | Filed as hotfix-sized. Its one decision was made 2026-10-13: "Tool 1" (below). |
| **46.4** | **"`feeder_map` boot import re-binds an emptied box."** Latent: dev's and prod's `feeder_map` are empty today. | Retire it the way the `printer_map` seed was retired. |
| **46.5** | **37.1: a blank LocationID is accepted, then reported as "already exists"** (ROOT-CAUSED 2026-10-08). | The filed minimal fix, below. |

## 46.1 — The buffer carousel deposits the previous spool

**Code trace (2026-10-12): consistent with the report, but NOT yet reproduced.**
1. Prev/next (`inv_cmd.js:101-102`) rotates `state.heldSpools` and calls `renderBuffer()`, which dispatches `inventory:buffer-updated` (`inv_cmd.js:73`).
2. The Location Manager's listener (`inv_loc_mgr.js:4-12`) calls `renderManagerNav()` **synchronously**, so the centre card visibly changes at once. It then calls `refreshManageView(id)`.
3. `refreshManageView` (`inv_loc_mgr.js:850-862`) **returns early if a `/api/get_contents` fetch is already in flight** (`_refreshManageViewInflight`). Otherwise the DEPOSIT card is rebuilt only when that fetch resolves (`_renderManagePayload` → `renderList`).
4. The DEPOSIT card's handler captures the spool at render time: `depositCard.onclick = () => doAssign(locId, item.id, null)`, with `item = state.heldSpools[0]` (`inv_loc_mgr.js:1011-1020`). Until the re-render lands, a click deposits the **previous** top spool.
5. The card's QR encodes only the location (`LOC:<id>`, `inv_loc_mgr.js:1134`/`:1142`). A scan resolves the spool from `state` when it's processed, so the click handler is the suspect path, not the QR.
6. During an active print the delay is longer: `doAssign` probes the printer (`fetchPrinterStateForToolhead`, with no timeout) before its confirm, so a slow answer reads as "nothing happened". [Group 39](39-confirm-on-every-door.md) 39.3 covers that wait.

**Fix direction:**
- Resolve the spool at click time: the handler reads `state.heldSpools[0]` when clicked.
- Re-render just the DEPOSIT card synchronously in the `inventory:buffer-updated` listener, without waiting for `get_contents`.
- Check the multi-slot grid view (`renderGrid`) and Quick-Swap's deposit (`quickSwapDeposit`, `inv_quickswap.js:646`, "Deposit the top buffered spool") for the same capture-at-render pattern.
- **Reproduce first** with Group 38's in-page fetch-delay lever: delay `/api/get_contents`, press next, click DEPOSIT, and assert the deposited id is the centre card's. Use a route-stubbed backend so nothing is written to dev. The test must fail on HEAD.

## 46.2 — Type dropdown + "t" + Enter is scanned as the code "t"

**Filed root cause.** The location edit modal has no Enter-to-save. The global barcode listener (`templates/components/scripts.html:250`) skips only `INPUT` and `TEXTAREA` targets. A letter typed on the Type `<select>` (`#edit-type`, `templates/components/modals_loc_mgr.html:75`) therefore lands in `state.scanBuffer`, and Enter submits it as a scan of "t".

**Filed fix.** Add a keydown handler on `#locModal`. For Enter on an input or select inside the modal, it should `preventDefault` + `stopPropagation`, clear `state.scanBuffer`, and call `saveLocation()` (`inv_loc_mgr.js:1986`). That's the CLAUDE.md "Enter confirms" idiom.
- **Deliberately NOT** a global "ignore SELECT" in the scanner: a focused dropdown would then swallow a blind barcode scan.
- Check that dev's Location Manager field-scan capture doesn't also act on that Enter.
- L298 lesson: use `stopImmediatePropagation()` and clear `scanBuffer` **deferred**, or the accumulator re-fills on the same tick.

## 46.3 — Toolhead label display mode — ✅ ANSWERED 2026-10-13: "Tool 1" (counts from 1)

**Decided 2026-10-13 (Claude's call; Derek reviewed it and didn't object): "Tool 1", counting from 1.** The tool-name choice reads Tool 1–Tool 5 on the XL and Tool 1–Tool 8 on the INDX, so its number always matches the head's own id (XL-3 → Tool 3) and the Feeds and Quick-Swap pickers ("Toolhead 3"); FCC stores head positions from 0, so the label is position + 1. It is what Derek's INDX setup report asked for: "(XL-1, vs just 1 (Or Tool 1))". Build it that way, on the filed shape below; the original question is kept for the record.

**Filed shape:**
- a client-scope `fcc.printerStatus.toolheadLabel` select in `config_schema.py`;
- a `_thLabel()` helper in `inv_printer_status.js` that changes the visible text only (keep `data-toolhead` and titles on the full id), with the mode included in `_fingerprint`;
- the new key added to the CLAUDE.md user-preferences table.

✅ **Decided 2026-10-13 ("Tool 1", the bold line above); this was "decide with Derek before building":** 1-based "Tool 1" (matches the printer screen and the Feeds dropdown) or 0-based "T0" (gcode). Longer term this becomes per printer, which hangs off [Group 44](44-printer-first-class.md)'s printer id and [Group 35](35-config-cluster.md)'s map type.

**Build notes from the 2026-10-13 brief** ("How Printer Status should number a toolhead" in [open-decisions-2026-10-13.md](open-decisions-2026-10-13.md)):
- The setting offers three choices: the full id (today's look, kept as the default), a bare number, or "Tool N". There is no "T0" choice.
- The collapsed one-line strip shows no printer names, so with a short label the XL's first head and the INDX's first head would read the same there. Keep the full id in that strip, or put the printer's name in front of each group.
- The 🛑 review card keeps its gcode-style "T0 · RCOI-1" line labels; the id printed beside each keeps that readable.

## 46.4 — Retire the `feeder_map` boot import

`migrate_feeder_map_if_needed` (`locations_db.py:506`) skips only boxes that still HAVE bindings. A box whose slots were all cleared is therefore re-bound from the legacy `config.json:feeder_map` on the next restart.
- Retire it the way the 2026-09-29 hotfix retired the `printer_map` seed: skip once any Dryer Box carries `slot_targets`.
- Update the CLAUDE.md "Legacy" bullet in the Dryer Box bindings section.
- Optional, same spirit: the vestigial `fb_url` / `filabridge_url` plumbing row (NOT-Grouped) is the same kind of mechanical retirement, if the session has room.

## 46.5 — Blank LocationID (37.1)

**Filed root cause (2026-10-08).**
- On save, `if old_id:` is falsy, so the old row is never filtered out (`routes_locations.py:326`).
- The duplicate guard is skipped because `_new_lid_dup` is falsy (`:335-336`).

So giving the blank row a real id **appends a second row** and leaves the blank one forever. Renaming again collides with the row just made, which is the "already exists" message. Delete returns 400 on a blank id, and `#edit-id` has no `required`.

**Filed minimal fix:**
- return 400 on a blank or whitespace LocationID in `_api_save_location_locked` (`routes_locations.py:322`);
- add `required` to `#edit-id`, plus a client-side check;
- either allow an explicit blank-id DELETE, or drop blank rows in a startup migration.

⚠️ **Existing blank rows stay until Derek says otherwise** (2026-10-12):
- dev row 0 `{"LocationID": "", "Name": "TestCart", …}`, his own repro. ✅ **Deleted 2026-10-13** with Derek's OK, through the app's own path (`DELETE /api/locations?blank_id=1`): 82 → 81 rows, no blank-ID rows left, no spool touched (backup `locations.pre-testcart-delete-20261013.json` in that session's scratchpad). The handoff's manual check 46-e is done. `CR-TC-1`, also named "TestCart" (with row `CR-TC-R1`), is a separate row and is **kept**, per Derek;
- prod row 0 `{"LocationID": "", "Name": "Unknown Location", "Type": "Virtual Room", …}`, hand-made, not a persisted synthetic row. The 2026-10-13 delete was dev-only; this row stays until Derek says otherwise.

A startup migration would touch prod's row, so prefer the explicit-DELETE path unless Derek chooses otherwise.

**The two standing sweep reds** (`test_locations_json_integrity`, `test_location_combobox_highlights_current_selection_on_focus`) cleared once dev's TestCart row was gone: both pass since the 2026-10-13 delete. The guard alone didn't remove it.

## Verification

- Use `--offline` for the backend pins in 46.4 and 46.5.
- 46.1 and 46.2 need route-stubbed or live E2E. These are frontend changes, so get Derek's OK for a full sweep before merging.

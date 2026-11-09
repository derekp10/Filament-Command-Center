# Group 54: 🧷 Group 36 Leftovers

**Branch name (when started):** `feature/group-54-group36-leftovers`
**Estimated effort:** SMALL–MEDIUM (~5–9 h, 1 session). 54.1–54.4 ~3–6 h · 54.5 ~1.5–3 h (with its check on dev) · 54.6 ~0.5–1 h.
**Risk:** **LOW–MEDIUM.** 54.1–54.4 are dormant on today's data. `setup_fields.py` runs on every prod deploy, but the change sits inside a branch that returns early. 54.5 changes the wizard's edit-mode save, a live path; 54.6 the archive edge of `update_spool`, a rare path.

> **Status: `TODO` — filed 2026-10-19 (`/refresh-groups`). No Derek decision needed.** Not in the 48 + 49 + 51 + 52 bundle.
> **🔄 2026-10-25 (`/refresh-groups`): gains 54.5 and 54.6**, two small items of the same shape (a clear or an edge that silently doesn't fire), filed 2026-10-21 by the extras-clear fix and 2026-10-19 by the Group 51 review. Still no Derek decision; 54.5 needs a check on dev first.
> Four small hardening fixes from Group 36's lineage (the filament-attribute work and its review). Group 36's other follow-up, the retry on the pre-merge extras read, is [Group 52](52-spoolman-read-load.md) 52.2. Every decision: [refresh-2026-10-19.md](refresh-2026-10-19.md).
> Code anchors were read on `dev` @ `c5c5aa6` (the refresh's grounding) and spot-checked at `08c4b10`. Line numbers drift, so re-grep before editing.

## Derek's answers, 2026-11-07 (read this first; it overrides the planning pass below)

1. **The "Auto-Archive 0g" switches (the weigh-out window and the Quick-Weigh): (a), off means off.** With the switch off, a spool weighed to 0 g stays in stock at 0 g; with it on, it is archived as today. Today the server archives any spool weighed to 0 g whatever the switch says.
2. **An emptied spool price: (a), it comes back from the filament's price, but marked as the filament's.** Derek: *"mark the spool price as coming from the filament price. Some times a filament's price might not be the price that exact spool costs, because it was on sale or purchased at a lower (or higher) price than the time that the filament entry was created."* So a person can always tell a spool's own price from one it takes from its filament. The planning pass's note that the next Save writes the refilled price as the spool's own would lose that mark: the build keeps the spool's own price empty while it shows the filament's (marked, e.g. "from the filament"), and writes a price of its own only when one is entered. A look change: show Derek a picture before the merge.

## Build plan, 2026-11-08 (read this second; it extends the planning pass below)

Started 2026-11-08 23:50 on `feature/group-54-group36-leftovers`, cut from `dev` `6e094e5` (code unchanged since the planning pass's `11126bb`). Derek, going to bed: *"feel free to work on all the parts for this that you can without my input."* So everything is built, and only the price look (54.8) waits for his OK, from pictures, before the merge. His two answers become two new parts, 54.7 and 54.8, because they touch the same code as 54.6 and 54.5.

**Order (five builders, one at a time, one commit per part, red-first tests; the workflow `group-54-build`):** b1-server: 54.6, 54.7 (server half), 54.1, 54.3 · b2-wizard-clears: 54.5 · b3-price-mark: 54.8, with its before pictures taken before the wizard changes (so Derek's pictures are ready first) · b4-migration-weigh: 54.4, 54.7 (page half) · b5-chips-docs: 54.2, the `?v=` bumps, the owed CLAUDE.md text · then a full `--offline` run (the orchestrator). Then one batched review (`docs/agent_docs/review-checklist.md`), its fixes, the full sweep, and Derek's picture check.

### 54.7 "Auto-Archive 0g" off means off (Derek's answer 1)

**Today.** Two switches: the weigh-out window's "Auto-Archive 0g" (`#weigh-auto-archive`, `modals_weigh_out.html:55-56`, on by default) and the Quick-Weigh's "Auto Archive & Eject if Empty (0g)" (`#fcc-we-auto-archive`, `weight_entry.js:151-152`; only `openQuickWeigh` shows it, `inv_weigh_out.js:1226`). Each decides only whether `saveSpoolWeight` (`inv_weigh_out.js:990`) sends `archived: true` and force-unassigns afterwards (`:1110-1120`). The server's archive edge (`spoolman_api._auto_archive_on_empty`, run from `update_spool` at `:672`) archives every weight write that leaves nothing, so with a switch off a spool weighed to 0 g is still archived, Unassigned, its trail blanked and its pre-archive note planted.

**Change.**
- Server: `update_spool(sid, data, archive_on_empty=True)`, a keyword with today's default. `False` skips `_auto_archive_on_empty` entirely: no `archived`, no location blank, no note, no trail blanks, no "📦 Auto-archived" line. The unarchive edge still runs, so a refill of an archived spool still un-archives it, and an archived spool weighed to 0 g stays archived where it is. `update_spool_or_raise` is unchanged.
- `/api/spool/update` reads an optional top-level `auto_archive` beside `id` and `updates`. Only exactly JSON `false` passes `archive_on_empty=False`; absent, `true` or anything else is today's behaviour. The route passes the keyword only in that case, so the tests that patch `update_spool` with a two-argument fake are untouched.
- Page: every weigh-out and Quick-Weigh save sends `auto_archive` with its window's switch state: the weigh-out list's switch for its row saves and the details-fallback row (`:906-920`), and the Quick-Weigh's own switch for its saves (`payload.auto_archive`). It sends the switch, not the per-save verdict, so with the switch on the server's rule still decides when the page's own arithmetic (its `details.initial`) disagrees. The `archived: true` and force-unassign chain stays as it is with the switch on.
- Words (Claude's call): with the switch off and a save that leaves 0 g by the page's own reading, the success toast says so, e.g. "Updated Spool #57: 0 g left, kept in stock (Auto-Archive is off)". With the switch on, the toast is unchanged.
- Tests (red first): `update_spool` and the route over `SpoolmanHTTPFake`: used weight = initial with `auto_archive: false` keeps the spool in stock, its location, slot and trail, with no note; without the key it archives as today; `remaining_weight: 0` with `false` (after 54.6) keeps it; an archived spool at 0 g with `false` stays archived; a refill with `false` still un-archives. Page: the POST body carries `auto_archive: false` with the switch off and `true` with it on, from a row save, the fallback row and the Quick-Weigh (use the harness the weigh-out family already uses: `test_weigh_out_scan_focus_js.py`, `test_quick_weigh_scan_js.py`, `test_weight_entry_overlay.py`, `test_weigh_out_e2e.py`).

### 54.8 An inherited spool price is marked as the filament's (Derek's answer 2)

**Today.** `wizardPrefillSpoolPrice(ownPrice, filamentPrice)` (`inv_wizard.js:743-749`) puts the filament's price into the spool's "Price Paid ($)" box (`#wiz-spool-price`, `modals_wizard.html:431-433`) as a plain number whenever the spool has none of its own: a new spool of an existing filament (`:4440`), a clone (`:4364`) and an edit (`:4658`). Save sends the box as the spool's own price (`wizardSubmit`, `:3826`). So every new spool, and every edited spool with no price of its own, gets its filament's price written as its own. No other FCC screen shows a spool's price; the section's collapsed summary does (`'wiz-spool-metadata-panel'`, `:392-400`, "$25").

**Change** (all three modes):
- A price of the spool's own (an edit's, or a clone's source spool's) shows as today, plain, and is saved as today.
- With none of its own and a filament price, the box shows the filament's price marked as the filament's, in the look the empty-weight box already has: the value in the box and a "↩ from filament" badge beside the label (`wizardSetSpoolEmptyWeightInherited`, `:70-82`; `#wiz-spool-empty-inherited-badge`, `modals_wizard.html:377-380`). Typing in the box makes it the spool's own, and the badge goes.
- Save sends a price only when it is the spool's own: the box was typed into (54.5's touched set), or it held the spool's own price. An untouched box showing the filament's price sends nothing, so a new spool is created with no price and an edited spool keeps none. 54.5's emptied box still sends `null` in edit mode.
- A price an external import puts in the box is that purchase's price, the spool's own (check whether any import writes `#wiz-spool-price`; the anchors above found none).
- The collapsed summary says where the price comes from (e.g. "$25 from filament").
- **Claude's call, the empty weight's twin (edit mode only).** An edited spool with no empty weight of its own shows its filament's (or brand's) with the badge, and Save writes it as the spool's own: the server's diff (`routes_inventory.py:1181-1183`) sees `None` against 200. So 54.5's clear of an empty weight would come back as the spool's own at the next Save. In edit mode, an untouched box showing an inherited empty weight sends nothing. New spools and clones keep today's rule (they take the cascade's value as their own, L34).
- **Pictures for Derek before the merge** (standing order: no look change without a sample): before and after, the price box and the collapsed summary, for a new spool and for an edit, at 1600×1300, into `review-samples/2026-11-08-group54/` (git-ignored), numbered in walk order. Take the "before" ones from the live dev page before the wizard code changes, with every read stubbed and nothing written.
- Tests (red first): a new spool of a $25 filament with the box untouched sends no `price`; an edit of a spool with no price of its own sends no `price`; a typed price is sent; an own price is sent as today; the badge shows and hides; the summary's words; the empty-weight twin. Update deliberately the cascade tests that pin the old plain prefill (`test_wizard_price_product_cascade_e2e.py` and its family).

### Claude's calls, for Derek's veto

- 54.7: `auto_archive: false` stops only the archive-on-empty edge; a refill still un-archives, and nothing un-archives a spool that is already archived. The toast says when a spool was kept in stock at 0 g.
- 54.8: a clone keeps its source spool's own price as its own (a sibling bought together); only a filament's price is marked. The empty-weight twin above, in edit mode only.
- Everything in the planning pass's "Claude's calls" stands.

### Build log

_(Each builder appends: the parts done, commits, tests run with results, anything left or surprising.)_

**b1-server, 2026-11-09: 54.6, 54.7 (server half), 54.1, 54.3. All done, all offline.** Commits `502f06d` (54.6), `cac365d` (54.7 server), `013f56e` (54.1), `4a89bb0` (54.3). Every new test file was run red on the commit before its part, and each RED case failed for the reason the spec gives.

- **54.6** `spoolman_api._auto_archive_on_empty` reads `remaining_weight` exactly as the refill edge does (without `used_weight` beside it, it is the weight left, and it decides over a new `initial_weight`). `tests/move_engine_harness.WeighedWireSpoolman` now stores a `remaining_weight` as Spoolman does (the used weight it leaves; refused beside `used_weight`, with no known capacity, or when it isn't a number). New `tests/test_archive_on_remaining_weight_54_6.py`, 19 tests: red 11 failed / 8 passed (every failure "not archived", the door's `auto_archived: false` with PM-DB-1 still bound to XL-1); green 19/19.
- **54.7, server half.** `update_spool(sid, data, archive_on_empty=True)`; False skips the archive edge entirely (the refill edge still runs). The harness's `FakeSpoolman.update_spool` / `WireSpoolman.update_spool` take the keyword; WireSpoolman hands it to the real `update_spool` only when it is False, so the harness still drives older product code. New `tests/test_auto_archive_off_54_7.py`, 20 tests over `SpoolmanHTTPFake` with an in-memory locations.json (the box release, the route's release and the single-slot helpers run for real), plus one through `run_move`: red on `502f06d` 9 failed / 11 passed (no keyword ×4; the route ignored the switch ×2, `used_weight` and `remaining_weight`, the second being where 54.6 meets 54.7; an archived spool taken off its shelf; the keyword never passed; the harness route test); green 20/20. Every `update_spool` monkeypatch in tests/ was checked: none sends `auto_archive`, and the route passes the keyword only for false (pinned by `test_control_a_two_argument_stand_in_serves_every_request_but_false`).
  - **What the route accepts, for the page builder (b4):** `POST /api/spool/update` with `{"id": <spool id>, "updates": {...}, "auto_archive": <boolean>}`. `auto_archive` is optional and top-level, beside `id` and `updates`, never inside `updates`. Only the JSON boolean `false` turns the archive-on-empty edge off; absent, `true`, the string `"false"`, `0` and `null` all keep today's rule, so send the switch as a real boolean (`!!checkbox.checked`). With `false`, a weight write that leaves 0 g writes only what `updates` carries (no `archived`, no location blank, no note, no trail blanks, no box release); the answer's `auto_archived` and `needs_empty_weight_prompt` are false; a refill of an archived spool still un-archives it (with `warning` as before); an archived spool weighed to 0 g stays archived where it is. With `true` or absent, nothing changes. A page's own `archived: true` inside `updates` (switch on) still goes as sent. Since 54.6 the fallback row's `remaining_weight: 0` with the switch on is archived by the server in that one write (`auto_archived: true`), and the page's force-unassign after it writes Unassigned again, harmlessly, as on the main path.
- **54.1** `/api/update_filament` answers 400, before anything is read (`request.get_json(silent=True)`): a body that isn't a JSON object ("The request isn't a JSON object, so nothing was updated."), no id ("Missing filament id."), no `data` ('Nothing was updated: the request has no "data" field. Send {id, data: {field: value}}.', plus "(It looks like the old {id, field, value} shape.)" when the body carries `field` or `value`, and one WARNING in hub.log naming the keys that came), a `data` that isn't an object ('"data" must be an object of field: value, so nothing was updated.'). `{id, data: {}}` keeps its 200. New `tests/test_update_filament_payload_54_1.py`, 15 tests: red 13 failed / 2 passed (200 generic answers, a crash on `.get` for a list or string body, Flask's HTML 400 for a body that isn't JSON); green 15/15. The live pins in `test_filament_edit_button.py:23-40` keep their words (skipped under `--offline`; they write nothing).
- **54.3** `_parse_filament_attrs_value` splits a non-JSON string and a JSON string on commas (`_split_attr_text`: trimmed, blanks and repeats dropped, first kept); lists are never split. `tests/test_search_api.py`'s `["Silk, Matte"]` pin updated deliberately to `["Silk", "Matte"]`. New `tests/test_filament_attrs_split_54_3.py`, 22 tests (the helper, the report and the sweep preview on the spec's `_install_wire` harness with the hidden list stubbed, and a real bulk add over `SpoolmanHTTPFake` 0.27): red 12 failed / 10 passed (one pseudo-tag; Silk 1, Matte 0 and a rogue; Matte offered for deletion; Spoolman refusing `["Silk, Matte", "Glow"]` as invalid choices); green 22/22. The boot cleanup's decision to run reads no usage, so the split makes it write nothing new; only what it would restore is now the valid shape.
- **Test runs (all `--offline`, from inventory-hub/):** 54.6 + the archive-edge family (13 files) 295 passed, 11 skipped; every file importing the harness (37) 924 passed; after 54.7, every file that patches `update_spool`, posts to `/api/spool/update` or imports the harness, plus the route pin and source canaries (81 files) 2233 passed, 17 skipped; 54.1 with the route's other files (11) 212 passed, 157 skipped; 54.3 with every file touching attributes, search or stock (42) 693 passed, 202 skipped.
- **Claude's calls:** a weight left (or a used / initial pair) that works out to NaN never archives (`nan > 0` is False, so the bare mirror would have archived on "nan"); a JSON string holding a JSON list (a list once written through a text field) reads as that list rather than as one pseudo-tag; 54.1's words put the key in double quotes rather than backticks (they reach a toast); the "📦 Auto-archived" line is not gated on the keyword, so it fires only when a write newly archives, as before (with `archive_on_empty=False` the edge adds no `archived`, so only a caller's own `archived: true` could fire it, which no page sends with the switch off).
- **Left / surprising:** the spun-off 54.3 item (the browser's `parseFilamentAttributes`, the wizard's edit prefill, the Edit Filament form's diff, and the three server display parsers in `spoolman_api.format_spool_display`, `spoolman_api.search_inventory`'s filament cards and `labels_csv.get_smart_type`, which read the same comma string differently) is not filed yet: I left `Feature-Buglist.md` alone, because Derek types into it in VS Code. `SpoolmanHTTPFake.patch` stores a `remaining_weight` as a literal key and doesn't work out the used weight (left as it is, it is shared; the new tests assert on the PATCH bodies). `tests/roundtrip_bridge.py` errors at collection when named on the command line (a helper, not a test; harmless in a normal run).

**b2-wizard-clears, 2026-11-09: 54.5. Done.** Commit `49bf713` (code + tests). Red first on `d3497be`; every red failed for the reason its test names.

- **The dev check (dev's Spoolman only, `http://192.168.1.29:7913`, version 0.27.1).** A throwaway filament #224 and spool #299, both named "ZZ Group 54 null check (temporary, delete me)". Each field was PATCHed alone to JSON null and its record read back: spool `price` (was 30), spool `spool_weight` (196), filament `spool_weight` (200), `price` (25), `settings_extruder_temp` (215) and `settings_bed_temp` (60). Every PATCH answered 200, every field read back absent (Spoolman leaves a field with no value out of the record), and no other native field of the record changed. Both records were deleted (200) and each then read 404. No field is left out of 54.5. (The script and its log: `scratchpad/g54/dev_null_check_54_5.py` / `.log`, outside the repo.)
- **The re-checked claim: the cross-inherit never filled the spool's side.** `wizardSubmit` drops the spool payload's nulls (`delete sp_payload[k]`) before the "Cross-Inherit empty-spool-weight" block, so a blank spool box reaches the block as `undefined`, and its `if (sp_payload.spool_weight === null)` could never match. History: nulls were dropped before the older spool cross-inherit from the start, kept from `baf7637` (2026-03-29) to `13654bb` (2026-04-06, "correct clone spool payloads"), and dropped again since; today's Spool → Filament → Vendor block (`effeaa8`, 2026-04-22) came after that, so its spool line never ran. Only the filament's side fills (from the spool's box, else the brand). So the planning pass's red reason for "the emptied spool empty weight is null although the filament has 200" was wrong (on the base the key is missing, never 200), and its control "an untouched spool empty weight with no value of its own still takes the cross-inherit" doesn't hold at Save (Edit Spool's open draws the inherited value into the box, with its badge, and Save sends the box). The tests are written to what the code does. The dead line is gone, with a comment saying why; the filament line now skips a box emptied in edit mode, and create mode fills it as before.
- **The change (`inv_wizard.js` only; the server half needed nothing).** `WIZ_NATIVE_CLEARABLE` maps the five boxes to `"<entity>:<key>"`; `wizardState.touchedNative` (reset by `wizardReset`) is filled by `window.wizardNoteNativeTouched` from the wizard's `input` listener; `wizardNativeCleared(entity, key)` is true only in edit mode, for a touched box that reads `''` with no `validity.badInput`. The spool's and the filament's null-drops keep such a null, and the cross-inherit never refills it.
- **For b3 (54.8): the helper.** `wizardNativeTouched(entity, key)`, a top-level const beside `wizardExtraTouched` (not on `window`; `page.evaluate` and the node-vm harness reach it by name), says whether the user changed that box this session, e.g. `wizardNativeTouched('spool', 'price')`. Keys: `spool:price`, `spool:spool_weight`, `fil:spool_weight`, `fil:settings_extruder_temp`, `fil:settings_bed_temp`. It is filled in every mode (the listener doesn't look at the mode), by `input` events only; a value set by code (the open's prefill, `wizardPrefillSpoolPrice`, the filament empty weight's copy into the spool's) is never a touch. `wizardNativeCleared` is the edit-mode clear test.
- **Claude's calls.** (1) Only `input` counts as a touch, not `change` (a number box fires `input` for every change a person makes: a key, a paste, the spinner, the wheel). The first build counted `change` too, and its own test caught it: a box emptied in one session kept the focus, the next session's Save click blurred it, Chromium fired a `change` for the old edit, and the new spool's empty bed temperature went out as a clear. On the real page every close I traced moves the focus before the next session's reset (Save and the close buttons are clicks, and Escape on an edited form opens the Unsaved Changes question, which takes the focus), so there `input`-only is a guard rather than a fix for a seen bug; it costs nothing. (2) A number half typed (`-`, `1e`) reads `''` while it shows text; it is no clear, and the field is left as it is, as before. (3) The cross-inherit's dead spool line is removed rather than gated.
- **Tests:** new `tests/test_wizard_native_clear_54_5.py`, 19 items: 18 hermetic on the Group 58.5 harness (the real `modals_wizard.html` and modules in `isolated_page`, real number inputs, the real Save; they run under `--offline`), one on the real dashboard (the bed temperature, its POST read in the browser, nothing reaching dev), and one offline server pin (`/api/edit_spool_wizard` over `SpoolmanHTTPFake` 0.27.1: the nulls reach both PATCHes; green on the base). Red on `d3497be`: 10 of the 18 offline failed (the five boxes and a typed-then-emptied price `<missing>`; the spool empty weight `<missing>`, not 200; the filament empty weight refilled with the brand's 180; no touched set, twice), and the real-page case failed (`settings_bed_temp` missing). The 8 controls and pins passed there, and each pin fails on a mutant of the fix (copies of the modules in the scratchpad, loaded through a pytest plugin, no repo file touched): touch ignored, 3 tests; no badInput guard, 1; reset keeps the set, 1; cross-inherit gate in every mode, 1; `change` counted, 1.
- **Test runs (from inventory-hub/):** the new file `--offline` on the base 10 failed / 8 passed / 1 skipped, and its real-page case alone 1 failed; after, 18 passed / 1 skipped, and the real-page case 1 passed; the five mutants as above. Every file that loads `inv_wizard.js` or drives the wizard's Save, the routes and the cascade (48 files) `--offline`: 832 passed, 249 skipped (2:43). The wizard's browser files against the dev container (20 files: 54.5, 58.5, the price / product cascade, location, e2e, vendor edit, per-spool scan, collapse, vendor create, the empty-weight fallback and prefill family, UX polish, groups 10 and 25, the overlay migration, `test_wizard.py`, the weight-setting events, the field files): 164 passed (2:49; it labelled itself BUSY RUN at 1.38×, with no red).
- **Left / surprising.** (a) **Pre-existing, outside 54.5: in Edit Spool a typed filament empty weight replaces the spool's own.** `wizardSetupFieldSync` (wired in every mode) copies the filament's Spool Wt box into the spool's on every keystroke, so correcting the filament's 200 to 205 puts 205 in the spool's box over its own measured 196, and Save writes 205 as the spool's own, while the spool's weight section is collapsed by default. 54.5 doesn't change it (a copy is no touch, so never a clear); suggested as a standalone buglist item: in edit mode, copy only into a spool box that shows an inherited value. (b) The extras' touched set still counts `change`, so the stale `change` above could in principle mark an extra touched in the next session, but only if the extra's box kept the focus from one session to the next, which no close I traced allows (see call 1). Left as it is; not reproduced; noted for the review. (c) Spoolman leaves a null field out of a record, so the route's diff sends `price: null` even for a spool with no price (`k not in original_spool`): a no-op write, harmless.

**b3-price-mark, 2026-11-09: 54.8. Done.** Commit `c536fe8` (code + tests). The "before" pictures were taken on `4a896e8`'s wizard before any code changed, and the "after" ones with the same capture.

- **The pictures, for Derek** (`review-samples/2026-11-08-group54/`, git-ignored): 1a / 1b a new spool of a filament priced 25.00 with Pricing & Metadata closed (its summary), 2a / 2b the same open (the price box), 3a / 3b an edit of a spool with no price of its own whose filament is priced 25.00, closed, 4a / 4b the same open, and 5 the same edit's empty-weight box with its "↩ from filament" badge (taken after, and before too so the two can be compared). Each is the wizard's window as it shows on the 1600×1300 dashboard at 1x, cropped to the window's visible part, never scaled. The capture is `tests/test_price_mark_pictures_54_8.py` (not a check: it skips unless `G54_PICS=1`; `G54_PICS_PHASE=before|after`). Its spool and filament are made up (#9001 / #9002, "Example Brand PLA, Ocean Blue", 25.00, 200 g) and served in the browser, every write is answered in the browser (`test_text_size_guard._read_only`), and Save is never pressed. Pixel diffs of before against after: 1 and 3 differ only in the summary line; 5's top 770 px (the whole weight section) is identical, its other differences being the price section under it; in 2 and 4 the badge makes the label line about a pixel taller, so what is below it moves.
- **The change (`inv_wizard.js`, `modals_wizard.html`; the server is unchanged).** `wizardPrefillSpoolPrice` records where the shown price came from (`wizardState.spoolPriceFrom`: `'filament'` or null, reset by `wizardReset`) and `window.wizardRefreshSpoolPriceMark` shows the badge (`#wiz-spool-price-inherited-badge`, beside Price Paid, the empty-weight badge's classes, `--fcc-fs-label`) while `wizardSpoolPriceIsFilaments()` (from the filament, and not in 54.5's touched set). The wizard's `input` listener refreshes it after noting the touch, so a key typed in the box takes the mark away. The summary reads "$25 ↩ from filament" while marked. Save deletes `sp_payload.price` while marked, after 54.5's null-drop, so 54.5's emptied box is still sent as null in edit mode. The twin: `wizardSetSpoolEmptyWeightInherited` records `wizardState.spoolEmptyWeightFrom` (`'filament'` / `'vendor'` when it shows an inherited value), `wizardClearSpoolEmptyWeightBadge` clears it, and in Edit Spool Save deletes `sp_payload.spool_weight` while `wizardSpoolEmptyWeightIsInherited()` (inherited and untouched). The weigh window's `onSubmit` calls `wizardClearSpoolEmptyWeightBadge` when it fills an empty spool box, because that tare is the person's: the badge used to stay up over it, and with the twin Save would have left it out.
- **The import check:** nothing but the prefill writes `#wiz-spool-price` (a grep of `static/js`: the prefill, the touched map and Save; no external template or Prusament override carries a price), so no import's price needs marking as the spool's own.
- **Tests:** new `tests/test_wizard_price_mark_54_8.py`, 23 items: 22 hermetic on the Group 58.5 harness (they run under `--offline`; the fixture and helpers are 54.5's) and one real-dashboard case (a new spool of a stubbed $25 filament: the summary, the badge once the section is opened by a click, and the create POST read in the browser has no `price` and keeps L34's `spool_weight: 200`). `tests/test_contrast_guard.py` gains `test_the_wizards_price_from_the_filament_is_readable` (the summary scored from its toggle, and the badge from its column, each proved scored at 100:1; the toggle's ▾ is left out, see (c) below). `tests/test_wizard_price_product_cascade_e2e.py`'s four prefill cases now pin the mark as well (updated deliberately).
- **Red first.** On `4a896e8` (HEAD's module and template copied into the scratchpad and loaded through a scratch pytest plugin, no repo file touched), 12 of the 22 hermetic cases failed, each for its stated reason: `price: 25` sent for a new spool, an edited spool and a clone; no badge (5 tests); the summary "$25"; 200, 180 and a followed 205 sent as an edited spool's own empty weight; and the badge left up over a tare from the weigh window. The 10 pins and controls passed there. Each pin fails on a copy of the fix with one rule taken out: typing ignored, 5 tests; the reset keeps the mark, 1; the twin in every mode, 2; the weigh window keeps the mark, 1; an own price marked, 5. The real-page case was red before any code changed (the summary "$25"), and it and the contrast check were red again on the container with HEAD's two files put back for one run (backed up to the scratchpad, then restored and checked byte for byte with `cmp`).
- **Test runs (from inventory-hub/):** the new file `--offline` on the base copy 12 failed / 10 passed / 1 skipped; after, 23 passed with the container; the five mutants as above. Every test file that loads or drives the wizard, its routes or its cascade (74 files) plus `test_text_size_floor.py`, `--offline`: 1056 passed, 367 skipped (3:45). The wizard's browser files against the container (21 files plus the wizard cases of the contrast, text-size, visual-baseline and structural checks): 179 passed (3:19; BUSY RUN at 1.34×, no red).
- **Claude's calls.** (1) The summary's words are "$25 ↩ from filament", the arrow and the info colour tying them to the badge. (2) A filament price of 0 is still shown, marked, as the cascade drew it; it is no longer saved. (3) The tooltip: "The filament's price: this spool has no price of its own, and saving keeps it that way. Type a price to give the spool its own." (4) A tare from the weigh window is the spool's own (above). (5) The capture lives in `tests/` (gated by `G54_PICS`) rather than the scratchpad, so a review fix or Derek's next look can take the pictures again.
- **Left / surprising.** (a) **The filament side of the twin (not built; suggested as a standalone buglist item).** Edit Spool's open fills the FILAMENT's empty-weight box with its brand's value when the filament has none (`resolveEmptySpoolWeight({filamentWt, vendor})`, with no badge on that box), and Save writes it as the filament's own. So 54.5's clear of a filament empty weight comes back at the next Save whenever the brand has one, and a later change to the brand's value no longer reaches that filament. A fix needs a mark on the filament's box (a look change). (b) `wizardSetupFieldSync` copies the filament box into the spool's on `change` (at blur) as well as `input`, so an emptied filament box blanks the spool's box again at the next blur. My first weigh-window test opened the weigh window without a blur, and the Save click's blur emptied the tare; a person's click on "Weigh from scale…" blurs first, and the test now presses that real button. It is the same copy as b2's (a). (c) The section toggle's ▾ is 3.71:1 (#6c757d on #1a1a1a), a state glyph rather than text (WCAG asks 3:1 of a control's parts), older than 54.8 and never measured before; the contrast check leaves it out by its class and says why.

**b4-migration-weigh, 2026-11-09: 54.4 and 54.7 (page half). Both done.** Commits `94f87de` (54.4) and `95b4298` (54.7 page half). Each new test file was run red on its part's base, and each red failed for the reason its test names.

- **54.4, `setup-and-rebuild/setup_fields.py`** (plain `requests`, no `spoolman_api` import; the file parses, and its new helpers run, on the container's Python 3.9.25). The snapshot asks for archived spools too (`params={"allow_archived": "true"}`) and keeps where each spool was. `_as_text_wire` puts every value in the text type's wire form before anything is deleted. `_restore_container_slot` restores each spool through a fresh `GET /api/v1/spool/<id>` and a PATCH of its whole `extra`, and takes that read as the last look: a spool deleted since is "gone"; one holding a `container_slot` again, or somewhere else now, is "kept"; one it can't read is sent nothing ("failed"). A write that reports failure is read again before it is called failed. The run prints restored / kept / gone / failed and every value a failure kept from coming back (`#12: 2 (at LR-MDB-1)`). A rebuild that fails after its DELETE prints every snapshotted value; one refused at the DELETE re-reads the field and says every value is still in Spoolman. A spool list whose 200 isn't JSON, or isn't a list, aborts before the DELETE; it used to raise out of setup_fields, which skipped every field set up after it. `tests/test_setup_fields_idempotent.py`'s restore test is updated deliberately: it answers the per-spool GET as Spoolman would after the DELETE (the record without its slot), checks that the snapshot asks for archived spools, and checks that the sibling `other` goes back.
  - **Claude's calls.** (1) The converter keeps a non-string JSON value's own text ('true' → '"true"', '2.50' → '"2.50"'; a list or object too), not the plan's `json.dumps(str(decoded))`, which writes Python's "True" and reformats a number. (2) "kept" also covers a blank slot written since the rebuild (a move to a place with no slot writes "", so a key present at all is a newer write; the plan said non-blank), and a spool whose location changed since the snapshot (its old slot was a place in a box it has left: the review checklist's last look before each write). (3) The re-read after a write that reported failure (a timeout is a read timeout). (4) The DELETE-refused and unreadable-list cases above. (5) The CLAUDE.md sentence is owed text #6, not an edit in the 54.4 commit as the planning pass said: in this workflow b5 applies them all.
- **54.7, the page half (`inv_weigh_out.js` only).** `saveSpoolWeight` takes a sixth argument, `how` (`{archiveSwitch, empties, wasArchived}`), and sends `archiveSwitch` as `auto_archive`, a real boolean, per b1's contract. A weigh-out row's save and its details fallback send the list's switch (`listArchiveSwitch`). The Quick-Weigh's `onSubmit` sends its own switch, never the list's, whose markup is on the page, hidden, with a state of its own. It is always the switch and never the per-save verdict; with the switch on, `archived: true` and the force-unassign are unchanged. With the switch off and a save that leaves 0 g by the page's own reading, the success toast reads "Updated Spool #57: 0 g left, kept in stock (Auto-Archive is off)" for 4 s. That doesn't apply to a spool already archived before the save (the weigh-out details now carry `archived`, the fallback reads the scan buffer's entry, the Quick-Weigh its own read), nor to one the answer says was archived. A caller that names no switch sends the list's only where it leaves the verdict to `saveSpoolWeight`, as that path always read it, else no `auto_archive`, so the server's rule decides as before (`test_single_slot_lifecycle_js`'s 4-argument call is one). Grep: `saveSpoolWeight` has no other caller in `static/` or `templates/`, and it is the page's only `/api/spool/update` caller.
  - **Claude's calls.** (1) The kept toast takes 4 s, CLAUDE.md's success toast; the plain "Updated Spool #57" keeps `showToast`'s 2 s default, as before. (2) "Kept in stock" is not said for a spool archived before the save, which stays archived (the server's rule), nor when the answer's `auto_archived` is true.
- **Tests.**
  - New `tests/test_setup_fields_migration_54_4.py`, 33 items. `FieldFake` is `SpoolmanHTTPFake` plus Spoolman's field DELETE and POST, a `params`-aware `get`, and switches for a failed read, a refused or timed-out PATCH, a failed POST or DELETE, a hook after the POST, and an unreadable list. It covers the spec's (a) to (f), the converter, the last-look cases and the failure prints.
  - New `tests/test_auto_archive_switch_page_54_7_js.py`, 20 items, hermetic: the weigh-out family's `isolated_page` harness from `test_weigh_out_scan_focus_js.py`, plus `weight_entry.js`. It covers a row save, the fallback and the Quick-Weigh, each with the switch on and off, emptying the spool or not; the Quick-Weigh against the list's switch set the other way; the kept toast's 4 s; archived spools; and an older caller.
  - New `tests/test_auto_archive_switch_real_54_7_e2e.py`, integration-gated. The real Quick-Weigh on the dev container, with its switch off, weighs a throwaway spool on dev's Spoolman to 0 g; the spool stays in stock at its place with no pre-archive note, and the toast says so. The conftest fixtures delete its records.
  - `tests/test_weigh_out_scan_focus_js.py` is updated deliberately: its 14 exact POST bodies (17 tests) now carry `"auto_archive": True`, the list's switch, which is on in those tests. Each of the 17 differed from the new body by that key alone (checked from the failure report before the update).
- **Red first.**
  - 54.4 on `224bc63`: 30 failed / 3 passed. The 3 are the 0.27 string control, the already-text no-op and the no-app-import canary. With `HEAD`'s `setup_fields.py` loaded through a scratch plugin, both files gave 31 failed / 9 passed: the 30, plus the updated idempotent test.
  - 54.7 page on `94f87de` (`HEAD`'s `inv_weigh_out.js` served through a scratch plugin): 19 failed / 1 passed. Every POST body lacked `auto_archive` and no kept toast came; the older-caller control passed.
  - Six mutants of the page fix (scratch copies served through the plugin, no repo file touched): no kept toast, 5 failed; an archived spool called kept, 2; the verdict sent for the switch, 4; the Quick-Weigh sending the list's switch, 5; only `false` sent, 8; the kept toast at 2 s, 1.
  - The real-chain check was red with `HEAD`'s `inv_weigh_out.js` served for one run (the answer's `auto_archived` was true). The fixed file was restored and checked byte for byte with `cmp`. The check was green before and after.
- **Test runs (from inventory-hub/).**
  - 54.4, its two files: 40 passed. With the 6 other files that read `setup_fields.py` (`test_extras_clear_027`, `test_filament_attributes_auto_cleanup`, `test_single_slot_box_lifecycle`, `test_stock_exclusion`, `test_wizard_field_order`, `test_spoolman_integration`) `--offline`: 311 passed, 10 skipped.
  - 54.7, the weigh-out family `--offline` (13 files) before the focus update: 401 passed, 17 failed (the focus pins above), 42 skipped. After it, the focus file, the page file and `test_single_slot_lifecycle_js`: 146 passed.
  - The weigh browser files on the container (`test_weigh_out_e2e`, `test_weigh_out_preserve_text_e2e`, `test_weight_entry_overlay`, `test_text_size_guard`'s `test_questions_text_is_readable` and the real-chain check with `--run-integration`): 28 passed.
  - Both families together at `95b4298`, `--offline` (23 files: the 13 weigh-out files, the page and real-chain files, `test_weight_setting_dispatches_events` and the 8 `setup_fields` files): 737 passed, 54 skipped (3:43).
- **Left / surprising.**
  - `showToast`'s default duration is 2 s, though CLAUDE.md says success toasts are 4 s. Only the new message takes 4 s here.
  - `test_weigh_out_scan_focus_js.py` pinned exact POST bodies; the plan's list of existing tests didn't name it.
  - The real-chain check runs only with `--run-integration`, so the orchestrator's sweep skips it. Each run leaves an "is out" WARNING in dev's Activity Log for its throwaway filament ("⚠️ __fcc_test_vendor__ PLA __Fcc_Test_Filament_… is out: #299 was its last spool in stock"): the low-stock check, harmless.
  - Dev's Spoolman reused deleted ids for the throwaway records (filament #224 and spool #299, b2's deleted check records' ids), so a "deleted, reads 404" check by id can later find a new record.
  - 54.4's "kept" line prints the raw wire value (`'"4"'`). It is accurate but technical; the migration is dormant.
  - This file's owed-text header said "B4 applies them all" from the numbering before `7cb6988`. It now names b5-chips-docs.

**b5-chips-docs, 2026-11-09: 54.2, the `?v=` bumps and the owed CLAUDE.md text. Done.** Commits `724f022` (54.2, tests only), `e067c00` (cache bust), `cc11239` (CLAUDE.md), and this entry.

- **54.2: nothing broke at 1600x1300, so no code changed and there is no look change (no 6a / 6b pictures).**
  - New `tests/test_max_attribute_chips_e2e.py`, 3 browser tests. The real dashboard on the dev container. Every read the four windows make is answered in the browser from made-up records: spool #9541; filament #9542 with all 28 in Spoolman's wire form; a field list shaped like dev's, with the 28 as choices; materials, brands, filaments and locations. Every request that isn't a read is answered in the browser too. The heartbeat and log polls are cut off (`conftest.quiet_heartbeat`), so nothing live repaints a window while it is measured and no "N new" log pill floats over it. The scan buffer is the page's own. Nothing reaches dev.
  - One page session per size walks the spool window, the filament window, its Edit Filament form (opened by its ✏️) and the wizard's Edit Spool. In the wizard, Custom Filament Attributes is opened by its toggle, as a person does, because every optional section opens closed.
  - Per window, it checks:
    - 28 chips, in the filament's order;
    - each chip inside its box and inside the window (`getBoundingClientRect`);
    - more than one row;
    - no sideways scroll on the box, the window's body, its frame (the `.modal`) or the page;
    - the window inside the screen;
    - the controls after the chips can be reached. They are the next field and the window's last button: Close, ✏️ Edit Filament, the tag box, Save, the wizard's ➕, Slicer Profile and SAVE CHANGES. Each is scrolled to (up and down only), must sit inside the window and on the screen, and must be what `elementFromPoint` finds at its centre.
  - Results:
    - Committed sizes, 1600x1300 and 1366x768 at Text size Extra Large: everything holds. At 1600 the chips take 3 rows in the two detail windows, 4 in Edit Filament and 6 in the wizard.
    - Explored with a scratch plugin, not committed: 1366x768 Standard, 1600x1300 Extra Large, 1280x600 Large and 1024x700 Extra Large. Everything holds.
  - **At 390x844 (a phone), the chips hold (13 to 16 rows), but two footers don't. That is the phone view, not the attributes.**
    - The spool window's and the filament window's footer row of buttons doesn't wrap. So Close sticks out past the window's right edge (the spool window's at x 370 to 435, the filament window's at 327 to 392, with the window at 8 to 382), and the window's frame scrolls sideways (435 and 392 px of content in 390).
    - It is the same, to the pixel, with one attribute as with 28, and at Extra Large it reads 540 and 487 px. So it is recorded in the test's `PHONE_KNOWN` for the phone-view work rather than fixed.
    - A finding not on that list fails the phone test, and so does a window whose Close no longer sticks out (take it off the list then).
    - Edit Filament and the wizard hold at 390.
  - New `TestSearchWithAMaxAttributeFilament` in `tests/test_max_attributes_supported.py`, 61 offline tests on `test_search_api`'s `_attr_filament` / `_attr_get`:
    - each of the 28 finds the filament (filament target) and its spool (spool target), and nothing else;
    - all 28 in one query (33 words) find it;
    - a control finds the plain filament by its own words, which shows the 28 queries discriminate;
    - `filament_attribute_list` gives all 28 in order, from the wire form and from the parsed one;
    - both cards' line (the spool card's `format_spool_display` and the filament card's own builder) is every attribute in order, then "PLA".
  - A side probe (a scratch script, not committed): in the search panel, the card with that 28-word material line wraps it over 5 lines (6 at 390 px) inside the card. Nothing sticks out at 1600 or at 390.
- **The proof that the checks bite.** Scratch plugins outside the repo either set the test module's `ATTRS` / `EXTRA_CSS` hooks or patch `spoolman_api` in memory (`scratchpad/g54/bite_542.py`, `mut_search_542.py`). No repo file was touched.
  - E2E (all three tests each time):
    - the stub cut to one attribute: 3 failed (12 × "1 chips, not 28" and 12 × "1 row(s)": every window, every size);
    - the 28 reversed: 3 failed (the order, 12×);
    - the chip boxes made not to wrap (`NOWRAP_CSS`): 3 failed. That is 228 chips outside the window, the body scrolling sideways 12×, the frame 7×, one row 12×, and the wizard's tag box and ➕ pushed out of the window 6×;
    - not wrapping and held to their line's width ("boxed"): 3 failed, adding 175 chips outside their box and the box scrolling sideways 9×. The wizard's box grows with its chips, so for the wizard the window checks catch it.
  - Never fired in any run, so not proven to bite; kept as guards: "the page scrolls sideways" (the windows are fixed-position, so they can't widen the page), "the window is wider than the screen", and the reach check's "off the screen", "covered" and "isn't drawn".
  - Search:
    - `filament_attribute_list` answering [] fails 59 of 61; the control and the card line, which don't use it, pass;
    - capped at 10 fails 37 (Matte is still found through "Duel Matte": the search matches substrings);
    - the card's line cut to 3 words fails the card test only.
- **Cache bust (`e067c00`).** The two static files the branch changes, in `scripts.html`: `inv_wizard.js` 15 → 16 and `inv_weigh_out.js` 2.2 → 2.3. No test pins a `?v=`, and the dev dashboard serves the new ones.
- **CLAUDE.md (`cc11239`).** All seven owed entries were applied, in order, by `scratchpad/g54/apply_owed_claude_md.py`, which:
  - reads each entry's heading to decide between replace and insert, and takes its two fenced blocks;
  - applies an entry only when its anchor occurs exactly once at its turn;
  - checks that the new text occurs once afterwards;
  - keeps CRLF.

  None was skipped, and a second run finds all seven already applied. 54.2 owes none: CLAUDE.md describes neither the chips nor their tests.
- **Test runs (from inventory-hub/):**
  - First draft, against the container: the desktop test 1 passed; the phone test 1 failed (the two footers).
  - Draft bite runs: one attribute 2 failed; nowrap 2 failed; boxed and reversed (desktop) 1 failed each.
  - Explored sizes: the five above 1 passed each. The phone at Extra Large 1 failed (the same footers), and the same with one attribute.
  - The final file: 3 passed, four runs in a row (about 20 s each).
  - Final bite runs: one, reversed, nowrap and boxed: 3 failed each.
  - `test_max_attributes_supported.py --offline`: 71 passed. The class alone: 61 passed. Mutants: empty 59 failed / 2 passed; cap10 37 / 24; cardcut 1 / 60.
  - `--offline` with the new E2E file, the supported file and `test_offline_mode.py`: 89 passed, 3 skipped (the E2E file skips offline).
  - Related offline (`test_search_api`, `test_l316_charact_filament_attributes_unit`, `test_max_attributes_supported`, `test_filament_attrs_split_54_3`): 139 passed.
  - Browser: `test_detail_modal_attributes` plus the new file: 7 passed. After the `?v=` bump, the new file plus `test_weight_entry_overlay`: 26 passed.
  - The CLAUDE.md script: the check found 7 to apply; the write applied 7; a re-check found 7 already applied.
- **Claude's calls.**
  1. The phone footers are recorded in the test, strictly (Close must still stick out), rather than marked xfail, so the phone run still guards everything else.
  2. A third committed size, 1366x768 at Extra Large (the review checklist's small laptop and large text). It costs about 7 s.
  3. The heartbeat is cut off for the walk.
  4. Edit Filament is opened by a DOM click on the filament window's ✏️, which runs the same handler; the reach check covers the ✏️ itself.
- **Left / surprising.**
  - (a) The phone footers want a standalone buglist item for the phone-view work. Not filed: like b1, I left `Feature-Buglist.md` alone.
  - (b) **Pre-existing, outside 54.2: the wizard's chips build their HTML with the attribute unescaped.** Both builders do it: `wizardAddMultiChoiceChip` (`inv_wizard.js:2234-2238`) and Edit Spool's prefill (`:4759-4760`), as `data-value="${val}">${val} &times;`.
    - A probe swapped the 28th attribute for `Odd "Quote" <b>Tag</b> & Co`. The spool window, the filament window and Edit Filament show it whole, because they escape it. The wizard's chip reads "Odd".
    - Save collects the chips by `data-value`, so it would send "Odd". Spoolman 0.27 refuses a value that isn't a choice, so the filament's save would fail; were "Odd" a choice, the attribute would be swapped silently.
    - `validateNewChoice` lets a quote or `<` into a new choice. No such choice exists on dev today.
    - Suggested as a standalone item: escape the value in both builders, as the other windows do.
  - (c) The planning pass's wizard anchors had drifted. The chip box is now built by `wizardGenerateFieldHTML` (`inv_wizard.js:2116`, `chip-container-fil-<key>`), `wizardAddMultiChoiceChip` is at `:2176`, and the edit prefill's chip loop is at `:4741-4762`. The Edit Filament chips are at `inv_details.js:2219-2240`, as filed.

### Review fixes, 2026-11-09

_(Each fixer appends: the findings fixed with their commits, the tests added, each test run with its counts, anything left or surprising.)_

**X1-server, 2026-11-09: R1-1, R1-2, R3-3, R3-4. All done, all offline.** Commits `9c40996` (R1-1), `7c831c6` (R1-2), `321c5d8` (R3-3), `4eb9f15` (R3-4), then this entry with CLAUDE.md (one docs commit). Each new test was run red on the commit before its fix, and each red failed for the reason the finding gives.

- **R1-1** (`spoolman_api.update_spool`): the archive edge runs only on a record FCC read (`existing.get('id') is not None`). With none (no answer, a 404 or 5xx body) the write goes out as the caller sent it, so the weigh-out fallback's own `archived: true` archives the spool where it is, and the page's force-unassign then takes it off its head and releases its single-slot box, as before 54.6. That covers a blind used + initial weight write too. Seven new tests in `tests/test_archive_on_remaining_weight_54_6.py`: the fallback, then the real force-unassign, over `WeighedWireSpoolman` with `get_spool` failing (no answer, a 5xx body); `update_spool` over `SpoolmanHTTPFake` on an unread spool (weight left, used + initial; both failures); a control (a read spool with no capacity is still archived). Red on `d60c86e`: 6 failed, 2 passed (the control and the existing `test_it_needs_no_known_capacity`).
- **R1-2** (`spoolman_api.update_spool`): the 📦 and 📤 lines are written only once the write lands, by `_log_archive_change` after `r.ok`, or by `_after_unanswered_write` once a re-read of a timed-out PATCH shows the change landed where the write put it (the Group 42 review's `_release_box_if_archive_landed`, renamed and widened; it still releases the box only for an archive that blanked the location, and now runs only when the PATCH was sent). `_archive_line` words it: "📦 Auto-archived Spool #N (remaining weight hit 0)" when the edge read the spool as empty (`_auto_archive_on_empty` now returns True then), else "📦 Archived Spool #N"; then "moved to UNASSIGNED" only when the write blanked a place the spool had, "still Unassigned" when it had none, "moved to <place>" for a place the write named, else "still at <place>" (from Spoolman's answer or FCC's read), the place HTML-escaped. New `tests/test_archive_log_after_write_54.py`, 24 tests (refused writes, FCC's own pre-merge refusal, landed archives in each wording, timeouts that land or don't, controls for today's words). Red on `9c40996`: 18 failed, 6 passed (the controls). No existing pin encoded the false line, so none was changed.
- **R3-3** (`setup-and-rebuild/setup_fields.py`): `_read_field_definition` answers (field, None), (None, None) or (None, why) and never raises (no answer of any kind, an HTTP error, a body that isn't JSON or isn't a list; entries that aren't objects are skipped); `_get_field_definition` keeps its contract on top of it. The migration says when it couldn't read the list ("Couldn't read Spoolman's spool field list (its answer wasn't JSON); skipping the container_slot migration this run, with nothing changed.") instead of "not present yet", and the rebuild-failure branch says when its re-read failed, then prints every value. Six new tests and a control in `tests/test_setup_fields_migration_54_4.py` (`FieldFake.field_read_answers`), one of them running the whole script as update.sh does. Red on `7c831c6`: 6 failed (ValueError ×3, AttributeError ×2, the words ×1), the control passed.
- **R3-4**: CLAUDE.md's 54.5 sentence and its owed-text copy (#4 below) now say "(checked on dev's 0.27.1, 2026-11-09, together with the filament's price, which no box clears): the five boxes are …".
- **CLAUDE.md** (the docs commit): the `/api/spool/update` row's 54.6 sentence gains R1-1's rule, a new sentence there gives R1-2's (when the 📦 / 📤 lines are written and what they say), and the setup_fields template rule gains R3-3's read. No static file changed, so no `?v=` bump.
- **Test runs (all `--offline`, from inventory-hub/):** R1-1: the 54.6 file 26 passed; the 103 test files that drive `update_spool`, the route or the harnesses, plus the route pin and the extra-patch canary, 2992 passed, 34 skipped (6:42). R1-2: the new file 24 passed; with the 54.6, 54.7, 51.1, 42-review and archive-helper files, 151 passed; the 103 files plus the new one and the two pins, 3016 passed, 34 skipped (6:31); the 75 other test files that read the Activity Log or `archived`, 1396 passed, 293 skipped (5:52). R3-3: the migration file 40 passed, with `test_setup_fields_idempotent` 47; the 11 files that read `setup_fields.py`, 365 passed, 11 skipped. At `4eb9f15`, the ten touched families together: 260 passed. The reviewers' probes (`C1/probe_blind_archive.py`, `C1/probe_log_before_write.py`, `R3/probe_rebuild_fail_reread.py`, `R3/probe_field_list_not_json.py`) all behave after the fixes.
- **Claude's calls.** (1) R1-2: "Auto-archived … (remaining weight hit 0)" whenever the edge read the spool as empty, also when the caller set `archived` itself (a weigh screen with Auto-Archive on, the wizard's box at 0 g): the weight did hit 0 and FCC's rule would have archived it anyway, so today's words stay true there. "📦 Archived" is for an archive with weight left, or a spool FCC couldn't read. (2) "still Unassigned" for a spool that already had no place, where the finding's literal rule (location '') would have said "moved to UNASSIGNED". (3) The timed-out re-read covers every write that archives or un-archives, not only the edge's blank-location archive, and logs the 📤 line and its 42.3c warning too. (4) R3-3's read catches any exception from `requests.get`, not just a RequestException, since a crash there stops every later field on a deploy.
- **Left / surprising.** (a) Pre-existing, outside these findings: `/api/spool/update` keeps a 5xx body from its own pre-read as `pre` (`get_spool(...) or {}` keeps the truthy error dict), so `_log_manual_weight_change` logs a made-up "before" (a probe's line: "✏️ Weight updated — Spool #57: [0.0g ➔ 0.0g remaining] (used 0.0g ➔ 1000.0g) [total 0.0g ➔ 1000.0g]") and the low-stock check reads it too. Suggested as a standalone item: treat a `pre` with no id as unread, as `update_spool` now does. (b) `setup-and-rebuild/migrate_filament_attributes.py` has its own copy of the unguarded field-list read; it is a manual one-off that update.sh doesn't run, so it was left.

**X2-weigh, 2026-11-09: R3-1 with R3-2, then R1-3. All done.** Commits `d132506` (R3-1 + R3-2, one commit: one cause), `5890e5e` (R1-3), then this entry with CLAUDE.md and the `?v=` bump (one docs commit). Each new test was run red on the commit before its fix, and each red failed for the reason the finding gives.

- **R3-1 / R3-2** (`inv_weigh_out.js`, `saveWeighOutRow`): the window's mode and the list's Auto-Archive switch are read once, at the Enter or 💾 press, before any await, and used for the verdict, `how.archiveSwitch`, the fallback's Net-only check and `computeRowResult`, which takes the mode as an argument now (a row's preview passes the window's mode). The fallback also passes its verdict to `saveSpoolWeight`, which read the switch itself, late, when given none. Read after a wait by design (checked, and said in the code): the spool's own state (its details; the fallback's scan buffer entry), the tare the prompt gives, where the focus is and what was typed meanwhile (the late tare prompt's check), and the row as drawn now. Tests: `test_auto_archive_switch_page_54_7_js.py`, `test_a_save_that_waits_for_its_details_sends_the_switch_as_it_was_at_enter` (off / on at Enter × details / fallback: #57's details held, the switch clicked meanwhile); `test_weigh_out_scan_focus_js.py`, `test_a_save_that_waits_for_its_details_reads_the_mode_as_it_was_at_enter` [Net 425, then Set Used: 325 g used] [Additive 0, then Net: 100 g used, no archive], `test_with_no_details_an_additive_reading_stays_unsaved_after_a_click_on_net` and `test_with_no_details_a_net_reading_is_saved_after_a_click_on_additive`. Red on `c2f4222`: 8 of 8 (the switch as clicked: archived and force-unassigned, or kept in stock; 425; 750, archived and unassigned; saved as 25 g left; nothing saved).
- **R1-3** (`saveSpoolWeight`): a refused save's toast is the route's `msg`, else its `error`, else "Failed to update weight", for 7 s, and "Error updating weight" (no answer it could read) for 7 s. **The Activity Log check found no line:** the route and `update_spool` write a refused weight write only to hub.log (`state.logger`, which isn't the Activity Log), and a save with no answer reaches no log. So the page writes the one line, through `window.logClientEvent` (ERROR), as Quick-Swap, Return and Assign do for theirs: "❌ Spool #57: <the toast's words>", with the raw `error` after them where `msg` doesn't hold it (today it does), and the `.catch`'s error words; escaped. New `tests/test_weigh_save_failure_toast_js.py`, 7 tests: 6 on node's `vm` (`run_js`: the toast's exact arguments and the log line) and 1 on the real weigh-out window (`isolated_page`: the words on screen, '<' and quotes whole, still up at 2.7 s; the log POST escaped; the row open again). Red on `d132506`: 7 of 7, through a scratch pytest plugin that serves that commit's module from a scratch copy (no repo file touched); the same plugin over a copy of the fix's modules: 7 passed.
- **Test runs (from inventory-hub/, `--offline` unless said):** the 8 R3 pins 8 passed; the weigh-out family (13 files: the focus, 54.7 page, Quick-Weigh, weight-box, single-slot, dispatch, source-presence, door canary, scan-path, compute, scan-queue, buffer-order and empty-weight-prompt files) after R3, 402 passed, 43 skipped (3:48); the R1-3 file 7 passed; the family with it (14 files) after R1-3, 409 passed, 43 skipped (3:48). On the dev container: `test_weigh_out_e2e`, `test_weigh_out_preserve_text_e2e` and `test_weight_entry_overlay` 26 passed (0:33), and `test_auto_archive_switch_real_54_7_e2e` with `--run-integration` 1 passed (its throwaway filament and spool are gone from dev's Spoolman, checked; the long-lived `__fcc_test_vendor__` stays by design). After the bump, dev's dashboard serves `inv_weigh_out.js?v=2.4`.
- **Claude's calls.** (1) The Activity Log line (above): the finding expected the route to log the failure; it doesn't, so the page writes the only line. (2) The log keeps the route's raw `error` when its `msg` doesn't hold it, so a route that words its `msg` (below) still leaves the raw text in the log, as CLAUDE.md asks of a log line, with no page change. (3) The toast follows the finding (the route's `msg`); see (a).
- **Left / surprising.** (a) **The route's raw reason doesn't fit FCC's toast.** A scratch probe on the dev dashboard (every request answered in the browser, nothing written; `scratchpad/g54fix/probe_error_toast_sizes.py`, its screenshots in `scratchpad/g54fix/shots/`): at 1600×1300, 1366×768 and 390×844, Standard and Extra Large, a Spoolman 422 JSON body, a read timeout ("HTTPConnectionPool(host=…, port=…): Read timed out. (read timeout=15)") and a refused connection each run past the toast's border (their tokens have no break, and `.toast-msg` has no `overflow-wrap`), and on the phone the refused connection's toast is 932 px (Standard) to 1268 px (Extra Large) tall in an 844 px screen, cut at top and bottom. "Failed to update weight" fit everywhere. The fix belongs on the server, outside my files: answer `msg` worded through `spoolman_api.refusal_words(err)` (CLAUDE.md's rule for a refusal a person reads away from a log line, "so no Spoolman address reaches a person") and keep the raw `err` in `error`; this page then toasts the words and logs the raw, unchanged. Optionally `.toast-msg { overflow-wrap: anywhere; }` in global.css, for every surface on CLAUDE.md's pattern (b) (`showToast(err, "error", 7000)`), which has the same overflow. (b) The Quick-Weigh reads its own switch after its tare prompt too (`weight_entry.js`), but that prompt's overlay covers the whole window, so no click reaches the switch meanwhile: left as it is.

### Owed CLAUDE.md text

_(Each builder appends the CLAUDE.md sentences its parts make stale or owe, quoting the anchor sentence. b5-chips-docs applies them all with an anchor-checked script, one commit. This line said "B4", the builder numbering before `7cb6988`, where B4 was the chips-and-docs builder; b1's and b3's notes saying "b4" mean the same builder.)_

**From b1-server (54.6, 54.7 server half, 54.1; 54.3 owes nothing, since CLAUDE.md doesn't describe the attribute parser).** All three sit in the "Spool / Filament write surfaces" table. Each anchor and each new text is one line of CLAUDE.md, in its own fenced block, exactly as it is or is to be (checked against CLAUDE.md on 2026-11-09).

1. **54.6 (replace the anchor with the new text).** **Applied in `cc11239`.** In the `/api/spool/update` row. Anchor:

   ```text
   **Only a weight write is a refill (Group 51.1):** the unarchive edge runs only when a write carries `used_weight`, `initial_weight` or `remaining_weight` (the weigh-out row's fallback, Group 51 review; the archive edge still reads only the first two)
   ```

   New text:

   ```text
   **Only a weight write is a refill (Group 51.1):** the unarchive edge runs only when a write carries `used_weight`, `initial_weight` or `remaining_weight` (the weigh-out row's fallback, Group 51 review; since Group 54.6 the archive edge reads all three too, a `remaining_weight` without `used_weight` beside it read as the weight left, so the fallback row weighing a spool to 0 g archives it in that one write, with its note, its trail blanked and its single-slot box released; a weight left that isn't a number changes nothing)
   ```

2. **54.7 (insert the new text right after the anchor, one space between).** **Applied in `cc11239`.** Same row. Anchor:

   ```text
   ⚠️ Sending `initial_weight` here runs `_auto_archive_on_empty`/`_auto_unarchive_on_refill` — a too-low total can silently archive+unassign a loaded spool.
   ```

   New text:

   ```text
   **"Auto-Archive 0g" off means off (Group 54.7; Derek, 2026-11-07, (a)):** an optional top-level `auto_archive` beside `id` and `updates` is the weigh screen's switch. Only JSON `false` passes `update_spool(sid, data, archive_on_empty=False)`, which skips the archive edge entirely (no `archived` added, no location blank, no note, no trail blanks, no box release): a spool weighed to 0 g stays in stock where it is, `auto_archived` is false, the refill edge still runs, and an archived spool weighed to 0 g stays archived where it is. Absent, `true` or anything else (`"false"`, `0`, `null`) is the rule as before. The keyword is passed only for `false`, so a two-argument stand-in for `update_spool` still serves every other request (`tests/move_engine_harness`'s stand-ins take it; `WireSpoolman` hands it on only when False).
   ```

3. **54.1 (replace the anchor with the new text).** **Applied in `cc11239`.** The whole row. Anchor:

   ```text
   | `routes_scan.py` | `/api/update_filament` quick-edit | Reference impl — surfaces error in response JSON. |
   ```

   New text:

   ```text
   | `routes_scan.py` | `/api/update_filament` quick-edit | Reference impl — surfaces error in response JSON. A malformed request is refused with 400 before anything is read (Group 54.1; its siblings `/api/create_filament` and `PATCH /api/vendors/<id>` already did): a body that isn't a JSON object, no `id`, no `data` (naming the old {id, field, value} shape when the body carries `field` or `value`, whose generic 200 hid the attribute purge's restore no-op for months, plus one WARNING in hub.log naming the keys that came) and a `data` that isn't an object, each in its own words. `{id, data: {}}` keeps its 200 "No fields to update." Pinned by `tests/test_update_filament_payload_54_1.py`. |
   ```

**From b2-wizard-clears (54.5).** One entry, in the same table's `api_edit_spool_wizard` spool save row (the anchor checked against CLAUDE.md on 2026-11-09: it occurs once). 54.8 changes the price box after this, so b3 may extend the new text.

4. **54.5 (insert the new text right after the anchor, one space between).** **Applied in `cc11239`.** Anchor:

   ```text
   Pinned by `tests/test_wizard_extras_touched.py` (a browser) and `tests/test_extras_clear_027_js.py`.
   ```

   New text:

   ```text
   **Plain fields clear too (Group 54.5):** in edit mode a plain number box the user emptied is sent as `null`, which the route passes through and Spoolman takes as no value (checked on dev's 0.27.1, 2026-11-09, together with the filament's price, which no box clears): the five boxes are the spool's Price Paid and empty weight, and the filament's empty weight, Nozzle Min and Bed Min (`WIZ_NATIVE_CLEARABLE`, box id → `"<entity>:<key>"`). Only a box the user changed counts: `wizardState.touchedNative`, reset by `wizardReset` and filled by the wizard's `input` listener alone (a number box's `change` comes at blur and can belong to an edit made before the wizard was reset for the next spool), read per key through `wizardNativeTouched(entity, key)`. A box the page drew or blanked itself (the filament empty weight's copy into the spool's) is left out as before, and so is a number half typed (`validity.badInput`). The empty-weight cross-inherit at Save fills only the filament's side, and never a box emptied in edit mode; its spool line could never fire (the spool's nulls are dropped before it, since `13654bb`) and is gone. Initial and used weight are not cleared this way, and create, clone and external modes are unchanged. Pinned by `tests/test_wizard_native_clear_54_5.py`.
   ```

**From b3-price-mark (54.8).** One entry in the same row. CLAUDE.md says nothing about the price cascade today (no line holds "price"), so this follows 54.5's text: **apply it after #4**, whose last sentence is its anchor. That sentence occurs once in this task file and not yet in CLAUDE.md, so it occurs once in CLAUDE.md once #4 is in.

5. **54.8 (insert the new text right after the anchor, one space between; after #4).** **Applied in `cc11239`.** Anchor (the last sentence of #4's new text):

   ```text
   Pinned by `tests/test_wizard_native_clear_54_5.py`.
   ```

   New text:

   ```text
   **A price or empty weight the spool only inherits is not saved as its own (Group 54.8; Derek, 2026-11-07, (a): a filament's price "might not be the price that exact spool costs").** A spool with no price of its own shows its filament's in Price Paid, marked "↩ from filament" beside the label (`#wiz-spool-price-inherited-badge`, the empty-weight badge's look) and in the Pricing & Metadata summary ("$25 ↩ from filament"), and Save leaves it out: a new spool (the filament window's New Spool, or a Clone of a spool with no price of its own) is created with no price, and an edited spool keeps none (`wizardState.spoolPriceFrom`, set by `wizardPrefillSpoolPrice`, read through `wizardSpoolPriceIsFilaments`). A price typed there is the spool's own (the touched set; the mark goes), and so are an edit's own price and a clone's source spool's (a sibling bought together), which show plain and save as before. Its twin, in Edit Spool only: an empty weight the spool only inherits (its filament's or brand's, shown with its badge; `wizardState.spoolEmptyWeightFrom`) is not sent untouched (`wizardSpoolEmptyWeightIsInherited`), so the spool keeps having none of its own and 54.5's clear stays a clear; a tare the weigh window fills in is the spool's own. New spools and clones still take the cascade's empty weight as their own (L34). Pinned by `tests/test_wizard_price_mark_54_8.py` and `tests/test_contrast_guard.py`'s `test_the_wizards_price_from_the_filament_is_readable`.
   ```

**From b4-migration-weigh (54.4, 54.7 page half).** Two entries. A script applied all seven entries in order to an in-memory copy of CLAUDE.md (`scratchpad/g54/check_anchors_b4.py`, outside the repo): each anchor occurred exactly once when its turn came, and each new text once after.

6. **54.4 (replace the anchor with the new text).** **Applied in `cc11239`.** In "Spool / Filament write surfaces", the "Don't add `force_reset=True` to `setup_fields.py` lightly" bullet, which the planning pass says this group owes. Anchor:

   ```text
   The existing `migrate_container_slot_to_text()` is the template for any future legitimate type migration: snapshot values, force_reset, restore.
   ```

   New text:

   ```text
   The existing `migrate_container_slot_to_text()` is the template for any future legitimate type migration (Group 54.4; it runs on every deploy, while FCC is still running): snapshot every record, archived ones too (`allow_archived=true`, or their values are lost), with where each one is; put every value in the new type's wire form before anything is deleted (`_as_text_wire`: Spoolman refuses an old type's value in the new field, an integer's `2` in a text one); force_reset; then restore each record through a fresh read and a write of its whole `extra` (`_restore_container_slot`; a Spoolman before 0.22 replaced a spool's whole `extra` with a PATCH's), leaving alone one deleted ("gone"), given a value of that field since the rebuild (a blank too) or moved since the snapshot ("kept"), sending nothing for one it can't read, and reading a write that reports failure again before calling it failed. It prints the counts and every value a failure kept from coming back (and every value when the rebuild fails after its delete), so they can be put back by hand; the deploy's Spoolman backup is the other way back. Plain `requests` only, no `spoolman_api` import. Pinned by `tests/test_setup_fields_migration_54_4.py` (on `SpoolmanHTTPFake` with Spoolman's field DELETE and POST) and `tests/test_setup_fields_idempotent.py`.
   ```

7. **54.7, the page half (insert the new text right after the anchor, one space between; after #2).** **Applied in `cc11239`.** Anchor (the last sentence of #2's new text, so it occurs in CLAUDE.md once #2 is in):

   ```text
   The keyword is passed only for `false`, so a two-argument stand-in for `update_spool` still serves every other request (`tests/move_engine_harness`'s stand-ins take it; `WireSpoolman` hands it on only when False).
   ```

   New text:

   ```text
   The page sends it from every weigh save, through `saveSpoolWeight`'s sixth argument (`how`: `{archiveSwitch, empties, wasArchived}`): a weigh-out row's save and its details fallback send the list's switch (`#weigh-auto-archive`), the Quick-Weigh its own (`#fcc-we-auto-archive`, never the list's, whose markup is on the page with a state of its own), always the switch and never the per-save verdict, so with it on the server's rule still decides where the page's arithmetic disagrees; with it on, `archived: true` and the force-unassign after it are as before. With the switch off, a save that leaves 0 g by the page's own reading raises a 4 s success toast, "Updated Spool #57: 0 g left, kept in stock (Auto-Archive is off)", but not for a spool already archived before the save (it stays archived where it is; the weigh-out details carry `archived`, the fallback reads the scan buffer's entry) nor one the answer says was archived. A caller that names no switch sends the list's only where it leaves the verdict to `saveSpoolWeight`, as that path always read it, else none. Pinned by `tests/test_auto_archive_switch_page_54_7_js.py` (hermetic) and `tests/test_auto_archive_switch_real_54_7_e2e.py` (integration-gated: the real chain on the dev container and dev's Spoolman, on a throwaway spool).
   ```

**From b5-chips-docs (54.2): none.** CLAUDE.md describes neither the attribute chips nor their tests. The phone footers that 54.2 found are recorded in the test's `PHONE_KNOWN`, the Build log and the builder's report, for the phone-view work. All seven entries above were applied to CLAUDE.md in `cc11239`, in order, by `scratchpad/g54/apply_owed_claude_md.py` (outside the repo). Each anchor occurred exactly once at its turn and each new text once after. A second run finds all seven already applied.

## Planning pass, 2026-11-06 (read-only; re-check anchors before editing)

Read on `dev` @ `11126bb`, after Groups 40 to 61 merged (Group 58 as `d8c073c`). No code was changed. A read-only probe ran on a scratch copy of the modules outside the repo, against the offline fakes (`tests/spoolman_extra_fake.SpoolmanHTTPFake`), with no Spoolman and no prod. Its results are quoted below. Every anchor below is from `11126bb`. This section supersedes the older sections where they disagree: the decisions, the 54.4 design, the 54.5 log check and the estimate. Those sections are kept as filed.

### Conclusions

| Part | Status on `11126bb` | The change, in one line |
|---|---|---|
| **54.1** | **Still a bug** (dormant: every caller sends `{id, data}`). Its two sibling doors already answer 400. | 400 naming a missing or non-object `data`, and a missing `id`; `data: {}` keeps today's answer. |
| **54.2** | **Still open, and bigger.** The attribute search (Group 49.1, "Adding attributes in search") shipped, so the item's "once that ships" search case is due now. The Edit Filament form is a fourth chip renderer the task file didn't list. | One E2E on the real page with every read stubbed (four surfaces), and one offline search test. Code changes only if a surface fails. |
| **54.3** | **Still a bug (dormant), and wider than filed.** A JSON string that holds a comma list (`'"Silk, Matte"'`, what a text-type field leaves behind) collapses to one tag too. It also makes a purge's restore write a value Spoolman refuses. | Split both shapes on commas. JSON lists are never split. |
| **54.4** | **Still a bug (dormant). The filing named the mildest of three defects in the function.** The probe shows that archived spools are never snapshotted, so their slot is lost on any Spoolman, and that a value of the old type (an integer `2`) is refused by the new text field, so a real type migration loses every value. The partial PATCH the item names only bites on Spoolman before 0.22. | Snapshot archived spools too, convert each value to text before deleting anything, and restore through a fresh read-merge-write of the whole `extra`. |
| **54.5** | **Still a bug** (a live path). The server half already passes a `null` through, so only the page changes. | In edit mode, a native box the person emptied is sent as `null`, and the empty-weight cross-inherit skips it. |
| **54.6** | **Still a bug (rare path). The filing's wording is half stale.** With the weigh-out window's "Auto-Archive 0g" switch on (the default), the page already archives the spool and unassigns it in a second call, but plants no pre-archive note. With the switch off, the spool stays in stock at 0 g. | `_auto_archive_on_empty` reads `remaining_weight`, mirroring the unarchive edge. |

**For Derek** (two items; neither blocks the build; each has a default):

1. **His call (a PENDING DEREK line): the "Auto-Archive 0g" switch does nothing when it's off.** This is the weigh-out window's switch (`modals_weigh_out.html:55-56`), and its twin is the Quick-Weigh's "Auto Archive & Eject if Empty (0g)" (`weight_entry.js:151-152`). With either switch off, a spool weighed to 0 g is still archived and taken off its place. The server archives any weight write that leaves nothing (`spoolman_api._auto_archive_on_empty`, his 2026-04-22 answer "Auto"). The page uses the switch only to decide whether it sends `archived: true` and unassigns the spool a second time (`inv_weigh_out.js:1009-1018`, `:1237`). For example: with the switch off, weigh #57 on the Gross tab at exactly its empty reel's weight, and #57 is archived and Unassigned anyway. No test covers the switch turned off. The options:
   - (a) Keep "0 g always archives", and drop or relabel the switches (a look change, so show a sample first).
   - (b) Make off mean off: the page tells the server not to archive, and a 0 g spool stays in stock where it is. This is a server change, because today an explicit `archived: false` with 0 g still blanks the location: `_auto_archive_on_empty` sets `location` whenever the caller didn't.
   - (c) Leave it as it is.

   Recommendation: (b), because a switch that does nothing misleads. The default until he answers is (c). 54.6 brings the last weigh path into line with the server's rule whichever he picks, so it is built now, and the switch is filed as its own item.
2. **Needs his OK, default (a): an emptied spool price comes back at the next edit.** With 54.5, emptying the price box and saving clears the spool's own price. But his rule from the price cascade (buglist L349, "as long as we aren't overwriting filaments/spools that have data for that field") fills an edited spool's empty price box with the filament's price, as a plain number with no "inherited" mark (`wizardPrefillSpoolPrice`, `inv_wizard.js:743-749`). The next Save of that spool for any other reason then writes the filament's price as the spool's own. For example: spool #57 costs $30 and its filament $25. Empty #57's price and save, and #57 has no price. Open it tomorrow to fix its weight and save, and #57 now says $25. The options:
   - (a) Leave the cascade as it is. A spool with no price of its own takes the filament's, which is what an empty box meant anyway.
   - (b) Show the filament's price as an "inherited from filament" hint, the way the spool's empty weight already does (`wizardSetSpoolEmptyWeightInherited`, `:70-82`), and save it only when someone types it. That is a look change, so show a sample first.

   Recommendation: (a) for this group, and (b) as its own item if he wants it.

**Claude's calls** (made here, so the builder doesn't stop):
- 54.1: `{id, data: {}}` keeps its 200 "No fields to update." No caller sends it today (the task file's "a no-change modal save sends it" is stale: the Edit Filament form stops at "No changes to save.", `inv_details.js:2625`), but keeping it costs nothing. A missing `id` becomes a 400 as well.
- 54.2: the layout is proven on the real page, with real Bootstrap and stubbed reads. A hermetic page has no Bootstrap (it loads from a CDN, `dashboard.html:43`), and a stand-in would only prove the stand-in. A failure at phone width is recorded for the phone-view work, not fixed here.
- 54.3: a JSON string holding commas is split as well. JSON lists are never split. The browser's attribute parsers are filed as a standalone follow-up, not built here (see 54.3).
- 54.4: restore the whole `extra` from a fresh read of each spool, not from the snapshot, because FCC keeps running during the deploy (`update.sh` stops the app at `:70`, after setup_fields at `:62`). Archived spools are included, and values are converted before anything is deleted.
- 54.5: an emptied empty weight means "no value of its own". FCC's cascade then reads the filament, then the brand, wherever it needs one, and the next open shows that value with the existing "inherited from filament / vendor" badge. It does not mean "copy the filament's value now". Initial weight and used weight stay out of 54.5.
- 54.6: mirror the unarchive edge's `remaining_weight` rule exactly.

**Estimate, for one builder plus one review: about 8 to 11 agent-hours**, 30% above the 5 to 9 h filed. 54.4 grew, 54.2 gained the search case, and this project's estimates have run about 30% low.
- Build: 54.1 0.5 h · 54.2 1.5 to 2.5 h · 54.3 0.5 to 1 h · 54.4 1 to 1.5 h · 54.5 2 to 3 h (including the 15-minute dev check) · 54.6 0.5 h.
- Review: one agent over the whole diff, using `docs/agent_docs/review-checklist.md`'s "honest reads and writes", "real runs and old-code proofs" and "what a person reads" lenses: about 1 h, plus 0.5 to 1 h of fixes.
- Sweep: `--offline` in the background while iterating, then one full run at the end (about 21 min; it writes to dev).

**Lean, without cutting quality:**
- One builder, in this order: 54.6, 54.1, 54.3 (small and offline, one commit each), then 54.4 and 54.5, then 54.2 last, since it may find nothing to fix.
- One batched review agent for the group, never one per part.
- 54.2: one E2E file, one page session per viewport, and the stubs written once.
- 54.4: reuse `SpoolmanHTTPFake` with a 25-line field DELETE / POST subclass (the probe's `FieldFake`). No new fake.
- Don't build the two spun-off items (the switch, and the browser's attribute parsers): file them as standalone buglist items.

### 54.1 `/api/update_filament` answers a malformed request loudly

**Today.** `routes_scan.py:164-222`, with the checks at `:176-182`: `data = payload.get('data') or {}`. A missing `id` answers 200 `{success: false, msg: "Missing filament id."}`. A missing, `null`, non-dict, `[]` or `{}` `data` answers 200 "No fields to update." Its two siblings already answer 400: `/api/create_filament` (`routes_inventory.py:65-68`) and `PATCH /api/vendors/<id>` (`:167-170`). Every caller sends `{id, data: {…}}` with fields in it: `inv_cmd.js:3024` (Prusament temperatures; shown only with a conflict), `inv_details.js:783`, `:928`, `:1670`, `:2668`, and `inv_wizard.js:5336` (returns early on an empty diff, `:5325`). Each reads `r.json()` whatever the status, so a 400's `msg` is shown exactly as today's 200's is.

**Still happens:** yes, by reading the code: `{id, field, value}` reaches `:181` and answers 200.

**Change** (in `api_update_filament`, before any read):
- `request.json` that isn't an object → 400: "The request isn't a JSON object, so nothing was updated."
- no `id` → 400, same words as today.
- `'data' not in payload` → 400: "Nothing was updated: the request has no `data` field. Send {id, data: {field: value}}." When the body carries `field` or `value` (the old `_restore` shape), add "(it looks like the old {id, field, value} shape)". Also add one `state.logger.warning` naming the keys that came, so a broken caller can be found in hub.log.
- `data` present but not an object (`null`, a string, a list) → 400: "`data` must be an object of field: value, so nothing was updated."
- `data == {}` → unchanged (200, "No fields to update.").

No new route, so the route pin is unchanged. Python 3.9.

**Tests.** A new `tests/test_update_filament_payload_54_1.py` (Flask test client, offline). It patches `spoolman_api.get_filament` / `update_filament` to fail if called, which proves nothing is read or written:
- `{id: 5, field: "name", value: "X"}` → 400, msg names `data` and the old shape (**red** today: 200).
- `{id: 5, data: "x"}`, `{id: 5, data: ["a"]}`, `{id: 5, data: null}` → 400 (**red**: 200).
- `{data: {name: "X"}}` → 400, msg names the id (**red**: 200).
- A list body `[1]` → 400 (**red**: today it raises on `.get` and the route 500s).
- Control: `{id: 5, data: {}}` → 200 "No fields to update." (green on the base).
- Control: `{id: 5, data: {name: "X"}}` still reaches `update_filament` (green).

**Existing tests:** `test_filament_edit_button.py:23-40` (live container) asserts only `success` and the message's words, so it stays green. `test_l316_charact_filament_edit_log.py` sends valid shapes and is unchanged.

### 54.2 Twenty-eight attributes, on every surface that shows them

**Today.** No test renders more than a few chips. There are five surfaces:
1. The spool window: `renderReadonlyAttributeChips` (`inv_details.js:34-48`), called at `:203` into `#spool-detail-attributes` (`modals_details.html:59-61`, `d-flex flex-wrap gap-1`).
2. The filament window: `:411` into `#fil-detail-attributes` (`modals_details.html:178-180`).
3. The Edit Filament form (the filament window's ✏️, where attributes are edited; not in the task file): `#editfil-attr-chips` (`modals_details.html:444`), drawn at `inv_details.js:2219-2240`.
4. The wizard: `#chip-container-fil-filament_attributes` (`inv_wizard.js:2000`), filled by the edit prefill (`:4595-4616`) and `wizardAddMultiChoiceChip` (`:2060`).
5. Search: `spoolman_api.filament_attribute_list` (`:2571-2593`) feeds `search_inventory`, and a card's line joins every attribute into its material (`format_spool_display`, `spoolman_api.py:2173-2179`), so a 28-tag filament's card says 28 words before "PLA".

The CSS lets chips wrap (`.fcc-attr-chip` is inline-flex, `modals_details.html:320-330`, inside `flex-wrap` rows). Nothing caps a row's height. Whether anything breaks is unknown until it is drawn.

**Change:** tests first, and code only if a surface fails. A fix would be local (a wrap, or a capped height with its own scroll), and a visible one gets before / after images for Derek in `review-samples/` (standing order: no look change without a sample).

**Tests.**
- `tests/test_max_attribute_chips_e2e.py`: the real dashboard (`page`), with every read the windows make stubbed by `page.route`. It writes nothing, so it never touches dev data, and it skips under `--offline`. The filament's `filament_attributes` holds all 28 choices (`ALL_CHOICES`, imported from `tests/test_max_attributes_supported.py`), and surfaces 1 to 4 are opened at the 1600×1300 baseline. Per surface it asserts:
  - 28 chips;
  - each chip's box inside its host's and inside the window (`getBoundingClientRect`);
  - more than one row (they wrap);
  - `host.scrollWidth <= host.clientWidth + 1`;
  - no sideways scroll on the window body or the page;
  - the next control (the row after, Save) still reachable.

  Repeat at 390 px wide. If that fails, record it for the phone-view work rather than fixing it here. Stub templates: `test_card_move_pencil_48_3_e2e.py` (the spool window) and `test_filament_edit_button.py:120` (Edit Filament).

  Proof that it can fail: a pass is the expected result on today's code, so prove the assertions bite. Run once with the stub cut to one attribute (the count fails) and once with `page.add_style_tag("… {flex-wrap: nowrap !important}")` (the overflow assertions fail).
- Offline, as a new class in `tests/test_max_attributes_supported.py`, using `test_search_api.py`'s `_attr_filament` / `_attr_get` shapes:
  - a filament carrying all 28 is found by `search_inventory(query=<each choice>)`, for filament and spool targets;
  - `filament_attribute_list` gives all 28 in order;
  - the card's display line holds every one.

### 54.3 `_parse_filament_attrs_value` splits a comma list

**Today.** `spoolman_api.py:1747-1762`. A string that isn't JSON returns `[raw]` (`:1760-1761`), and a JSON string returns `[str(parsed)]` (`:1759`). The probe, on a scratch copy, gave `'Silk, Matte'` → `['Silk, Matte']` and `'"Silk, Matte"'` → `['Silk, Matte']`. Where the pseudo-tag goes:
- the attribute report (`routes_config_attrs.py:236`): it lands in `rogue_counts`, and Silk and Matte count 0;
- `sweep_unused` (`:848`): Silk and Matte read as unused, so a sweep offers to delete two tags in use;
- the remove / hide carrier scan (`:562`): such a record is no carrier of Silk;
- bulk add / remove (`:308`) and the purge's restore payloads (`:455`): they write `["Silk, Matte"]` back, which Spoolman 0.27 refuses as not a choice, so in a purge that filament loses its attributes;
- the boot cleanup (`spoolman_api.py:1826`, `:1864`);
- the attribute search (`:2586`).

**Still happens:** yes, but dormant. Spoolman 0.27 checks every write to a multi-choice field (a JSON list of known choices), so FCC can't write such a value now. Only an old record can hold one: from when the field was text, or from before Spoolman checked. This pass didn't read dev or prod data.

**Change.** In `_parse_filament_attrs_value`, when the value is a string that isn't JSON, or is JSON that decodes to a string, split it on commas, trim each piece, drop blanks, and drop repeats (the first is kept). A JSON list is returned as today, with its items never split: a list is the multi-choice shape, and an item with a comma could only be a real choice. `None`, `''`, other types and a JSON number keep today's results. What follows is all wanted:
- the report counts Silk and Matte;
- the sweep no longer offers them;
- bulk edits and a purge's restore write `["Silk", "Matte"]`, the valid shape, so the record is mended at its next write.

The task file's risk stands: a future choice containing a comma, held only in an old string, would be split. None of today's 28 has one.

**Spun off, not built here** (one standalone buglist item, display only, no data loss): the other parsers disagree on the same value.
- the browser's `parseFilamentAttributes` (`inv_details.js:18-29`) shows one chip, "Silk, Matte";
- the wizard's edit prefill splits on commas (`inv_wizard.js:4600-4605`);
- the Edit Filament form's diff reads it as `[]` (`inv_details.js:2489-2496`);
- the three display parsers drop it to nothing (`spoolman_api.py:2173-2177` and `:2807-2811`, and `labels_csv.py:45-49`), so the card and the label's Type column show no attributes.

**Tests.** A new `tests/test_filament_attrs_split_54_3.py`:
- The helper, parametrized:
  - `'Silk, Matte'`, `'"Silk, Matte"'` and `'Silk,Matte,'` → `['Silk', 'Matte']`;
  - `' Silk , Silk '` → `['Silk']` (**red** today on all four);
  - controls (green on the base): `'["Silk, Matte"]'` (one item), `'["+", "Silk"]'`, `None`, `''`, `42`, `'7'`.
- The routes, on `test_max_attributes_supported.py`'s `_install_wire` / `client` harness, with one filament holding `'Silk, Matte'` (raw) and one holding `'["Silk"]'`:
  - the report counts Silk 2 and Matte 1, with no rogue "Silk, Matte" (**red**: Silk 1, Matte 0, and a rogue);
  - the `sweep_unused` preview doesn't list Matte (**red**: it does).

**Existing tests:** `tests/test_search_api.py:341` pins `["Silk, Matte"]`. Update it deliberately to `["Silk", "Matte"]`. Its sibling at `:310` stays green (its docstring already names 54.3).

### 54.4 `migrate_container_slot_to_text`, the type-migration template

**Today.** `setup-and-rebuild/setup_fields.py:180-257`, called at `:359` on every prod deploy (`update.sh:62`). FCC is still running then: the app stops at `:70`, after the Spoolman backup. It is dormant: it returns at `:204-207` while `container_slot` is already text, as it is on dev and prod (it has been text in this script since `728a91e`).

**Probe** (a scratch copy, on `SpoolmanHTTPFake` plus a key-scoped field DELETE / POST; spool #1 holds `container_slot` and a sibling `needs_label_print`, spool #2 is archived with a slot):

| Spoolman, old type, value | #1 after | #2 (archived) after | Printed |
|---|---|---|---|
| 0.27.0, integer field holding `'"LR-MDB-1:2"'` | slot and sibling kept | **slot lost** | "1 restored, 0 failed" |
| 0.21.0 (a spool PATCH replaces `extra`; it merges from 0.22) | **sibling lost** | **slot lost** | "1 restored, 0 failed" |
| 0.27.0, integer field holding `'2'` | **slot lost** | **slot lost** | "Failed … 400 … Value is not a string.", "0 restored, 1 failed" |

The causes: the snapshot lists `/api/v1/spool` without `allow_archived=true` (`:214`), so archived spools are never snapshotted. The restore sends the old type's value (`2`) into the new text field. And the restore is the partial `{"extra": {"container_slot": value}}` (`:244-248`). The first two bite on every Spoolman, and they matter because CLAUDE.md names this function as the template for type migrations.

**Change** (plain `requests`, no `spoolman_api` import, Python 3.9):
1. Snapshot with `requests.get(f"{SPOOLMAN_IP}/api/v1/spool", params={"allow_archived": "true"}, timeout=15)`. Passing `params` keeps the URL the existing test matches as `…/api/v1/spool`.
2. Convert every snapshotted value to the new type's wire form before the rebuild, with one small helper (`_as_text_wire`):
   - a JSON string stays;
   - a JSON number or bool becomes `json.dumps(str(decoded))`;
   - a value that isn't JSON becomes `json.dumps(v)`;
   - JSON null or a blank is skipped.

   Every value is then known good before anything is deleted.
3. Restore each spool through a fresh read-merge-write: `GET /api/v1/spool/<id>`.
   - A failed read: count it failed and send nothing for that spool, never a partial.
   - A 404: the spool was deleted, so count it "gone".
   - A record that already has a non-blank `container_slot` (a move since the rebuild, with FCC still running): keep it, and count it "kept".
   - Otherwise PATCH `{"extra": {**record_extra, "container_slot": value}}`, the whole `extra`, as `update_spool` sends it.
4. Print the counts restored / kept / gone / failed. When any failed, print the snapshot (`#sid: value`), so the values can be put back by hand. The deploy's Spoolman backup is the other way back.

A Spoolman that refuses a stored sibling's value refuses the whole PATCH. Every `update_spool` on that spool already fails the same way, so this is no new failure class. In the same commit, update CLAUDE.md's write-surface sentence ("the template … snapshot values, force_reset, restore") to: list archived records too, convert to the new type before deleting anything, and restore through a fresh read-merge-write of the whole `extra`.

**Tests.** A new `tests/test_setup_fields_migration_54_4.py`. It drives the real `migrate_container_slot_to_text`, loaded with `test_setup_fields_idempotent._load_setup_fields`, on `SpoolmanHTTPFake` subclassed with the field DELETE (drop the key from every record and from the field list) and POST (add it back with the new type). That subclass is the probe's `FieldFake`, about 25 lines, and its `get` turns `params` into the query the fake reads.
- (a) Spoolman 0.21.0: #1's sibling survives (**red** today).
- (b) An archived spool's slot is restored (**red**).
- (c) Old type integer, value `2` → restored as `"2"` (**red**: refused, 0 restored).
- (d) A slot written after the rebuild (a hook on the fake's POST) is kept (**red**: overwritten).
- (e) A failed re-read sends no PATCH for that spool, and the others still restore (the new rule).
- (f) Control on 0.27.0 with a string value: restored, sibling intact (green on the base too).

**Existing tests:** update `tests/test_setup_fields_idempotent.py:112-163` (`test_snapshots_then_restores_every_non_empty_value`) deliberately. Its `fake_get` answers only the field list and the spool list (`:124`), so the new per-spool re-read would get its 404 and restore nothing. Answer the per-spool GET, and add the filed sibling assertion (`body["extra"]["other"] == "x"`). The snapshot-fails case (`:181`) stays green.

### 54.5 Emptying a plain field in the edit wizard clears it

**Today** (`inv_wizard.js`, `wizardSubmit` at `:3797`):
- The spool payload reads an empty box as `null` (empty weight `:3822`, price `:3826`), then drops every null (`:3860`).
- The filament payload does the same (empty weight `:3879`, temperatures `:3883-3884`), dropping every null except the two multi-colour keys (`:3989-3992`).
- The cross-inherit (`:3905-3922`) fills a null empty weight on either record from the other, or from the vendor, before the drop.

The server already passes a `null` through: the spool's dirty diff keeps `price: None` when the record had a price (`routes_inventory.py:1204-1205`; `spool_weight` at `:1181-1183`), the filament goes whole to `update_filament` (`:1293`), and neither write function touches a native key (only `"extra": null` is dropped, `_without_null_extra`). So only the page changes.

**Still happens:** yes. By the code path, erase the bed temperature in Edit Spool, save, and the key is never sent, so Spoolman keeps the old value.

**Spoolman and null.** The filament side is already exercised. The Edit Filament form sends `null` for an emptied price, empty weight and both temperatures (`numOrNull` / `intOrNull`, `inv_details.js:2385-2394`, read at `:2514-2521`; sent when changed, `:2593-2602`), and every wizard filament save sends `multi_color_hexes: null`. The spool's `price` and `spool_weight` have no null sender today. So the first build step stays the dev check: on dev's Spoolman (7913) only (dev spools are agent fixtures), make a throwaway filament and spool, PATCH each of the spool's `price` and `spool_weight` and the filament's `spool_weight`, `price`, `settings_extruder_temp` and `settings_bed_temp` to null, read each back as null, then delete both records. If Spoolman refuses a field, leave that field out of the change and say so in the task file.

**Change** (edit mode only, `isWizardEdit`):
1. A touched set for the native boxes, beside `touchedExtras`: `wizardState.touchedNative`, reset in `wizardReset` (`:751-753`) and filled by the wizard's existing input / change listener (`:168-169`) through one map of box id → key:
   - `wiz-spool-price` → `spool:price`;
   - `wiz-spool-empty_weight` → `spool:spool_weight`;
   - `wiz-fil-empty_weight` → `fil:spool_weight`;
   - `wiz-fil-settings_extruder_temp` → `fil:settings_extruder_temp`;
   - `wiz-fil-settings_bed_temp` → `fil:settings_bed_temp`.
2. The two null-drops keep a `null` whose key is touched, and drop the rest as today.
3. The cross-inherit fills a null only for an untouched box: an emptied box means "no value of its own".

**Edge cases:**
- The filament's empty-weight box copies itself into the spool's (`:1792-1801`, set by code, no event). Emptying the filament's box empties the spool's on screen but leaves the spool untouched. The spool then keeps its own tare or takes the cross-inherit, and is never cleared by a box the person didn't empty.
- The vendor push (`:1560-1566`) fires a synthetic input on the filament box, but only to fill a blank box with a value, so it can never send a clear. No `isTrusted` check is needed.
- A box typed into and then emptied is touched, so it sends `null`. One emptied and then retyped sends the number.
- Create, clone and external modes are unchanged (they build a fresh record).
- Initial weight and used weight stay out on purpose. An emptied initial weight would be a weight write (`update_spool`'s archive edge reads it, CLAUDE.md's warning on `/api/spool/update`), and an emptied used weight already sends 0 (`:3821`), which is a different question.
- No new UI, and no weight-entry UI (CLAUDE.md: none before Phase 2). Only what Save sends changes.
- The task file's "the edit log says → (cleared)" has nothing to check. The wizard edit writes no per-field Activity Log line, only weight changes (`_log_manual_weight_change`).
- What a person sees afterwards: an emptied spool empty weight comes back at the next open as the filament's (or brand's) value, with the existing "inherited from filament / vendor" badge. An emptied price comes back as the filament's price, plain (decision 2 above).

**Tests.** A new `tests/test_wizard_native_clear_54_5.py`, on the Group 58.5 harness: `test_wizard_label_status_58_5.py`'s `wizard` fixture, `_open_edit` and `_save` (`isolated_page`, the real `modals_wizard.html` and modules, the real Save; it runs under `--offline`). The spool has its own price 30 and empty weight 196; the filament has empty weight 200 and temperatures 215 / 60.
- For each of the five boxes: `fill("")`, Save, and that key is sent as `null` (**red** today: the key is missing).
- The emptied spool empty weight is `null` although the filament has 200 (**red**: 200 by the cross-inherit).
- Controls (green on the base):
  - an untouched empty box sends nothing (a filament with no bed temperature);
  - an untouched spool empty weight with no value of its own still takes the cross-inherit;
  - create mode, an emptied box sends nothing.
- Emptying the filament's empty weight never sends the spool's as `null`.
- Typed then emptied → `null`; emptied then retyped → the number.
- The next wizard session forgets a touch.

One real-page case goes in the same file, shaped like 58.5's `test_the_real_page_sends_no_status_for_an_untouched_box` (`page`, the POST intercepted, nothing reaching dev): empty the bed temperature, Save, and the intercepted body carries `settings_bed_temp: null`.

An offline server pin (Flask client on `SpoolmanHTTPFake` or `move_engine_harness.WeighedWireSpoolman`): `/api/edit_spool_wizard` with `spool_data.price: null` on a spool priced 30 PATCHes `price: null`, and `filament_data.settings_bed_temp: null` reaches the filament's PATCH. It is green on the base, and it pins that the server half needs nothing.

**Existing tests:** none should change. Every prefill and cascade test sets values by code, which records no touch (`test_wizard_price_product_cascade_e2e.py`, `test_empty_weight_vendor_fallback_update_flows.py`, `test_wizard_auto_prefill_empty_weight.py`). Run them.

### 54.6 The archive edge reads `remaining_weight`

**Today.** `spoolman_api._auto_archive_on_empty` (`:410-481`) returns at `:437-438` unless the write carries `used_weight` or `initial_weight`, while `_auto_unarchive_on_refill` already reads `remaining_weight` (`:520-527`). It is called once, from `update_spool` (`:672-678`). The probe gave `{"remaining_weight": 0}` → nothing set, and `{"used_weight": 1000}` → archived with location `''`. The only page that sends `remaining_weight` is the weigh-out list's fallback, used when a spool's details couldn't be read (`inv_weigh_out.js:906-920` → `saveSpoolWeight`, `:990-994`; Net mode only).

**Still happens:** yes, and the filing's "doesn't archive it" needs one correction. With the window's "Auto-Archive 0g" switch on (the default), the page sends `archived: true` itself (`inv_weigh_out.js:1009-1018`) and then force-unassigns the spool (`:1117-1120`), so it is archived and Unassigned. But:
- it gets no pre-archive note, so a later weigh-back can't put it back where it was;
- its trail isn't cleared in the same write;
- its single-slot box is released only by the second call.

With the switch off, it stays in stock at 0 g (see decision 1).

**Change.** In `_auto_archive_on_empty`, count `remaining_weight` as a weight write. When the write carries `remaining_weight` and not `used_weight`, use `remaining = float(data['remaining_weight'])`; a value that isn't a number changes nothing, as in the unarchive edge. Otherwise keep today's math. Everything after it is unchanged: `archived` and `location` are set only when the caller didn't set them, and the note and the trail blanks follow. This mirrors `:523-527`. Update the docstring.

**Edge cases:**
- `remaining_weight` with `used_weight`: the used weight decides (Spoolman refuses the pair anyway).
- `remaining_weight` with `initial_weight`: the remaining weight decides, as in the unarchive edge.
- An archived spool weighed to 0 again makes the same idempotent write the used path makes (`test_already_archived_zero_weight_update_is_idempotent`).
- The two edges can't both fire: the unarchive edge returns when `archived is True`.
- `/api/spool/update`'s `auto_archived` and `needs_empty_weight_prompt` (`routes_inventory.py:1495-1510`) then fire on the fallback as on the main path. The browser's force-unassign afterwards writes Unassigned again, harmlessly, exactly as the main path does with the switch on.

**Tests.** A new `tests/test_archive_on_remaining_weight_54_6.py`:
- Unit cases:
  - `remaining_weight` 0, 0.0, `"0"` and -0.0 → archived, location `''`, note "CR-SHELF", trail blanked (**red** today);
  - 0.4 → nothing; `"x"` → nothing;
  - used 300 with remaining 0 → nothing;
  - a caller's own `location` → no note.
- `update_spool` over `SpoolmanHTTPFake`: the PATCH carries `archived: true`, `location: ""` and the note (**red**).
- The door: `/api/spool/update {remaining_weight: 0}` through `move_engine_harness.run_move`, for a spool on XL-1 that came from a single-slot box. It answers `auto_archived: true` and the box lets go (`LocationsStore.bound`) (**red**).
- Control: `{remaining_weight: 40}` on an archived spool still un-archives it (green).

**Existing tests:** none change. `test_archived_stays_archived_51_1.py:200-215` call the unarchive edge only, and `test_manual_weight_log.py:95` writes 750 g.

## Items covered (quoted from `Feature-Buglist.md`)

| # | Buglist item | Direction |
|---|---|---|
| **54.1** | 🧪 Attribute-suite residual (1), narrowed 2026-10-12: *"A malformed payload still gets a generic answer… That generic message is what hid the `_restore` no-op for months. Reject an unrecognized payload shape loudly instead, naming the missing `data` key."* | 400 naming a missing or non-dict `data`. |
| **54.2** | Residual (2), Derek: *"Highly unlikely in reality, but we should make sure that having that many attributes doesn't break things like it might be doing right now, so we should probably put in some tests for this kind of thing, so that it's supported, even though it might not currently be possible."* | A browser test that renders all 28 chips. |
| **54.3** | 🟡 Group 36 follow-up (2): *"`_parse_filament_attrs_value` collapses a non-JSON string such as 'Silk, Matte' into one pseudo-tag, so real tags can read as zero-usage and therefore sweepable."* | Split a comma list when the string isn't JSON. |
| **54.4** | Follow-up (3): *"`setup-and-rebuild/setup_fields.py` still sends a partial-`extra` spool PATCH (`{"extra": {"container_slot": value}}`), the replace-the-whole-`extra` landmine, inside `migrate_container_slot_to_text`, the function CLAUDE.md names as the template for type migrations (dormant, guarded)."* | Snapshot each spool's whole `extra` and restore it whole. |
| **54.5** | *"Emptying a plain field in the wizard doesn't clear it (found 2026-10-21 by the extras-clear fix). The wizard drops a native field it reads as empty from its payload (`settings_extruder_temp`, `settings_bed_temp`, price, the spool's and the filament's empty weight), so erasing one and saving keeps the old value. Not an extra, so the sentinel doesn't cover it: an edit-mode clear would send `null` for these (Spoolman takes null for its own optional fields; check each on dev first)."* | In edit mode, send `null` for a native field the user emptied (touched fields only), after checking each field on dev. |
| **54.6** | *"The archive edge doesn't read `remaining_weight` (Group 51 review note, 2026-10-19). Since the review, a `remaining_weight` write (the weigh-out row's fallback when the spool's details can't be read) un-archives a spool weighed back into stock, but weighing one to 0 g that way still doesn't archive it (it never did). Rare path: make `spoolman_api._auto_archive_on_empty` read it too."* | The archive edge reads `remaining_weight` too, as the unarchive edge already does. |

## Decisions

- **No Derek decision.**

## Today's code (anchors, `dev` @ `c5c5aa6`)

- **54.1:** `/api/update_filament` reads `data = payload.get('data') or {}` (`routes_scan.py:174`); a missing, empty or non-dict `data` all answer 200 `{success: false, msg: "No fields to update."}` (`:177-178`). Every current caller sends `{id, data}` (`inv_cmd.js:1257`, `inv_details.js:773`, `:912`, `:1539`, `:2535`, `inv_wizard.js:4990`).
- **54.2:** `tests/test_max_attributes_supported.py` covers the backend only (28 choices at `:39-45`). No test renders 28 chips: `renderReadonlyAttributeChips` (`inv_details.js:34`; used by the spool window `:186` and the filament window `:394`) and the wizard's chip container (`inv_wizard.js:1903`; `wizardAddMultiChoiceChip` `:1963`).
- **54.3:** `_parse_filament_attrs_value` returns `[raw]` for a non-JSON string (`spoolman_api.py:1191-1206`, the fallback at `:1204-1205`). It feeds the attribute report (`routes_config_attrs.py:236`) and `sweep_unused` (`:848`), and is also read at `:308`, `:455`, `:562`. Group 49.1's attribute search should use it too.
- **54.4:** `migrate_container_slot_to_text` restores with `{'extra': {'container_slot': value}}` (`setup-and-rebuild/setup_fields.py:242-248`). Dormant: it returns early when `container_slot` is already text (`:204-207`). It runs on every prod deploy (`update.sh:62`, with no `set -e`). `tests/test_setup_fields_idempotent.py` pins the partial shape (`:128`, `:160-165`) and never checks that siblings survive.
- **54.5 (read on `dev` @ `d4b1ad7`):** the wizard's save builds `null` for an empty field (the spool's empty weight, `inv_wizard.js:3805`; the filament's, `:3862`; the temperatures, `:3866-3867`), then drops every `null` key before sending: the spool payload at `:3843` (null, undefined or NaN), the filament payload at `:3964-3966` (every null except `multi_color_hexes` / `multi_color_direction`). The empty-weight cross-inherit (`:3888-3903`) also fills a null empty weight from the filament or vendor, so an emptied spool empty weight is refilled on purpose: decide per field which clears and which inherits. Extras already clear only for a touched field (`wizardState.touchedExtras`, CLAUDE.md's wizard write-surface row); reuse that idea for native fields.
- **54.6 (read on `dev` @ `d4b1ad7`):** `spoolman_api._auto_archive_on_empty` (`spoolman_api.py:281+`) returns early unless the write carries `used_weight` or `initial_weight` (`:308`) and computes remaining from them (`:310-323`); the unarchive edge, `_auto_unarchive_on_refill` (`:355+`), already reads `remaining_weight` (`:394`). Called from `update_spool` (`:543`).

## Design, by sub-task

- **54.1:** answer 400 naming a missing or non-dict `data` key; keep today's answer for a present-but-empty `data` (a no-change modal save sends it).
- **54.2:** a browser test on stubbed data (no dev writes) rendering all 28 chips on the spool window, the filament window and the wizard: they wrap, nothing overflows, all are visible. The search half follows Group 49.1.
- **54.3:** split a comma list when the string isn't JSON (none of the 28 choices contains a comma).
- **54.4:** snapshot each spool's whole `extra` and restore it whole (still plain `requests` inside `setup_fields.py`, no Flask import); add a sibling-survival assertion to the test.
- **54.5:** first check on dev, with throwaway records deleted afterwards (dev spools are agent fixtures), that Spoolman 0.27 takes `null` for each field: `price`, `spool_weight` (spool and filament), `settings_extruder_temp`, `settings_bed_temp`. Then, in edit mode only, send `null` for such a field the user emptied (a touched-field set like `touchedExtras`); create mode and untouched fields keep today's drop. Check that `api_edit_spool_wizard` and `sanitize_outbound_data` pass a `null` through, and that the edit log says "→ (cleared)". The empty-weight cross-inherit stays for an untouched field.
- **54.6:** in `_auto_archive_on_empty`, treat a write carrying `remaining_weight` (and neither `used_weight` nor `initial_weight`) as a weight write: remaining ≤ 0 archives, with the same pre-archive note and location handling as today's path.

## Tests

- As above, each mutation-proven (red on the base).
- 54.5: a browser test on the edit wizard: empty the bed temperature, save, and the filament reads it empty; an untouched empty field sends nothing; create mode unchanged. Plus an offline test of the payload builder if it can be reached from the node-vm harness.
- 54.6: an offline `update_spool` test on `tests/spoolman_extra_fake.SpoolmanHTTPFake` (or the existing archive-edge harness): `remaining_weight: 0` archives a spool; `remaining_weight: 40` on an archived spool still un-archives it.

## Risks

- `setup_fields.py` runs on every prod deploy; the change sits inside the dormant branch.
- A comma split would mis-split a future attribute that contains a comma.
- 54.5: a field Spoolman refuses as `null` would make the whole PATCH fail; that is why each field is checked on dev first. A clear sent for an untouched field would erase data (the 2026-10-21 ➕ lesson): touched fields only.
- 54.6: archiving also takes the spool off its place (the archive edge's own outcome); the weigh-out's fallback row must say so as the other weigh paths do.

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

**Order (one builder at a time, one commit per part, red-first tests):** B1 server: 54.6, 54.7 (server half), 54.1, 54.3 · B2: 54.4, 54.7 (page half) · B3: 54.5 then 54.8, with before pictures taken before the wizard changes · B4: 54.2, the `?v=` bumps, the owed CLAUDE.md text · then a full `--offline` run. Then one batched review (`docs/agent_docs/review-checklist.md`), its fixes, the full sweep, and Derek's picture check.

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

### Owed CLAUDE.md text

_(Each builder appends the CLAUDE.md sentences its parts make stale or owe, quoting the anchor sentence. B4 applies them all with an anchor-checked script, one commit.)_

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

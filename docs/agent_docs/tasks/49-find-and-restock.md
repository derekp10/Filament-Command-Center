# Group 49: 🔍 Find & Restock

**Branch name (when started):** `feature/group-49-find-and-restock`
**Estimated effort:** MEDIUM (~6–10 h, 1 session). 49.1 ~1–2 h · the Low-stock list ~4–6 h · the Activity Log warning ~1–2 h.
**Risk:** **LOW–MEDIUM.** Search and the list are read-only. The Activity Log warning hooks in after the print deduct's ledger write and after a manual weight change, both hot paths, so it must never fail, refuse or noticeably delay either.

> **Status: `DONE` 2026-10-19 (the bundle run; merged to `dev` with the bundle; archived in `completed-archive.md`). Was: `TODO` — filed 2026-10-19 (`/refresh-groups`). Derek's decision is in (2026-10-19: the list plus one Activity Log warning); nothing waits on him.** Planned for the bundle run with Groups 48, 51 and 52 ([bundle-2026-10-19.md](bundle-2026-10-19.md)).
> Finding what you have and knowing what to rebuy. Every decision and his exact answers: [refresh-2026-10-19.md](refresh-2026-10-19.md).
> Code anchors were read on `dev` @ `c5c5aa6` (the refresh's grounding) and spot-checked at `08c4b10`. Line numbers drift, so re-grep before editing.

## Items covered (quoted from `Feature-Buglist.md`)

| # | Buglist item | Direction |
|---|---|---|
| **49.1** | Derek, 2026-10-08: *"Adding attributes in search to help find certain types would be useful. I was trying to find the 'For Infill' filaments, but couldn't seem to find them using the search text box. So either a dropdown, or being able to use them in the search text."* It sat inside the ⏸️ PENDING DEREK section by position only; a code item, now in "🔍 Search, Display & Filtering". | Attribute words become searchable text: "infill" finds his For Infill filaments and their spools. No dropdown for now. |
| **49.2** | Top of the buglist, Derek 2026-10-13: *"Perhaps a warning system, or report system for low or out filaments?"* | A **⚠️ Low-stock list** per filament **plus one Activity Log warning** when a print or a weigh-out drops a filament under the threshold (Derek's answer). |

## Decisions

- **Derek (2026-10-19), on what "warnings" means:** the ⚠️ Low-stock list (per filament, a Settings threshold, default 250 g; "out" = no stock left; Buy More links) **plus one Activity Log warning** when a print or a weigh-out takes a filament under the threshold (the question's option B).
- **Not in this group:** the print-start check. He loves it (*"#99 has ~34 g, this print needs ~61 g"*), but it needs the gcode before it reaches the printer, and he does that check by hand while planning. It comes **later, with Project Color Loadout**, estimated from the `.3mf`'s data (the buglist's "Build Project Color Loadout Add-on" item).
- **Claude's calls (offered for veto on 2026-10-19; none vetoed):**
  - search: attributes are searchable text; no attribute dropdown for now (Derek said either would do);
  - stock is counted per filament (all its in-stock spools added up), against a Settings threshold defaulting to 250 g;
  - a filament he won't rebuy stays off the "out" list when he tags it with an attribute such as "One-off" (no new field; findable through 49.1).

## Today's code (anchors, `dev` @ `c5c5aa6`)

### 49.1 — search
- `search_inventory` (`spoolman_api.py:1945`) builds `matchable` from the id, the filament's name, material, vendor and `original_color` only (`spoolman_api.py:2061-2066`). `filament_attributes` isn't in it, in spool or filament mode (both resolve `fil` at `:2008-2013`).
- The attribute parse already exists (`format_spool_display`, `spoolman_api.py:1550-1556`; the filament branch `:2109-2115`), and cards print the tags in front of the material ("For Infill PLA"), so **a tag you can see on a card can't be found by typing it.**
- The only dropdown is Material (`offcanvas_search.html:63-67`, filled from `/api/materials`, `inv_search.js:324-330`). `api_search_inventory` (`routes_inventory.py:1473`) takes no attribute. The wizard's filament search calls the same `/api/search`.
- Prod has one "For Infill" filament (#175 "Transition Spool", read 2026-10-12).

### 49.2 — stock
- **No report and no warning today.** Pieces that exist:
  - Printer Status colours a head amber under 100 g and red at 0 (`_weightPalette`, `inv_printer_status.js:196-200`);
  - Search has min/max remaining weight and In Stock (`offcanvas_search.html:75-77`, `:102`; `spoolman_api.py:2026-2037`) and a "Fewest spools" filament sort (`offcanvas_search.html:97`; `spoolman_api.py:2160-2168`);
  - a spool that hits 0 g auto-archives with an Activity Log line (`spoolman_api.py:456-459`);
  - Buy More links on the spool and filament windows (`inv_details.js:237-259`, `:419-440`; the template is config `buy_more_url_template`, `app.py:171`).
  - Nothing adds up a filament's spools.
- **Reads:** `get_all_spools` fails open to `[]` (`spoolman_api.py:94-107`), so a list built on it would read a Spoolman blip as "everything is out". `get_all_spools_strict(allow_archived=True)` (`spoolman_api.py:109`) raises instead: use it.
- **Spoolman ignores `extra=` query filters** (the 2026-10-19 backlog bug, `afdd509`: `/api/print_queue/pending` asked for `?extra={"needs_label_print":true}` and got every record). Filter extras such as `filament_attributes` in FCC, never in the query.
- Settings are flat `Field`s (`config_schema.py`, `SECTIONS` at `:56`; `path_filament_g` at `:83` is the pattern), so the threshold is one Field.
- FCC never reads Spoolman's `last_used` / `first_used` (no hits outside `tests/conftest.py:1409-1410`) and stores no archive date. Whether Spoolman stamps `last_used` on FCC's `used_weight` PATCH is unknown: check read-only on dev before any "ran out recently" rule relies on it (none is planned).
- **Hook points for the warning:**
  - the print deduct writes its exactly-once ledger in `_record_applied_deduct` (`print_deduct.py:496`; the ledger write at `:556-557`);
  - manual weight changes funnel through `_log_manual_weight_change` (`routes_inventory.py:957`, called from the wizard at `:1219` and from `/api/spool/update` at `:1416`, which the weigh-out and Quick Weigh screens use; Group 24).

## Design, by sub-task

### 49.1 — attributes as search text
- Add the cleaned attribute list (lower-cased, same parse as `spoolman_api.py:1550-1556`) to `matchable`. One place covers both modes, and multi-word tags work through the existing every-token rule ("for infill", "matte pla").
- Prefer the shared `_parse_filament_attrs_value` (`spoolman_api.py:1191-1206`) over a third copy of the parse, so Group 54.3's comma split (a non-JSON "Silk, Matte") reaches search too.
- No dropdown in v1 (Claude's call). Later, if wanted: choices from `/api/external/fields` (as `promptEditSlicerProfile` does, `inv_details.js:670-684`) and an `attribute` parameter through `api_search_inventory`.

### 49.2a — the ⚠️ Low-stock list
- **Server:** one function (a flat module such as `stock_report.py`, or in `spoolman_api.py`) computes per-filament stock from ONE strict spool read including archived (`get_all_spools_strict(allow_archived=True)`) plus the filament list (names, colours, Buy More link):
  - in stock = a spool that isn't archived and has remaining > 0;
  - **low** = a filament's in-stock spools add up to less than `low_stock_g`;
  - **out** = a filament that has had spools but has none in stock (a filament with no spools at all was never stocked: not listed; Claude's call);
  - a filament tagged with an attribute such as "One-off" stays off the "out" list; while it still has stock it can show on "low", with its tag visible, so he sees why it isn't on "out" later.
- **Setting:** `low_stock_g`, a new Field in ⚙️ Behavior, default 250 (help text: per filament, across its in-stock spools).
- **Route:** e.g. `GET /api/stock_report` (update `tests/test_route_table_pin.py` deliberately). A failed read answers an error, **never** an empty or "all out" list.
- **Panel:** a `mountOverlay` panel "⚠️ Low stock", opened by a button in the search panel. Two lists, Low then Out; each row: swatch, Brand - Material - Color, total grams, spool count, a Buy More link (only when a URL resolves, using the details windows' rule), and a click that opens the filament window. Computed when it opens only, **never on the 5 s heartbeat** (Group 45.8's lesson). An error state that says Spoolman didn't answer, and an empty state ("Nothing is low").
- Keyboard and contrast (standing orders): arrows move between rows, Enter opens the filament, Escape closes (`mountOverlay` owns Escape); light text on the dark panel, checked by the contrast guard.

### 49.2b — one Activity Log warning when stock drops under the threshold
- **When:** after the print deduct's ledger write, and after a manual weight change (the `_log_manual_weight_change` funnel), for each filament that was just charged.
- **What:** one WARNING only on the **crossing**: the filament was at or above `low_stock_g` before the write and is under it after. E.g. "⚠️ Prusament PLA Galaxy Black is running low: 220 g left in 2 spools". When its last in-stock spool empties (the 0 g auto-archive), say "out" instead. A filament already under the threshold stays quiet, so a print on a low filament doesn't log every time.
- **How:** "before" is the charged spool's own before/after grams plus the filament's other in-stock spools; one read of that filament's spools (verify on dev that Spoolman honours the filter you use; it ignores `extra=`). Strict read; on any failure log nothing (a debug line at most).
- **Never in the way:** wrapped so it can never raise into, refuse, or reorder the deduct or the weight write; it runs only after the ledger write (so a crash can't re-run a deduct) and after the weight write landed. If the extra read adds noticeable latency to `/api/spool/update`, run the check off the request thread.

## Tests (each proven red on the base first)

- **Search** (`tests/test_search_api.py`, mocked Spoolman): "infill" finds the For Infill filament and its spools; "matte pla" crosses a tag and a material; a filament with no tags is unaffected; a non-JSON attribute string doesn't crash.
- **Stock unit tests:** 80 g + 140 g = 220 g is low at 250; all archived is out; a One-off filament is not "out"; archived spools never count as stock; a filament with no spools isn't listed; a failed strict read answers an error, not an empty list.
- Route pin; Playwright for the panel on a stubbed route: rows, the Buy More link, the empty state, the error state, keyboard navigation, the contrast guard.
- **Warning:** fires once when a deduct takes a filament from 300 g to 220 g; stays quiet from 220 g to 150 g; says "out" when the last spool archives; never raises (patch the read to throw: the deduct and the ledger entry are unchanged); runs only after the ledger write; the same through `/api/spool/update` for a weigh-out.

## Risks

- **49.1 widens results** in the search panel and in the wizard's filament search: a word that matches a tag ("silk", "matte") also returns tagged filaments.
- **Spoolman load:** one full read (spools including archived) plus the filament list each time the panel opens; never on the heartbeat.
- **Fail-open reads:** anything that reads stock must use the strict read, or a blip shows "everything is out".
- **The warning touches `print_deduct`** (the hot path): after the ledger write only, fully wrapped. Same for the weight funnel.
- A new route: `tests/test_route_table_pin.py`.

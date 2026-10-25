# Group 48: 🃏 Spool Cards & Label Queue

**Branch name (when started):** `feature/group-48-spool-cards-label-queue`
**Estimated effort:** MEDIUM (~8–14 h, 1.5–2 sessions). 48.2 ~1 h · 48.1 ~2–4 h · 48.4 ~2–4 h · 48.3 ~3–5 h · tests and visual baselines throughout.
**Risk:** **LOW.** Frontend only, with no new write path: 48.3 reuses Force Location's doors, and 48.4 only pre-fills a field that the wizard's own Save writes. The real hazards are an invisible Force Location (its dialog is tied to the spool window today) and visual-baseline churn.

> **Status: `DONE` 2026-10-19 (the bundle run; merged to `dev` `2ec9f46` with the bundle; archived in `completed-archive.md`). Was: `TODO` — filed 2026-10-19 (`/refresh-groups`). Derek's decisions are in (2026-10-19); nothing waits on him.** Planned for the bundle run with Groups 49, 51 and 52 ([bundle-2026-10-19.md](bundle-2026-10-19.md)).
> Three of Derek's own asks about what a spool card or window shows and does, plus his same-day idea of filling in the slicer profile. Every decision and his exact answers: [refresh-2026-10-19.md](refresh-2026-10-19.md).
> Code anchors were read on `dev` @ `c5c5aa6` (the refresh's grounding) and spot-checked at `08c4b10`. Line numbers drift, so re-grep before editing.
> Suggested order: 48.2 (about an hour, no risk) → 48.1 → 48.4 → 48.3.

## Items covered (quoted from `Feature-Buglist.md`)

| # | Buglist item | Direction |
|---|---|---|
| **48.1** | Derek, 2026-10-08: *"We should standardize the data shown in the label Queue. Some items added by button show minimum amount of data. (Spools on the id, not much else, samples show more.) Anything added to the queue from the label backlog is added using better identifying text/info. We should standardize all print label functions to try and match the backlog's queue text/info setup, so it's easier to read what is what. (Just listing a spool id doesn't tell me what color it is, so it's hard to tell at a glance if what I added and am looking at was what I was just working with.)"* It sat inside the ⏸️ PENDING DEREK section by position only (that section had no closing heading until this refresh); there is no hands-on part. | One row renderer that draws every queued row like the backlog does (colour swatch + Brand - Material - Color), from live data when the queue opens. Printed labels don't change. |
| **48.2** | Derek, 2026-10-19: *"I've had a few instances where I wanted to see what spool profile I should use with some filaments, only to find that I have to open the spool, click the swatch button, then find the profile suggestion there. If we could just have that data on the spool (sourced from the filament data) then that would save a step."* | The filament's slicer profile on the spool window, **read-only, and saying it comes from the filament** (Derek's answer). |
| **48.3** | Derek, 2026-10-19: *"Allow you to click on the location portion of the buffer label (or any label that uses the code base) to allow you to move the spool. Currently you have to open the spool display, and then click the pencil button to change its location (if doing it manually) and sometimes I just want to click the location part of the info card to edit it. Like how updating weight works from the buffer/display card."* Correction to the item: the location part isn't dead; the 📍 badge opens that location in the Location Manager. | **A separate ✏️ beside the 📍 badge moves the spool** through Force Location and its pickers; the badge keeps opening the location (Derek's answer). |
| **48.4** | Derek, 2026-10-19 (filed after the refresh's grounding ran): *"If possible, we should try and determine what profile should be used, at least with well documented spool/filament creations based on things like prusament spool barcodes. It gets everything (or at least everything I have noticed) but we miss out on that aspect of data, that we might just be able to do for the user."* **Caveat, same day:** the profile names are PrusaSlicer's (its defaults, or a custom one he makes when needed), so they don't line up with other printer brands and their slicers. | Suggest a profile from **brand + material** when a Prusament scan leaves it blank. PrusaSlicer names only for now. |

## Decisions

- **Derek (2026-10-19):**
  - **48.3:** the 📍 badge keeps opening the location; **a separate ✏️ beside it moves the spool** (option B of the question: the same pair the spool window already has). Its other options were the badge itself moving the spool (with a small ↗ to open the location) or a two-item menu.
  - **48.2:** the profile on the spool window is **read-only and says it comes from the filament**, so he knows to edit it there.
  - **48.4:** build the Prusa case first; don't assume one profile name fits every slicer (a later version might keep a profile per slicer).
- **Claude's calls (offered for veto on 2026-10-19; none vetoed):**
  - Queue rows are drawn from live data when the queue opens; printed labels don't change.
  - A spool moved from its buffer card leaves the buffer once the move lands, as it does when you scan it into a location.
- **Claude's call (written into this file 2026-10-19, not yet shown to Derek):** 48.4's suggestion comes from his own filaments of the same brand + material (no new table or setting); his other idea, a small editable brand + material → profile table, is the fallback if that proves noisy.

## Today's code (anchors, `dev` @ `c5c5aa6`)

### 48.1 — the label queue
- The queue window writes each row as `${icon} #${item.id} - ${item.display}` straight into `innerHTML`: no colour and no escaping (`inv_queue.js:75-84`).
- `addToQueue` de-duplicates on id + type, then flags `needs_label_print` (`inv_queue.js:24-55`). The queue lives in localStorage `fcc_label_queue` (`inv_queue.js:6`, `:18`) and in `/api/state/queue` (`persistQueue`, `inv_queue.js:230`).
- About 20 callers pass different `display` text:
  - the backlog: "Brand - Material - Color" (`inv_backlog.js:64-68`, `data-display` at `:87`, the add at `:165`), the look Derek wants everywhere;
  - the wizard's post-create 🖨️ chips: "Spool #57" (`inv_wizard.js:2943`, `:2991`), so the row reads "#57 - Spool #57";
  - the spool window's ➕ Queue Label: only the filament name (`scripts.html:205`); the filament window's: its colour name (`:221`);
  - the filament window's spool rows: "<name> (ID:57)" (`inv_details.js:538`, `:556`); the filament reprint prompt: "Filament #12" (`inv_details.js:2793`);
  - cards: `item.display`, "#57 Brand MAT (Color)", so the id shows twice (`ui_builder.js:112`, `:145`, `:206`, `:368`, `:416`);
  - Location Manager cards (`inv_loc_mgr.js:924`, `:951`, `:1220`, `:1275`); location labels "Location: X" (`inv_loc_mgr.js:2015`);
  - also `inv_cmd.js:1240`, `duplicate_picker.js:112`, `inv_details.js:447` and the multi-spool add (`inv_queue.js:196`).
- Labels print by id only (`printQueueCSV`, `inv_queue.js:117-129`), so printed labels are unaffected by any of this.
- `quickQueue` (`inv_details.js:634-641`) has no callers.
- A Location Manager list card adds to the queue twice per LABEL click: the inline `onclick` (`ui_builder.js:189`) plus a listener (`inv_loc_mgr.js:1216-1222`, `:1271-1277`). `addToQueue`'s de-dup hides it.
- Live data already exists: `POST /api/spools/refresh` → `logic.get_live_spools_data` (`logic.py:4908-4946`: one `get_spool` per id; answers display, colour, details), and `/api/filament_details` for a filament (`routes_locations.py:1026-1030`).

### 48.2 — the spool window
- It shows material, vendor, temperatures and the filament's attributes, all read from the nested filament (`modals_details.html:13-52`; `inv_details.js:149-186`: temps from `filExtra` at `:153-162`, attributes at `:183-186`). No slicer profile.
- The profile shows only on the filament window's fact card ("🎚️ Slicer Profile:", `modals_details.html:148-154`; filled at `inv_details.js:318-326`). Its ✏️ (`promptEditSlicerProfile`, `inv_details.js:662-808`) is bound to `#filamentModal` (Swal targets `:675`, `:696`, `:779`, `:799`; it refreshes `openFilamentDetails` at `:795`).
- `/api/spool_details` already returns the spool with `filament.extra` (`routes_locations.py:1020-1024`), so the value is already loaded: no new read.

### 48.3 — the card's location badge
- Search and buffer cards: the 📍 badge opens the location in the Location Manager ("Jump to Location"; `ui_builder.js:122-135`, the search card's also closes the search panel; `ui_builder.js:430-441`). An Unassigned badge has no click (`ui_builder.js:136`, `:442-443`). The card's weight opens Quick Weigh (`ui_builder.js:519`).
- The spool window already pairs a jump badge (`inv_details.js:136-144`) with a separate ✏️ that opens Force Location (`modals_details.html:18` → `promptEditLocation`, `inv_details.js:942`). That is the pair Derek chose for the cards.
- `promptEditLocation` assumes the spool window is open: its Swal targets `#spoolModal` (`inv_details.js:969`, `document.getElementById('spoolModal') || document.body`), its questions are hosted on it (`spoolModalEl`, `:1220`, used at `:1305`, `:1330`, `:1358`), and success refreshes `openSpoolDetails` (`:1253`). Since Group 40.4 a box or a Printer row opens the pickers (`inv_details.js:1345-1375`). Its list leaves out heads, MMU, virtual rows, Wall Shelf and Row (`inv_details.js:951-958`).
- The jump is deliberate (since `f1f2d73`, 2026-04-15; fixed after Derek reported it broken), and it stays.
- Location Manager list cards have no location badge (`ui_builder.js:156`).

### 48.4 — the Prusament scan and the profile
- The Prusament parser's result (`PrusamentParser.search`, `external_parsers.py:128-224`; the object it returns at `:192-218`) fills name, material, vendor, weights, density, colour, links, temps and the Prusament extras (manufacture date, length), **never `slicer_profile`**.
- A Prusament spool-QR scan (`_handle_prusament_url_scan`, `routes_scan.py:808`): with no matching spool it hands the parsed object to the Add wizard (`prusament_new`); with a match it backfills the parent filament's blank temps through `update_filament_or_raise` with a partial `extra`.
- The wizard applies a picked external result in `wizardExternalSelected` (`inv_wizard.js:2812`); a lone result (a scanned Prusament URL) is applied automatically (`:2622-2628`). It already holds every filament (`wizardState.allFilaments`, from `/api/filaments`, `inv_wizard.js:1343-1349`), and `window.splitMaterialAndAttributes` (`inv_wizard.js:4372`) splits a Prusament "full" material string ("PC Blend Carbon Fiber") into a base material and attributes.
- The profile's choices come from `/api/external/fields` (as `promptEditSlicerProfile` reads them, `inv_details.js:670-684`). Group 10.5's "auto-assign" only selects a profile you just added as a new choice (`inv_wizard.js:2246`).

## Design, by sub-task

### 48.2 — the profile on the spool window (do first)
- One template row beside the temps and attributes (`modals_details.html`), reusing the filament card's label: "🎚️ Slicer Profile: Prusament PLA (from the filament)". Fill it from `unquoteExtra(filExtra.slicer_profile)` next to `inv_details.js:153-162`; "--" when blank, like the temps.
- Read-only (Derek): no ✏️ here. The "(from the filament)" note tells him where to edit it; making it a link that opens the filament window (the 🧬 swatch button's action) is a cheap extra, builder's call.

### 48.1 — one queue row renderer
- One row renderer in `inv_queue.js`:
  - spool and filament rows: a swatch (`window.getFilamentStyle`, `inv_core.js:1229`) + "Brand - Material - Color" (the backlog's text) + `#id`;
  - location rows: "LOC-ID — Name".
- When the queue window opens: one `POST /api/spools/refresh` for the queued spool ids and one `/api/filament_details` per queued filament. On demand only, never on the heartbeat. Draw the stored text first and upgrade each row when its data lands; if a read fails, keep the stored `display` with a leading "#id" stripped.
- Escape every piece of text (`window.escHtml`, `inv_core.js:736`): a colour name is free text.
- Keep the stored `display` field: localStorage and the server blob carry it, and it is the fallback.
- A 30-minute first step that already helps: the wizard chips pass the filament text the wizard already holds.
- Housekeeping in the same files: delete `quickQueue`; keep one LABEL handler on Location Manager cards (the double add).

### 48.3 — a ✏️ beside the 📍 badge
- **Wiring (Derek's choice):** the badge is unchanged; a small ✏️ right after it (search and buffer cards) opens Force Location for that spool. The grey Unassigned badge gets the ✏️ too.
- **Make `promptEditLocation` work without the spool window.** Give it an options argument `{host, onDone}`; the default stays today's spool-window behaviour. From a card:
  - mount the Swal on `document.body` and host the questions on the body (opened from a card with the spool window closed, today's `#spoolModal` target would draw it inside a hidden window: invisible);
  - on success, fire the sync pulse (`inventory:sync-pulse`), and for a buffer card take the spool out of the buffer once the move landed (Claude's call, as a location scan does);
  - from a search card, hide the search panel first (as the jump does), so the offcanvas focus trap can't take the Swal's input.
- **No new write path:** it reuses `manage_contents add` and `window.placeOneWithPicker` (the Group 40 doors), so a box opens the slot picker and a Printer row the Printer picker, exactly as from the spool window.
- Keyboard (standing order): the ✏️ is a real button (reachable by Tab, Enter opens it); Force Location's list already has the arrow / Enter / Escape idiom.

### 48.4 — suggest the profile from brand + material
- One helper, `suggestSlicerProfile(vendorName, material)`: among Derek's own filaments (`wizardState.allFilaments`; no new read), the `slicer_profile` most used by filaments with the same vendor and the same base material (case-insensitive; split the material with `splitMaterialAndAttributes`). On a tie, pre-fill neither: name both in the note and let him pick. No match: nothing.
- **Where it applies first:** a Prusament scan that opens the Add wizard (`prusament_new`), and any external import applied by `wizardExternalSelected`, whenever the result leaves the profile blank. Pre-fill the wizard's Slicer Profile field (`wiz_fil_ef_slicer_profile`) and say where it came from ("suggested: 3 of your Prusament PLA filaments use it"). Never overwrite a profile already set; nothing is written until the wizard's own Save (no new write path).
- **PrusaSlicer names only for now** (Derek's caveat): the suggestion copies a name he already uses, so it is whatever his slicer calls it. Don't build a cross-slicer mapping or invent names ("Prusament <material>" may not exist in his profile list).
- **Optional second step, only if the first proves useful:** the same suggestion as a fill-blank on the matched Prusament scan (`_handle_prusament_url_scan` already backfills blank temps on the parent filament). That IS a filament write: blank-only, through the existing `update_filament_or_raise` partial extra, `LAST_SPOOLMAN_ERROR` surfaced, and the CLAUDE.md write-surface table updated in the same commit.
- Derek's other idea, a small editable brand + material → profile table, is the fallback if suggestions from his own filaments turn out noisy.

## Tests (each proven red on the base first)

- **Queue** (Playwright with routed `/api/spools/refresh` and `/api/filament_details`, or node-vm): a spool queued as "Spool #57" shows its swatch and "Brand - Material - Color"; a filament row; a location row; a failed live read keeps the stored text; a colour name containing `<img onerror>` renders as text; one `/api/spools/refresh` per open and none on the heartbeat. Recapture `queue-modal-default.png` and look at it.
- The wizard chips queue the filament text (extend `tests/test_wizard_queue_label_chips.py`).
- One `set_flag` POST per Location Manager LABEL click.
- **Spool window:** shows the profile with "(from the filament)"; blank → "--"; a JSON-quoted value is unquoted (pattern: `tests/test_detail_modal_attributes.py`, which mocks `/api/spool_details`). Recapture `spool-details-modal-default.png`.
- **Card ✏️ with the spool window closed:** the Force Location list is visible and focused over the dashboard, and from a search card; a plain location lands and the badge updates; `LR-MDB-1` opens the slot picker; Escape moves nothing; a buffer card's spool leaves the buffer after the move; the badge itself still jumps; the spool window's own badge still jumps (`tests/test_ui_details_modal_e2e.py:55-68` unchanged); `tests/test_door_fed_heads_canary.py` and `tests/test_door_to_buffer_canary.py` stay green.
- **48.4** (node-vm on the helper, plus one routed Playwright run of the wizard): picks the most-used profile for the same vendor + base material; "PC Blend Carbon Fiber" matches base "PC Blend"; no match leaves it blank; a profile already set is never replaced; the wizard shows the "suggested" note and nothing is written before Save.
- Contrast guard on any new row or button (`tests/test_contrast_guard.py`), per the standing order.
- Full E2E sweep before merging (a frontend change). It writes dev data, which is fine: dev spools are agent fixtures (the bundle's rule); never `--reset-dev` without asking Derek.

## Risks

- An invisible Force Location if its Swal target stays `#spoolModal` while that window is closed (`inv_details.js:969`).
- The search offcanvas's focus trap vs the Swal's search input.
- Visual baselines: `queue-modal-default.png`, `spool-details-modal-default.png`, and any buffer or search card baseline the ✏️ changes.
- Spoolman load: queue lookups run only when the queue opens; a long queue is one `get_spool` per spool.
- 48.4: a wrong suggestion is worse than none, so it only fills a blank, says where it came from, and is visible before Save.

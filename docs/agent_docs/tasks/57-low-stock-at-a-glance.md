# Group 57: ⚠️ Low Stock at a Glance

**Branch name (when started):** `feature/group-57-low-stock-at-a-glance`
**Estimated effort:** MEDIUM (~5–8 h, 1 session plus one sample look with Derek). 57.1 ~1–1.5 h · 57.2 ~2–4 h (after the sample) · 57.3 ~1 h (only if the sample needs it) · 57.4 ~0.5 h · 57.5 ~1–1.5 h.
**Risk:** **LOW–MEDIUM.** Mostly display. Two real hazards: the heartbeat feeds every open page (a new section must keep the old shape for an old page), and the title bar is a size container that already tightens at Large / Extra Large.

> **Status: `TODO` — filed 2026-10-25 (`/refresh-groups`; Derek approved the grouping the same day: "Ok apply the grouping").** Build order: **57.1 first (ready, no decision)**, then **57.2's sample** at Large / Extra Large, then 57.2 / 57.3 on his pick. 57.4 and 57.5 are ready any time.
> The ⚠️ Low stock list (Group 49.2, released 2026-10-25 in `main` `97fcf7c`) moves to the title bar with a count, and its window stops jumping in size. Two small fixes ride along: the Buy More `&`, and the buffer cards' per-spool reads.
> Code anchors were read on `dev` @ `d4b1ad7` (2026-10-25). Line numbers drift, so re-grep before editing.

## Items covered (quoted from `Feature-Buglist.md`)

| # | Buglist item | Direction |
|---|---|---|
| **57.1** | ⚠️ Low stock, (b), Derek 2026-10-25 on prod: *"It jumps in size depending on its content's length, which makes everything move around in a weird way. This is kind of contradictory to some of the other modal design decisions we've made in the past."* *"If that means adding a scrollbar to the list of filaments, that's fine."* | A fixed height in rem; the list scrolls inside; tabs, filter and legend stay put. The come-back behaviour (2026-10-20) stays. |
| **57.2** | Same item, (a): the button sits in the 🔍 Search panel (*"works, seems a bit odd. And doesn't really tell you anything at a glance"*; 2026-10-20: *"a bit fiddly"*). *"Move it to the title bar beside 🏷️ Backlog and 🛒 Queue, with a count, so it reads at a glance."* To settle: what the count shows, its cost, room in the title bar at Large / Extra Large. | **Where: decided (Derek).** One sample at Large / Extra Large first. |
| **57.3** | 🎨 Design follow-ups, (e): *"The title bar at Extra Large: if the squeeze ever bothers him, Backlog and Queue could shrink to their icon and count at that size."* | Only if 57.2's sample needs the room. |
| **57.4** | *"A Buy More link template with `&` breaks in the spool and filament windows… an `&` in it arrives as `&amp;` in the links they build. The ⚠️ Low stock panel builds its links on the server and is fine. Pass the setting with `\|tojson` instead."* | One template line. |
| **57.5** | 🐢 *"The buffer cards' live refresh reads Spoolman once per buffered spool on every heartbeat… ten buffered spools are ten reads every 5 s. It could use the tick's one spool-list read (`SpoolListRead`), as the other heartbeat sections do since Group 52."* | Read from the tick's list; a per-spool GET only for an id the list lacks. |

## Decisions

- **For Derek, with the sample (57.2):**
  - **What the count shows.** (a) one number, Low + Out ("⚠️ 14"); (b) both ("⚠️ 3 · 11"); (c) Low only. Excluded never counts. Recommendation: (a), since the window's tabs already split it; on prod today Out holds the 11 filaments with no spool record until he excludes them (the ⏸️ PENDING DEREK Low stock item), so the first count he sees will be high. Default if he doesn't answer: (a).
  - **Room at Large / Extra Large.** The sample shows the bar at all four Text sizes with the new button; if it squeezes, 57.3 (Backlog, Queue and Low stock as icon + count at Extra Large). His call on the picture.
- **Claude's calls (for veto):**
  - 57.1: a fixed height such as `min(36rem, 86vh)` (rem, so it follows the Text size; vh, so a short window still fits), the filament list the only thing that scrolls.
  - 57.2: the count rides the heartbeat if the check below holds; a read that fails shows "?" and keeps the last count, never 0 (Group 52's rule). The Search panel button stays or goes with the sample (Derek's "a bit odd" leans to removing it).
  - 57.5: no cache across ticks; only the tick's own read is shared.

## Today's code (anchors, `dev` @ `d4b1ad7`)

- **The window:** `inv_stock.js` builds it. Panel `width:min(50rem, 94vw); max-height:86vh; display:flex; flex-direction:column` (`inv_stock.js:76`), so its height follows its content; the list body `.fcc-stock-body { overflow:auto; flex:1 1 auto; min-height:70px }` (`:98`); tabs `:279`; the list `#fcc-stock-list` (`:294`); the come-back state (tab, filter, row, scroll) `:502-513`, restored at `:614`.
- **The button today:** `#global-search-low-stock` in `templates/components/offcanvas_search.html:25-27`.
- **The title bar:** `templates/dashboard.html:45-70` (`.fcc-titlebar-actions`): 🏷️ Backlog `#btn-backlog-count` (`:60`), 🛒 Queue `#btn-queue-count` (`:63`). `global.css` "Title bar": a size container that tightens as it runs out of room (ADD INVENTORY reads ADD at Extra Large); CLAUDE.md: a new title-bar button keeps `white-space: nowrap`.
- **The report:** `stock_report.build_report` (`stock_report.py:335-398`) reads every spool strictly, archived ones included (`:347`), and every filament (`:348`). Membership: `stock_of` counts only in-stock spools (`:192-204`); an Excluded filament is never Low or Out (`:377-380`); a filament with no spool on record is Out, last (`:385-391`).
- **The heartbeat:** one spool-list read per tick, `spoolman_api.SpoolListRead()` (`routes_state_pulse.py:506`), shared by the sections. The 🏷️ Backlog count section (`_pulse_section_label_backlog`, `:345-351`, `:562-564`) already reads the filament list every tick through `routes_print_queue.backlog_count` (`routes_print_queue.py:32-51`, `read_filament_list` at `:45`), on the tick's non-archived spool list (its docstring, `:34`).
- **The idea to check before designing a slower cadence (read-only check, 2026-10-25):** archived spools never change Low / Out *membership*. A filament whose spools are all archived has no in-stock spool, so it is Out either way (through the no-spool loop instead of `count == 0`); archived spools change only its `no_spools` label. So the count = f(the tick's in-stock spool list, the filament list), and both are already read on every tick. To confirm in the build: that the tick's list is exactly the non-archived list `build_report` would filter to, and that a Low row's unknown-weight rule (`:383`) gives the same answer on it. If it holds, the count costs no extra Spoolman read.
- **Buy More:** `templates/dashboard.html:260`, `const BUY_MORE_URL_TEMPLATE = "{{ buy_more_template }}";`: Jinja auto-escapes inside the `<script>`, so `&` becomes `&amp;`. Read by the spool window (`inv_details.js:257-265`) and the filament window (`:431+`); passed in at `app.py:188`.
- **The buffer refresh:** `logic.get_live_spools_data` (`logic.py:5145+`) makes one `spoolman_api.get_spool` per id (`:5152-5154`), called by the heartbeat's `spools_refresh` (`routes_state_pulse.py:570`) and `/api/spools_refresh` (`:132-138`).

## Design, by sub-task

### 57.1 — one size
- Give the panel a fixed height (the call above) instead of `max-height`; the body keeps `flex: 1 1 auto; overflow: auto`. The tabs, filter, legend and footer don't move between Low / Out / Excluded, a filter with no match, the loading state or an error.
- Check at Small, Standard, Large and Extra Large on 1600×1300 and on 1280×800.

### 57.2 — the title-bar button and its count
- `⚠️ Low stock (N)` (or the sample's pick) beside Backlog and Queue; click opens the list (`inv_stock.js`'s open); keyboard reachable (standing order); a shortcut only if Derek wants one (then `window.registerShortcut`).
- If the check holds: a heartbeat section (e.g. `low_stock`) computed from the tick's spool list and the filament list `backlog_count` already read (share it rather than read twice). A sibling key, absent for an old page; `{read_ok: false}` keeps the last count with a "?".
- If it doesn't: compute after a deduct, a weigh-in, an exclusion and on open, never per tick.
- The 🔕 / Include again changes and a deduct's low-stock warning (49.2b) refresh the count.

### 57.3 — icon + count at Extra Large (only if needed)
- Under `global.css`'s Extra Large rules, Backlog / Queue / Low stock keep their icon and count and drop the word, with the word in `title` and `aria-label`.

### 57.4 — the `&`
- `const BUY_MORE_URL_TEMPLATE = {{ buy_more_template|tojson }};` (no quotes around it).

### 57.5 — the buffer refresh
- Build the answer from the tick's `SpoolListRead` for every id it holds; a per-spool `get_spool` only for an id it lacks (an archived buffered spool, or a failed list read). `/api/spools_refresh` (no tick) keeps today's path or reads the list once.

## Tests

- **Offline:** the count function equals `len(low) + len(out)` from `build_report` on fixtures with an archived-only filament, a filament with no spools, an excluded one and a spool of unknown weight; the heartbeat makes no extra Spoolman GET for the count (count GETs per tick, as Group 52's tests do); `spools_refresh` makes no per-spool GET for ids in the tick's list; a template with `&` reaches the page unescaped (a render test of `dashboard.html`).
- **Browser:** the window's bounding box is the same height on every tab, an empty filter, loading and an error, and its list scrolls (`test_stock_*` neighbours); the title-bar button shows the count, opens the list, and "?" on a failed read (routed); `tests/test_contrast_guard.py`, `tests/test_text_size_guard.py` and `tests/test_text_size_floor.py` cover the new button; title-bar visual baselines recaptured deliberately after Derek's pick.
- The full sweep before merging (the frontend changes).

## Done when

- The window keeps one size at every Text size; the title bar shows the count Derek picked from his sample and opens the list; Buy More links keep their `&`; the heartbeat makes no per-spool reads for the buffer.

## Risks

- Title-bar room at Large / Extra Large (the sample decides).
- The heartbeat shape: a new sibling key only, so `_notePrinterStatesForFastPoll` and the widget never read it as a printer.
- A count that disagrees with the opened list: compute both from the same rule (one helper in `stock_report.py`).

# Group 45: 🧪 Sweep Load-Tolerance & Test Hygiene

**Branch name (when started):** `feature/group-45-sweep-load-tolerance`
**Estimated effort:** MEDIUM (~6–10 h, 1–2 sessions), plus the dev-data refresh (~2–4 h if scripted).
**Risk:** **LOW for product code, MEDIUM for shared dev data.** This is mostly test infrastructure, with three exceptions:
- one CSS change (45.3), decided 2026-10-13: OFFLINE text alpha 0.45 → 0.50;
- 45.4 and 45.5 were filed as touching dev `locations.json`, but the 2026-10-13 answers avoid that: TST-MDB-1 becomes a test box whose baseline is the empty state dev already has, so neither changes dev's `locations.json`; they edit the committed reset snapshot and the tests;
- 45.6 copies data into dev.

Derek answered all three on 2026-10-13 (see "Decisions (answered 2026-10-13)" below). 45.6's run still needs him around to approve the prod reads.

> **Status: `PARTIAL` — built in the 2026-10-13/14 overnight run on `feature/group-45-sweep-hygiene`, merged to `dev` (sha in [session-handoff-2026-10-14.md](session-handoff-2026-10-14.md)).** Shipped: **45.1(b)(c)**, **45.2**, **45.3**, **45.4**, **45.5**, and **45.8**'s fix (the Printer Status widget was re-reading the whole spool list per toolhead on every heartbeat: FCC itself was the sweep's load). Details and the review's fixes: the 2026-10-14 Group 45 block in `completed-archive.md`. **Left:** 45.1(a) a per-wait triage only where a red recurs, plus a sweep on a genuinely busy desktop (the load line labels it); 45.8's done criterion, three consecutive clean full sweeps; **45.6 / 45.7** the scripted dev-data refresh, one evening with Derek to approve the prod reads; 45.1(d) only if still needed.
>
> ⚠️ **Correcting this file's own build notes (2026-10-14):** the 3 s waits were not the main mechanism. On a quiet machine, every dashboard load and heartbeat queued each test's requests behind 13 full spool-list reads (45.8). Fixing that made the page fast enough to expose tests that had leaned on the slowness (closing a modal inside Bootstrap's show transition, opening the Location Manager before the locations load, injecting state a real poll owns); use `conftest.close_wizard` / `wait_modal_settled` / `quiet_heartbeat` / `own_the_buffer` for those shapes. Run sweeps from `inventory-hub/`.
>
> It has the Group 32 / 33 / 38 shape: make a red sweep mean something again, on the working desktop Derek actually has.

---

## ⚠️ Read this first: Group 38's lesson

**Not one of Group 38's eight flakes wanted a bigger timeout.** Each asserted against state the app was entitled to change: a late `.then()` re-showing a modal, a panel closing itself, a 2 s poll reclaiming the buffer, a save reverted by its own sibling request. Two could not have been fixed by widening, even in principle.

45.1 proposes raising some 3 s waits. That's not a contradiction: the load-sensitive failures are a different population. A 30% slower machine trips proportionally more hard 3 s bounds that assert nothing about latency.

So **triage each wait**:
- If it waits on something the app may legitimately change or destroy, fix the race. Group 38's levers apply: ordered-prefix reproduction and in-page fetch delay.
- Raise it only if it's a pure "this eventually appears" wait.

Other ground rules:
- **pytest here is SERIAL** (no xdist or randomly), so test-vs-test contention is impossible. The pressure in 45.1 comes from outside the suite: ordinary desktop load.
- **Never edit repo files mid-sweep**, and never run visual or E2E tests alongside a sweep ([[reference_fcc_e2e_load_sensitivity]], [[feedback_no_concurrent_sweep_and_visual]]).
- **A full sweep writes to shared dev data.** Get Derek's OK before each one.

## Items covered (quoted from `Feature-Buglist.md`)

| # | Buglist item | Direction |
|---|---|---|
| **45.1** | **🧪 "The E2E suite is LOAD-SENSITIVE: a busy machine turns a 2-red sweep into a 13–16-red one, with a different set each time."** Two back-to-back `RUN_INTEGRATION` sweeps failed 13, then 16, with only 5 in both; 19 of 24 distinct failures didn't reproduce. They took 33:40 against 26:17 on a quiet machine. *"almost every failure is a `wait_for_function` / `expect` hitting a hard 3000 ms timeout."* Derek: *"Not sure I can make the machine quiet… If it's a re-occurring issue, we may need to dig further."* | Filed directions, cheapest first: (a) raise the 3 s waits to ~8–10 s; (b) a conftest-level default timeout, so tests stop hardcoding one; (c) have the harness print total wall-clock and warn when a run exceeds the quiet baseline; (d) auto-retry a failed browser test once and report it as flaky. **Do NOT "fix" this by requiring a quiet machine.** Measured 2026-10-12: **42 `timeout=3000` sites in 18 files** (426 literal `timeout=` sites in all), and conftest sets **no** default timeout (no `set_default_timeout` or `expect.set_options`). |
| **45.2** | **🧪 "Two intermittent `test_config_save.py` failures on Windows."** `test_concurrent_writes_no_lost_update` (`:319`) and `test_import_new_secret_masked_in_diff_and_response` (`:879`) each failed once in a full hermetic run on 2026-09-29. They pass 6/6 and 3/3 in isolation, and 81/81 as a module. | Capture a traceback first (`--tb=long -rf`, teed to a file). Suspects: the config.json write path's Windows `os.replace` behaviour (compare `atomic_store.replace_with_retry`, Group 32), and thread timing in the concurrency test. These are hermetic tests, so browser load isn't the cause. |
| **45.3** | **🎨 "The dark-contrast guard composites the BACKGROUND but not the FOREGROUND — and `.fcc-ps-state-offline` is sub-AA behind that blind spot."** `CONTRAST_GUARD_JS` (`tests/conftest.py:1235`) scores a translucent foreground at full strength. `rgba(255,255,255,0.25)` on `rgba(255,255,255,0.08)` over `#000` paints at 2.24:1 but scores 18.36:1. | Filed fix: `const fgPaint = fg.a >= OPAQUE ? fg : over(fg, bg)`. **It can't land alone**: it immediately flags `.fcc-ps-state-offline` (`static/css/global.css:1531`), whose text alpha 0.45 gives 4.41:1 against the guard's 4.5:1 threshold. Land it with the CSS change (alpha 0.45 → 0.50 gives 5.29:1, "visually imperceptible"), **decided 2026-10-13** (Claude's call; Derek reviewed it and didn't object; see Decisions below). Pin the 2.24:1 pair as an offender. |
| **45.4** | **🧪 "`test_feeds_section_save_with_some_slots_none` can never run — it is permanently skipped."** (`tests/test_loc_mgr_bindings_ui_e2e.py`) Its `TEST_BOX` is `PM-DB-1`, which has Max Spools 1, but the test needs ≥2 Feeds selects. | Filed route, replaced 2026-10-13: widen a baseline box to 2 slots and register it in `DEV_BOX_BINDING_BASELINES` (`conftest.py:392`). **Derek chose instead to point the test at TST-MDB-1** (6 slots, empty), so PM-DB-1 stays a one-slot PolyDryer and dev's `locations.json` doesn't change. It depends on 45.5's TST-MDB-1 baseline; see Decisions below. |
| **45.5** | *Sweep-triage follow-ups from the 2026-09-13 pre-merge sweep*, item 4: **"Three more dev-data borrowers still restore what they observed."** They are `test_quickswap_printer_pool.py` `pool_binding` (`:23`, borrows TST-MDB-1), `conftest.bound_loaded_slot` (`:540`), and `test_printer_status_widget::test_widget_shows_unbound_printers_with_placeholder` (`:159`, which clears EVERY dryer box). | Each needed a Derek call, **answered 2026-10-13** (see Decisions below). Is TST-MDB-1's `{"1": "PRINTER:XL"}` binding deliberate? No: TST-MDB-1 is just a test box, with an empty baseline. Should the widget test get a fixed fleet-wide baseline, or stubbed data? Stubbed data. Then convert the other two to `borrow_box_bindings` (`conftest.py:519`) with fixed baselines. Items 1–3 of that triage shipped on `test/sweep-reds-hermetic`, merged 2026-10-08. |
| **45.6** | **🔄 "Refresh dev's data from prod (locations, Spoolman inventory, config) — and make it a repeatable operation."** Derek, 2026-10-01: *"we should also now consider updating dev to a more recent version of the data on prod."* Explicitly NOT urgent. | **Answered 2026-10-13: Derek chose a scripted full refresh** (see Decisions below). The three things it settled: how much to copy (locations only, or Spoolman spools/filaments/vendors too); what dev-only state must survive (the `DEV_BOX_BINDING_BASELINES` boxes PM-DB-1/2/4/5 at `{}`, the virtual test spools); and whether it becomes a scripted `--refresh-from-prod` beside `--reset-dev` (`setup-and-rebuild/reset_dev.py`) or stays a manual copy. ⚠️ **Read-only against prod: never write to `:7912`.** This also absorbs two follow-ups:
- item 4 of the Bulk Move report (dev/prod parity before the next manual pass);
- [Group 36](36-attribute-force-reset-data-loss.md)'s never-filed **prod→dev sibling-extras restore** for ~4 drained dev filaments (#4, #121, #175, #157; see [Group 47](47-buglist-reconciliation.md) 47.1). A Spoolman refresh covers it; a locations-only refresh does not. |
| **45.7** | _(residual)_ *"Dev data: spool #99 carries a stale ghost trail."* The trail itself was cleared (2026-09-18 handoff), but its suggestion stands: *"a read-only count on dev AND prod of spools whose `physical_source` is set while their location is not a toolhead, to size the drift."* | Read-only. Fold it into 45.6's inventory step. |

## Decisions (answered 2026-10-13)

Derek answered these on the afternoon of 2026-10-13. The plain-language briefs, with the code each claim was checked against, are in [open-decisions-2026-10-13.md](open-decisions-2026-10-13.md); its "Derek's answers" list is the source of truth.

### 45.3 — Land the guard fix together with the OFFLINE label change? — ✅ ANSWERED 2026-10-13: yes, text alpha 0.45 → 0.50

**Decided 2026-10-13 (Claude's call; Derek reviewed it and didn't object): land the guard fix together with `.fcc-ps-state-offline` text alpha 0.45 → 0.50 (5.29:1).** Ship the filed `fgPaint` change in `CONTRAST_GUARD_JS` and the one value at `static/css/global.css:1531` in the same commit, so `tests/test_contrast_guard_compositing.py` never goes red; OFFLINE stays dimmer than IDLE (0.6). Build it that way, with the filed direction in the table above (pin the 2.24:1 pair), and rewrite the comment that calls foreground alpha "a design decision about that chip" (`tests/conftest.py:1228-1231`).

### 45.4 — Which box should `test_feeds_section_save_with_some_slots_none` use? — ✅ ANSWERED 2026-10-13: TST-MDB-1

**Derek chose TST-MDB-1 (2026-10-13).** Point this one test at TST-MDB-1 (6 slots, empty bindings on dev) instead of widening PM-DB-1, which stays a one-slot PolyDryer; the module's other tests stay on `TEST_BOX = "PM-DB-1"` (`tests/test_loc_mgr_bindings_ui_e2e.py:14`). It borrows the box through `borrow_box_bindings`, so it lands after 45.5 registers TST-MDB-1's empty baseline. Build it that way; the filed "widen a baseline box" route in the table above is replaced and kept only for the record.

### 45.5 — Is TST-MDB-1's old binding deliberate, and what data does the widget test use? — ✅ ANSWERED 2026-10-13: TST-MDB-1 is just a test box; the widget test gets stubbed data

**Derek chose "TST-MDB-1 is just a test box" (2026-10-13).** Register TST-MDB-1 in `DEV_BOX_BINDING_BASELINES` (`tests/conftest.py:392`) with an empty baseline and drop its old `{"1": "PRINTER:XL"}` leftover from the reset snapshot (`setup-and-rebuild/seeds/locations-seed.json`; `test_baselines_match_the_reset_dev_seed` keeps the two equal). `test_printer_status_widget::test_widget_shows_unbound_printers_with_placeholder` gets stubbed data through `window.refreshPrinterStatusWidgetFromAggregate`, as its neighbouring tests already do, instead of clearing every dryer box, and `conftest.bound_loaded_slot` uses a test box holding one of the virtual dev spools instead of Derek's real boxes (CR-MDB-1, LR-MDB-1, LR-MDB-2). Dev's data doesn't change: TST-MDB-1 has read `{}` on dev since the 2026-10-08 copy from prod. Build it that way; the background in the table above is kept for the record.

- `test_quickswap_printer_pool.pool_binding` then borrows TST-MDB-1 through `borrow_box_bindings`.
- Converting the widget test retires its `_OBSERVED_RESTORE_ALLOWED` entry in `tests/test_box_binding_loans.py`; the canary there fails until the entry is removed.

### 45.6 — How much of prod to copy into dev, and how? — ✅ ANSWERED 2026-10-13: script the full refresh

**Derek chose the full scripted refresh (2026-10-13).** One script refreshes dev from prod: the locations plus the Spoolman inventory (spools, filaments, vendors), prod strictly read-only, then it re-applies the dev-only test fixtures and retakes the reset snapshot from the refreshed data. Run it one evening when Derek is around to approve the prod reads; it is not urgent. Build it that way; the background in the table above is kept for the record.

- Dev-only pieces to re-apply: the `DEV_BOX_BINDING_BASELINES` boxes at their baselines (PM-DB-1/2/4/5, plus TST-MDB-1 after 45.5, all `{}`); the CR-TC test carts (CR-TC-1 "TestCart" with row CR-TC-R1, and CR-TC-2 with rows CR-TC-2-R1..R3); the virtual test spools; and a deliberate choice about printer logins. The 2026-10-08 copy stripped the logins, but dev's `locations.json` holds an IP and API key for XL and RCOI again.
- A locations copy brings in prod's own blank-ID row ("Unknown Location"). The script must drop or handle it, or the two sweep reds that went away with dev's TestCart row (46.5) come back.
- Keeping spool numbers the same as Derek's labels probably means copying prod Spoolman's database file into dev's Spoolman while dev's Spoolman is stopped, which may need Derek in TrueNAS; copying through Spoolman's API renumbers every spool. Tests that lean on particular dev spools may need a one-time touch-up.
- Today's reset snapshot (`setup-and-rebuild/seeds/locations-seed.json`, captured 2026-06-02) predates the INDX: a `--reset-dev` would bring back CORE1 and drop RCOI-1..8. Retaking it is part of the refresh.
- Fold in 45.7's read-only `physical_source` drift count.

## Build order

1. **45.1(c)** first: print wall-clock and warn against the quiet baseline, so every later sweep labels itself.
2. **45.1(b), then (a)**: a conftest default, then triage the 42 `timeout=3000` sites one by one (see "Read this first").
3. **45.2**: capture a traceback, then fix.
4. **45.3**: ready; the CSS call was made 2026-10-13 (OFFLINE text alpha 0.45 → 0.50).
5. **45.6 and 45.7**: the dev-data refresh, scripted (decided 2026-10-13) and run one evening when Derek can approve the prod reads. **45.4 / 45.5** were answered 2026-10-13 and change no dev data, so they needn't wait for the refresh: 45.5 first (TST-MDB-1's empty baseline), then 45.4. The refresh re-applies that baseline.
6. **45.1(d)** last, and only if it's still needed. An auto-retry can hide a real regression, so report retried-then-passed tests loudly.

## Interactions

- **[Group 46](46-quick-fix-sweep-2026-10.md) 46.5 (37.1).** Dev's blank-LocationID `TestCart` row was deleted on 2026-10-13 with Derek's OK, and the two standing sweep reds it caused now pass. Prod carries its own blank row ("Unknown Location"), which a refresh from prod would bring in, so 45.6's script must drop or handle it, or those reds come back. `CR-TC-1` (also named "TestCart") is a kept dev test cart, not a leftover.
- **[Group 44](44-printer-first-class.md).** Dev's locations have had prod's fleet (XL, and RCOI with 8 heads) since the 2026-10-08 copy, but the reset snapshot still has the old single-head CORE1 until 45.6 retakes it. `644a395` already made one CORE1-naming test fleet-agnostic; check the remaining fixtures for hard-coded printer names.

## Verification

- The deliverable is a sweep that reads at a glance on a normal working desktop: every red is either real or labels itself as load noise.
- `--offline` stays at ~42 s and green, apart from known reds.

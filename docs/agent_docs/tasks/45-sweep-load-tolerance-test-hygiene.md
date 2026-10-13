# Group 45: 🧪 Sweep Load-Tolerance & Test Hygiene

**Branch name (when started):** `feature/group-45-sweep-load-tolerance`
**Estimated effort:** MEDIUM (~6–10 h, 1–2 sessions), plus the dev-data refresh (~2–4 h if scripted).
**Risk:** **LOW for product code, MEDIUM for shared dev data.** This is mostly test infrastructure, with three exceptions:
- one CSS change (45.3), which is Derek's call;
- 45.4 and 45.5 touch dev `locations.json`;
- 45.6 copies data into dev.

Each of those needs Derek's OK.

> **Status: `TODO` — filed 2026-10-12 (`/refresh-groups`), not started.**
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
| **45.3** | **🎨 "The dark-contrast guard composites the BACKGROUND but not the FOREGROUND — and `.fcc-ps-state-offline` is sub-AA behind that blind spot."** `CONTRAST_GUARD_JS` (`tests/conftest.py:1235`) scores a translucent foreground at full strength. `rgba(255,255,255,0.25)` on `rgba(255,255,255,0.08)` over `#000` paints at 2.24:1 but scores 18.36:1. | Filed fix: `const fgPaint = fg.a >= OPAQUE ? fg : over(fg, bg)`. **It can't land alone**: it immediately flags `.fcc-ps-state-offline` (`static/css/global.css:1531`), whose text alpha 0.45 gives 4.41:1 against the guard's 4.5:1 threshold. Land it with the CSS change (alpha 0.45 → 0.50 gives 5.29:1, "visually imperceptible"), which is **Derek's call**. Pin the 2.24:1 pair as an offender. |
| **45.4** | **🧪 "`test_feeds_section_save_with_some_slots_none` can never run — it is permanently skipped."** (`tests/test_loc_mgr_bindings_ui_e2e.py`) Its `TEST_BOX` is `PM-DB-1`, which has Max Spools 1, but the test needs ≥2 Feeds selects. | Filed route: widen a baseline box to 2 slots and register it in `DEV_BOX_BINDING_BASELINES` (`conftest.py:392`). **Needs Derek's OK** (`locations.json`). |
| **45.5** | *Sweep-triage follow-ups from the 2026-09-13 pre-merge sweep*, item 4: **"Three more dev-data borrowers still restore what they observed."** They are `test_quickswap_printer_pool.py` `pool_binding` (`:23`, borrows TST-MDB-1), `conftest.bound_loaded_slot` (`:540`), and `test_printer_status_widget::test_widget_shows_unbound_printers_with_placeholder` (`:159`, which clears EVERY dryer box). | Each needs a Derek call. Is TST-MDB-1's `{"1": "PRINTER:XL"}` binding deliberate? Should the widget test get a fixed fleet-wide baseline, or stubbed data? Then convert each to `borrow_box_bindings` (`conftest.py:519`) with fixed baselines. Items 1–3 of that triage shipped on `test/sweep-reds-hermetic`, merged 2026-10-08. |
| **45.6** | **🔄 "Refresh dev's data from prod (locations, Spoolman inventory, config) — and make it a repeatable operation."** Derek, 2026-10-01: *"we should also now consider updating dev to a more recent version of the data on prod."* Explicitly NOT urgent. | Decide three things: how much to copy (locations only, or Spoolman spools/filaments/vendors too); what dev-only state must survive (the `DEV_BOX_BINDING_BASELINES` boxes PM-DB-1/2/4/5 at `{}`, the virtual test spools); and whether it becomes a scripted `--refresh-from-prod` beside `--reset-dev` (`setup-and-rebuild/reset_dev.py`) or stays a manual copy. ⚠️ **Read-only against prod: never write to `:7912`.** This also absorbs two follow-ups:
- item 4 of the Bulk Move report (dev/prod parity before the next manual pass);
- [Group 36](36-attribute-force-reset-data-loss.md)'s never-filed **prod→dev sibling-extras restore** for ~4 drained dev filaments (#4, #121, #175, #157; see [Group 47](47-buglist-reconciliation.md) 47.1). A Spoolman refresh covers it; a locations-only refresh does not. |
| **45.7** | _(residual)_ *"Dev data: spool #99 carries a stale ghost trail."* The trail itself was cleared (2026-09-18 handoff), but its suggestion stands: *"a read-only count on dev AND prod of spools whose `physical_source` is set while their location is not a toolhead, to size the drift."* | Read-only. Fold it into 45.6's inventory step. |

## Build order

1. **45.1(c)** first: print wall-clock and warn against the quiet baseline, so every later sweep labels itself.
2. **45.1(b), then (a)**: a conftest default, then triage the 42 `timeout=3000` sites one by one (see "Read this first").
3. **45.2**: capture a traceback, then fix.
4. **45.3**: after Derek's CSS call.
5. **45.6 and 45.7**: the dev-data refresh plan. Then **45.4 / 45.5** against the refreshed fleet; each needs Derek's OK.
6. **45.1(d)** last, and only if it's still needed. An auto-retry can hide a real regression, so report retried-then-passed tests loudly.

## Interactions

- **[Group 46](46-quick-fix-sweep-2026-10.md) 46.5 (37.1).** Removing dev's blank-LocationID `TestCart` row clears the two standing sweep reds; that's Derek's call. A refresh from prod would also replace the row, but prod carries its own blank row ("Unknown Location"). Sequence 45.6 with 46.5.
- **[Group 44](44-printer-first-class.md).** A refresh changes the dev fleet (prod has `RCOI` with 8 heads). `644a395` already made one CORE1-naming test fleet-agnostic; check the remaining fixtures for hard-coded printer names.

## Verification

- The deliverable is a sweep that reads at a glance on a normal working desktop: every red is either real or labels itself as load noise.
- `--offline` stays at ~42 s and green, apart from known reds.

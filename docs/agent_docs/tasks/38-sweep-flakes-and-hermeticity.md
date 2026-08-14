# Group 38: 🧪 Sweep Flakes & Hermeticity Residuals

**Branch name (when started):** `feature/group-38-sweep-flakes-hermeticity`
**Estimated effort:** ~4–7 hours (6 flakes + 5 test-infra residuals)
**Risk:** **LOW.** Test-infra only — no product code expected.

> **Status: `PARTIAL`** — filed 2026-08-06; **hermeticity residuals DONE 2026-08-07**
> (`2d36a62`, branch `feature/group-38-hermeticity-residuals`, stacked on Group 36).
> **38.7 / 38.8 / 38.9 / 38.10 / 38.11 are all closed** (38.9 by Group 36).
>
> **2026-08-07 flake session — ALL SIX filed members closed at the root, plus the two the
> confirming sweep surfaced** (`1756259`, `ac93cb5`, `fe2fb61`).
> **38.1, 38.3, 38.4, 38.5, 38.6a, 38.6b + the new 38.12 / 38.13 are FIXED.**
> 38.2 is reclassified as collateral (see below) and needed no change.
> ⚠️ **Two of the four turned out to be genuine PRODUCT bugs** (38.1 and 38.6a — the latter a
> silent data-loss path on *Save Feeds*), so this group's "**Risk: LOW.** Test-infra only — no
> product code expected" header is now WRONG for it.
>
> ✅ **THE ACCEPTANCE BAR IS MET.** Final sweep (`RUN_INTEGRATION=1`, 2026-08-07):
> **2 failed / 2420 passed / 25 skipped** (25m19s), and **both failures are the two known
> [Group 37.1](37-location-system-redesign.md) blank-`LocationID` rows** — Derek's live repro data,
> not test defects. **Zero flake-family reds.** Progression across the session:
> `3 failed` (38.1 + the 2 known) → `4 failed` (2 NEW + the 2 known) → **`2 failed` (only the 2
> known)**. The fourth in the Group 26 → 32 → 33 lineage, and a red sweep means something again.
>
> ⚠️ **Landing [Group 37.1](37-location-system-redesign.md) should take this to a literal 0.** Until
> then those two rows are the expected tail, and **any third red is genuinely new signal.**
>
> **Scope decision (Derek, 2026-08-06): fix all six flakes directly**, Group 32/33 style, with the
> hermeticity work done **alongside** rather than as a gate. This group absorbs the two standalone
> flake rows (escape-key + weigh-out) that the buglist itself kept recommending be consolidated —
> the "consolidate if more accumulate" bar was met at six.

---

## 🔴 CORRECTED 2026-08-07 — the group's framing was wrong twice

Both prior theories were wrong, and the second one was wrong in a way that made the work look
harder and more expensive than it is. **Read this before the two sections below it**, which are
kept for their evidence but whose *conclusions* are superseded.

**1. The sweep is SERIAL and deterministically ordered.** There is no `pytest-xdist` and no
`pytest-randomly` installed (`pip list` confirms only `pytest-base-url` + `pytest-playwright`),
and `pytest.ini` adds no ordering plugin. `pytest_collection_modifyitems` in `conftest.py` only
*adds skip markers* — it never reorders or deselects. So collection order is byte-identical on
every run.

**Therefore "a concurrent test had moved the spool it needed" is mechanically impossible.**
Test-vs-test contention cannot occur. What actually remains is only:
  - **(a)** state left behind by a test that ran EARLIER in the same serial run, or
  - **(b)** a race against the **app's own** background activity — the 2 s buffer poll, the 5 s
    dashboard pulse, the 30 s cancel-monitor daemon. This one IS genuine concurrency even under
    serial pytest, and it is the archived Group 26.8 `test_doassign_buffer_safety` signature.

**2. "Do not go hunting Bootstrap bugs that aren't there" was itself wrong.** 38.6b turned out to
be exactly a Bootstrap bug — not the *focus* bug originally filed, but the `_isTransitioning`
guard silently swallowing `.hide()`. The repo had already diagnosed and defended that same bug
once (Group 26.7); 38.6b's file contained a stripped copy of the defended helper.

**3. Run positions beat alphabetical file order.** pytest reorders to group the session-scoped
parametrized `browser` fixture, so E2E tests do NOT run in plain alphabetical file order. Any
analysis that assumes they do will produce confident, wrong polluter rankings — two such claims
were refuted this session (`test_archive_unarchive_e2e` was said to precede `test_clone_e2e`; it
actually runs at position **663** vs the victim's **115**, and `test_loc_mgr_bindings_api_e2e`
runs at **1922**, long AFTER the UI file at **304**). Derive positions empirically:
`pytest --collect-only -q --offline` — the line number IS the run position.

**The practical payoff:** a victim at position *P* can only be polluted by the tests at positions
1..*P*. Reproducing 38.2 took **96 seconds** instead of a 25-minute sweep. And where the cause is
in-app rather than ordering, delaying the relevant fetch *in-page* reproduces it on demand — the
38.1 pin does exactly that and runs in **~15 s**.

---

## ⚠️ Evidence from the 2026-08-03 capture (conclusions superseded — see above)

The originally filed theory was **Bootstrap focus / overlay-dismiss timing under load**. A captured
traceback on 2026-08-03 refuted *that specific* theory for two members. It was then read as
**shared-data contention**, which is right about the *symptom* for 38.6a but wrong about the
*mechanism* (it is an in-app dual-write race, not another test):

- **`test_clone_e2e::test_clone_spool_button`** — `TimeoutError: waiting for
  locator(".backlog-row").filter(has_text="SPOOL").first`. The backlog panel itself rendered
  (`expect(backlog_list).to_be_visible()` passed) — **there was simply no SPOOL row in it.** Nothing
  was intercepted or occluded; the element never existed. A concurrent test had
  archived/moved/consumed the spool it needed.
- **`test_loc_mgr_bindings_ui_e2e::test_feeds_section_save_round_trip`** — not a timeout or a missing
  element but `assert 'XL-1' == 'XL-2'`: **a save that did not stick.** That is what a concurrent test
  rewriting the same `slot_targets` row looks like.

**Method for each member: capture its own traceback first.** Run the sweep with `--tb=long -rf` teed
to a file — the failure detail has been lost to output truncation nearly every time, so most prior
"diagnoses" (including in the buglist) are inference, not evidence.

📌 **The 2026-08-03 capture was NOT lost — it is committed at
[flake-traceback-2026-08-03.txt](flake-traceback-2026-08-03.txt).** The 2026-08-06 handoff implied
otherwise, and that cost real time. It holds the real tracebacks for **38.4, 38.6a and 38.6b**
(5 failures / 2332 passed / 28m28s). The 2026-08-07 sweep added the first-ever capture for **38.1**
(`sweep_full_01`, 3 failed / 2415 passed / 25m19s). So four of the seven ids now have hard evidence;
**38.2, 38.3 and 38.5 still have none.**

---

## 📊 Baseline: a clean full sweep on 2026-08-06 fired NONE of them

The Group 36 verification sweep (`RUN_INTEGRATION=1`) came back
**2406 passed / 2 failed / 25 skipped** in 23m35s, and **zero of the seven test ids below
appeared.** Both failures were [Group 37.1](37-location-system-redesign.md)'s blank-`LocationID`
repro row (`test_locations_json_integrity` + the newly-attributed
`test_location_combobox_highlights_current_selection_on_focus`).

⚠️ **Do NOT read this as "they're fixed."** The whole premise of this group is
**load sensitivity**, and that sweep ran quiet — no concurrent agents, no parallel
verification, nothing else touching the container. A clean run under low contention is exactly
what the theory predicts. What it does establish:

- **One clean sweep is not evidence of a fix** — the acceptance bar needs repeated sweeps, and
  ideally one under deliberate contention.
- **38.1's filed rate ("fails ~2 of 3 FULL sweeps") did not reproduce here**, so that figure is
  stale or was measured under heavier load than a normal sweep.
- **The expected red tail while Derek's repro row is live is exactly those two** — so any future
  sweep can treat a third red as genuinely new signal.

**Update — the 2026-08-07 sweep produced exactly that third red, and it was 38.1.**
`RUN_INTEGRATION=1` came back **3 failed / 2415 passed / 25 skipped** (25m19s):
`test_escape_key_walks_out_of_three_level_stack` plus the two known Group 37.1 rows. So the
"treat a third red as new signal" rule worked as designed on its first outing. Two lessons worth
keeping:

- **One quiet sweep proving nothing cuts both ways.** 38.1 fired on the very next sweep with no
  deliberate contention at all — so "provoke them under load" was never a prerequisite, and the
  session that planned to start there would have spent its budget on the wrong thing.
- **Only ONE of the six fired.** A sweep is a poor sampling instrument for this family: ~25 min
  per sample, one member per sample if you are lucky. That is precisely why the two 🆕 levers
  below matter more than another sweep.

### Confirming sweep (#2, post-fix): 4 failed / 2415 passed / 27 skipped (25m01s)

**None of the four fixed members fired** — 38.1, 38.5, 38.6a and 38.6b were all absent, and 38.1
had fired in sweep #1, so that is a real (if single-sample) signal. **But two NEW reds appeared,
and neither should be swept under the rug:**

| New red | Assessment |
|---|---|
| `test_audit_visual_panel::test_audit_panel_opens_and_closes` | **Unrelated to any change here.** `#fcc-audit-panel-overlay` mounted *and* rendered its "Audit in Progress" title, but `#fcc-audit-panel-close` was never created — an element-never-created failure inside `mountOverlay`. A genuinely new, previously-unseen flake. **File it as a new member.** |
| `test_edit_full_bindings_auto_expands_feeds_section` | On a surface this session touched, so it was investigated rather than dismissed. **Not reproduced: 5/5 green isolated.** It is a **known load flake** — fixed once as Group 33.6 with a 12 s readiness gate, and it failed *at* that 12 s gate. The guard also has no bail path in this flow (exactly two `openManage` calls, zero dismissals) and `refreshManageView` — the 5 s pulse re-render — **does not call `openManage`**, so the pulse cannot move the counter. **Verdict: most likely the 33.6 flake recurring, NOT a regression — but not proven, so the guard was hardened anyway (`ac93cb5`).** |

⚠️ **Honest reading: this is a two-new-reds sweep, so the group is NOT closed.** The family is best
understood as a *population* — the same fixed-timeout / element-never-created / shared-state
classes keep producing new members. The four fixes are real and root-caused; the acceptance bar
("a fresh full sweep with 0 failures") is **not** met.

## Items — the six flakes

All six share the signature: **fails in a full sweep, passes 3/3–8/8 in isolation, zero surface
overlap with whatever diff ran alongside them.**

### ✅ Status after the 2026-08-07 session (`1756259`)

| # | Verdict | Root cause | Fix |
|---|---|---|---|
| **38.1** | ✅ **FIXED** | 🔴 **PRODUCT BUG.** `openManage` calls `modals.manageModal.show()` at the END of its `/api/get_contents` `.then()`. Escape 1 pops the breadcrumb and starts that fetch — its `#manage-loc-id` write is *synchronous*, which is precisely why Escape 1's assertions pass while the fetch is still outstanding. Escape 2 hides the modal; the late `.then()` re-opens it, and nothing closes it again. | Generation counter bumped by every dismissal + every newer open; stale `.then()` bails. Invalidated **synchronously** in `closeManage` (the `hidden.bs.modal` event trails `hide()` by the ~460 ms fade) plus a catch-all on `hidden.bs.modal`. Pinned by an in-page fetch-delay repro, **~15 s**, RED→GREEN proven. |
| **38.2** | ⚪ **RECLASSIFIED — collateral, not a member** | Did **not** reproduce from its own prefix (positions 1..35 = its only possible polluters): **49 passed / 3 skipped / 96 s**. It also owns its state via the save-seed-restore `bound_slot` fixture, and nothing before it writes the one row it needs (`XL-1`, `Type: Tool Head`). Its filed evidence was only ever "failed alongside 38.1 once". | None needed. Expected to stop appearing now 38.1 is fixed. **If it ever fires alone, that is new signal** — capture the traceback and check whether the failure is the *click* at :198 (⇒ the XL-1 row itself is wrong) or the *assert* at :200 (⇒ latency). |
| **38.3** | ✅ **FIXED** | The **seeding step** is the divergence window. `processScan` does **not** return its fetch, so two back-to-back `page.evaluate("window.processScan(...)")` calls launch two INDEPENDENT chains, each ending in `renderBuffer()` → `persistBuffer()`, which POSTs the WHOLE held-spool list unsequenced. Their POSTs can land out of order, leaving the server holding `[1]` while the client shows `[1, 2]`. `loadBuffer` runs every 2 s and its only defence is a hard-coded wall-clock grace (`localAge < 3000`); once the test's steps outrun 3 s the poll replaces the client list with the server's and takes row 2's un-submitted text with it. Same root cause as the archived Group 26.8 `doassign` flake. | Wait for the **server** buffer to converge on the scanned ids before proceeding. That removes the precondition entirely — afterwards `loadBuffer` sees `currentStr === serverStr` and is a no-op no matter how long the rest of the test takes. Strictly better than a bigger timeout, which would not have helped: the row was already gone. |
| **38.4** | ✅ **FIXED** | Traceback captured 2026-08-03 (backlog panel rendered, no SPOOL row). The filed "a concurrent test archived it" story is **refuted**: pytest is serial, and the accused `test_archive_unarchive_e2e` runs at position **663**, well AFTER the victim at **115**. The real defect is that the test could not tell three situations apart: it took only `page` (no `require_server`, no seeding, no precondition assertion), and `expect(backlog_list).to_be_visible()` passes on "Loading backlog…", on an **error div**, and on an empty list alike. `/api/print_queue/pending` collapses ANY exception — including its two `timeout=2` Spoolman reads — into `{success:false}`, which `inv_backlog.js:31` renders as a `.text-danger` div INSIDE the visible `#backlog-list`. So "Spoolman was briefly slow" was indistinguishable from "no flagged spool exists". | Check the precondition through the API first, wait for a real END state, then distinguish errored / empty / loaded with a skip message that names its own cause. Failure now reports in seconds instead of an opaque 30 s locator timeout. |
| **38.5** | ✅ **FIXED** | Wait budget **shorter than the product's own latency floor**. `showConfirmOverlay` awaits a ~3 s active-print probe before mounting (`inv_quickswap.js:340`/`:368`; `mountOverlay` not reached until `:468`), and the probe cache is request-scoped so every call re-pays it. Group 14.2 raised these waits to 8000 ms and **missed four sites still at 4000 ms** — two are 38.5, two were latent siblings. | All four raised to 8000 ms, matching the documented precedent at `test_quickswap_ui_e2e.py:77-79`. Plus a **hermetic source-level canary** (`test_overlay_wait_budgets.py`, runs in `--offline` in 0.5 s) so the budget cannot drift back under the floor — mutation-proven against both call spellings. |
| **38.6a** | ✅ **FIXED** | 🔴 **PRODUCT BUG — silent data loss.** One *Save Feeds* click fired the `slot_order` PUT in the **same tick** as the `bindings` PUT. Both are whole-file read-modify-write on `locations.json`; `set_dryer_box_slot_order` copies the **entire** `extra` dict including `slot_targets` (`locations_db.py:1549-1551`); `locations_db.py` holds **no lock of any kind**; Flask runs threaded. So slot_order could snapshot the pre-edit row, bindings write the new targets and return 200, then slot_order write its stale copy back — reverting a save the UI had already reported as "✅ Saved". | Sequence `slot_order` **after** the bindings write settles, so it always reads a row that already holds the new `slot_targets`. |
| **38.6b** | ✅ **FIXED** | Bootstrap swallowed `.hide()`. `to_be_visible()` returns at the **start** of the `.modal.fade` transition, so the immediately-following `.hide()` hit the `_isTransitioning` guard and returned **before** dispatching `hide.bs.modal` — the listener that mounts `#fcc-wiz-unsaved-changes` never ran. | Wait for the public `shown.bs.modal` event before hiding; restore the 3-attempt retry to `_force_close_wizard`, which was a stripped copy of the **defended** helper at `test_wizard_group10_session_a.py:33-56` (Group 26.7). |

### Members 7 and 8 — surfaced BY the confirming sweep, then fixed the same day

| # | Verdict | Root cause | Fix |
|---|---|---|---|
| **38.12** `test_audit_visual_panel::test_audit_panel_opens_and_closes` | ✅ **FIXED** | **The test raced the panel's OWN correct behaviour.** `openAuditPanel()` mounts synchronously and immediately starts `_poll()`; on `{active: false}` that poll calls `closeAuditPanel()` and tears the whole overlay down. The test never started an audit — its docstring claims it seeds one "via API + state", but the body never did — so dev answers `{"active": false}` and the panel is *right* to close. It passed only when all three assertions beat the fetch. | Stub `/api/audit_session` with an active session: this is a visual-panel smoke test, the endpoint is covered by `test_audit_session_endpoint.py`, and stubbing avoids starting (and cleaning up) a real audit on shared dev. Plus a **new pin** for the self-close on `{active: false}` — correct behaviour worth keeping, and now discoverable by test name. |
| **38.13** `test_edit_full_bindings_auto_expands_feeds_section` | ✅ **FIXED** | **Not the slow-chain story its own comment told.** `renderQuickSwapSection` reveals its section synchronously (`inv_quickswap.js:86`) but builds the `.fcc-qs-slot` buttons inside an async `/api/printer_map` fetch (`:88-96`), and `openManage` calls `.show()` without awaiting it — so the modal is **visible before the slots exist**. `editBindingsFromToolhead` reads `grid.querySelector('.fcc-qs-slot')` at click time; with no slot yet, `targetBox` is null and it takes the **fallback branch, which CLOSES the manage modal** and opens the Locations modal. `#manage-feeds-section` then never appears — hence 15 polls across the full 12 s, always hidden. | Wait for the grid to actually **populate** before clicking, and skip if it never does — the discipline its sibling `test_escape_key_walks_out_of_three_level_stack` has always had. ⚠️ Widening the gate a **third** time could not have worked: the click had already gone down the wrong branch. |

> ⚠️ **Row 38.6 must be SPLIT.** It bundles two demonstrably different root causes — 38.6a is a
> backend lost-update race (a *value* failure), 38.6b is a Bootstrap transition swallow (an
> *element-never-created* failure). They share nothing but a row number.

> 🧠 **The pattern across all eight.** Not one member wanted a bigger timeout. Every single one was
> a test asserting against state the app was **entitled to change** — a modal re-showing itself, a
> panel closing itself, a grid not yet built, a poll reclaiming the buffer, a save reverted by its
> own sibling request. Two were unfixable by widening *in principle*, because by the time the
> assertion ran the thing being waited for had already been destroyed or never created. When a
> flake here looks like "just needs longer", that is the hypothesis to distrust first.

| # | Test | Evidence so far |
|---|---|---|
| **38.1** | `test_return_and_breadcrumb.py::test_escape_key_walks_out_of_three_level_stack` | Fails ~2 of 3 FULL sweeps; passes 5/5 then 3/3 isolated. "Escape 2" expects `#manageModal` hidden, it stays visible (`tests/test_return_and_breadcrumb.py:291`). Failed sweeps #2 and #4, clean on #3 with identical UI. |
| **38.2** | `test_bind_slot_picker.py::test_bind_picker_opens_from_quickswap_header` | Failed alongside 38.1 once; 3/3 isolated. Filed as its sibling — treat together. |
| **38.3** | `test_weigh_out_preserve_text_e2e.py::test_weigh_out_preserves_sibling_text_on_save_redraw` | One full-sweep failure, then **5/5 isolated** and 2/2 under moderate load. ⚠️ Traceback was LOST (background task retained only 15 lines) — **reproduce with the traceback before fixing.** Guards Group 31.3 (`renderWeighOutList()` snapshotting `.weigh-input` across the `innerHTML` rebuild). Both redraw triggers race the live buffer poll — same "live poll overwrites locally-injected state" root cause as the archived `test_doassign_buffer_safety` flake (Group 26.8). |
| **38.4** | `test_clone_e2e.py::test_clone_spool_button` | ✅ **Traceback captured** — DATA failure, see above. |
| **38.5** | `test_return_text_and_overlay_close.py::test_return_overlay_flags_missing_origin_explicitly` | Same return/overlay-close surface as 38.1 — strong signal they share a root cause. |
| **38.6** | `test_loc_mgr_bindings_ui_e2e.py::test_feeds_section_save_round_trip` **+** `test_wizard_overlay_migration.py::test_unsaved_changes_overlay_escape_keeps_editing` | Both cleared as flakes, **4/4 isolated**, and structurally impossible for the diff that ran alongside (that change added `onchange="this.blur()"` to the slot-**ORDER** radios in `modals_loc_mgr.html`; the failing test never touches those — it drives a `<select>` and asserts on `slot_targets`). The bindings failure mode is itself a contention signature (see above). |

## Items — the hermeticity residuals

From the 2026-08-05 adversarial review's deferred findings (all LOW, none data-losing). They belong
here because they are exactly the levers that make the flakes above reproducible-or-gone.

| # | Item |
|---|---|
| **38.7** | ✅ **DONE 2026-08-07** (`2d36a62`). `--offline` is now ENFORCED, not merely intended: a session-scoped autouse socket guard refuses any TCP connect to port **8000 / 7913 / 7912** (matching on port covers localhost / 127.0.0.1 / ::1 / the NAS uniformly). Chose the socket guard over the lint because a lint cannot see an f-string, an env-derived URL, or a helper. `OfflineNetworkAccess` subclasses `requests.exceptions.ConnectionError` so the many existing `except requests.RequestException: pytest.skip("Container not responding")` guards do the right thing untouched — under `--offline` the container IS unreachable, by policy. **It immediately found FOUR leaks, not two**: `test_printer_state_api`, `test_search_deployed_filter` and `test_locations_json_integrity`'s printer_map probe now skip gracefully; the fourth was a real defect — `test_wizard::test_edit_spool_wizard`, a Flask-test-client "unit" test that mocked `update_spool`/`update_filament` but never the pre-edit `get_spool` added by 27.1, so it was reaching the NAS and passing only because dev Spoolman happened to hold spool 100. Now mocked. |
| **38.8** | ✅ **DONE 2026-08-07** (`2d36a62`). Four direct tests of `pytest_collection_modifyitems`: a container-fixture item skips, a hermetic item does NOT (over-skipping would hollow out the fast sweep), a normal run skips nothing for offline reasons, and **every** name in `CONTAINER_FIXTURES` actually triggers the hook — the set and the hook must agree for all of them, not just `page`. |
| **38.9** | ✅ **DONE 2026-08-06 by [Group 36](36-attribute-force-reset-data-loss.md)** (`43389c6`). The canary now collects every name bound to `requests` via `ast.Import` (module-level *or* function-local) and matches on that set, with two new pins: an aliased `_req.patch`/`_req.delete` sample is caught, and a look-alike receiver (`import some_other_lib as _req`, `self.session.get`) is NOT flagged. Group 36 also widened the **sibling** canary `test_no_direct_extra_patch.py` to see the restore PATCH through `http_retry.request_with_retry("patch", ...)` — that call had moved behind the helper, taking its `# noqa: spoolman-extra-patch` marker out of scope and silently dropping the same loop from *that* canary too. _Original: matched only `requests.<verb>(...)`, so all 14 `_req.*` calls in `routes_config_attrs.py` — including the destructive migration PATCH loop — were invisible._ |
| **38.10** | ✅ **DONE 2026-08-07** (`2d36a62`). `created_id` is now set on the ADOPT branch too, so the fixture owns a reused record and deletes it. Previously self-healing by name but never self-CLEANING: an interrupted run leaked `__fcc_attr_test__` permanently, and every later run adopted-then-re-leaked it. Teardown is best-effort so it cannot mask the test's own result. |
| **38.11** | ✅ **DONE 2026-08-07** (`2d36a62`). The real hazard was ORDERING and the old test could not see it: the drain must be **last** in the IIFE because `registerShortcut` calls `renderList`, a `const` declared partway down — draining earlier throws a TDZ `ReferenceError` that wipes EVERY shortcut. Added a hermetic source-level pin for that ordering, one for `splice(0)`-consumes-the-queue, and a live test that the **shipped** drain emptied the queue after a real page load. The old `page.evaluate` test is kept but labelled non-load-bearing. |

---

## Levers available (that Groups 26/32/33 did not have)

- 🆕 **Ordered-prefix reproduction (2026-08-07).** Because the run order is deterministic, a victim
  at position *P* can only be polluted by positions 1..*P*. Get positions with
  `pytest --collect-only -q --offline` (line number = run position), then run just the files in
  that prefix, in order. 38.2's entire prefix ran in **96 s** versus a 25-minute sweep. A pass
  there is a real result: it **exhausts the ordering hypothesis** for that member.
- 🆕 **In-page fetch delay (2026-08-07)** — the lever for the (b)-class races, where the enemy is
  the app's own async behaviour rather than another test. Patch `window.fetch` inside the page to
  delay one endpoint, instead of hoping sweep load reproduces the timing:

  ```js
  const orig = window.fetch;
  window.fetch = (url, ...rest) => (String(url).includes('/api/get_contents')
      ? new Promise((res, rej) => setTimeout(() => orig.call(window, url, ...rest).then(res, rej), 2000))
      : orig.call(window, url, ...rest));
  ```

  This turned 38.1 from "fails ~2 of 3 sweeps, 25 min a throw" into a **~15 s deterministic pin**
  that reproduces the captured traceback byte-for-byte. Prefer it to a Playwright `route` handler
  with a blocking `sleep`, which stalls the sync dispatcher. Reference:
  `test_return_and_breadcrumb.py::test_late_get_contents_cannot_reopen_a_dismissed_manage_modal`.
- **`--offline` / `FCC_OFFLINE=1`** (shipped `4f10e35`) — a genuinely hermetic sweep, **~27 min → ~42 s**,
  cannot write to dev. Skips by **fixture name** at collection time. Use it for all iteration.
- **`pytest --reset-dev`** — restores dev to the committed seed baseline before a sweep, so cross-test
  contamination can't accumulate. It exists for exactly this problem but is not yet part of the routine
  cadence. ⚠️ **It discards hand-made dev state — check with Derek before using it**, and note
  `data/locations.json` currently holds his live blank-LocationID repro row (Group 37.1).
- **`atomic_store.replace_with_retry`** (Group 32) and the `mask=` snapshot support (Group 33) are
  already in place.

## 📋 Follow-ups surfaced 2026-08-07 — for Derek to file STANDALONE

Not filed into the buglist by me (it is Derek's), and deliberately **not nested under this group**
— nesting a follow-up under an epic that later closes makes it vanish when the epic is archived
([[feedback_standalone_followups_not_under_completed_epics]]).

1. **🔴 `locations.json` writes have no concurrency control at all — the 38.6a fix only removed the
   trigger, not the race.** `grep -c 'Lock\|RLock\|threading' inventory-hub/locations_db.py` returns
   **0**, while `app.run()` is threaded. Every mutator is a whole-file read-modify-write. The
   38.6a fix sequences the one client-side caller that reliably collided; **two browser tabs, or a
   pulse-driven write racing a user save, can still lose an update.** Worth a deliberate decision:
   a module-level lock around load→mutate→save, or compare-and-set.
2. **🟠 `set_dryer_box_bindings` / `set_dryer_box_slot_order` discard `save_locations_list`'s return
   value and report success unconditionally** (`locations_db.py:1553`, `:1694` — both are a bare
   `save_locations_list(loc_list)` followed by `return True, ...`). That function's own docstring
   says it "Returns True when the new list is durably persisted + verified, False on any failure
   path". It can return False via the orphan write-guard, an atomic-write exception, or a failed
   verify-after-write — and the user still gets HTTP 200 + "✅ Saved N binding(s)" with the disk
   unchanged. **This is an independent second way to produce the exact 38.6a symptom**, and it
   makes every snapshot/restore fixture in the suite unreliable.
3. **🟡 A Playwright route stub that has never matched anything.**
   `test_toolhead_scan_single_spool.py:43` does `page.route("**/api/buffer", ...)`, but the real
   endpoints are `/api/state/buffer` and `/api/buffer/clear` — a URL glob must match the whole URL
   and neither ends in `/api/buffer`. The stub's stated purpose ("so background polling can't
   overwrite the test's synthetic spools") is therefore **not being served**; the test currently
   survives on the `lastLocalBufferChange` grace instead.
   ⚠️ **Scope note, checked:** the claim that this leaks synthetic spools 9991/9992 into the shared
   buffer is **NOT confirmed** — the live buffer read `[]` immediately after a full sweep. Treat as
   test-hygiene, not a data leak.
4. **🟡 `test_archive_unarchive_e2e.py` carries no `@pytest.mark.integration`** yet archives a real
   dev spool (it picks the first non-archived spool with a location, drains it to trigger
   `_auto_archive_on_empty`, and restores inside a bare `except Exception: pass`). It runs on any
   plain sweep where the container is up. It is **not** a 38.4 suspect (position 663 vs 115), but
   it does mutate shared inventory for every test after it.

---

## Verification

- Per-flake: capture the traceback, fix, then **≥5 isolated runs** before accepting any verdict
  ([[feedback_flaky_e2e_needs_multiple_samples]] — a one-sample A/B has already *falsely* convicted an
  innocent change here).
- Group deliverable: a fresh full `RUN_INTEGRATION=1` sweep with **0 failures**, the same bar Group 33
  hit (`2138 passed / 0 failed / 11 skipped`).
- ⚠️ **Do not run visual/E2E verification while a full sweep is concurrently saturating the dev
  container** ([[feedback_no_concurrent_sweep_and_visual]]) — that cost 5 spurious failures in Group 33.

## Why these are one group

Same class as Groups 26 / 32 / 33: concurrency and shared-state robustness that only bites on the
saturated full sweep. The difference this time is that the evidence points at **data contention** on
the shared dev container rather than UI timing — so the hermeticity residuals (38.7–38.11) are not a
side quest, they are the same bug seen from the tooling side. Test-only, LOW risk.

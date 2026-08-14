# Group 38: 🧪 Sweep Flakes & Hermeticity Residuals

**Branch name (when started):** `feature/group-38-sweep-flakes-hermeticity`
**Estimated effort:** ~4–7 hours (6 flakes + 5 test-infra residuals)
**Risk:** **LOW.** Test-infra only — no product code expected.

> **Status: `TODO`** — filed 2026-08-06 (`/refresh-groups`). The fourth in the
> Group 26 → 32 → 33 lineage: make a red sweep mean something again.
>
> **Scope decision (Derek, 2026-08-06): fix all six flakes directly**, Group 32/33 style, with the
> hermeticity work done **alongside** rather than as a gate. This group absorbs the two standalone
> flake rows (escape-key + weigh-out) that the buglist itself kept recommending be consolidated —
> the "consolidate if more accumulate" bar was met at six.

---

## ⚠️ The evidence changed — read before diagnosing

The originally filed theory was **Bootstrap focus / overlay-dismiss timing under load**. A captured
traceback on 2026-08-03 **refuted that for at least two members**, and the real cause is
**shared-data contention**:

- **`test_clone_e2e::test_clone_spool_button`** — `TimeoutError: waiting for
  locator(".backlog-row").filter(has_text="SPOOL").first`. The backlog panel itself rendered
  (`expect(backlog_list).to_be_visible()` passed) — **there was simply no SPOOL row in it.** Nothing
  was intercepted or occluded; the element never existed. A concurrent test had
  archived/moved/consumed the spool it needed.
- **`test_loc_mgr_bindings_ui_e2e::test_feeds_section_save_round_trip`** — not a timeout or a missing
  element but `assert 'XL-1' == 'XL-2'`: **a save that did not stick.** That is what a concurrent test
  rewriting the same `slot_targets` row looks like.

**Three of the six members now point at shared-data contention rather than focus/dismiss races.**
Do not go hunting Bootstrap focus bugs that aren't there.

**Method for each member: capture its own traceback first.** Run the sweep with `--tb=long -rf` teed
to a file — the failure detail has been lost to output truncation nearly every time, so most prior
"diagnoses" (including in the buglist) are inference, not evidence.

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

## Items — the six flakes

All six share the signature: **fails in a full sweep, passes 3/3–8/8 in isolation, zero surface
overlap with whatever diff ran alongside them.**

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
| **38.7** | **`--offline` leaks via hardcoded URLs.** The gating is fixture-name-based, so two in-tree tests that hit `http://localhost:8000` with a literal URL and no gated fixture still run in an "offline" sweep. Either add a socket-level guard under `--offline`, or a lint forbidding literal `localhost:8000` outside the gated fixtures. |
| **38.8** | **The `--offline` collection hook itself is untested.** `test_offline_mode.py` pins the constant and the env parser, not the hook. _(Refuted as stated — the hook is exercised implicitly every offline run — but a direct test is cheap.)_ |
| **38.9** | ✅ **DONE 2026-08-06 by [Group 36](36-attribute-force-reset-data-loss.md)** (`43389c6`). The canary now collects every name bound to `requests` via `ast.Import` (module-level *or* function-local) and matches on that set, with two new pins: an aliased `_req.patch`/`_req.delete` sample is caught, and a look-alike receiver (`import some_other_lib as _req`, `self.session.get`) is NOT flagged. Group 36 also widened the **sibling** canary `test_no_direct_extra_patch.py` to see the restore PATCH through `http_retry.request_with_retry("patch", ...)` — that call had moved behind the helper, taking its `# noqa: spoolman-extra-patch` marker out of scope and silently dropping the same loop from *that* canary too. _Original: matched only `requests.<verb>(...)`, so all 14 `_req.*` calls in `routes_config_attrs.py` — including the destructive migration PATCH loop — were invisible._ |
| **38.10** | **`scratch_filament` never deletes a REUSED record.** It only deletes what it created, so an interrupted run leaves `__fcc_attr_test__` in dev Spoolman permanently (the next run adopts it and never cleans up). Delete on adoption too, or clean up by name at session end. |
| **38.11** | **The shortcut-queue drain has no real test.** `test_shortcut_registration_order.py`'s "end-to-end" case re-implements the shim inside `page.evaluate` rather than exercising the shipped one, so it **passes against pre-fix code**. The drain line — whose placement caused a TDZ crash that wiped every shortcut — is only covered indirectly by `test_bulk_move_shortcuts_are_listed_in_the_help_overlay`. Pin it directly. |

---

## Levers available (that Groups 26/32/33 did not have)

- **`--offline` / `FCC_OFFLINE=1`** (shipped `4f10e35`) — a genuinely hermetic sweep, **~27 min → ~42 s**,
  cannot write to dev. Skips by **fixture name** at collection time. Use it for all iteration.
- **`pytest --reset-dev`** — restores dev to the committed seed baseline before a sweep, so cross-test
  contamination can't accumulate. It exists for exactly this problem but is not yet part of the routine
  cadence. ⚠️ **It discards hand-made dev state — check with Derek before using it**, and note
  `data/locations.json` currently holds his live blank-LocationID repro row (Group 37.1).
- **`atomic_store.replace_with_retry`** (Group 32) and the `mask=` snapshot support (Group 33) are
  already in place.

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

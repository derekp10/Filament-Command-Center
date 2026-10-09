# Group 36: 🔴 Filament-Attribute `force_reset` Data Loss

**Branch:** `feature/group-36-attribute-force-reset-data-loss`
**Effort spent:** ~1 session (grounding + build + adversarial review + fixes)
**Risk:** HIGH blast radius, MEDIUM change size — every change here had to be provably value-preserving.

> **Status: ✅ BUILT, pending merge to `dev`.** Commits `43389c6` (the fix) and
> `a9a582d` (adversarial-review fixes). Full offline sweep **1654 passed / 1 failed** —
> the failure is the pre-existing blank-`LocationID` repro row kept for [Group 37.1](37-location-system-redesign.md).
>
> ⚠️ **The `pytest.mark.integration` + `FCC_ALLOW_DESTRUCTIVE_ATTR_TESTS` double gate on
> `test_filament_attributes_bulk_api.py` STAYS.** Those tests still drive the real destructive
> migration against dev Spoolman; the gate is not what this group was fixing.

---

## ⚠️ The filed premise was WRONG — read this before anything else

**36.1 asked us to confirm a suspected escalation to every extra. There is none.** Settled at
source for the exact deployed build (Spoolman **v0.23.1**, `git_commit eafbc64`, matched against
the live dev `/api/v1/info`):

- Spoolman does **not** store `extra` as a JSON sub-document. It is a child table
  `filament_field` with composite primary key `(filament_id, key)`.
- The field delete is `sqlalchemy.delete(FilamentField).where(FilamentField.key == key)` —
  global across records, **surgical within each one**.

So a failed restore loses **exactly `filament_attributes`** on that record. Siblings are
*structurally* untouchable by it. **No scratch-record repro was needed, and none was run** — the
source answers it, and poking a live Spoolman carried real risk for no added certainty.

**Where the sibling losses actually came from:** the pre-2026-05-19 draft that PATCHed a *partial*
extras dict, tripping Spoolman's replace-the-whole-sub-document PATCH semantics. Already fixed;
its rationale is recorded at [spoolman_api.py:1013-1020](../../../inventory-hub/spoolman_api.py#L1013-L1020).
Its fingerprint is still in the data — dev is bimodal (attrs-only 110, siblings-only 64, **both 2**)
where prod has 22 "both".

**The circumstantial statistic in the original filing was also misleading.** A fresh dev↔prod diff
(2026-08-06, both dumped read-only) shows only **12** records where dev lacks a prod sibling, versus
**1** the other way — and 16 of the 31 missing keys are the `nozzle_temp_max`/`bed_temp_max` pair,
which is feature drift, not loss. Genuinely suspicious: **#4** (extras entirely empty), **#121**,
**#175**, **#157**.

### 🔎 Still open, and separable

Dev is missing sibling extras that **prod still has**, from that already-fixed historical bug.
A read-only prod→dev restore would recover them. Filed as a follow-up, not part of this group —
prod (`:7912`) is the reference, and *never guess-restore*.

---

## What was actually wrong (the audit found worse than what was filed)

**Three MASS-loss paths, none of them in the original task file:**

1. **`remove_choice` had no zero-filament guard** — `sweep_unused` has had one since it shipped.
   On a transient empty read it deleted the field, recreated it, restored **nothing**, and returned
   `success: True`. Every filament loses its attributes because Spoolman blinked.
2. **Purging the last choice** — Spoolman rejects an empty `choices` array, and that rejection
   lands **after** the DELETE. Schema missing, restore loop never reached. Reachable from Sweep,
   whose checkboxes default to all-checked.
3. **Death between DELETE and restore** was unbounded and untraced — the snapshot lived only in the
   request handler's memory. In DEV, editing any `.py` restarts the container mid-flight via
   `use_reloader`. **This is the most plausible explanation for "26 filaments drained over months."**

**The real failure mode is a transport ReadTimeout**, proven by wall-clock arithmetic in `hub.log`:
every restore failure cost almost exactly the loop's 10 s timeout, which an HTTP rejection
(milliseconds) cannot produce. So a bounded retry genuinely recovers them.

**And the loss was invisible because** both endpoints returned `success: True` over confirmed data
loss, the frontend showed a green toast and never read `restore_failures`, and
`configAttrsRemoveChoice` hardcoded `force: true` so the server's `needs_confirm` gate was
unreachable — a zero-usage tag got **no confirmation at all** before ~150 records were rewritten.

---

## Items — all delivered

| # | Item | Outcome |
|---|---|---|
| **36.1** | Confirm the suspected escalation | ✅ **ANSWERED: no escalation.** Attributes-only, proven at source. Premise corrected above. |
| **36.2** | Retry failed restores, fail LOUDLY | ✅ New `http_retry.py` — transport-only retry, 15 s floor. Plus **verify-by-re-read**: a ReadTimeout may mean the write *landed*, so the record is re-read before anything is called lost. `success: false` on loss; casualty ids in a 12 s error toast. |
| **36.3** | Fix the recovery-payload logging | ✅ Logs the **post-filter** payload (the pre-filter one re-introduced the removed choice, which then 400s on replay — observable in Derek's own `hub.log`). Explicit ASCII `...TRUNCATED` sentinel; `msg` and payload both ASCII-coerced so a non-ASCII Spoolman error can't drop the line on the Windows host. |
| **36.4** | Stop force-resetting on a user click | ✅ **Both**, per Derek. **Hide by default** — strips the tag from carriers via `update_filament`'s read-merge-write, suppresses the choice locally, schema untouched, reversible. **Purge** remains behind a confirm stating the record count. |

**Beyond the filed scope:** all three force_reset sites now share the primitives — including the
boot-time `ensure_filament_attributes_cleaned`, which was the worst of the three (bare count, no
ids, narrower `except`). Restore set narrowed to records that actually carry the key (**176 → 158**
on live dev). Migration lock (409 on concurrent runs). Full field-def echo on recreate
(`order`/`unit`/`default_value` were being silently reset). Unfinished migrations are **announced**
at boot — deliberately not auto-replayed, since a stale snapshot would revert every edit made since.

---

## New modules

| File | Owns |
|---|---|
| `inventory-hub/http_retry.py` | Bounded transport-only retry, 15 s floor. Dispatches via `getattr(requests, verb)` **on purpose** — `requests.request` would bypass every test monkeypatch seam. |
| `inventory-hub/attr_migration.py` | Recovery snapshot to `data/` *before* the DELETE, the retrying+verifying restore loop, shared casualty reporting, and the hidden-choice store. |

---

## The adversarial review earned its keep

8 agents (6 lenses + **2 batched** verifiers per the CLAUDE.md budget rule), **44 raw → 23 confirmed
/ 21 refuted**, collapsing to 10 root fixes. The top finding was a regression *I introduced*:

- 🔴 **A timed-out schema DELETE was discarding the recovery snapshot.** A returned status means the
  field is intact (clearing is right); an *exception* is precisely the case where Spoolman may have
  committed the DELETE and only the response was lost. That re-opened the exact hole this group
  exists to close. The boot site had the mirror-image bug.
- 🔴 **Hidden choices were still offered by every tag picker** — the filter was applied to the
  Choices-Manager report but not `/api/external/fields`, which is what the wizard and Edit Filament
  modal actually read. `visible_choices` existed for this and had zero call sites.
- 🟠 **`_get_raw_extras` returned `{}` on read FAILURE**, indistinguishable from "no extras" — so a
  read blip turned a merge into a sibling-wiping partial PATCH. Now returns `None`; all three
  callers refuse the write.

**One review suggestion deliberately not taken:** retrying the pre-merge extras read through
`http_retry`. That helper resolves `requests` from its own namespace, while **eleven** test files
patch the seam as `spoolman_api.requests` — routing through it silently escapes that seam on the
app's hottest write path. Caught by `test_logic_undo`; reverted to a direct call.

---

## Verification

- **26 hermetic pins** in `tests/test_attr_migration_group36.py`, **11 of them mutation-proven**
  (fix reverted → test fails). Nothing here needs the live dev Spoolman.
- L316 characterization pins flipped in the same commit per the pin-in-same-commit contract, each
  with the reason recorded in its docstring.
- Route-table pin updated for `/api/filament_attributes/unhide_choice` + the `app.` re-export.
- **Both canaries widened**, closing real coverage holes:
  - `test_requests_timeout_canary.py` now follows `import requests as _req` (**Group 38.9** — the
    app's most dangerous write loop was invisible to it).
  - `test_no_direct_extra_patch.py` now sees the PATCH through `request_with_retry`, so the
    `# noqa: spoolman-extra-patch` marker is load-bearing again rather than decorative.
- **Repo-wide autouse isolation** in `conftest.py` redirects `attr_migration`'s data paths to
  `tmp_path`, so no test can leave a recovery snapshot or a hidden choice in the real `data/`.

## Follow-ups (not blockers)

- **Prod→dev sibling-extras restore** for the ~4 genuinely-drained records (§"Still open" above).
- The pre-merge extras read has no retry — a genuine Spoolman outage now refuses writes rather than
  wiping siblings. Correct, but a seam-aware retry would reduce false refusals.
- `_parse_filament_attrs_value` collapses a non-JSON string (`"Silk, Matte"`) into one pseudo-tag,
  which can make real tags read as zero-usage and therefore sweepable. Dormant on current data.
- `setup-and-rebuild/setup_fields.py:244-248` still holds a partial-`extra` PATCH on the **spool**
  side — dormant (guarded), but the same landmine in the function CLAUDE.md calls the template.

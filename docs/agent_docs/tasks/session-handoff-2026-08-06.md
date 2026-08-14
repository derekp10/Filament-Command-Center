# 🔁 Session Handoff — 2026-08-06 (Group 36)

> For a fresh context window. Read this, then the group task files it points at.
> Supersedes [session-handoff-2026-08-05.md](session-handoff-2026-08-05.md), whose open
> items are now filed as Groups 36 / 37 / 38.

## Git state

| Branch | Contents |
|---|---|
| `feature/group-36-attribute-force-reset-data-loss` | **4 commits — this session. NOT merged.** |
| `dev` | `70132aa` — unchanged this session |
| `main` | `b49158b` — **51 commits behind `dev`; release still HELD** |

**The dev→main release is still held** pending Derek driving the Bulk Move panel on dev. That
predates this session and nothing here changes it. The prod pull is also still pending.

**Nothing was merged.** Group 36 is built and verified on its branch, awaiting Derek's call.

---

## ✅ Group 36 — DONE on its branch

Commits: `43389c6` (fix) · `a9a582d` (adversarial-review fixes) · `32c31be` + `312b210` (docs).
Full detail: [36-attribute-force-reset-data-loss.md](36-attribute-force-reset-data-loss.md).

### 🔴 Read this first: the group's founding premise was REFUTED, not confirmed

36.1 said "confirm the suspected escalation to every extra, before anything else." **There is no
escalation.** Spoolman v0.23.1 (`eafbc64`, matched against the live dev `/api/v1/info`) stores
`extra` as the child table `filament_field` keyed `(filament_id, key)`; the field delete is
`DELETE … WHERE key = ?`. A failed restore loses **exactly `filament_attributes`** — siblings are
*structurally* untouchable.

**The planned scratch-record repro was therefore NOT run**, deliberately: the source settles it,
and poking a live Spoolman carried real risk for no added certainty. Durable fact captured in the
`reference_spoolman_extra_is_a_child_table` memory so nobody re-derives it.

#175's missing siblings come from the **already-fixed** pre-2026-05-19 partial-PATCH draft. The
filed "6 of 7 vs 27 of 76" statistic was misleading — a fresh read-only dev↔prod diff shows
**12 vs 1**, over half of it benign `nozzle_temp_max`/`bed_temp_max` drift.

### The audit found worse than what was filed

Three **mass-loss** paths, none of them in the task file, all closed:

1. `remove_choice` had no zero-filament guard (`sweep_unused` always did) — a transient empty read
   deleted the field, restored nothing, returned `success: True`.
2. Purging the **last** choice: Spoolman rejects an empty `choices` array *after* the DELETE →
   schema missing, restore loop never reached.
3. Death between DELETE and restore was unbounded + untraced. **In DEV, editing any `.py` restarts
   the container mid-flight — the most plausible explanation for the 26 drained filaments.**

Root cause of the observed failures proven to be **transport ReadTimeouts** (each cost ~10.0 s =
the loop timeout; a 4xx returns in ms), so a bounded retry genuinely recovers them.

### What shipped

New `http_retry.py` + `attr_migration.py` (disk recovery snapshot **before** the DELETE, retry with
verify-by-re-read, shared casualty reporting), applied to **all three** force_reset sites including
the boot-time `ensure_filament_attributes_cleaned`. **36.4 = both** (Derek's call): hide-by-default
plus a hardened purge behind a record-count confirm. `success: false` on confirmed loss with
casualty ids in the toast.

**Also closes [Group 38](38-sweep-flakes-and-hermeticity.md) item 38.9.**

### Verification

- Offline sweep: **1654 passed / 1 failed**
- Full `RUN_INTEGRATION=1`: **2406 passed / 2 failed / 25 skipped** (23m35s) — **zero regressions**
- 26 hermetic pins, **11 mutation-proven** (fix reverted → test fails)

---

## 🧪 The red tail is now fully attributed — expect exactly TWO

Both sweep failures are **the same cause**: Derek's live blank-`LocationID` repro row
([Group 37.1](37-location-system-redesign.md)). Both A/B-proven pre-existing.

1. `test_locations_json_integrity::test_every_row_is_a_dict_with_LocationID_and_Type` (known)
2. `test_wizard_group10_session_a::test_location_combobox_highlights_current_selection_on_focus`
   — **newly attributed this session.** Deterministic (5/5 isolated), *not* a load flake. Chain
   verified, not assumed: the blank row is served in `/api/locations` (1 of 60, checked live) →
   the helper picks **dropdown index 1**, where that row sorts → its `data-value` is `""` → no
   option can be marked `.active`.

**Both go green when 37.1 lands. Neither test needs editing.** Any third red on a future sweep is
genuinely new signal.

---

## Open items, in the order I'd take them

1. **Merge Group 36 to `dev`** — Derek's call. Built, reviewed, swept.
2. **[Group 38](38-sweep-flakes-and-hermeticity.md) — flakes & hermeticity.** ⚠️ **New evidence:
   the 2026-08-06 clean sweep fired ZERO of the seven filed flake ids.** Do not read that as
   "fixed" — the premise is load sensitivity and that sweep ran quiet. It does mean one clean
   sweep proves nothing, and 38.1's filed "fails ~2 of 3 sweeps" rate did not reproduce.
   **38.9 is already DONE** (Group 36). The four remaining hermeticity residuals (38.7, 38.8,
   38.10, 38.11) are small, offline-testable, and independent of the flake hunt — a good
   self-contained slice. The six flakes need repeated full sweeps (~24 min each) plus ≥5 isolated
   runs per member, so budget a session for them alone.
3. **[Group 37](37-location-system-redesign.md) — location redesign.** ⛔ **4 open forks must be
   decided before ANY build** (biggest: is the human-readable composite LocationID still the right
   model?). LARGE / multi-session / HIGH risk. Landing 37.1 alone would clear both sweep reds.
4. **Prod→dev sibling-extras restore** (new follow-up from Group 36) — ~4 filaments still drained
   by the old partial-PATCH bug. Prod (`:7912`) is the read-only reference. **Never guess-restore.**
5. **Remaining audit axes** — (b) overlay/confirm reachability, (c) silent-failure, (d)
   write-surface conformance, (e) load-order. ~0.5–1M tokens each, one at a time, batched verify.

---

## Conventions worth carrying forward

- **Check the source before designing an experiment.** Group 36's entire first task was to run a
  risky repro against live Spoolman. Reading the deployed build's source answered it in one agent
  and made the experiment unnecessary.
- **Mutation-test a pin before trusting it.** Revert the fix, confirm the test fails. 11 of 26 new
  pins were checked this way; all held, but the discipline is what makes that meaningful.
- **An A/B proves "not my change", NOT "not a real bug".** Both sweep reds were A/B'd against the
  base commit *and* then traced to a mechanism.
- **Don't change a patch seam as a side effect.** Routing a read through `http_retry` escaped the
  `spoolman_api.requests` seam that 11 test files rely on. Caught by `test_logic_undo`; reverted.
  A review suggested it; being right in the abstract isn't enough.
- **Batch the verify stage.** 8 agents total (6 lenses + **2** batched verifiers) for 44 findings —
  per the CLAUDE.md budget rule, never one agent per finding.
- **Editing any `.py` restarts the dev container.** Don't do it while Derek is testing, and never
  mid-migration.

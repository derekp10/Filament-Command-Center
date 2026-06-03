# Group 19 — Investigation Notes (19.1a Seed-Readiness + 19.1b Failure Buckets)

Companion to [19-dev-env-reset-test-debt.md](19-dev-env-reset-test-debt.md).
Records the findings behind the `reset-dev` script and the test-debt fixes.

---

## 19.1a — Are the `.example` seeds test-ready?

**No. `data/locations.json.example` is a fresh-install stub, not a test baseline.**

Evidence (probed 2026-06-02 against dev Spoolman 7913):

| Artifact | Locations | Verdict |
|----------|-----------|---------|
| `data/locations.json.example` (tracked) | **6** (CORE1-M0, CR, CR-CT-1, CR-MDB-1, LR-SD-1, XL-1) | Bootstrap stub for a brand-new install. |
| live `data/locations.json` (gitignored) | **53** | The real working set the E2E fixtures assume. |
| spools' referenced locations | **40 distinct** in use | Restoring from the 6-location stub would orphan ~170 spools. |

**Conclusion:** the test baseline needs a *coordinated pair* — a Spoolman
dump **and** a matching locations.json that actually contains every location
the spools reference. The `.example` stub can't do that job; it stays as the
fresh-install bootstrap. The Group 19 seed is a **new artifact**, captured
from current dev:

- `setup-and-rebuild/seeds/locations-seed.json` — full 53-location snapshot.
- `setup-and-rebuild/seeds/spoolman-dev-seed.json` — 40 vendors / 177 filaments /
  238 spools (de-nested FKs; Pytest-PLA test junk curated out — see below).

**Seed source decision (Derek, 2026-06-02): current dev** — it's what the
fixtures were written against and carries all 40 referenced locations, decoupled
from prod (which has its own locations/vendors that don't match dev's
locations.json). Re-snapshot any time with `reset_dev.py --capture` from a
known-good dev.

### Seed curation

The raw capture pulled **224 filaments / 280 spools**, of which **47 filaments
+ 42 spools** were `material == "Pytest-PLA"` / `E2E Ruby Red` — accumulated
junk from many past runs of `test_wizard_manual_creation` (which creates a real
record every run and never cleans up). That junk was filtered out of the
**seed file locally** (no shared-dev mutation), leaving a clean 177/238
baseline. The junk still sits in dev; `reset_dev.py --prune` will flag and
delete it (gated behind the flag, Derek-invoked — see below).

> Side-finding worth a follow-up: `test_wizard_manual_creation` is itself a
> contamination *source* (creates an un-prefixed, un-cleaned real record each
> run). Candidate fix: have it create with `TEST_RECORD_PREFIX` and tear down,
> or assert via a stubbed `/api/create_inventory_wizard`. Not in Group 19 scope.

---

## The `reset-dev` script (19.1)

`setup-and-rebuild/reset_dev.py` (+ `reset-dev.ps1` / `reset-dev.sh` host
wrappers). Runs on the **host** (must `docker restart` + rewrite the
bind-mounted locations.json; reaches dev Spoolman directly).

| Mode | Effect |
|------|--------|
| `reset_dev.py` | **Non-destructive restore**: locations.json ← seed; PATCH only the spool/filament/vendor fields that *drifted* from the seed back to baseline; `docker restart inventory_hub`. |
| `--prune` | Also **DELETE** entities present in dev but absent from the seed (sweep-created). Spool→filament→vendor order (FK-safe). |
| `--capture` | Snapshot current dev → the two seed files. |
| `--dry-run` | Report what would change; write nothing. |
| `--no-restart` / `--no-locations` / `--no-spoolman` | Skip a stage. |

**Reset-mode decision (Derek, 2026-06-02): non-destructive default, prune
behind a flag.** A plain run never deletes; `--prune` is the explicit opt-in
for a fully pristine reconcile.

> **⚠️ Who invokes this (Derek, 2026-06-02): NOT Derek.** Derek will not run
> `reset_dev.py` from the CLI — and specifically **will never call `--prune`**
> ("don't even know how to anyway"). Treat reset-dev as **agent-invoked**:
> Claude runs it on Derek's behalf (e.g. when asked to do a clean sweep), and
> only runs the destructive `--prune` with Derek's explicit OK *that time*. So
> the accumulated Pytest-PLA junk is **not** cleaned by a human running prune —
> it's cleaned the next time *Claude* is asked to prune. Any "run this yourself"
> instruction below is really a Claude runbook, not a Derek to-do.

### Pytest integration (`--reset-dev`) — implemented 2026-06-02

Rather than expect a manual pre-sweep invocation, reset-dev is wired into the
test harness as an **opt-in** session step (`inventory-hub/tests/conftest.py`):

- `pytest --reset-dev` (or `RESET_DEV_BEFORE_SWEEP=1`) — runs the
  **non-destructive** restore once at session start, waits for the container to
  come back, then runs the tests. For full sweeps.
- `pytest --reset-dev-prune` (or `RESET_DEV_PRUNE=1`) — same but with `--prune`
  (DESTRUCTIVE; agent-invoked with Derek's OK only).
- **No flag → no-op.** A normal single-test run triggers nothing — no docker
  restart, no Spoolman reconcile. (Deliberately *not* an unconditional autouse:
  auto-resetting before every `pytest` would docker-restart the container on
  every single-test run and yank dev state mid-use. Opt-in keeps the common
  case fast while making a clean full sweep a one-flag command.)
- If the reset fails, the session aborts (`pytest.exit`) rather than run on a
  dirty baseline.

**Restored fields** (the contamination class, per `RESTORE_FIELDS`):
- spool: `location`, `archived`, weight triple (`initial_weight` /
  `spool_weight` / `used_weight`), `lot_nr`, `comment`, and the whole `extra`
  dict (container_slot, physical_source*, needs_label_print, is_refill,
  fcc_pre_archive_location).
- filament: spec scalars + the whole `extra` (filament_attributes — the
  L319/L58 cleanup vector).
- vendor: scalars + `extra`.

`extra` is **whole-dict overwritten** to the seed (Spoolman replaces the entire
extra on PATCH — for a *reset* that's exactly right, the inverse of the
user-edit `compute_dirty_extras` merge rule).

**Idempotent:** a restore immediately after a clean restore makes zero writes.
Verified 2026-06-02 — `--dry-run --prune` right after `--capture` reported
**0 drift** across all 455 real entities, locations unchanged, and correctly
flagged the 47+42 junk records as "would prune".

**Known limitation:** Spoolman assigns ids on create, so an entity a sweep
*deleted* can't be restored with its original id. Such entities are **reported,
not silently recreated** (recreating would break idempotency and churn ids).
Recover genuinely-deleted real data via a Spoolman backup restore. In practice
sweeps corrupt location/extra/archived/weight on *existing* spools — all fully
PATCH-restorable.

### Validation status
- ✅ Read/compare/detect + idempotency: proven live (`--dry-run --prune` = 0 drift).
- ✅ Restore-decision logic: `tests/test_reset_dev.py` (11 hermetic unit tests).
- ✅ Live restore + docker-restart + pytest `--reset-dev` wiring: exercised
  end-to-end 2026-06-02 (with Derek's OK). `pytest --reset-dev tests/test_reset_dev.py`
  ran the restore (0 drift, junk correctly *left* — non-destructive), actually
  `docker restart`ed inventory_hub, health-waited for recovery, then passed all
  11 tests. The fixture's no-op (no-flag) path is also proven (default run
  triggers nothing).
- ⏳ DELETE (`--prune`) path: still not run against shared dev — only fires when
  Claude runs `--prune` / `--reset-dev-prune` with Derek's explicit per-time OK.
  The accumulated Pytest-PLA junk (47 filaments + 42 spools) stays in dev until
  then.

---

## 19.1b — Bucketing the 77 sweep failures

The 2026-05-30 full sweep (`feature/scan-match-pipeline`) reported **77 failed /
986 passed / 24 skipped**, A/B-confirmed environmental (identical failures on
baseline `dev`). Two buckets:

### Bucket A — DATA-caused (a `reset-dev` fixes these)
Failures that need a clean backend; they fail because a *prior* test in the
same sweep left dev mutated. From the buglist's own enumeration + the
contamination surfaces:

- **manage-modal won't open** — Location Manager state depends on
  locations.json + spool locations matching; drift breaks the open path.
- **quickswap / locmgr / returns** — depend on toolhead/slot bindings
  (`slot_targets` + spool `container_slot`/`location`) being at baseline.
- **buffer-card refresh** — depends on which spools are in the buffer /
  deployed; sweep mutations change the buffer set.
- **weigh-out / backfill / archive-prompt** — depend on spool weights +
  archived state a prior weight/archive test moved.
- Any test asserting a specific spool count / location occupancy.

These are **measured, not eliminated, by the script**: the success criterion is
*“a full sweep immediately after `reset-dev` (with `--prune`) has no DATA-caused
failures.”* Running that empirical re-bucket requires a full contaminating
sweep + a follow-up reset, so it's the script's **acceptance test**, run by
Derek when convenient — see procedure below. (The agent did not run a full 77-
item empirical sweep: doing so re-contaminates shared dev and the bucket counts
shift run-to-run; the script + this framework are the deliverable.)

### Bucket B — TEST-DEBT (fails in a pristine env too — fixed in this group)
These do **not** depend on dev data; a reset won't touch them. All four are
fixed and verified green against the live container:

| Item | Test | Root cause | Fix |
|------|------|-----------|-----|
| 19.2 | `test_ui_structural.py::test_wizard_escape_warns_when_dirty` | Asserted `.swal2-container`; the dirty-close guard migrated to `mountOverlay` (`#fcc-wiz-unsaved-changes`) in Group 10.8. | Assert the overlay + its Keep-Editing/Discard buttons; drive the real Escape-key trigger (distinct from the migration suite's programmatic `m.hide()`). |
| 19.3 | `test_ui_structural.py::test_structural_global_modals` | Layout scanner flagged designed-to-clip elements as `OVERFLOW_CUTOFF`. | Whitelist `text-truncate` **and** `.fcc-wiz-section-toggle` (hand-rolled ellipsis truncation — same class, surfaced once the offcanvas mask was removed). |
| 19.4 | `test_wizard_e2e.py::test_wizard_manual_creation`, `test_wizard_vendor_edit_button.py::test_vendor_created_does_not_clobber_user_typed_empty_weight` | `#wiz-fil-density` / `#wiz-fil-empty_weight` moved into the Physical Specs panel, which `wizardApplyCollapseDefaults('create')` collapses on open → fields "not visible" for `.fill()`. | Expand `#wiz-fil-physical-panel` before filling (same idiom already used for the color panel). |
| 19.5 | `test_wizard_per_spool_scan_e2e.py::test_per_spool_scan_splits_material_into_base_plus_attribute_chips` | `splitMaterialAndAttributes` only recognizes attrs in the `filament_attributes` *choices* (from `/api/external/fields`), which mirrors ambient dev config. | Route `/api/external/fields` and merge the required attrs into the choices via `route.fetch()` (keeps the rest of the schema real) → hermetic regardless of dev state. |

> Material-split *unit* tests (`test_wizard_per_spool_scan_unit.py`) were
> already hermetic — they pass the known-attrs list explicitly — so only the
> e2e chip-render test needed the choices stub.

---

## Acceptance-test procedure — a **Claude runbook**, not a Derek to-do

Derek won't run these (see "Who invokes this" above). This is the sequence
**Claude** runs when asked to validate that the DATA-caused bucket is actually
eliminated end-to-end. The `--prune` steps are destructive against shared dev,
so Claude runs them only with Derek's explicit OK that session:

With the pytest integration the reset folds into the sweep command itself:

```powershell
# Reset to baseline (incl. pruning the accumulated Pytest-PLA junk) AND run the
# full sweep in one shot — the --reset-dev-prune fixture resets at session start:
cd inventory-hub ; & C:/Python314/python.exe -m pytest --reset-dev-prune -p no:cacheprovider -q

# Then reset + re-run ONLY the previously-DATA-failing clusters:
& C:/Python314/python.exe -m pytest --reset-dev-prune tests/test_loc_mgr_*.py tests/test_buffer_*.py tests/test_quickswap*.py -q
#    Expect: the DATA-caused failures are gone; only genuine code failures remain.
```

(Or call the script directly — `./setup-and-rebuild/reset-dev.ps1 --prune` —
between sweeps; same effect.) The `--prune` deletes are destructive against
shared dev, so Claude runs these only with Derek's explicit OK that session.

Idempotency check (safe / read-only — Claude may run unprompted):
`./setup-and-rebuild/reset-dev.ps1 --dry-run --prune` twice — the second run
should report 0 drift / 0 would-prune.

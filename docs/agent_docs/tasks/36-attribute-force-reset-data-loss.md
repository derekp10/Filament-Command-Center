# Group 36: 🔴 Filament-Attribute `force_reset` Data Loss

**Branch name (when started):** `feature/group-36-attribute-force-reset-data-loss`
**Estimated effort:** ~4–7 hours (1 controlled repro + 3 fixes + a redesign decision)
**Risk:** **HIGH blast radius, MEDIUM change size.** This touches a user-facing endpoint that already performs a destructive schema migration on ~150 live records. Every change here must be provably value-preserving. See the CLAUDE.md warning: *"Don't add `force_reset=True` to `setup_fields.py` lightly."*

> **Status: `TODO`** — filed 2026-08-06 (`/refresh-groups`). The bug is **MITIGATED, NOT FIXED**: failures now name their casualty and log a recovery payload (`ada670e`), and the test suite that kept triggering it is opt-in (`6834b7f`). ⚠️ **Do not remove that `pytest.mark.integration` marker until this group lands.**
>
> Buglist item: the 🔴 DATA LOSS entry at the top of `Feature-Buglist.md`. Session context: [session-handoff-2026-08-05.md](session-handoff-2026-08-05.md).

---

## The bug in one paragraph

Spoolman cannot delete a single choice from a `choice` field. So `remove_choice` and
`sweep_unused` (`routes_config_attrs.py`) perform a **schema `force_reset`**: snapshot every
attribute-bearing filament, DELETE + recreate the field, then PATCH all ~150 records back.
**If any single restore PATCH fails, that filament's extras are gone permanently** — the field
was already wiped and nothing retries. This fires on an ordinary click in
**Config → Filament Attributes**. It is a production path, not a test artifact.

### Measured, live, on dev (2026-08-05)

- The attribute-bearing population fell **155 → 153 → 152 → 151** across a handful of invocations.
- **26 filaments** had been drained over months. Two confirmed emptied in the observed window:
  **#175 "Transition Spool"** (`['For Infill']` → `[]`) and **#63 "Blue (Azure Blue)"** (`['Blend']` → `[]`).
- ✅ **Dev data restored 2026-08-05** with Derek's explicit OK, values read from **PROD** — never guessed.
  All 26 returned via the app's own `bulk_set`; choices `Duel Matte` + `Neon` re-added; verified dev == prod
  (0 missing / 0 extra / 0 differing).

### The compounding trap (why losses become unrecoverable)

A loss makes its choice **unused** → the next `sweep_unused` deletes that choice → the value can no
longer be re-entered without re-creating the choice first. `Duel Matte` and `Neon` were both swept
away for exactly this reason.

---

## Items

### 36.1 — 🔬 Confirm the suspected escalation FIRST (do this before anything else)

**The loss may not be limited to attributes.** The migration restores each filament's **full `extra`
dict**, so a failed restore should lose **every extra on that record** — `product_url`,
`purchase_url`, `original_color`, `slicer_profile`, `nozzle_temp_max`/`bed_temp_max`,
`sample_printed`, …

Circumstantial evidence recorded 2026-08-05: of the 26 restored casualties that carry sibling extras
in prod, **6 of 7 are also missing siblings in dev**, versus **27 of 76** among untouched records.
Not conclusive — dev and prod legitimately diverge on workflow flags like
`needs_label_print`/`sample_printed` — but **#175 is missing `product_url`, `purchase_url`,
`original_color` AND `slicer_profile`**, which is not workflow drift.

**Method:** reproduce a forced restore-failure on a **scratch record** (never a real one) and observe
whether the whole `extra` dict goes. If it does, the blast radius is every extra the app stores, and
36.4 (snapshot-to-disk) moves from nice-to-have to **mandatory**.

_(Ruled out already: the 2026-08-05 restore writes did NOT cause the sibling gaps — `bulk_set` goes
through `update_filament`'s read-merge-write, pinned by `test_bulk_set_preserves_sibling_extras`, and
filament #55 was written during the restore and kept all five siblings.)_

### 36.2 — Retry failed restores, and fail LOUDLY if one still can't be restored

The failures look like transient PATCH failures under load — the same family as the `_req` transport
retry already present in the test module. Add a bounded retry per record; if a record still can't be
restored after retries, raise it as an ERROR the user cannot miss (Activity Log + a ≥7s error toast
per the CLAUDE.md toast convention), not a buried count.

Today the log says only `restored 151/152 sibling-attr records; 1 restore failure(s)`.

### 36.3 — Fix the recovery-payload logging (from the 2026-08-05 review's deferred findings)

`ada670e` added casualty logging, but the adversarial review found two defects in it:

- **It logs the PRE-filter snapshot.** `_report_restore_failures` logs `extras_snapshot[fid]` — the
  extras as they were **before** the doomed choice was filtered out, not the payload whose write
  actually failed. **Restoring verbatim from that log would re-introduce the choice being removed.**
  Log the post-filter `extras_out` instead.
- **Truncation is silent.** The payload is cut at 4000 chars with no marker, so a large record yields
  silently invalid JSON. Append an explicit `…TRUNCATED` sentinel.

### 36.4 — The real fix: stop force-resetting on a user click (decision required)

Ranked by preference:

1. **Strongly consider not force-resetting at all.** CLAUDE.md already flags this hazard; this is that
   hazard wired to an ordinary button. Options: leave dead choices in the schema and filter them at
   the *display* layer; or gate the destructive migration behind an explicit "this rewrites 150
   records" confirmation rather than firing it on `remove_choice`/`sweep_unused`.
2. **If a force_reset is unavoidable, write the snapshot to disk first** so a crash mid-migration is
   recoverable — not just an in-memory dict that dies with the request. `atomic_store` is the
   existing primitive.

⚠️ **`sweep_unused` with `force` currently runs a full schema force_reset + restore across all ~158
attribute-bearing records on every invocation.** That is a prod-shaped migration firing on a click.

---

## Files

| File | Why |
|---|---|
| `inventory-hub/routes_config_attrs.py` | `remove_choice`, `sweep_unused`, `_report_restore_failures`, the `_req.patch` restore loop |
| `inventory-hub/spoolman_api.py` | `update_filament` read-merge-write (the *correct* path — `bulk_set` uses it and preserves siblings) |
| `setup-and-rebuild/setup_fields.py` | `migrate_container_slot_to_text()` is the template for a legitimate value-preserving type migration |
| `inventory-hub/atomic_store.py` | For 36.4's snapshot-to-disk |
| `tests/test_filament_attributes_bulk_api.py` | Opt-in as of `6834b7f`; **keep the marker until this group ships** |

## Verification

- A pinning test that a restore failure is (a) **named**, (b) **retried**, and (c) **loud**.
- A pinning test that the logged recovery payload is the **post-filter** one and round-trips as valid JSON.
- `test_bulk_set_preserves_sibling_extras` must stay green.
- Offline sweep (`--offline`) for iteration; a full `RUN_INTEGRATION=1` sweep before merge.
- ⚠️ **Never guess-restore Derek's data.** Prod (`:7912`) is readable and is the reference; dev is `:7913`.

## Related

- Cross-refs the `## ⚙️ App Flow` "Clean up filament attributes" (L319) buglist item — this is the
  root cause of why that cleanup is worse than "heavyweight".
- [[feedback_adversarial_review_runtime_lens]] — verify against the live container, not just logic.

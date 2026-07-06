# Group 29: L316 Characterization Findings — 🟡 Attrs Manager + Bindings + State/Pulse

**Branch name (when started):** `feature/group-29-l316-charact-yellows`
**Estimated effort:** ~4–7 hours (10 actionable fixes + 3 doc/observation notes to resolve, each fix + its pin-test update)
**Risk:** **LOW.** The lowest-severity tier — edge-case robustness, response-shape consistency, a lexicographic sort that only bites the 10+-toolhead future, and persistence-input validation. A few require a "decide which behavior is intended" call before coding.

> **Status: ✅ DONE 2026-07-05** (`feature/group-29-l316-charact-yellows` → `dev`). All 10 actionable fixes + 4 notes shipped (findings 36–39, 42–45, 47, 48, 50, plus notes 26/28/29), each pin flipped to the corrected behavior in the same change; 338 tests green / 0 regressions; a 4-lens adversarial diff-review returned zero confirmed findings. Three decisions with Derek: 29.A2 docstring→code, 29.A3 `success = updated>0 or unchanged>0`, 29.B3 `toolhead`=requested + new `active_toolhead`. N3 needed no change (CLAUDE.md was already correct); N1 removed the dead `cfg` (no longer part of the vestigial-FB item). Per-item detail archived in `completed-archive.md`. **This closes the last L316 characterization tier — all 50 findings resolved (Groups 27+28+29).** _(Original filing note preserved below.)_
>
> **Status (original): TODO** — filed 2026-07-01 by `/refresh-groups`. The 🟡 findings from the **L316 characterization layer** (buglist lines 26–28), plus the folded doc/observation notes. Every fix-finding is PINNED by a `tests/test_l316_charact_*.py` test — **fixing one = update its pin in the SAME commit.** Full annotated write-up + pin-test names: [L316-characterization-findings.md](L316-characterization-findings.md).

## Why these are one group

The remaining lower-priority findings: the filament-attributes manager's report/restore edge cases (`routes_config_attrs.py`), bindings/quickswap response-shape + sort consistency (`routes_bindings.py`), and the state/pulse persistence-input validation + misc (`routes_state_pulse.py` + a few small ones). Same pin-test-update workflow, mostly "harden the edge / make the shape consistent" rather than "stop a live bug." Batching them keeps the last of the L316 findings from scattering into forgotten one-offs.

## The pin-test contract (read first)

Each fix-finding is guarded by a `test_l316_charact_*.py` test encoding current behavior. For every fix: change the code, then flip that finding's pin to the corrected contract in the same commit. Names in [L316-characterization-findings.md](L316-characterization-findings.md).

## Items — actionable fixes

### Cluster A — Filament-attributes manager (`routes_config_attrs.py`)
- **29.A1 — (36)** report counts gain keys OUTSIDE the schema choice list from rogue attribute data (the live test would go red against such data). **Fix:** restrict the report to schema choices (or handle rogue keys explicitly).
- **29.A2 — (37)** `remove_choice` docstring claims strip-filaments-BEFORE-schema-delete, but the code does snapshot→DELETE→recreate→strip-during-restore — the documented crash invariant is not what ships. **Decide which is intended**, then align code+docstring.
- **29.A3 — (38)** `bulk_set` returns top-level `success:true` even when EVERY id errored. **Fix:** reflect per-id failure in the top-level result.
- **29.A4 — (39)** the `remove_choice`/`sweep_unused` restore loops only catch `RequestException` — any other mid-restore exception escapes as a raw 500 AFTER the schema was already recreated, with no `restore_failures` report. **Fix:** broaden the catch + report `restore_failures` so a partial restore is visible, not a bare 500.

### Cluster B — Bindings / quickswap (`routes_bindings.py`)
- **29.B1 — (42)** quickswap-return fan-out sorts toolheads LEXICOGRAPHICALLY (`XL-10` before `XL-2` — bites the 10+-toolhead indxx future). **Fix:** natural/numeric sort. (Forward-looking; the fleet isn't there yet but the indxx upgrade is planned — see CLAUDE.md "Indxx forward-compat".)
- **29.B2 — (43)** `printer_creds` PUT logs `'Printer connection updated'` even on a no-op unchanged PUT. **Fix:** only log on an actual change.
- **29.B3 — (44)** return-taxonomy response shape is inconsistent — `toolhead` means the REQUESTED prefix in `return_no_spool` but the ACTIVE toolhead in `return_no_binding`. **Fix:** make the field's meaning consistent across the two branches (or rename one).

### Cluster C — State/pulse + misc (`routes_state_pulse.py` + small)
- **29.C1 — (50)** `/api/state/buffer` + `/api/state/queue` POST store ANY JSON type verbatim (no list validation, unlike `/api/spools/refresh`) — one malformed client write poisons the persisted buffer/queue for every dashboard. **Fix:** validate the payload is a list (mirror `/api/spools/refresh`) before persisting.
- **29.C2 — (26)** `api_update_filament` generic-Exception branch returns 200, not 500. **Fix:** 500 on an unexpected exception.
- **29.C3 — (47)** multi-spool picker display `.strip(' -')` eats legitimate leading/trailing hyphens in vendor/name. **Fix:** trim only what's intended (don't strip content hyphens).

## Items — notes to resolve (no code fix, or fold elsewhere)

- **29.N1 — (45)** dead `cfg = config_loader.load_config()` in `quickswap_return` — vestigial FilaBridge residue. **Action:** fold into the standalone **vestigial-FilaBridge-artifacts cleanup** NOT-Grouped row (remove it there), OR delete it here if convenient while in `routes_bindings.py`. Don't double-track.
- **29.N2 — (48)** backfill with a malformed spool entry (no id) PATCHes `/spool/None` — malformed-Spoolman-data only, **not pinned** by a test. **Action:** low-value hardening; add a guard if touching `print_deduct.backfill`, else leave documented.
- **29.N3 — (28)** doc staleness: CLAUDE.md said the delete-sentinel render was pinned by `test_delete_sentinel.py`, but the `(cleared)` formatter render is actually pinned by `test_l316_charact_filament_edit_log.py`. **Action:** correct the CLAUDE.md reference (pure doc fix — do it in whichever commit is convenient; already partially reflected in CLAUDE.md's Group-23.4 section, verify).
- **29.N4 — (29)** observation: the 23.6 `product_url` idempotency compare doesn't strip a trailing slash, so QR-form stored URLs fire exactly ONE self-healing upgrade write. **Action:** benign (one-time, self-healing). Optionally strip the trailing slash in the compare to suppress the single write; otherwise document + close.

## Recommended order
1. **29.C1 (persistence-input validation)** first — it's the one with real multi-client blast radius ("poisons the buffer/queue for every dashboard"); cheap list-validation, high value.
2. **Cluster A** — the attrs-manager robustness set; 29.A2 needs a "which behavior is intended" decision (align code+docstring), so settle that before coding 29.A2.
3. **Cluster B** — response-shape/sort consistency; 29.B1 is forward-looking (numeric sort), 29.B3 needs a naming decision.
4. **29.C2 / 29.C3** — the two small misc fixes.
5. **Notes (29.N1–29.N4)** — fold/doc-fix/close; do 29.N1 with the vestigial-FB row if that gets picked up, and 29.N3 as a CLAUDE.md touch.

## Out of scope / do NOT do
- Reopening the vestigial-FilaBridge-artifacts cleanup as part of this group — 29.N1 just cross-references it; don't duplicate the whole cleanup here.
- Changing 29.A2's behavior without deciding whether the docstring or the code is the intended contract — surface it if unclear.
- The 🔴/🟠 findings — those are Groups 27/28.

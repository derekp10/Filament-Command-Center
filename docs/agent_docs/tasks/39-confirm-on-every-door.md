# Group 39: 🚪 Confirm on Every Door

**Branch name (when started):** `feature/group-39-confirm-on-every-door`
**Estimated effort:** MEDIUM–LARGE, about two sessions (~10–16 h). The engine contract and its test-mock pass are half of it.
**Risk:** **MEDIUM–HIGH.** It changes the active-print pre-flight in `perform_smart_move`, which every move surface goes through, and six frontend confirm consumers. Every change asks *more*, never less. The real hazards are a double prompt, a dead-end prompt, or a confirm that covers the wrong toolhead.

> **Status: `TODO`.** Planned 2026-09-13 from Derek's D1 and D6 answers
> ([open-decisions-2026-09-13.md](open-decisions-2026-09-13.md)). Nothing has been built yet.
> All code references were read on `dev` @ `be9f045`. Line numbers drift, so re-read before editing.

---

## Read this first

- **The printer probe stays fail-open.** An unreachable printer never blocks a move. This group makes that wait visible and says so plainly; it doesn't turn "can't reach" into "refuse".
- **"Active" means PRINTING, PAUSING or RESUMING** (`prusalink_api.py:458`). PAUSED never asks, per D6. The docstring at `logic.py:14-17` still says "PRINTING/PAUSED/BUSY", and that docstring is wrong; fix it on the way past.
- **Chaining flows must drive the REAL move engine.** Never mock `perform_smart_move` ([[mocked engine hides chain bugs]]: every Return test mocked it, and a five-month no-op stayed green). The harness to reuse is already in `tests/test_active_print_chain_confirm.py`: `FakeSpoolman` (`:114`), `WireSpoolman` (`:199`, runs the real `update_spool` merge), `_probe_for` (`:237`, patched *below* the per-move memo), and `_run` (`:265`). Before adding more tests, extract it into a flat helper module such as `tests/move_engine_harness.py` (precedent: `tests/source_family.py`).
- **Prove every new test fails on the old code** (`git archive HEAD` into a scratch dir), not only that it passes on the new code.
- **Container runtime is Python 3.9** (CLAUDE.md), so no 3.10+ syntax.

---

## Buglist items covered

### Core (named by the decisions)

| # | Buglist item (title as filed) | Decision / direction |
|---|---|---|
| **39.1** | 🟡 *Move-pipeline follow-ups left open by the 2026-09-12 diff reviews*, item 3: **"The deposit's confirm is an unscoped boolean (R2-08)."** | *"Decided with item 2 (2026-09-13): every confirm names its toolhead; build both together."* |
| **39.2** | Same item, item 2: **"Quick-Swap and Return still trust their overlay (R2-06 — decide)."** | *"Decided 2026-09-13 (Derek): the server re-checks whenever no banner was shown. Return probes the head it empties, not the box it lands in. Every confirm names its toolhead, which also closes item 3 (R2-08)."* Steering: *"Quick-Swap is meant for non-active states (idle, stopped, paused; a pause may be a filament swap or runout). Using it mid-print is a deliberate sync correction for when FCC has drifted from the physical world after a print started."* |
| **39.3** | 🟡 **"Show when FCC is waiting on a printer."** | Derek: *"We should probably notify the user when we are waiting on a server response, so the dead time doesn't seem like a lock up or that nothing happened… I know it will happen when the printers are offline."* Direction: a "Checking XL…" state after about 300 ms, cleared on answer, and a plain "couldn't be reached" on timeout. *"Build it together with the R2-06 server re-check."* |
| **39.4** | 🟠 *Active-print guard gaps left after the chain fix*, item 3: **"Moving a spool OFF a printing toolhead (buffer assign, `manage_contents` add, override) is never guarded."** | *"Decided 2026-09-13 (Derek): ask first, like Eject."* **When:** before a move writes anything, if a moving spool's own location is a toolhead whose printer is PRINTING, PAUSING or RESUMING, never while paused. **Wording:** *"#42 is loaded on XL-3. Moving it to SHELF-A means FCC stops charging this print to it. Continue?"* **Scope:** share the printer probe with the destination check, so a same-printer move asks once; a multi-spool move asks once before writing. **Build:** together with item 2, and with or after R2-06. |
| **39.5** | Same item, item 2: **"Force Location Override (`inv_details.js`) never probes the printer and never sends `confirm_active_print`…"** | No separate decision. D6's build note says to build it with D6, *"Otherwise Force Location becomes a dead-end error."* |

### Considered and INCLUDED

| # | Buglist item | Why it belongs here |
|---|---|---|
| **39.6** | 🟡 *Eject / Return UX leftovers*, item 1: **ejecting a toolhead spool with no saved home during a print takes three round-trips, and the second prompt says "Spool is already in a room…"** | It is the same door as D6 (a spool leaving a printing head), it needs the same consequence wording, and it runs through the same `requires_confirm` payload. Collapsing the chain also removes a Bootstrap confirm raised from inside another confirm's callback, which is the re-show race class fixed on 2026-09-12. |
| **39.7** | 🟡 *Move-pipeline follow-ups*, item 1: **"Smart Load's resident LIST read is still fail-open (R1-03)."** | 39.4 rewrites the same pre-flight block (`logic.py:524-678`) and forces a pass over the same move-test mocks that the buglist says R1-03 needs. Doing them apart means two passes over the same mocks. |
| **39.8** | Same item, item 4: **"Return / Quick-Swap failures answer HTTP 502 (R2-07, info)."** | 39.2 rewrites both routes' answers and both frontend handlers anyway. Settling the status codes at the same time costs almost nothing. |
| **39.9** | Same item, item 5: **"`CMD:TRASH:<id>` while the bulk-move panel is open still opens the eject confirm behind the panel."** This is the same bug as *Eject / Return UX leftovers* item 4. | It is a confirm door that dead-ends, touches the same eject confirm chain as 39.6, and takes a one-line guard. |

### Considered and EXCLUDED

| Buglist item | Where it goes, and why |
|---|---|
| 🟠 *Only Smart Load enforces "one spool per toolhead"*, item 1: **auto-unarchive writes an old spool back onto its toolhead; the deduct-to-0 archive runs with no active-print guard.** | **Not this group; it belongs with the one-spool-per-toolhead / single-slot-box lifecycle work.** The write happens inside `spoolman_api.update_spool` (`_auto_unarchive_on_refill`, `spoolman_api.py:284-287`), not in the move engine this group guards. The deduct-to-0 archive (`_auto_archive_on_empty`, `:170-241`) runs from the print monitor daemon, where no user exists to answer a confirm. Its fix is an occupancy check with a redirect ("restore only if the head is empty, else Room/Unassigned plus a WARNING"), not a prompt. |

---

## Current behaviour (verified 2026-09-13)

### The door map

| Door | How it starts | Frontend probe | What the server does with the confirm | Gap |
|---|---|---|---|---|
| **Quick-Swap tile** | `quickSwapTap`, `inv_quickswap.js:697-733` | `showConfirmOverlay` races the probe against 3 s (`:340-349`, awaited at `:370`) | `routes_bindings.py:817-824` hard-codes `confirm_active_print=True` ("the user already saw the warning") | The probe fails open, so no banner shows, yet the resident is still unloaded off a printing head. `onConfirm: () => performSwap(opts)` (`:731`) throws the probe result away. |
| **Quick-Swap Return** | `returnToolheadToSlot`, `:826-892` | Probes the head being emptied (`toolhead: th`, `:884-888`) | `routes_bindings.py:700-714` hard-codes `True`. The engine pre-flight checks only the destination and a named slot's bound head (`logic.py:524-540`), never the head the spool leaves. | Same as Quick-Swap: no server-side source check at all. |
| **Deposit** (toolhead grid) | `quickSwapDeposit`, `:607-695` | Same overlay | Sends `confirm_active_print: !!stateInfo` (`:644`) and re-opens with the backend's answer on `assignment_requires_confirm` (`:668-679`). The server takes a bare boolean (`routes_scan.py:1125-1129`). | **Unscoped (R2-08):** a stale grid whose slot was rebound can carry an XL confirm onto another printing head. |
| **Slot-QR scan + confirmed replay** | `processScan` → `assignment_requires_confirm` → `_confirmActivePrintScan` | None before the scan | The replay posts `confirm_active_print: true` (`inv_cmd.js:1579-1593`) | Unscoped, same class as the deposit. The `requires_confirm` answer writes no Activity Log line (`routes_scan.py:1133-1142`). |
| **Location Manager assign** (deposit card, slot tap) | `doAssign`, `inv_loc_mgr.js:1242-1282` | `fetchPrinterStateForToolhead` with **no timeout** (`:416-434`, called at `:1262-1263`) | `manage_contents add` → engine. Retries on `requires_confirm` (`:1443-1449`). | Destination only. A spool moved **off** a printing head is never asked about (D6). |
| **Buffer location scan** | `performContextAssign`, `inv_cmd.js:1889-1951` → `/api/smart_move` (`print_deduct.py:253-261`) | None | Retries on `requires_confirm` (`:1916-1922`) | Destination only (D6). |
| **Force Location** | `promptEditLocation`, `inv_details.js:942-1244` | None | Payload `{action, location, spool_id, origin}` with no confirm (`:1211-1216`). A `requires_confirm` answer lands in the error branch as a 7 s toast (`:1236`). | **Dead end**: no way to proceed. The buglist's other half ("treats any `status: success` as done") is **already fixed**: `:1228` reads `res.failures`. |
| **Eject** (card button, eject mode) | `ejectSpool` → `doEject`, `inv_loc_mgr.js:1491-1582` | None | `manage_contents remove` (`routes_scan.py:294-314`) → `perform_smart_eject`, which guards its own source (`logic.py:1766-1774`) | Up to three round-trips, each prompt raised from the previous one's callback (`:1540-1553`). The second prompt reads *"Spool is already in a room. Confirm true unassign to nowhere?"* (`routes_scan.py:310`) about a spool on a toolhead. |
| **`CMD:TRASH:<id>` scan** | `inv_cmd.js:1442` | None | Opens Bootstrap `requestConfirmation` (z 1100) | While a bulk move is armed, that confirm renders behind the panel (z 20000). `CMD:CLEAR` already has the guard (`:1435-1437`). |

### Waiting today

- **The Quick-Swap/Return/Deposit overlay mounts only after the probe settles** (`inv_quickswap.js:370`). For up to 3 s nothing new appears on screen.
- **Location Manager assign has no timeout at all** (`inv_loc_mgr.js:420`). It waits for the server's own probe.
- **Scan paths, eject, Force Location and Bulk Move** show only `#processing-overlay`, a blank 50 % dim (`inv_core.js:294-298`), while the server probes.
- **Server probe cost.**
  - The v1 status call has a 2 s timeout (`prusalink_api.py:468`).
  - A connection error or timeout skips the legacy call (`:475-480`).
  - A non-OK v1 answer (a wrong API key) tries the legacy `/api/printer` with another 2 s (`:488`).
  - The buglist's "~2 s powered down, ~4 s wrong key" matches this.

### Engine facts the design leans on

- **The probe is memoized per outermost move**, keyed by `(url, printer_name)`: `perform_smart_move` wrapper at `logic.py:441-474`, memo at `prusalink_api.py:421-437`. A source check and a destination check on the same printer inside one move therefore cost **one** probe, which is exactly D6's "same-printer move asks once".
- **The pre-flight walks a named slot's binding even when `auto_deploy=False`** (`logic.py:529-533`; investigation I1-06). Return passes `auto_deploy=False` (`routes_bindings.py:711-714`).
- **Smart Load's resident list is fail-open** (`logic.py:629`, known-gap comment `:621-624`). `get_spools_at_location` → `get_spools_at_location_detailed` returns `[]` on any error (`spoolman_api.py:1507-1523`). A strict reader already exists (`:1633`).
- **Failure status codes are mixed.**
  - `return_ambiguous` answers 409 (`routes_bindings.py:591`).
  - `return_failed` answers 502 (`:609`, `:732`), as does `quickswap_failed` (`:839`).
  - `assignment_failed` answers 200 (`routes_scan.py:1159`).
  - `performSwap`/`performReturn` call `r.json()` unguarded (`inv_quickswap.js:546`, `:577`).
- **The three active-print confirm overlays are near-copies** (~90 lines each), and each hard-codes a destination sentence:
  - `showConfirmOverlay` banner (`inv_quickswap.js:371-375`)
  - `_confirmActivePrintAssign` (`inv_loc_mgr.js:1296-1389`, text `:1302-1305`)
  - `_confirmActivePrintScan` (`inv_cmd.js:1799-1887`, text `:1810-1813`)

---

## Design, by sub-task

### 39.1 — Scoped confirms: every confirm names its toolhead (R2-08)

This is the shared contract everything else in the group uses, so build it first.

**Wire format.** A new request field, `confirmed_toolheads: ["XL-3", …]` (upper-cased LocationIDs of the heads whose warning the user actually saw).

**Engine.**
- `perform_smart_move(…, confirm_active_print=…)` accepts either a bool (internal Python callers) or an iterable of head ids.
- A new helper, `_uncovered_active_heads(touched, confirm, printer_map)`:
  - takes the heads this move will touch, each tagged with a role (`destination`, `feeds` for a named bound slot, `source` for 39.4);
  - skips heads the confirm already covers, so a shown banner never costs a second probe;
  - probes each remaining printer once through the memo;
  - returns the active heads left over.
- If any remain, the move answers before writing anything, in the one `requires_confirm` shape defined below.
- **The auto-deploy chain** (`logic.py:908-913`) passes the scoped set through. The existing "only when the caller named the slot" rule (`explicit_slot`, `:545`) stays until Group 40.0e moves auto-slot ahead of the pre-flight.

**The shared pre-write contract. It is defined here once; Groups 40, 41 and 42 extend it and never redefine it.** Sub-tasks in all four groups edit `_perform_smart_move_impl`'s pre-write section: 39.1, 39.4, 39.7, 40.0a, 40.0c, 40.0d, 40.0e, 41.6, 42.1, 42.2 and 42.3a. When 39.1 lands, write this order into the code as a comment block:

1. **Resolve the spool list** (`logic.py:505-512`).
2. **Structural refusals.** No Spoolman or printer I/O. Answer `{"status": "error", "blocked_reason", "msg", "failures"}`:
   - a Printer row that is not its own toolhead (40.0a, `printer_row`);
   - several spools onto a single-occupancy target (42.3a, `single_occupancy`).
3. **Slot choice.** Auto-slot for a slotless single spool into a multi-slot box (40.0e moves it here from `logic.py:553-578`).
4. **Strict reads, fail closed.** On any exception, answer `status: error` and write nothing. The reads:
   - the moving spools' own records (39.4);
   - the target head's residents (39.7);
   - the bound head's residents (40.0c).
5. **One confirm answer.** Run `_uncovered_active_heads` over the `destination` / `feeds` / `source` roles (one probe per printer, through the memo), plus 40.0c's fed-head check.
6. **Writes, per spool, in this order:**
   - Smart Load's resident ejects;
   - the slot unseat (41.6: a rejected unseat refuses that spool);
   - the spool's own write, including 13.6 / `record_source` at a head (40.0d) and the single-slot box release after a move off a head (42.1);
   - then the chain.

Every confirm the engine asks for uses one answer shape:

```
{"status": "requires_confirm",
 "confirm_type": "head_fed" if fed_heads else "active_print",
 "active_prints": [{"toolhead", "printer_name", "state", "role", "spools": [ids]}],
 "active_print": <first active_prints entry, kept for existing consumers>,
 "fed_heads": [...],   # Group 40.0c; always present, empty until 40 lands
 "can_store": false,   # Group 40.0c; true when the target is a box slot that can be stored without deploying
 "target_slot": "2",   # the slot this answer is about (40.0e), so a replay sends the same one
 "msg": <built by _active_print_message, see 39.4>}
```

**Request fields.**
- `confirmed_toolheads`: the printing warnings the user saw (this sub-task).
- `confirmed_fed_heads`: the "already fed" warnings the user saw (40.0c).
- Each list is keyed by head id. A stale confirm is therefore asked again, whichever warning it covered.
- **Why `fed_heads` is a sibling list, not a role inside `active_prints`:** an idle fed head has no printer state, and 39.4's "stops charging this print" wording doesn't fit it.

**Routes.**
- `/api/quickswap`, `/api/quickswap/return`, the `identify_scan` slot branch, `manage_contents add` and `/api/smart_move` read `confirmed_toolheads`.
  - A bare browser `confirm_active_print: true` is treated as **an empty list** on these five. A stale cached bundle is therefore asked again, which is the safe direction (the build-version cache-bust in `app.py` keeps that window short).
- `manage_contents remove` / `force_unassign` / `clear_location` and `DELETE /api/locations` keep their boolean. Each only ever touches the one head the request itself names. They still adopt the new message.
- Internal callers keep the boolean: the bulk-move commit, which re-plans from live state, and the chain.

**Frontend.** Every confirm's Yes sends the heads it displayed: `stateInfo ? [head] : []` from an overlay probe, or `active_prints.map(a => a.toolhead)` from a backend answer.

**Why this closes R2-08.** The server compares the head it is about to touch with the list the user confirmed. A grid whose slot was rebound to CORE1 carries `["XL-3"]` and gets asked about CORE1.

**Tests (hermetic, real engine).**
- A deposit into `LR-MDB-1:3` with `confirmed_toolheads: ["XL-3"]` while the slot is now bound to `XL-2` and XL is printing answers `assignment_requires_confirm` naming XL-2. **Zero writes** (the `WireSpoolman` PATCH log is empty).
- A bare `confirm_active_print: true` on `/api/quickswap` while printing is asked again.
- `["XL-3"]` covers XL-3 and **does not probe it** (probe call count 0 for that printer).

**Risks.**
- Exact-kwargs pins assert the old boolean and must be flipped deliberately: `tests/test_quickswap_api.py:76`, `tests/test_l316_charact_bindings_errors.py:240`, `tests/test_active_print_backend_enforcement.py:140-159`.
- Many move tests pass `confirm_active_print=True`. The bool path must stay exactly equivalent, or ~100 tests churn.

### 39.2 — The server re-checks Quick-Swap and Return (D1 / R2-06)

**Routes.**
- Drop both hard-coded `confirm_active_print=True` (`routes_bindings.py:711-714`, `:821-824`) and pass `confirmed_toolheads` from the request (default: none).
- `/api/quickswap`: the existing destination pre-flight probes the head, and a new answer `quickswap_requires_confirm` carries `active_prints`.
- `/api/quickswap/return`: 39.4's source check sees that the spool's own location is the head being emptied, and answers `return_requires_confirm`. **That is exactly "Return probes the head it empties", with no route-specific probe code.**
- Also fix I1-06: walk a named slot's binding only `if auto_deploy` (`logic.py:529`). Otherwise Return's box leg could ask about a head it will never touch.

**Frontend.**
- `performSwap(opts, stateInfo)` / `performReturn(opts, stateInfo)` send `confirmed_toolheads`.
  - Fix `:731`, which currently discards `stateInfo`, and `:888`.
- On `*_requires_confirm`, re-open `showConfirmOverlay` with `knownState` and replay with the returned heads. The Deposit already does this (`inv_quickswap.js:668-679`); lift it into one helper used by all three.
- Write an Activity Log WARNING through `logClientEvent`, because CLAUDE.md requires every outcome to log and toast.

**Keep the client probe in the overlays.** On the usual mid-print path the user sees one confirm with the banner. The server re-check only catches the probe's misses.
- *Rejected alternative:* drop the client probe and let the server always ask. Every mid-print Quick-Swap would then show the plain overlay **and** a second banner overlay.

**Tests.**
- Hermetic, through `app_core.app.test_client()` and the real engine:
  - `/api/quickswap` onto a printing `XL-3` with no confirm → `quickswap_requires_confirm`, `#99` still on XL-3, zero writes.
  - With `["XL-3"]` → swapped; the resident is home in its box.
  - Return from a printing `XL-3` with no confirm → `return_requires_confirm` naming XL-3, zero writes; confirmed → parked in `LR-MDB-1` slot 3.
  - Return where the box slot is bound to the same printer → exactly **one** probe.
  - Paused → no ask.
- Route-stubbed E2E, extending `tests/test_move_result_consumers_e2e.py`'s `FakeBackend`: probe stubbed "unknown" → overlay without a banner → Yes → stub answers `quickswap_requires_confirm` → the overlay re-opens **with** the banner → Yes → the second POST carries `confirmed_toolheads: ["FCC-TEST-TH"]`. Same shape for Return.
- Route-stubbed E2E for the failure toasts that no test drives today (Move-pipeline follow-ups item 6), in `performSwap` / `performReturn` (`inv_quickswap.js:540-582`):
  - stubbed `quickswap_failed`, `return_failed` and `return_ambiguous` answers each raise their 7 s error toast;
  - a non-JSON 502 body shows "server answered 502" (39.8).
- **Fix the silent restore in `tests/test_return_overlay_and_refresh.py:168-175`** (Eject / Return UX leftovers item 5).
  - **Today:** the test restores dev data through `/api/quickswap/return` inside a bare `try/except`, with no assertion.
  - **After this sub-task:** that call answers `return_requires_confirm` whenever the XL is printing, so the restore would fail silently and leave the spool on the head.
  - **The fix:** assert `action == "return_done"` and the spool's final location. On `return_requires_confirm`, fail with a message naming the printer. A test must never confirm a real print.
  - If Group 40.6 lands first, it takes this fix.

**Risk.** The 29.B3 response-shape pins in `test_l316_charact_bindings_errors.py` cover every Return branch. The new action must follow 29.B3: `toolhead` = the requested value, plus `active_toolhead` and `requested`.

### 39.3 — "Checking XL…" whenever FCC waits on a printer

**One shared helper in `inv_core.js`.**
- `withPrinterCheck(printerName, promise, {timeoutMs})` shows a **pinned pill**, "⏳ Checking XL…", after 300 ms, and removes it when the promise settles.
- On a client timeout it replaces the pill with a warning, "XL didn't answer — FCC couldn't check whether it is printing", and logs a WARNING.
- **One pill for clicks and scans alike:** a scan has no pressed control to put a spinner on, and one look everywhere is easier to learn.

**Probe that can tell "idle" from "couldn't ask".**
- Add `fetchPrinterStateDetailed(toolhead)`, which returns `{active, known, reason, state, printer_name}`.
- Keep `fetchPrinterStateForToolhead` as a wrapper, because its `null` means both "idle" and "unknown" and the banner logic depends on that truthiness.
- When `known` is false, the overlay adds one line: "ℹ️ Couldn't reach XL — FCC can't tell whether it is printing."
- **Tell "no credentials" apart from "unreachable".**
  - **Today:** `_probe_printer_state` returns `None` when the Printer row has no credentials (`prusalink_api.py:459-461`), and `/api/printer_state` then answers `reason: "prusalink_unreachable"` (`routes_bindings.py:143-144`). The message would say "couldn't reach XL" when the real fix is entering its login.
  - **Route:** check `prusalink_api.fetch_printer_credentials(fb_url, printer_name)` first (a `locations.json` read, no network) and answer `reason: "no_credentials"`.
  - **Client:** `fetchPrinterStateDetailed` passes `reason` through. The pill and the overlay line then say "FCC has no login for XL — add it in Config's printer credentials", linking to that grid (the same grid Group 35 reuses).
  - The move itself still fails open.

**Every client probe gets the timeout race.**
- `doAssign`'s bare fetch (`inv_loc_mgr.js:1262`) moves onto the same race `_probeWithTimeout` uses (`inv_quickswap.js:340-349`). Move that helper somewhere shared.
- `showConfirmOverlay` starts the pill *before* awaiting (`:370`) and marks the pressed tile `aria-busy`/disabled against a double tap.

**Server-side waits** (scan assign, eject, Force Location, Bulk Move commit, location delete).
- Extend `setProcessing(true)` to `setProcessing(true, {label})` (`inv_core.js:294-298`). The label appears centred on the existing dim after 300 ms.
- `printerLabelForTarget(locId, slot)` resolves the label:
  - a toolhead gives its `printer_name` from `state.printerMap`;
  - a Dryer Box plus a slot gives the bound head's printer from `extra.slot_targets`;
  - a spool on a head (39.4) gives that head's printer.
- No printer implied means no label, which leaves the dim exactly as today. The signature change is backward compatible.

**Tests** (route-stubbed E2E, using Group 38's in-page fetch-delay lever, never a blocking `route` sleep):
- delay `/api/printer_state` 2 s → the pill is visible by about 500 ms and gone after the answer;
- a 4 s delay → the overlay says "Couldn't reach";
- delay `POST /api/identify_scan` on a slot scan whose slot is bound → "Checking FCC-TEST printer…" on the dim;
- a hermetic source canary pins the 300 ms delay and the timeout budgets, like `test_overlay_wait_budgets.py`;
- hermetic Flask client: a Printer row with no `printer_creds` → `reason: "no_credentials"`, and `_probe_printer_state` is never called;
- a stubbed `no_credentials` answer shows the credentials wording, not "couldn't reach". There is no manual row for this, because producing it would mean removing a live printer's credentials.

**Risks.**
- **Escape.** Escape dismisses the newest `.toast-msg` (`inv_core.js:268-292`). The pill must not use that class, or an Escape meant for a modal gets swallowed while it shows.
- **Layering.** The toast layer (z 11000) sits under `mountOverlay` panels; the bulk-move panel (z 20000) can cover the pill. That is acceptable, because the pill shows *before* an overlay mounts.
- **Existing wait budgets.** Group 38.5 set 8 s E2E waits against the ~3 s probe floor. Adding a server re-probe lengthens the worst case to ~3 s + ~2 s, so re-check `test_overlay_wait_budgets.py`.
- **Considered, deferred:** a short server-side cache of "unreachable" results to avoid paying twice. It changes nothing for safety, since unreachable already fails open, but it adds state. Revisit only if the double wait annoys.

### 39.4 — Ask before moving a spool OFF a printing head (D6)

**Engine** (`_perform_smart_move_impl`, before any write). Extend the pre-flight at `logic.py:524-540` with a **source pass**:
- Read each moving spool's record (`get_spool`).
- Tag every spool whose own `location` is a `printer_map` key as role `source`.
- Skip a re-scan onto the same head (`location == target`, the `is_already_here` case at `:751`).
- Feed source, destination and feeds heads into **one** `_uncovered_active_heads` call. That means one probe per printer through the memo, one answer for the whole move, and nothing written.
- The write loop keeps its own fresh `get_spool` (`:688-689`). A second read costs ~15 ms (investigation I2-16: `get_spool` median 15.5 ms) and avoids acting on a record read before a 2 s probe.

**Message helper, `_active_print_message(active_prints, target)`.** Derek's wording, generalised:

| Case | Message |
|---|---|
| One source | "#42 is loaded on XL-3. Moving it to CR-CT-2-R1 means FCC stops charging this print to it. Continue?" |
| Several sources | "#42 is loaded on XL-3 and #57 on XL-1. Moving them to CR-CT-2-R1 means FCC stops charging this XL print to them. Continue?" |
| Destination (existing meaning, now with the consequence) | "XL is PRINTING. Loading #57 onto XL-2 unloads #196, so FCC stops charging this print to #196. Continue?" |
| Same printer, head → head | One message naming both heads; one ask. |

**Doors this covers with no per-door code.**
- Location Manager assign.
- Buffer location scan (`/api/smart_move`).
- Slot-QR scan or deposit of a spool that currently sits on a head.
- Force Location "add".
- Return (39.2).
- A Quick-Swap whose slot spool is a ghost loaded on another head (`find_spool_in_slot` includes ghosts, `logic.py:2375-2390`).

**Deliberately not covered.**
- **The chain's internal hop.** Its spool is in the box by then.
- **Smart Load's resident unload.** `perform_smart_eject` already guards its own source with the forwarded confirm (`logic.py:650-653`, `:1766-1774`).
- **Bulk Move.** `plan_bulk_move` skips every head-loaded spool (`:1119-1126`); unchanged.
- Undo, the wizard's location edit, and `/api/spool/update`. See "Doors this group does NOT close" below.

**Frontend.** The three overlays render the backend `msg` and send the `active_prints` heads.
- Extract **one** shared confirm, e.g. `window.confirmActivePrint({activePrints, msg, host, onConfirm})`, from the three copies. Check the name for collisions first.
- Keep their proven keyboard and scan contract: the `isScanInFlight` Enter guard, Tab cycling, `attachConfirmQRs` mounted in `handle.panel`, and `tier: 'confirm'` plus `host`.

**Tests (hermetic, real engine, `WireSpoolman`).**
- `manage_contents add` of `#42` (on `XL-3`) to `CR-CT-2-R1` while XL is PRINTING / PAUSING / RESUMING → `requires_confirm`, role `source`, a message naming #42, XL-3, CR-CT-2-R1 and "stops charging"; zero writes.
- PAUSED → moves.
- Head → head `XL-1` → `XL-3` while printing → exactly one answer listing both heads; `_probe_printer_state` called once.
- `/api/smart_move` with `#42` on XL-3 and `#57` on XL-1 → one answer, zero writes.
- Re-scan `#42` onto XL-3 → no ask.
- Confirmed with `["XL-3", "XL-1"]` → both move.

**Risks.**
- **Mock churn.** Tests that feed `get_spool` a `side_effect` sequence break on the extra read. This is the same pass as 39.7.
- **Deduct truth (checked 2026-09-13).**
  - **The moved spool:** the wording is true. A mid-print swap event is recorded only on a resume (`print_monitor.py:421-438`), so a D6-confirmed move while PRINTING records nothing, and the moved spool is never charged.
  - **The emptied head's grams are the gap:**
    - If another spool is loaded onto that head before the print ends, completion sees a clean 1→1 change and routes to the `spool_changed` review (`print_deduct.py:781-805`).
    - If the head stays empty, `_is_sid_swap` needs a spool on both sides (`:473-484`). Completion therefore auto-applies, charges nobody for that head, and only logs the shortfall ("wasn't deducted", `:406`).
    - A cancelled print's review keeps only heads that resolve to a spool (`:1352-1366`) and drops the rest silently.
  - **Where the fix goes:** found-while-briefing item 6 covers this. It belongs to Group 22, but Group 22's only open item is blocked on data. File it as an **unblocked 22.5 and build it alongside 39.4**, because D6 turns "a head emptied mid-print" into a confirmed everyday action. See Cross-plan notes.
- **Legacy firmware.** Its `is_active` also counts the `printing` flag (`prusalink_api.py:498`), which some firmware may keep set while paused.

### 39.5 — Force Location gets a yes-path

- **Branch on both confirm answers** in `inv_details.js:1224-1237`:
  - `res.status === 'requires_confirm'` (the `add` answer);
  - `res.require_confirm && res.confirm_type === 'active_print'` (the `force_unassign` answer, `routes_scan.py:317-324`).
- Show the shared confirm from 39.4 with `host: #spoolModal`. The Swal has already closed by the time `.then(result)` runs.
- Retry with `confirmed_toolheads` (add) or `confirm_active_print: true` (force_unassign).
- Use the server's `msg`, so D6 wording shows for "move #42 off XL-3 to Unassigned".
- **Later interaction:** the slot-picker group (D2) will turn Force Location into a Dryer Box into the picker. This yes-path stays the confirm step that picker calls. Its location filter still offers Printer rows (`:954`); that is D3's job.
- **Tests (route-stubbed E2E, `test_move_result_consumers_e2e.py`).**
  - Stubbed `requires_confirm` → the confirm appears above `#spoolModal` → Yes → the retry body carries the head. Same for `force_unassign`.
  - Cancel → no second POST, and the details stay open.
  - **Test debt** from Move-pipeline follow-ups item 6, in the same file (`inv_details.js:1228-1236`):
    - a stubbed `status: error` answer shows its `msg` as a 7 s error;
    - a stubbed success with `auto_deploy_skipped` for the spool shows the 7 s "placed, but NOT deployed" warning.

### 39.6 — One confirm to eject off a printing head

**Today.**
- `perform_smart_eject` answers the active-print dict first (`logic.py:1766-1774`).
- Only on the next trip does it answer `"REQUIRE_CONFIRM"` for a head spool with no saved home (`:1896-1905`).
- `doEject` chains `requestConfirmation` twice (`inv_loc_mgr.js:1540-1553`).

**Design: combine the two gates in the route, and leave the engine's answer alone.**

**The engine contract does NOT change.**
- `perform_smart_eject` keeps returning `True` / `False` / `"REQUIRE_CONFIRM"` / the active-print dict (`logic.py:1746-1753`). Every refusal is truthy, and callers test `is True`.
- Three other consumers depend on that contract:
  - Smart Load's `_eject_refusal_reason` (`logic.py:408-419`, used at `:654-655`);
  - Group 41.2's per-spool result table;
  - Group 42.5a's `report` dict, which assumes the contract stays.
- A combined engine answer would break all three. (This replaces an earlier draft that reshaped the engine's return.)

**Factor the "no saved home" decision into a pure helper that `perform_smart_eject` itself calls,** so the two can't drift.
- Signature: `_eject_destination(spool_data, printer_map, homeless_destination)` → `(target_loc, slot, needs_unassign_confirm)`.
- It covers the saved-source guards (`:1801-1837`: the loop check, the room bypass, the stale toolhead trail) and the fallback (`:1890-1905`).
- It reads `locations.json`, writes nothing, and never touches the printer.
- For the Room fallback it calls the shared no-home resolver (Cross-plan notes), not a copy.

**`manage_contents remove`** (`routes_scan.py:294-314`).
- When the eject answers the active-print dict, call the helper for the same spool.
- If the spool also needs the unassign, answer once:
  `{"success": false, "require_confirm": true, "confirm_types": ["active_print", "unassign"], "confirm_type": "active_print", "active_print": …, "msg": …}`.
- `doEject` then sends `confirmed: true` and `confirm_active_print: true` on the one Yes.

**Wording by where the spool is.**
- Toolhead: "#42 is loaded on XL-3 and has no saved home. Ejecting it leaves it Unassigned, and FCC stops charging this print to it. Continue?"
- Room: "#88 is loose in CR with no saved home. Unassign it?"
- **This depends on Group 41's Q1.** Under its option B, a cart, shelf or drawer spool with no home also gets the unassign prompt, instead of going up to its Room. The wording then needs that case too: "#88 is on CR-CT-2-R1 with no saved home. Unassign it?" Get Derek's Q1 answer before freezing the text.

**Flip the pin** that holds the old text, `tests/test_l316_charact_scan_audit.py:388`, in the same commit.

**Tests.**
- Hermetic Flask client: one confirmed call ejects a homeless resident from a printing head (the investigation's I5-16 sequence, in one round-trip).
- A resident with a saved home still gets only the print prompt.
- `_eject_destination` agrees with `perform_smart_eject` on every no-home case, parametrized over:
  - a toolhead;
  - a Room;
  - a cart row;
  - `PM-DB-n`;
  - a stale toolhead trail.
- Smart Load's refusal reasons are unchanged: the `_eject_refusal_reason` pins stay green.
- Route-stubbed E2E in `test_confirm_chain_reshow_e2e.py`:
  - exactly one `#confirmModal` show, then the success toast;
  - the Activity Log line for "the dialog isn't on screen yet" (`inv_cmd.js:1458`), which Move-pipeline follow-ups item 6 lists as untested.

**Risk.** The helper must be the code `perform_smart_eject` actually runs, not a copy. A copy would drift and re-open the double prompt. Smart Load passes `homeless_destination` and must stay unchanged (`:1891-1893`).

### 39.7 — Smart Load's resident list fails closed (R1-03)

- **Read strictly.** `logic.py:629` switches to `get_spools_at_location_detailed_strict`.
- **On an exception:** record `failures[sid] = "could not read XL-1 from Spoolman"` for every incoming spool, log ERROR, and answer `status: error` before any eject or write. This matches `plan_bulk_move`'s fail-closed source read (`:1072-1078`).
- **Use the detailed rows' `is_ghost` / `location`** to skip non-residents, which also removes R1-02's extra reads.
- **Mock pass.** Re-derived by grep on `be9f045`. The list drifts, so re-run `grep -n "get_spools_at_location\b" tests/*.py` before starting. Fifteen test files reference the fail-open `get_spools_at_location` by name:
  - **Move tests that reach the switched read, so they need the strict reader too** (check each against the new read rather than assuming):
    - `test_active_print_chain_confirm.py` (`:287`, inside the shared `_run`);
    - `test_smart_move_spoolman.py` (`:46`);
    - `test_deployed_flag_preservation.py` (`:46`, `:85`, `:130`);
    - `test_toolhead_resident_eject_21_3.py` (`:64`);
    - `test_universal_fallback.py` (`:64`, `:139`);
    - `test_logic_undo.py` (`:44`, a whole-module mock);
    - `test_return_and_breadcrumb.py` (`:63`, `:97`, `:133`);
    - `test_l316_charact_bindings_errors.py` (`:57`, `:101`, `:134`, `:158`);
    - `test_unknown_location_bucket.py` (`:106`).
  - **Not affected by the Smart Load switch:**
    - the deduct-side files `test_cancel_deduct.py`, `test_cancel_detection.py`, `test_cancel_review.py`, `test_deduct_followups_22_4.py` and `test_spool_swap_22_3.py`, which patch it for `_resolve_usage_to_spools` (`print_deduct.py:1097`);
    - `test_l316_charact_record_deletes.py` (`:537`, `:576`), which covers the location-delete cascade that Group 41.3 changes.
  - **Dropped from the list:** `test_auto_slot_pick.py` patches only `get_spools_at_location_detailed` (`:66`).
  - **Merge order:** `test/sweep-reds-hermetic` (`d785444`) rewrites `test_deployed_flag_preservation.py`. Merge it to `dev` before this pass, or the two rewrites conflict.
- **Test:** the list read raises → XL-1 still holds only `#99`, the result is `status: error`, zero writes.

### 39.8 — Status codes for Quick-Swap and Return

- **Refusals that need an answer from the user** (`*_requires_confirm`) return **200** with the action, like `assignment_requires_confirm`.
- **Failures** (`return_failed`, `quickswap_failed`) change 502 → **409**. Bodies are unchanged.
- **Handle a non-JSON body.** `performSwap`/`performReturn` read `r.text()` and try `JSON.parse`, so a proxy's HTML error page shows "server answered 502" rather than "network error".
- **Pins:** update the 29.B3 status assertions in `test_l316_charact_bindings_errors.py` and the failure tests in `test_active_print_chain_confirm.py` (`:955-999`, `:1040`).

### 39.9 — `CMD:TRASH` while a bulk move is armed

- Mirror `CMD:CLEAR` at `inv_cmd.js:1435-1437` in the `CMD:TRASH` handler (`:1442`): if `state.bulkMoveActive`, show an info toast ("Eject waits until the bulk move is finished or cancelled") and log it. No confirm opens.
- **Test:** route-stubbed E2E in `test_confirm_chain_reshow_e2e.py`.
  - Arm the session, scan `CMD:TRASH:999101`: no `#confirmModal` show, `state.activeModal` stays null, and a following location scan still reaches the session.

---

## Doors this group does NOT close (so nobody assumes it did)

- **Undo** writes directly and never probes the printer (`logic.py:2096-2111`). [Group 41](41-honest-bulk-results.md) 41.4 adds the D6 ask there by default, using this group's `_uncovered_active_heads`. Its Q2 only confirms that with Derek.
- **The wizard's location edit** writes `location` straight to Spoolman (`api_edit_spool_wizard`). That belongs to the D3 printer-picker work.
- **A weight edit that auto-archives a loaded spool** silently unloads it (`spoolman_api.py:215-227`). That belongs to the one-spool-per-toolhead work (see the excluded row).

---

## Calls this plan makes on Derek's behalf (flag any that are wrong)

- **An offline printer never adds a prompt.** The move proceeds, and FCC says plainly that it couldn't check. Derek expects offline printers often; asking every time would train him to click through.
- **Overlays keep their own printer check.** The server re-check only catches what that check missed, so a mid-print Quick-Swap is one confirm, not two.
- **A browser still running pre-change code** (a stale cached page) gets asked again rather than trusted.
- **"Checking…" is one pinned pill** for both clicks and scans. The buglist offered a spinner or a toast; scans have no button to spin.

---

## Dependencies and build order

**Upstream.**
- **`fix/core1-return-ejectall-guard`** (`1fb5678` + `76398cb`; committed locally, not pushed or merged) edits code next to the handlers this group rewrites. Merge it to `dev` first. It touches:
  - the Return route (`_printer_row_toolheads`, `routes_bindings.py`);
  - `clear_location`, `triggerEjectAll` and `ejectAllFromScan`;
  - `_resolveReturnTarget` in `inv_quickswap.js`.
- **`test/sweep-reds-hermetic`** (`d785444`, local only) rewrites `test_deployed_flag_preservation.py`, which 39.7's mock pass touches. Merge it first too.
- Otherwise nothing is hard-blocking.

**Downstream.**
- **[Group 41](41-honest-bulk-results.md)** reuses 39.1's scoped confirm, 39.3's pill and label, 39.4's shared confirm component, and `_uncovered_active_heads` (for Undo). Build 39 first.
- **[Group 40](40-slot-picker.md)** adds the "head already fed from elsewhere" check (40.0c) as a **sibling `fed_heads` / `confirmed_fed_heads` pair**, not as a role inside `active_prints`. 39.1 reserves both fields in the shared answer shape, so the contract is defined once, here. Build 39 first.
- **[Group 42](42-single-slot-box-lifecycle.md)** edits the same PRINTER MOVE branch and `perform_smart_eject`'s write paths, and it adds a stateful locations store to the shared harness. Its only logic dependency is the eject contract, which 39.6 keeps unchanged; otherwise it is merge order only.

**Inside the group:**
1. **39.1** scoped confirm contract, plus the harness extraction.
2. **39.7** the fail-closed resident read, which is where the mock pass happens.
3. **39.4** the source guard and the message helper.
4. **39.2** the route re-check, with **39.3** the pill. The buglist says to build these two together.
5. **39.5** the Force Location yes-path.
6. **39.6** one eject confirm.
7. **39.8** status codes.
8. **39.9** the `CMD:TRASH` guard.

---

## Cross-plan notes (Groups 39–42, reviewed 2026-09-13)

### Recommended build order across the four groups

0. **Merge the two local prerequisite branches into `dev`:**
   - `fix/core1-return-ejectall-guard` (`1fb5678`, `76398cb`);
   - `test/sweep-reds-hermetic` (`d785444`).

   Neither branch is on origin. Both touch code or tests that 39, 40, 41 and 42 rewrite, so merging them now avoids rebasing every group over them.
1. **Before any build, ask Derek the three questions that change shared contracts:**
   - [41's Q1](41-honest-bulk-results.md): where a spool with no home goes. It shapes 39.6's wording, 41.2's lists and 42.3c's redirect.
   - **This doc's Q1:** how deliberate a mid-print confirm must be. It sets the shared confirm component's keyboard default.
   - [42's Q-B](42-single-slot-box-lifecycle.md): what a location scan does in eject mode. It fixes the order of checks in `inv_cmd.js`'s location branch.

   The other questions can wait for their sub-task.
2. **Group 39 (this group).** Everything else consumes what it defines. Start the unblocked Group 22.5 (below) alongside 39.4.
3. **Group 41.** The smallest group. It closes the destructive doors, and it settles the no-home rule before 42.3c copies it.
4. **Group 42.** Its effective slot, 13.6 single-slot exclusion and multi-spool refusal are prerequisites for 40.0c/40.0d, and 40 reuses its stateful locations store. Its 42.5b lands before 40 touches the same scan branch.
5. **Group 40.** The largest group, built on 39 and 42. Inside it, build 40.3 (Derek's slot-label path) early.

If Derek wants the PolyDryer release before the honest bulk results, 41 and 42 can swap. 42 then uses its fallback undo toast, and 42.3c still waits for 41's Q1.

### Overlaps that concern this group

**The shared pre-write contract (39.1).**
- It is edited by 39.1, 39.4, 39.7, 40.0a, 40.0c, 40.0d, 40.0e, 41.6, 42.1, 42.2 and 42.3a.
- This doc defines the order and the one `requires_confirm` shape; the others extend it.

**`perform_smart_eject`'s answer.**
- Other groups reshape it: 41.2 (per-spool result lists), 41.8 (where a spool with no home goes), and 42.1 / 42.5a (the release plus a `report` dict).
- Its callers are Smart Load (`_eject_refusal_reason`), `clear_location`, `manage_contents remove` and Undo's ejections.
- That is why 39.6 keeps the return contract unchanged.

**One strict "direct residents of a single-occupancy location" reader.**
- It serves 39.7, 40.0c, 42.3b (the Undo moves restore, the same shape as `logic.py:2136-2140`), 42.3c, and 41.2 / 41.3.
- Build the helper once, in 39.7, with one harness fake and one mock pass.

**One "where a spool with no home goes" resolver.**
- Today there are several: `logic._known_room_of` (`logic.py:387-405`) and `get_room_from_location` (`:1713-1735`), with 42.3c and 41.8 about to need the same answer.
- 42.3c moves `_known_room_of` into `locations_db`; no test patches it as of `be9f045`.
- 39.6's `_eject_destination` calls that resolver rather than copying it.

**The test harness.**
- 39.1 extracts `tests/move_engine_harness.py` from `test_active_print_chain_confirm.py`: `FakeSpoolman` `:114`, `WireSpoolman` `:199`, `_probe_for` `:237`, `_run` `:265`, with attach/detach patched at `:280-283`.
- Group 42 adds the stateful in-memory locations store (it is the first real user), and 40 reuses it.

**One frontend confirm component: 39.4's `window.confirmActivePrint`.**
- 40.3 wraps it as `_confirmHeadLoad` and adds a STORE action to `attachConfirmQRs` / `routeConfirmScan` (`inv_core.js:387`, `:459`).
- 39.5, 40.4, 41.2 (Eject All on a head), 41.3 (`deleteLoc`) and 41.4 (Undo) reuse it.
- This doc's Q1 sets its keyboard default for all of them.

**Waiting UI.** 39.3's `withPrinterCheck`, `fetchPrinterStateDetailed` and `setProcessing(true, {label})` are reused by 40.1 (per-printer "checking…" tiles) and by 41.2, 41.3 and 41.4.

**The Return route and overlay.**
- Touched by the core1 branch, 39.2, 39.8, 40.6 (dry run, slot choice, `expected_spool`) and 42.1 (release on Return).
- Three of them edit `performReturn` (`inv_quickswap.js:571-582`). Land 39.2 / 39.8 first.

**`perform_undo` (`logic.py:2076-2204`).** 41.4 (honest reporting, plus the D6 ask through `_uncovered_active_heads`) and 42.3b (occupancy check, attach/release) edit the same loops.

**Group 22, and a new 22.5.**
- Found-while-briefing item 6 is owned by Group 22: a cancel review drops an emptied head silently, and a `no_spool` card names no spool.
- Group 22's only open item, 22.3(b), is blocked on data (`working-groups.md:116`).
- File item 6 as an unblocked 22.5 and build it alongside 39.4. 39.4's "Deduct truth" risk has the verified mechanism.
- Group 42.1b's release also runs on the deduct-to-0 archive edge, inside the print-monitor daemon's `_apply_usage_to_printer`.

**Group 35.**
- The only touch point is printer credentials: 39.3's `no_credentials` message points at the Config credentials grid that Group 35 reuses.
- No conflict. Group 35 keys settings by printer Name; this group keys on LocationID.

**Group 34.** 39.9 adds a "never during a bulk session" guard to `CMD:TRASH`, next to L298's `CMD:CLEAR` guard. No conflict with S5 or the auto-generated-id slice.

**Move-pipeline follow-ups item 6 (E2E test debt) is split across groups.**
- **Here:** the Quick-Swap / Return failure toasts (39.2); Force Location's error and `auto_deploy_skipped` toasts (39.5); the "isn't on screen yet" log line (39.6).
- **Group 40:** `not_deployed` in the confirmed slot-QR replay and `auto_deploy_skipped` in `_doAssignFinalize` (40.3); the virtual-printer ghost filter (40.6).
- **Group 41.2:** the FE-1 double-click on the safety and action dialogs.
- **Eject / Return item 5** (the silent restore in `test_return_overlay_and_refresh.py`) is in 39.2, or in 40.6 if that lands first.

**Shared test pins this group flips.** Flip each deliberately, in the commit that changes the behaviour, and tell the next group's session which pins moved.
- `test_l316_charact_bindings_errors.py` (also 40.6);
- `test_active_print_chain_confirm.py` (also 40.0d, 41.4 and 42.1);
- `test_l316_charact_scan_audit.py:388` (41.2 also touches its 27.6 `skipped_slotted` pins);
- `test_move_result_consumers_e2e.py` `:535` / `:600` (also 40.4 and 40.6);
- `test_confirm_chain_reshow_e2e.py` (also 40.3 and 41.2);
- `test_deployed_flag_preservation.py` (also rewritten on `test/sweep-reds-hermetic`).

---

## Verification

- **Iterate hermetically.** From `inventory-hub/`, run `"C:/Python314/python.exe" -m pytest tests/ -p no:cacheprovider -q --offline`.
- **Before merging** anything that touches the frontend, run the full E2E sweep. ⚠️ It writes to shared dev data (CLAUDE.md "Testing"), so get Derek's OK and don't run it while he is testing by hand. Don't run visual or E2E tests alongside a sweep ([[no concurrent sweep and visual]]).
- **Update CLAUDE.md's "Spool / Filament write surfaces" table** for the Return, Quick-Swap and eject rows, whose confirm contract changes. Also update the "Project Conventions" note on active-print confirms to describe `confirmed_toolheads`.
- **The route table is unchanged** (no new routes), so `tests/test_route_table_pin.py` needs no update.

---

## Manual checks for Derek (add to the checklist)

Printing checks need a real print on the XL or the Core One. "Powered off" means the printer is switched off at the wall.

| # | Check | Steps | Pass if |
|---|---|---|---|
| 39-a | **Quick-Swap mid-print** | XL printing. Open XL-2 → tap the `LR-MDB-1` slot 2 tile | One confirm with the yellow "XL is PRINTING" banner. Yes → the new spool is on XL-2 and XL-2's old spool is back in its box. No second prompt |
| 39-b | **Return mid-print** | XL printing. Open XL-3 → ↩️ Return | The banner names XL (the head being emptied). Yes → the spool is in `LR-MDB-1` slot 3. No second prompt |
| 39-c | **Return while idle** | XL idle. Open XL-3 → ↩️ Return | No banner. One tap parks the spool |
| 39-d | **"Checking…" (offline printer)** | Core One powered off. Open CORE1 → ↩️ Return (or tap the `CR-MDB-1` slot 1 tile) | "⏳ Checking CORE1…" appears within about half a second. The overlay then says it couldn't reach CORE1, and the action still works |
| 39-e | **"Checking…" on a scan** | Core One powered off. Put a spare spool in the buffer → scan the `CR-MDB-1` slot 1 label | The dim screen shows "Checking CORE1…" instead of a blank dim. The load then completes |
| 39-f | **Move off a printing head** | XL printing. Open XL-3 → pick its spool into the buffer → scan `CR-CT-2-R1` | One prompt naming the spool, XL-3, `CR-CT-2-R1` and "stops charging". Cancel → nothing moved. Repeat and choose Yes → moved |
| 39-g | **Paused never asks** | Pause the XL print → repeat 39-f | No prompt; the spool moves |
| 39-h | **Head to head asks once** | XL printing. Pick up XL-1's spool → scan XL-3's toolhead QR | Exactly one prompt, naming both heads |
| 39-i | **Force Location mid-print** | XL printing. Details of XL-3's spool → Force Location → `CR-CT-2-R1` → Force Move. Then repeat with "-- Unassigned --" | Both times a confirm appears (not a red "failed" toast); Yes moves the spool |
| 39-j | **One eject prompt** | XL printing, a spool on XL-2 with no saved home (e.g. one put there with Force Location) → ⏏️ Eject on its card | Only one prompt beyond "Eject spool #N?". Its wording mentions XL-2 and Unassigned, not "already in a room" |
| 39-k | **Eject during a bulk move** | Open `CR-CT-2-R1` → 🔀 Move all → (the Location Manager stays open behind the panel) → scan the TRASH QR on one of its spool cards (printed, or on a second screen if the panel covers it). Don't open another location first: while a bulk move is armed, a location scan becomes the move's destination | An info toast only. No invisible dialog; later scans still work |
| 39-l | **Deposit mid-print still works** | XL printing. XL-2 grid → Deposit a buffered spool into its slot; confirm once with Enter, once with a click, once with the scan QR | All three load the spool after one confirm (regression check for R2-01) |

---

## Open questions for Derek

### Q1 — What makes a mid-print Quick-Swap "deliberate"? — ✅ ANSWERED 2026-09-18: option A

**Derek chose A: keep today's overlay** (Yes focused; Enter, a click or the CONFIRM QR all confirm), adding only the new consequence wording. Build it that way; the background below is kept for the record.

**Background.**
- You said Quick-Swap is for idle, stopped or paused printers, and that using it mid-print is a deliberate correction when FCC has drifted from the real printer.
- After this group, FCC will **always** show the yellow "XL is PRINTING" banner when it can see a print. The server re-check closes the gap where a slow printer answer skipped the banner.
- Today the banner overlay has **Yes focused by default**. Enter, a click, or scanning its CONFIRM QR all confirm. A scanner's own Enter can't confirm by accident; that was fixed 2026-08-03.

**Where you meet it.** The ⚡ Quick-Swap grid on a toolhead's Location Manager view, and the Deposit button beside it.

**Worked example.** The XL is printing. FCC still thinks XL-2 holds `#196`, but on the printer you already loaded the spool from `LR-MDB-1` slot 2. You open XL-2 and tap slot 2 to bring FCC back in line. The banner appears.

**Options.**
- **A. Keep today's overlay** and add only the new consequence wording. Seeing the banner and then pressing Yes (or scanning CONFIRM) is the deliberate act. **(Recommended:** it adds no friction to the one realistic mid-print use.)
- **B. When the banner shows, focus "No, cancel" by default,** and relabel Yes as "Yes, swap during the print". A bare Enter then cancels; a click, Tab + Enter, or the CONFIRM QR still confirms.
- **C. While printing, allow only the CONFIRM QR scan or a mouse click.** The keyboard can't confirm.

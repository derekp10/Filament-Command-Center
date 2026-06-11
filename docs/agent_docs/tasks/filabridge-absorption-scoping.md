# FilaBridge: Absorb vs Adopt — Scoping

*Prepared for Derek (sole dev, Filament Command Center). 2026-06-10. File:line citations verified against the live `dev` tree; load-bearing claims went through an adversarial verification pass (see §8 — two were corrected, three refined).*

---

## 1. TL;DR / recommendation

**Do Scope 1 now, plan Scope 2 as the eventual direction, keep the archived upstream pinned as a fallback. Do NOT adopt the active fork.**

Scope 1 (FCC owns the toolhead↔spool mapping; stop *reading* FilaBridge `/status`) is a small, low-risk change that deletes a whole class of dual-writer desync bugs and removes the residual ~4s L3 latency tail — that tail is FilaBridge synchronously probing your offline printer, and FCC already probes PrusaLink directly without it.

**One precondition** (surfaced by verification): Scope 1's "single source of truth" is only true if FilaBridge's *own* `/api/nfc/assign` path is unused — in the code, that path lets FilaBridge mutate the map autonomously. You confirmed you don't use FilaBridge's NFC assignment, so this holds today; we should confirm/disable that route to harden it. Scope 2 removes the concern entirely.

---

## 2. Context — why this is on the table

Three forces converge:

1. **The L3 latency tail.** The slot-assign latency fix A+B already shipped (14.6s → 6.5s). Fix A is a per-operation probe memo ([prusalink_api.py:8-26](../../../inventory-hub/prusalink_api.py)); fix B short-circuits the legacy `/api/printer` fallback on a connection-level error ([prusalink_api.py:191-196](../../../inventory-hub/prusalink_api.py)). The *remaining* ~4s is not an FCC↔PrusaLink cost — FCC already probes PrusaLink directly with a 2s timeout ([prusalink_api.py:184](../../../inventory-hub/prusalink_api.py)). The tail is FilaBridge's `/status` endpoint, which synchronously and serially probes every printer's live PrusaLink state with no caching; an offline printer eats the full timeout. FCC's heartbeat already moved its liveness check OFF `/status` for exactly this reason — the comment at [app.py:5049-5058](../../../inventory-hub/app.py) records that `/status` "takes ~5-6s on a prod-sized fleet". Any FCC path still touching FilaBridge `/status` inherits that cost.

2. **FilaBridge is archived but actively forked.** Upstream `needo37/filabridge` is archived (last push 2026-04-16). The most-active fork (`doutorinfamous`) has pivoted away from Prusa entirely — it **deleted `prusalink.go`**, added a Moonraker client, and defaults the driver to `moonraker` (`COALESCE(driver,'moonraker')`, no `DriverPrusaLink` constant). It is single-maintainer, 0 releases, 0 tags. Continuing to depend on FilaBridge means depending on either a frozen archive or a personal Snapmaker/Moonraker project.

3. **The dual-writer desync class.** The 2026-04-22 outage (and the 2026-04-26/27 incidents) were caused by *two sources of truth* for the toolhead map — FilaBridge's SQLite `toolhead_mappings` vs. Spoolman's `location` field — drifting apart, with FilaBridge silently rejecting maps that violated its one-spool-one-toolhead invariant. The entire `_fb_spool_location` pre-flight ([logic.py:99-128](../../../inventory-hub/logic.py)) and the L324 reconcile feature ([app.py:4334-4448](../../../inventory-hub/app.py)) exist *only* to detect and heal that drift; the `_fb_write` docstring ([logic.py:131-160](../../../inventory-hub/logic.py)) names 2026-04-22 directly. With FCC as the only thing that assigns spools in your workflow, the second source of truth is mostly cost, not a safety net.

---

## 3. What FilaBridge does vs. what FCC already has

| Capability | FilaBridge (Go) | FCC today | Verdict |
|---|---|---|---|
| **Print-finish detection** (poll PrusaLink, edge-detect PRINTING→idle) | ✅ per-printer goroutines on a ticker | ❌ **none today** — FCC has no proactive monitor; it only reacts to FilaBridge's `/print-errors` feed ([app.py:5059](../../../inventory-hub/app.py)). **Cancelled-print detection now DESIGNED (see §9)** — rides the existing pulse probe; ships before the full Phase-2 monitor | **The only genuinely missing piece — cancel-edge slice designed** |
| **GCode download + `filament used [g]=` parse** | ✅ full download + 3× exp-backoff retry | ✅ **FCC's own implementation** — `download_gcode_and_parse_usage` ([prusalink_api.py:64-134](../../../inventory-hub/prusalink_api.py)). Shares the *parse regex* with FilaBridge; the Range fast-path (`bytes=-2097152`) is **FCC-original** (FilaBridge has none); FCC lacks FilaBridge's retry/backoff | FCC owns the capability |
| **Per-toolhead deduct** (read-modify-write `used_weight`) | ✅ PATCH `/spool/{id}` | ✅ three FCC paths: aggressive-parse ([app.py:4074](../../../inventory-hub/app.py)), manual-recovery ([app.py:4116](../../../inventory-hub/app.py)), auto-recover ([app.py:5138](../../../inventory-hub/app.py)) — same RMW PATCH mechanism | FCC owns it |
| **MMU-alias dedup** (M0/M1 same position) | ❌ deserializes the `mmu` flag but never uses it | ✅ `_resolve_active_locs_for_printer` + `processed_positions` ([app.py:461-504](../../../inventory-hub/app.py), [app.py:4055-4065](../../../inventory-hub/app.py)) | **FCC is ahead** |
| **Live printer state probe** | ✅ via `/status` | ✅ `get_printer_state`→`_probe_printer_state` direct to PrusaLink ([prusalink_api.py:136-221](../../../inventory-hub/prusalink_api.py)) | FCC owns it |
| **Toolhead↔spool mapping store** | ✅ SQLite `toolhead_mappings` | ✅ Spoolman `location` + Printer-row `toolheads[]` ([locations_db.py:792-806](../../../inventory-hub/locations_db.py)); FCC is the sole *FCC-side* writer | **Redundant — drop, don't migrate** |
| **Printer credentials** (IP + API key) | ✅ SQLite `printer_configs`, served at `/printers` | ❌ FCC reads them *from* FilaBridge — `fetch_printer_credentials` ([prusalink_api.py:29-47](../../../inventory-hub/prusalink_api.py)) | **The one real dependency to migrate** |
| **Spool→location assignment via NFC scan** | ✅ `/api/nfc/assign` → `AssignSpoolToLocation` → writes **both** Spoolman **and** the FB map | ✅ `perform_smart_move` covers the same assignment logic | **Overlaps FCC; this is the rogue second writer (see §4 Scope 1 caveat)** |
| **Error queue + ack** | ✅ in-memory, manual ack | ✅ FCC polls + snapshots + auto-recovers (a superset; [app.py:5059-5170](../../../inventory-hub/app.py)) | FCC owns it |
| **Reconcile** (FB↔Spoolman drift) | n/a | ✅ L324 ([app.py:4334-4448](../../../inventory-hub/app.py)) | Vestigial once single-source |
| **NFC tag reading hardware** (`nfc.go` air-interface) | ✅ session state machine | ❌ — and **out of scope** (your OpenPrintTag + SpoolmanScale path is independent) | **Do not replicate the tag layer** |

**Takeaway: FCC already owns ~80% of FilaBridge's job.** What it lacks is the unattended *trigger* — the loop that notices "a print just finished" — plus a local home for printer credentials.

---

## 4. The three options

### Scope 1 — "FCC owns the mapping" (recommended now)

**What it is.** Stop *reading* FilaBridge `/status`. Make FCC's binding model (Spoolman `location` + Printer-row `toolheads[]`) the single source of truth for "where is this spool mapped." FilaBridge keeps running for the print-monitor + auto-deduct loop, and FCC keeps *pushing* mappings to it via `POST /map_toolhead` so its deduct still targets the right spool. The read side collapses to one source; the write side stays one-way (FCC → FilaBridge).

**Effort — S.**
- Repoint `_fb_spool_location` ([logic.py:99-128](../../../inventory-hub/logic.py)) so "where is spool X mapped" is answered from FCC's own authoritative state (Spoolman `location`) instead of `GET {fb}/status`. Its callers ([logic.py:670, 727, 768, 944, 1234](../../../inventory-hub/logic.py)) keep the same `(printer_name, toolhead_id)` return contract → single-function swap.
- The L324 reconcile ([app.py:4334-4448](../../../inventory-hub/app.py)) becomes vestigial (it only heals FB↔Spoolman mapping/location drift, which can no longer occur). Leave or retire it.
- Keep `_fb_write` as-is — FilaBridge still needs the map for its deduct.

**⚠️ Precondition (from verification — this corrects the original "FCC is sole writer" assumption).** In the code, FilaBridge can mutate the map **autonomously** through its own NFC path: `GET /api/nfc/assign` → `AssignSpoolToLocation` → `SetToolheadMapping` → `INSERT OR REPLACE INTO toolhead_mappings`. So FCC is the sole writer **only if that NFC-assign path is unused.** You confirmed you don't use FilaBridge's NFC assignment — so this holds today — but to make FCC-as-single-source-of-truth *robust*, confirm nothing drives `/api/nfc/assign` and ideally disable that route on your FilaBridge instance. (Scope 2 removes the rogue writer entirely.)

**Risk — Low, and lower than the status quo** *provided* the precondition above holds. The other hazard: `_fb_spool_location` was originally added because Spoolman's `location` can *lag* ([logic.py:103-107](../../../inventory-hub/logic.py)). Before trusting Spoolman as the map source, confirm FCC writes Spoolman synchronously-first across all move paths (smart-move/eject/force/undo) — `perform_smart_move` writes Spoolman, then maps FilaBridge, so Spoolman (the thing FCC controls) is written first.

**Migration steps.**
1. Confirm/disable FilaBridge's `/api/nfc/assign` so FCC is genuinely the only map writer.
2. Audit the four move paths to confirm Spoolman `location` is written before any FB call returns.
3. Swap `_fb_spool_location`'s backing read to Spoolman; keep the return shape.
4. Run the FB-seam tests (`test_filabridge_recovery.py`, `test_filabridge_status_dot.py`, `test_filabridge_reconcile.py`).
5. Optionally deprecate the L324 reconcile UI.

**Interaction with the desync class.** **Eliminates it** (two map sources → one), once the NFC-assign writer is closed off.

---

### Scope 2 — "Replace FilaBridge" (later direction)

**What it is.** FCC absorbs the one missing capability — a proactive print-monitor loop that detects PRINTING→FINISHED per printer and fires FCC's *existing* parse+deduct pipeline. FilaBridge is decommissioned. **NFC tag *reading* is out of scope** (your OpenPrintTag/SpoolmanScale path writes Spoolman directly). Note that FilaBridge's `nfc.go` is not just a tag driver — it's a scan-session coordinator whose *assignment* logic already overlaps `perform_smart_move`; Scope 2 simply drops it (FCC's assignment path covers it).

**Effort — M (smaller than it looks).** Four pieces, in effort order:
1. **The monitor loop (the only substantial new code).** A daemon thread on a ~30s ticker iterating the printer map, calling the *existing* `get_printer_state` per printer (reuse the `ThreadPoolExecutor` fan-out at [app.py:5256-5314](../../../inventory-hub/app.py)), holding per-printer `was_printing` + `last_job_filename`, and on a finish-edge calling FCC's existing `download_gcode_and_parse_usage` + deduct. **Non-obvious bit:** capture the filename *while printing* — PrusaLink clears job info once idle, so "on idle, read current job" reads empty (FilaBridge stashes it in `currentJobFile[printerID]`; replicate that).
2. **Printer credentials into FCC config.** Move `ip_address`/`api_key`/`toolheads` out of FilaBridge's SQLite into FCC's own store (natural home: the first-class Printer rows in `locations.json`, where L271 Phase 4 already moved `printer_map`). Replace `fetch_printer_credentials` ([prusalink_api.py:29](../../../inventory-hub/prusalink_api.py)) with a config read. **This is the hard dependency** — until it lands, FCC can't reach PrusaLink standalone. (FCC becomes the keeper of printer API keys — a new responsibility.)
3. **Delete the redundant pieces.** `toolhead_mappings` (Spoolman is truth), `print_history` (Activity Log exists), the `/print-errors` round-trip (collapses into FCC's own try/except), the NFC tag layer. Net subtraction.
4. **Keep the printer layer pluggable** — wrap PrusaLink calls behind a thin `get_printer_state / get_completed_job / parse_usage` interface so a future vendor slots in. **Prusa-only today; do not build multi-vendor now.**

**Risk — Moderate.** Central new risk is **exactly-once deduction**: a poll can miss a very short print, or double-deduct if FINISHED persists across ticks. Mitigate by persisting `(printer, toolhead, job-id/filename)` of the last deduct and keying dedup on the *job*, not the state. Secondary:
- `update_spool` runs `_auto_archive_on_empty` ([spoolman_api.py:172-228, invoked at :299-327](../../../inventory-hub/spoolman_api.py)) — a deduct driving remaining ≤ 0 **archives AND clears the spool's location/slot** (it does write an Activity Log line + a `fcc_pre_archive_location` breadcrumb, so it's not fully silent). That would break the binding the monitor relies on; send only `{used_weight}` and keep that discipline.
- MMU wrong-alias deduction — use FCC's existing `_resolve_active_locs_for_printer` dedup.
- Restart amnesia: in-memory `was_printing` is lost on restart mid-print (FilaBridge has the same gap; decide whether to persist).

**Migration steps.** (1) Ship Scope 1 first. (2) Move credentials to FCC config + settings UI **before** the monitor goes live. (3) Build the monitor; extract `_auto_recover_task` ([app.py:5109-5151](../../../inventory-hub/app.py)) into a reusable `parse_and_deduct(printer, filename)`. (4) **Cut over atomically** — stop FilaBridge's monitor the instant FCC's goes live, or a finished print deducts twice. (5) Retire the `/api/fb_*` endpoints + `/print-errors` poll.

---

### Adopt the `doutorinfamous` fork + a mappings endpoint — NOT recommended

**Effort High, breakage High.** The fork is a Snapmaker/Bambu rewrite: `prusalink.go` **deleted**, Moonraker client added, driver defaults to `moonraker` via `COALESCE(driver,'moonraker')`, no `DriverPrusaLink` constant. Migrating your existing SQLite backfills every printer to the Moonraker driver, which **silently breaks Prusa monitoring/auto-deduct** (PrusaLink firmware doesn't speak Moonraker). The wire API still matches FCC's reads so it *looks* compatible — but the protocol behind it is wrong for your fleet. Single maintainer, 0 releases/tags — re-introduces exactly your stated concern. And **no fork fixes the L3 tail** (that's FCC-side).

**Useful crumb, not adoption:** `sargonas`'s small cancelled-print patch (keeps `prusalink.go`) addresses a real gap — usage deducted only on *completion*, not cancellation. Cherry-pick the *idea* if FCC's deduct doesn't handle cancellations (see Open Questions).

**License:** all forks are GPL-3.0. FCC's parser/probe are *independent* implementations, so the absorb is a clean-room reimplementation of a narrow contract — keep it that way (don't transliterate Go → Python).

---

## 5. Roadmap alignment

| Roadmap item | Scope 1 | Scope 2 (absorb) | Fork |
|---|---|---|---|
| **OpenPrintTag + SpoolmanScale** (future, mobile) | Neutral | Neutral | Neutral |
| **Mobile mode (L315)** | Neutral | **Simplifies** — one deployable a phone hits directly | Worse |
| **L25 print-status weight lag** | Neutral | **Unblocks a clean fix** | Neutral |
| **L20 FilaBridge status light (ON HOLD)** | **Dissolves the dot** | **Deletes the bug class** | Worse |
| **L161 Prusa metrics / exporter** | Neutral | **Consolidates the PrusaLink surface** | Worse |
| **L345 dev Spoolman/FilaBridge env** | Neutral | **Halves it** (no dev FilaBridge) | Worse |
| **L292 "Overarching Issue" (complexity)** | Compatible (removes a source) | **In tension** (adds a 4th responsibility) | Worse |

**OpenPrintTag + SpoolmanScale are orthogonal to this decision.** Both are Spoolman-centric: tag/scale → Spoolman REST; FCC reads the same Spoolman. Neither touches printer IPs, PrusaLink, live telemetry, or the toolhead map. They argue *for* FCC owning the Spoolman *write* surface (which it already does) — not for absorbing FilaBridge's telemetry/credential/deduct role. Two facts to bank for the mobile epic:
- **SpoolmanScale already has manual numeric Spoolman-ID entry** via an on-screen numpad (`linkIdLookupAndPatch` PATCHes Spoolman) — your "let the user input a Spoolman ID" feature is largely built.
- **Adding OpenPrintTag to that scale is a firmware/library change, not necessarily a hardware swap.** Its PN532 chip *natively* supports ISO 15693, but the stock `Adafruit_PN532` library + SpoolmanScale firmware implement only ISO 14443A / MIFARE, while OpenPrintTag is ISO 15693 / ICODE SLIX / NFC-Forum Type 5. So it can't read OpenPrintTag *as shipped* — the fix is an ISO-15693 read path in firmware, not (necessarily) a new reader chip.
- **One caution that lands on FCC:** a scale becomes a **third writer** of weight to Spoolman (alongside FCC and FilaBridge auto-deduct), not bound by FCC's `compute_dirty_extras` discipline — extend the reconcile mental model to "physical weight vs computed `used_weight`."

**Where absorbing UNBLOCKS / SIMPLIFIES:**
- **L25 (a decision-neutral quick win — but the mechanism in the buglist note is wrong, see §8).** The lag is real, but it is **not** caused by the printer going idle. The pulse cadence ([inv_core.js:1031-1035](../../../inventory-hub/static/js/modules/inv_core.js)) drops to the 15s/30s bucket based on **user inactivity (`_lastUserActivity`, bumped on keydown/pointerdown) and tab visibility (`document.hidden`)** — never on printer `is_active`. During an unattended print the *user* is idle, so the tab sits in the slow bucket while the deduct fires on FilaBridge's separate clock. A real fix must **detect the PRINTING→non-PRINTING transition in the pulse payload and force a short-cadence tick** (there's no existing printer-state→cadence link to exploit). Owning both the state transition and the deduct trigger in one process (Scope 2) makes this trivial and removes the inter-process race. The widget reads weight from `_pulse_section_printer_status` (now ~[app.py:5233](../../../inventory-hub/app.py); the buglist's `app.py:4056` ref has drifted).
- **L20 / status dot / L324 reconcile** are all artifacts of FilaBridge being a separate process. Scope 1 makes reconcile vestigial; Scope 2 deletes all three. **Don't sink effort into polishing FilaBridge integration before deciding** — you'd be polishing code that absorbing deletes.
- **L292** is the one explicit brake: you flagged 3 internal complexity layers and said "table for now." Scope 2 adds a 4th responsibility, so it should be *phased and deferred*. Scope 1 does **not** add complexity (it removes a source of truth) — fully compatible with the L292 posture.

---

## 6. Recommendation + phased path

**Phase 0 — decision-neutral quick win (now).** Fix **L25** with a one-shot fast-poll triggered by the **printer-state transition in the pulse payload** (not by user activity). Improves today's architecture and builds the exact event hook Scope 2 needs. Confirm the L271 Printer-entity rows are the home for the eventual credential store.

**Phase 1 — Scope 1 (now, high-value/low-risk).** Confirm/disable FilaBridge's `/api/nfc/assign`; repoint `_fb_spool_location` to Spoolman as the single map source; verify the four move paths write Spoolman synchronously first; retire/deprecate L324 reconcile. **Kills the desync class and stops FCC reads from paying FilaBridge's slow `/status` probe.**

**Phase 2 — Scope 2 (later, deferred & phased).** When the L271 Printer-entity work has settled (credentials get a home) and the L292 caution eases — ideally folded into the L315 mobile push if mobile makes a single deployable a hard requirement — build the proactive monitor and decommission FilaBridge. Cut over atomically to avoid double-deduct.

**Fallback.** Keep `needo37`'s archived image **pinned to a specific tag/digest** (not `:latest`) as the do-nothing safety net while Phase 2 is planned. Do **not** adopt `doutorinfamous` — the Moonraker pivot would silently break your Prusa fleet.

---

## 7. Open questions for Derek

1. **Cancelled prints — ✅ ANSWERED + DESIGNED (2026-06-10, see §9).** FCC does NOT handle cancellations today (neither does Derek's FilaBridge build — both bill the full estimate on the printing→idle edge). Now a designed feature: gcode prefix-parse per-tool partial deduction, shippable before Phase 2 by riding the existing pulse probe. Derek wants it.
2. **Filename at finish-edge:** does PrusaLink reliably expose the *just-completed* job's gcode filename the moment state flips to FINISHED, or only *during* the print (forcing the capture-on-PRINTING-edge stash)?
3. **Credential store:** when FilaBridge `/printers` goes away, where do `ip_address`/`api_key` live — folded into the L271 `locations.json` Printer rows, or a dedicated secrets store?
4. **Scope 1 backing store:** OK to use Spoolman `location` (already written on every move) as the map source, accepting its lag characteristics — or stand up a dedicated FCC-side mirror?
5. **NFC-assign route:** confirm nothing uses FilaBridge's `/api/nfc/assign` (the rogue second writer), so it can be disabled for Scope 1 and deleted for Scope 2.
6. **Fast-Fetch on prod:** is the Range fast-path actually succeeding, or silently always falling back to RAM-Fetch? (Your L301 watch item — now FCC's own code at [prusalink_api.py:76-108](../../../inventory-hub/prusalink_api.py).)
7. **indxx upgrade:** does the planned Core One → indxx (8–10 toolhead) upgrade change FilaBridge's role enough that Phase 2 should wait until that hardware settles?
8. **Live progress vs finish-edge:** does the Scope 2 monitor need live printing *progress*, or only the finish-edge deduct (the existing printer-status probe may already cover live state)?

---

## 8. Verification notes (what the adversarial pass changed)

23 load-bearing claims were re-checked against source by independent verifiers. The recommendation stands; these corrections were folded into the doc above:

- **Refuted — "FCC has a line-for-line port of FilaBridge's gcode download" (C3):** only the *parse regex* is shared. FCC's Range fast-path is FCC-original (FilaBridge has none); FilaBridge's 3× exp-backoff retry is not in FCC. FCC still *owns a working* gcode parse+deduct — that's what the absorb argument needs — but it's a reimplementation, not a port.
- **Refuted — "FCC is the only thing that mutates the mapping" (C23):** in the *code*, FilaBridge mutates the map autonomously via `/api/nfc/assign`. Your *workflow* doesn't use it, so the statement holds for your setup — but Scope 1 now carries an explicit precondition to confirm/disable that route (§4).
- **Uncertain — L25 mechanism (C13):** the buglist's "cadence drops when the printer goes idle" is wrong; cadence is driven by *user* inactivity + tab visibility, not printer state. The fix direction was rewritten accordingly (§5/§6).
- **Uncertain — nfc.go framing (C21):** it's a scan-session *assignment coordinator* (overlapping `perform_smart_move`), not just a tag driver. Doesn't change "don't replicate the tag layer," but it's why C23 matters.
- **Uncertain — OpenPrintTag barrier (C22):** firmware/library, not necessarily a hardware swap (PN532 supports ISO 15693 natively).

---

## 9. Cancelled-Print Partial Deduction — Locked Design (2026-06-10)

*Promoted from Open Question #1. Designed via two research workflows (cancelled-print mechanism — 20 agents; metrics + Connect legality — 8 agents) + a deep-read of `needo37/filabridge` and the `sargonas` fork. **Method locked; ready to build.** Derek wants this feature: partial usage on cancels currently goes unrecorded, so spool weight drifts and he has to re-weigh after several cancels.*

**Problem.** Neither FCC nor Derek's FilaBridge build deducts filament on a CANCELLED/aborted print — only on completion. The gcode `filament used [g]` footer is the FULL-job estimate, so a cancel must NOT deduct that total (massive over-deduct); we have to compute the ACTUAL partial grams **per toolhead**.

### 9.1 Data-availability findings (what's reachable, what isn't)
- **Local PrusaLink API exposes NO measured consumed-filament figure.** Confirmed 3 ways (Prusa OpenAPI `StatusJob`; firmware `basic_gets.cpp`; pyprusalink). `/api/v1/job` `file.meta['filament used [g]']` (+ per-tool arrays) is the SLICER ESTIMATE and doesn't shrink with progress. `progress` = `sd_percent_done` = gcode FILE-BYTE position (0–100).
- **Firmware-measured total is cloud-only AND a lifetime length odometer (meters).** `render.cpp` `"filament"=params.filament_used` = `Odometer_s::get_extruded_all()` (EEPROM, not per-print, not grams), emitted only to Prusa Connect. Connect derives per-print by differencing it server-side; the LAN endpoints never expose it.
- **Buddy metrics channel (buglist L150 / `prusa_exporter`) — NO-GO as a measured source.** `app_metrics.cpp` catalog has X/Y/Z position only (no `pos_e`/E-axis), `sdpos` (byte progress = same proxy we already have), `active_extruder` (index), and `filament` = TYPE-name STRING. No `filament_used`/`extruded_mm` anywhere. Transport is plain UDP syslog (port 8514 — ingestible without Prometheus/Grafana) but there is no useful payload, and enabling it needs an on-printer touchscreen confirm (M334/M340, off-by-default, dev-flagged). Cost moderate, benefit zero.
- **Prusa Connect cloud API — RISKY, and XL-blind.** No sanctioned own-data API; only the undocumented/unversioned web-app `/app/.../material_quantity` endpoint authed by a browser session cookie (`_sleek_session`, no token refresh). Explicit ToS anti-scraping clauses (Connect/Link T&C §5.3; Website ToS Art 9.1/9.3), no personal-use automation carve-out. HA deliberately uses local PrusaLink, not Connect. Community precedent works but warns it's unversioned + "probably won't work for toolchanger/INDX printers" (clusters by material → breaks the untouched-head invariant on the XL too). **Decision: stay local-only;** at most a far-future opt-in, off-by-default, fail-soft, never-redistribute side-channel — and even then it can't serve the XL.

### 9.2 Method — LOCKED: gcode prefix-parse (2-rung ladder)
**Hard multi-tool invariant (Derek):** never one global progress-scale across heads; an un-engaged toolhead deducts exactly **0**. Flat `estimate[t] × global_progress` deducts filament a never-engaged head never extruded (e.g. a top-band color tool on a cancel at 40%) — the `sargonas` fork does exactly this; fine for single-tool MK, WRONG for the XL.

- **Rung 1 (primary) — gcode prefix-parse.** Because `progress` IS byte-position, parse the gcode from byte 0 to `progress × filesize`, track the active tool via `Tn`, accumulate per-tool extrusion `E` (honor M82/M83 absolute/relative + G92 E0 resets), convert mm→g per filament diameter (1.75) + density. Yields per-tool actual grams at the cancel point; an un-reached tool sums to 0 NATIVELY. Subsumes global-scaling and removes the byte≠filament-density bias on ALL printers. **The only local method that satisfies the invariant on the XL.** FCC already downloads + parses the gcode for the completed path, so half the machinery exists.
- **Rung 2 (fallback) — estimate × progress.** When the gcode isn't parseable/available. NO per-tool breakdown → on the XL it CANNOT keep an untouched head at 0, so on multi-tool jobs it must surface **LOW-CONFIDENCE** (activity log + toast), never silently emit a fabricated per-tool figure.

mm→g: `g = (mm/1000) × π × (d/2)² × ρ`, d = 1.75 mm, ρ from filament density (PLA ≈ 1.24 g/cm³).

### 9.3 Detection
Probe `GET /api/v1/status` → `printer.state` (already in `_probe_printer_state`). Enum: IDLE/BUSY/PRINTING/PAUSED/FINISHED/STOPPED/ERROR/ATTENTION/READY. Cancel = STOPPED (no separate ABORTED); ERROR = failed; FINISHED = completion; PAUSED = not terminal.
- Use the RAW `state` string, **not** `is_active` (eject/swap-during-pause depends on `is_active` semantics — don't change them).
- **LATCH on every active poll** — the job block + progress are torn down at the STOPPED edge while the gcode only un-404s *post*-STOPPED (Prusa-Link-Web #431, Buddy #4744). Per printer stash: `last_job_filename`, `last_job_id`, `last_progress` (monotonic max), `last_file_meta['filament used [g]']`.
- On the terminal edge (`→ STOPPED/ERROR`, or bare IDLE with last_progress < 0.95 = cancel; FINISHED or IDLE ≥ 0.95 = completion) fire the deduct using the **latched** values.

### 9.4 Exactly-once
Persistent `data/print_deduct_ledger.json` keyed on `(printer_name, job_id)` — Spoolman's `/use` is NON-idempotent (issue #608, 2.6× on retry) and the in-memory latch is lost on restart. On a terminal edge: resolve job_id → if in ledger, skip; else deduct, write ledger, clear latch. `job_id == 0` → deduct once from the in-memory edge, don't write ledger. Bound the ledger (last N per printer) like `_evict_old_fb_snapshots`.

### 9.5 Integration — rides the existing pulse probe (no Phase-2 daemon needed yet)
`_pulse_section_printer_status` already iterates the printer_map and calls `get_printer_state` per printer on every heartbeat via a `ThreadPoolExecutor`. Hook a new `_track_print_edge(name, state_info, fb_url)` inside `fetch_for_printer`; on the terminal edge call a NEW reusable `parse_and_deduct(printer, filename, usage_scale, file_meta)` extracted from `_auto_recover_task` / `api_fb_aggressive_parse` (the extraction §4 Scope 2 step 3 already calls for). Reuse the deduct loop + MMU-alias dedup (`_resolve_active_locs_for_printer` + `processed_positions`) unchanged except for the per-tool prefix-parse amount.
- **Needs the Phase 0 fast-poll** (printer-state transition forces a short-cadence tick) so a short cancel isn't missed between 15 s/30 s idle-bucket ticks — same hook as L25, now with two consumers.
- **First ship = STOPPED/ERROR only** (additive; leave FINISHED to FilaBridge until the Phase-2 atomic cutover, else completed prints double-deduct). Covers exactly the gap FilaBridge never had.

### 9.6 Archive-on-empty hazard
Send ONLY `{used_weight}` to `update_spool` (never bundle `initial_weight`/`location`/`extra`); do NOT route through `/api/spool/update` (it runs `_auto_archive_on_empty`/`_auto_unarchive_on_refill` on `initial_weight`). The existing deduct sites already do this — preserve it in `parse_and_deduct`. Deduction is uni-directional (no `_auto_unarchive_on_refill`). Note: today's error-recovery path already over-deducts the FULL estimate on a cancel (~10× on a 10 % cancel) — scaling is a strict improvement.

### 9.7 UX
For cancels, PREVIEW the computed per-tool partial and let Derek confirm/nudge before it writes (the WeightEntry "preview the used_weight before submit" pattern) — automating the manual Connect-reading he does today.

### 9.8 Build slices (dependency order) — STATUS 2026-06-10
Branch `feature/filabridge-absorb-phase-0-1`. The whole backend is done + simulation-tested; only the live-pulse detection wiring and the UI remain.

| # | Slice | Size | Status |
|---|-------|------|--------|
| 0 | Phase 0 fast-poll (printer-state transition → short-cadence tick; also fixes L25) | S | ✅ `881f3d7` (8 tests) |
| 1 | Phase 1 / Scope 1 (`_fb_spool_location` → Spoolman) | S | ✅ `20f8802` (89 FB-seam tests) |
| 3 | gcode prefix-parse (`prusalink_api.parse_partial_filament_usage`, per-tool E-axis) | M | ✅ `0a9ea6c` (9 tests) |
| 4 | Exactly-once ledger (`print_deduct_ledger.py`) | S | ✅ `10abe33` |
| 2b | Cancel-deduct backend (`_apply_usage_to_printer` extract + `deduct_cancelled_print` orchestrator + `download_gcode_content`) | M | ✅ `10abe33` (4 sim tests) |
| 2a | **Cancel DETECTION + latching** — `PRINT_TRACKER` in `_pulse_section_printer_status`/`fetch_for_printer` (~app.py:5287-5310): latch `filename`/`job_id`/monotonic `progress` while PRINTING via a **`/api/v1/job` fetch** (`get_printer_state` lacks them); on the →STOPPED/ERROR edge fire `deduct_cancelled_print(...)` **async** (don't block the heartbeat). **STOPPED/ERROR-only first ship** (FINISHED stays with FilaBridge until Phase-2 cutover). Extend the sim harness to drive the edge through the pulse. | M | ⏳ TODO |
| 5 | Preview-and-confirm UX on a cancel (WeightEntry preview pattern) | M | ⏳ TODO |

# Group 22: FilaBridge Phase-2 — Detection & Deduct-Attribution Follow-ups

**Branch name (when started):** `feature/filabridge-phase2-followups` (or continue on `feature/filabridge-phase2-creds-gate`)
**Estimated effort:** ~5–8 hours (22.1+22.2 share one fix; 22.3 is an investigation)
**Risk:** **MEDIUM-HIGH.** Touches the live print-deduct path (`_cancel_monitor` / `_track_print_edge` / cancel-review pipeline / completion deduct) — the system that writes real weights to Spoolman. Validate against real `.bgcode` + live printer state, not just unit tests. See `[[feedback_adversarial_review_runtime_lens]]` and `[[project_filabridge_absorption_active]]`.

> **Status: PARTIAL** 2026-06-13 — **22.1 + 22.2 DONE** on `feature/filabridge-phase2-creds-gate` (`54f271c` "detection-layer hardening", **UNMERGED**): instant-ack log on the STOPPED edge + adaptive poll (10s busy / 30s idle) + the shared **ambiguous-IDLE review** (latched in-progress job → IDLE/READY without an observed terminal state routes to the cancel-review pipeline flagged "couldn't confirm", computed at retained progress, never auto-deducts; also catches the ATTENTION-screen hard-reset case). 106 backend + 5 frontend tests green, live-verified on dev. **⏳ 22.3 OPEN** (mid-print spool-swap apportionment — the investigate item; untouched). Filed 2026-06-13 by `/refresh-groups`; all three were field-observed running the new FCC-native monitor live. **NOT compute bugs** — the deduct itself worked end-to-end on real XL multi-tool bgcode. Part of the FilaBridge absorption epic.

## Why these three are one group

All three are about **what the print monitor observes and how it attributes usage** — they share the `_cancel_monitor` daemon, `_track_print_edge` / `_on_cancel_edge`, the `print_tracker_store` latch, and the cancel-review pipeline. 22.1 and 22.2 are **literally the same root cause + fix** (a latched in-progress job reaching IDLE without an *observed* terminal state must not be silently dropped). 22.3 is the adjacent attribution gap (full footer dumped on one spool).

## Items

### 22.1 — Cancel detection: no instant ACK + fast cancel→restart slips the 30s poll — ✅ DONE 2026-06-13 (`54f271c`, unmerged)
**Buglist:** line 3. Two distinct gaps from a real XL cancel:
- **(1) No instant ACK** — the cancel-edge action runs async (download + decode `.bgcode` → prefix-parse → resolve spools → write review) with NO log at the instant the STOPPED edge fires. On a slow XL bgcode download the user sees ~30–60s of silence. **Fix (one line, high value):** log an immediate `🛑 Cancel detected on {printer} (~{pct}%) — computing the partial…` in `_on_cancel_edge` BEFORE the async compute.
- **(2) Fast cancel+restart misses the 30s poll** — `_cancel_monitor` polls every 30s; if the cancel screen is cleared + a new print started inside one poll window, an instance whose poll phase doesn't sample STOPPED never sees the edge (`PRINTING→IDLE/new-job` → no review). **CONFIRMED prod data 2026-06-13:** same shared XL cancel — DEV's poll landed on STOPPED → fired (12.53g/3 spools); PROD's poll landed `PRINTING→IDLE` → silently dropped. Prod `print_tracker_latch.json` = `{state:"IDLE", filename:"/usb/RACOON~1.BGC", job_id:693, progress:0.26}` (a RETAINED in-progress job at IDLE, no fire/warning). Aggravated by Derek's printer-side "starts the file twice" quirk (very short STOPPED window).
**Fix direction:** **same as 22.2** — a latched in-progress job that reaches IDLE without an OBSERVED STOPPED/FINISHED must NOT be silently dropped: download the now-unlocked file → compute → route to the cancel-review pipeline flagged "couldn't confirm what happened" (retain `progress:0.26` as the hint). **Mitigations to weigh:** shorter poll; a state-change fast-poll BURST in the daemon (mirror the Phase-0/L25 frontend fast-poll); or persist+compare last-seen state across ticks so a `PRINTING→(unseen STOPPED)→IDLE` not matching a clean completion surfaces a review.

### 22.2 — Completion silently missed when the printer power-cycles before FCC observes FINISHED — ✅ DONE 2026-06-13 (`54f271c`, unmerged — same change as 22.1)
**Buglist:** line 5. If a Connect-completed print's printer is powered OFF at the finish screen within ~30s of finishing (before a monitor tick lands on FINISHED) and later powers back ON to IDLE, FCC only ever sees `PRINTING → offline → IDLE` — genuinely ambiguous (identical to cancel-then-power-off), so it does NOT auto-deduct. Today `_track_print_edge` handles this SILENTLY (no fire, no warning) = a lost completion with no nudge. (If FCC caught even ONE FINISHED tick first, the persistent deferred-fetch recovers it across the power-cycle — so this is only the <30s fast-power-off window.)
**Fix direction (shared with 22.1):** on a latched `PRINTING → offline → IDLE/READY` transition with NO observed terminal state, DON'T silently drop and DON'T blind-deduct (FilaBridge's indiscriminate printing→idle billing is exactly what over-deducts cancels). Instead download the now-unlocked file, compute the footer, and route it through the EXISTING cancel-review pipeline as a pending review flagged "couldn't confirm completed vs cancelled — review" (last-latched progress as a confidence hint). Safe (no phantom auto-deduct), surfaced, one-click.
**→ Do 22.1(2) + 22.2 together** — one "ambiguous terminal state → review" path covers both.

### 22.3 — Mid-print spool swap / run-out is not apportioned by the deduct (buglist line 7)
**Buglist:** line 7. Both FCC's completion deduct AND FilaBridge deduct the FULL per-tool footer to whatever spool is mapped to that toolhead AT completion time. If a spool runs out mid-print (runout sensor / M600) and is replaced to finish, the REPLACEMENT eats the whole tool's usage and the run-out spool records 0g — both wrong. **Pre-existing** (FilaBridge has the identical gap; NOT a Phase-2 regression).
**Investigation angles:**
- **(a) DETECT the swap** — runout/M600 sends the printer to PAUSED/ATTENTION (the cancel-monitor already holds the latch as "still in-progress"), and an FCC eject/load changes the toolhead's mapped spool; capture that swap event + which spool was on before vs after.
- **(b) APPORTION by the swap boundary** — reuse the cancel prefix-parse (`parse_partial_filament_usage`) to compute per-tool grams up to the progress/byte position at the swap; charge that to the run-out spool, the remainder to the replacement (needs progress % captured at swap time).
- **(c) MINIMUM VIABLE** — if a toolhead's mapped spool CHANGED during a print, flag that completion's deduct for manual review instead of dumping the full footer on the current spool.
**Hard part:** capturing the swap point + per-segment attribution; the prefix-parse machinery exists, it needs the swap-event hook.

## Recommended order
1. **22.1(1)** instant-ACK log (one line, ship immediately).
2. **22.1(2) + 22.2** the shared "ambiguous terminal state → cancel-review" path (the real fix; covers the prod-missed-cancel + the power-cycle-missed-completion).
3. **22.3** spool-swap apportionment — start with (c) minimum-viable (flag for review), then assess (a)+(b) if Derek wants real per-segment attribution.

## Out of scope / do NOT do without live repro
- Blind-deduct on ambiguous transitions (that's the FilaBridge over-deduct behavior we're replacing).
- Changing `parse_partial_filament_usage` math — it's real-XL-validated; 22.3 needs a swap-event hook feeding it a boundary, not a parser change.

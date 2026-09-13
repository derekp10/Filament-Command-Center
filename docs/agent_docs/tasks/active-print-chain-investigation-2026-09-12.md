# Active-print move pipeline — verified investigation (2026-09-12)

Evidence record for the fixes on fix/active-print-chain-confirm and the follow-up items filed in Feature-Buglist.md the same day. Produced by a 7-agent workflow run against dev HEAD cff5707 (line numbers refer to that tree): five investigators (I1 Quick-Swap Return vs the auto-deploy chain, I2 an audit of every consumer that trusts a move/eject result, I5 how a second spool lands on a toolhead, I3 the eject re-confirm race, I4 the bulk-move-timeout eject report) and two batched adversarial verifiers. Everything ran hermetically or read-only against dev: every non-GET in the browser runs was intercepted. The scratch tests and scripts it cites were session-temporary and are not kept; the claims, outputs and verdicts below are copied verbatim from the agents' structured results.

## Verdict summary

| id | verdict | severity after review | finding |
|---|---|---|---|
| I1-01 | CONFIRMED | red | On an idle printer, Return is undone: the auto-deploy chain puts the spool straight back on the toolhead and still reports return_done |
| I1-02 | CONFIRMED | red | Forwarding confirm_active_print into the chain (planned bug-A fix) makes Return undo itself mid-print too, so it must ship together with or after I1-01 |
| I1-03 | CONFIRMED | orange | Return with a physical_source box but no slot auto-picks a slot bound to a DIFFERENT toolhead and deploys there (ejecting its spool; two spools on that head mid-print once the confirm is forwarded) |
| I1-04 | CONFIRMED | orange | Return reports return_done plus a SUCCESS log even when the box write fails |
| I1-05 | CONFIRMED | orange | Moves with no slot into a multi-slot bound box (Force Location, buffer location-scan) auto-deploy onto a toolhead, and during a print they skip the confirm entirely |
| I1-06 | CONFIRMED | info | The active-print pre-flight checks slot bindings even when auto_deploy=False |
| I1-07 | CONFIRMED | red | The DRYER and GENERIC move branches pop() the ghost trail, but update_spool's merge re-sends it, so the stale ghost persists (and a fixed Return exposes it) |
| I1-08 | CONFIRMED | yellow | Undo after a chained move is two steps (the first CMD:UNDO completes the Return), and undoing a Smart Load never puts the ejected spool back |
| I1-09 | CONFIRMED | yellow | Quick-Swap Deposit into a bound slot can never succeed during a print: the backend always asks for a confirm the deposit never sends |
| I1-10 | PLAUSIBLE | info | An E2E cleanup relies on Return, so on live dev it silently leaves the swapped spool on the toolhead |
| I2-BASE-A | CONFIRMED | info | Baseline A: the auto-deploy chain drops confirm_active_print and claims a deploy it did not make |
| I2-BASE-B | CONFIRMED | info | Baseline B: the Smart Load resident eject treats truthy refusals and False as success |
| I2-01 | CONFIRMED | red | POST /api/quickswap/return re-deploys the returned spool back onto the toolhead, while reporting return_done |
| I2-02 | CONFIRMED | orange | Quick-swap Return can act on a GHOST resident, pulling a spool off a different toolhead |
| I2-03 | CONFIRMED | red | Dryer and Room/Cart (generic) moves 'clear' the ghost trail with dict.pop, which update_spool treats as KEEP, so physical_source survives |
| I2-04 | CONFIRMED | orange | clear_location (Eject-all) answers success:true while ejecting nothing |
| I2-05 | CONFIRMED | orange | execute_bulk_move trusts a fail-open readback over the engine's own failures map |
| I2-06 | CONFIRMED | orange | Slot-QR / deposit assignment reports a load and drops the spool from the buffer when the write was rejected |
| I2-07 | CONFIRMED | orange | POST /api/quickswap logs and returns quickswap_done when the toolhead write was rejected |
| I2-08 | CONFIRMED | orange | Frontend 'status === success' consumers claim success and mutate the buffer despite per-spool failures |
| I2-09 | CONFIRMED | orange | A failed slot unseat is not recorded, so the slot is double-booked while the move reports a clean success |
| I2-10 | CONFIRMED | yellow | Location delete reports success and orphans spools when the unassign writes fail |
| I2-11 | CONFIRMED | yellow | perform_undo reports success when restore writes fail; the frontend ignores the undo response |
| I2-12 | CONFIRMED | orange | Eject-all never handles require_confirm and never sends confirm_active_print, so a printing toolhead shows 'Cleared!' |
| I2-13 | CONFIRMED | yellow | deleteLoc ignores the 409 active-print refusal and the cascade errors |
| I2-14 | CONFIRMED | yellow | Quick-Swap deposit drops the active-print confirm the user just gave, then reports 'Deposit failed' |
| I2-15 | PLAUSIBLE | yellow | Force Location Override has no active-print path: no probe, no confirm flag, refusals shown as errors |
| I2-16 | PLAUSIBLE | orange | Candidate for the eject no-ops: chained Bootstrap confirms can be silently dropped, leaving an invisible armed confirm |
| I2-17 | CONFIRMED | yellow | Moving a spool OFF a printing toolhead is never guarded (single-move path) |
| I2-18 | REFUTED | info | Weigh-out archive: the fire-and-forget force_unassign can silently leave an archived spool on a printing toolhead |
| I5-1 | CONFIRMED | red | Derek's flow confirmed: toolhead view -> assign (deposit card or LOC-QR scan) -> endpoint -> Smart Load bug B -> two spools, reported as success |
| I5-2 | CONFIRMED | red | Quick-Swap on the toolhead view ALWAYS double-occupies during a print (the endpoint hard-codes confirm_active_print=True) |
| I5-3 | CONFIRMED | red | A toolhead-valued ghost trail makes Smart Load 'eject' a spool from ANOTHER head back onto the target, giving two spools on an idle printer. Not covered by the planned fixes. |
| I5-4 | CONFIRMED | orange | Eject return-home lands on an occupied toolhead (no destination occupancy check) |
| I5-5 | CONFIRMED | orange | Targeting a Printer row (e.g. dev 'XL', Max 0) needs no confirm; idle it mass-ejects every toolhead of that printer, and during a print it stacks spools on the row |
| I5-6 | CONFIRMED | orange | Idle box-slot assign chains onto a bound toolhead whose resident has no home, giving two spools plus an 'auto_deployed_to' claim |
| I5-7 | CONFIRMED | orange | Fix-ordering hazard: shipping fix A (forward confirm into the chain) without fix B converts the silent skip into double occupancy |
| I5-8 | CONFIRMED | yellow | /api/smart_move places several spools on one toolhead; the L124 single-occupancy guard exists only in the frontend |
| I5-9 | CONFIRMED | orange | Auto-unarchive restores a spool onto the toolhead it was archived from, even if that head is now occupied |
| I5-10 | CONFIRMED | yellow | perform_undo restores a spool's origin location with no occupancy check |
| I5-11 | PLAUSIBLE | yellow | The wizard and Force Location offer Printer-type rows; wizard edit writes location straight to Spoolman, bypassing Smart Load and the active-print guard |
| I5-12 | CONFIRMED | red | Quick-Swap Return to a bound slot immediately re-deploys the same spool back onto the toolhead |
| I5-13 | CONFIRMED | yellow | Consequence, deduct: with two direct spools on a head NEITHER spool is charged, and spool-swap detection goes blind |
| I5-14 | CONFIRMED | yellow | Consequence, deduct: a toolhead ghost trail charges a spool that is on a different head, double-charging it |
| I5-15 | CONFIRMED | yellow | Consequence, eject: acts on the clicked spool but detaches the single-slot box that the OTHER, still-loaded spool uses |
| I5-16 | CONFIRMED | info | Consequence, eject UX on a printing head: a homeless resident needs 3 round-trips with confirms chained from inside confirm callbacks, and the 2nd message is wrong |
| I5-17 | PLAUSIBLE | info | Consequence, displays: the Location Manager shows both cards, the printer-status bar shows only items[0], Quick-Swap Return acts on residents[0], and an idle Smart Load self-heals |
| I5-18 | CONFIRMED | info | Eject All (clear_location) reports homeless spools as ejected although perform_smart_eject refused |
| I3-1 | CONFIRMED | orange | Active-print re-confirm after an eject is silently dropped: Bootstrap show() is a no-op while the first confirm is still fading out |
| I3-2 | CONFIRMED | orange | A swallowed re-confirm leaves a live confirm_active_print:true callback in state.pendingConfirm, and a later CMD:CONFIRM scan fires it with no dialog on screen |
| I3-3 | CONFIRMED | orange | The true-unassign re-prompt after the active-print confirm is a second hop of the same race, with an even faster backend answer |
| I3-4 | CONFIRMED | yellow | A refused eject (REQUIRE_CONFIRM) has already auto-detached single-slot boxes from the toolhead |
| I3-5 | PLAUSIBLE | info | Why 'navigate away and come back' appeared to fix it: nothing in the view was wedged; the backend answer changed |
| I4-1 | CONFIRMED | orange | Chained eject confirm is silently dropped when the backend's require_confirm arrives during the first confirm's hide fade (Bootstrap show() ignored while transitioning) |
| I4-2 | CONFIRMED | orange | A dropped re-prompt leaves a live pendingConfirm that a later CMD:CONFIRM scan fires, ejecting from a printing toolhead with the active-print override and no dialog shown |
| I4-3 | PLAUSIBLE | info | The bulk-move timeout does not affect slot-card eject: all candidate client states behave like the control |
| I4-4 | PLAUSIBLE | info | Returning to the window after a long wait: the first click is absorbed by #focus-guard (by design) — a one-shot confounder |
| I4-5 | CONFIRMED | yellow | Quick-Swap 'Slot N' card eject posts the BOX as location and refreshes the box's contents while the toolhead view is on screen |

## Backend

### I1 — return-vs-autodeploy

Yes: the auto-deploy chain undoes /api/quickswap/return, and I proved it by driving the real route in a hermetic scratch test. That test used the real perform_smart_move, update_spool, extras merge and ghost matcher; only the Spoolman HTTP calls were faked. When the printer is IDLE, the spool ends up back on the toolhead on both the physical_source path and the first_binding path. The response still says return_done, the toast says 'Spool -> box:slot', the Activity Log says 'Auto-deployed ... -> XL-3' plus 'Return ... SUCCESS', and two undo records are pushed. While the printer is PRINTING, the Return only works today by accident: the chain drops the confirm (bug A), so the spool stays in the box, but the log and `auto_deployed_to` still claim a deploy. Once confirm_active_print is forwarded into the chain (the planned bug-A fix), Return is undone mid-print as well. Worse, when the spool's physical_source has no slot, the auto-slot picker can choose a slot bound to a DIFFERENT toolhead. Return then deploys onto that head: idle, it ejects that head's spool; with the confirm forwarded during a print, bug B leaves TWO spools on it. Simulating Return with auto_deploy=False fixed every case (the R1 pin fails today and passes with the fix). Paths that do NOT go through the chain (proven): perform_smart_eject's return-home, perform_undo, force_unassign (weigh-out archive). Bulk move already passes auto_deploy=False (code-trace plus existing pins). Deploy is intended for deposit, slot-QR and Location Manager slot assign, and forwarding the confirm fixes them during a print. Moves with no slot into a multi-slot box are a separate problem: Force Location and a buffer location-scan pick a slot only AFTER the active-print pre-flight, so they can deploy or eject with no prompt. The same scratch run also showed three things. The DRYER and GENERIC branches pop() physical_source, but update_spool's merge re-sends the old value, so the ghost trail survives. Undo of a Smart Load never restores the ejected spool. Return reports success even when Spoolman rejects the write. The repo-write tripwire recorded 0 write attempts and no dev data was touched. Note: inventory-hub/tests/test_universal_fallback.py was modified in the working tree at 19:48:38 by someone else, before my first scratch write at 19:57:13; logic.py and routes_bindings.py are unchanged, so all line numbers below are valid.

#### I1-01 — On an idle printer, Return is undone: the auto-deploy chain puts the spool straight back on the toolhead and still reports return_done

*Severity red → **red** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** api_quickswap_return calls perform_smart_move(found_box, [sid], target_slot=found_slot, origin='quickswap_return', confirm_active_print=True) and leaves auto_deploy at its default of True. The returned slot is bound to the same toolhead: always on first_binding, and on physical_source whenever the spool got there by auto-deploy. So the chain re-runs perform_smart_move(toolhead) and the spool lands back on the toolhead. The response is still return_done, the success toast still fires, and two undo records are pushed.

**Evidence.**

- routes_bindings.py:656-659 (no auto_deploy argument); logic.py:343 signature default auto_deploy=True; logic.py:692-715 chain; routes_bindings.py:604-628 slot selection
- Scratch test Q1|S1_physical_source|idle|today: final {240: location 'XL-3', physical_source 'LR-MDB-1', physical_source_slot '3'}; response {'action':'return_done','box':'LR-MDB-1','slot':'3','source':'physical_source','smart_move':{'auto_deployed_to':'XL-3','failures':{},'status':'success'}}
- Same case, Activity Log: ['INFO: 📦 #240 -> Dryer LR-MDB-1 [Slot 3]', 'INFO: 🖨️ #240 -> XL-3', 'SUCCESS: ⚡ Auto-deployed Spool #240 — S240 → XL-3 (source: LR-MDB-1:SLOT:3)', 'SUCCESS: ↩️ Return: Spool #240 from XL-3 → LR-MDB-1:SLOT:3 (original source)']; undo_stack: two records (quickswap_return, then auto_deploy_from_quickswap_return)
- Q1|S2_first_binding|idle|today: same result, 240 back on XL-3, log '(first bound slot)'
- Q1|round_trip|idle|today: a real deposit into LR-MDB-1:3, then Return. after_deposit == after_return == {location 'XL-3', physical_source 'LR-MDB-1', physical_source_slot '3'}; return_calls = [quickswap_return (auto_deploy True, confirm True), auto_deploy_from_quickswap_return -> XL-3 (auto_deploy False, confirm False)]
- test_seed_S1_is_what_a_real_forward_autodeploy_leaves PASSED: the S1 starting state is exactly what a real forward auto-deploy leaves
- Frontend success toast `↩️ Spool #N → box:SLOT:slot` at inv_quickswap.js:570-572 keys only on action === 'return_done' (code-trace)
- Every existing Return test mocks perform_smart_move, so none could see the chain: tests/test_return_and_breadcrumb.py:65,99,135; tests/test_l316_charact_bindings_errors.py:224-237

**Proof.** PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8 C:/Python314/python.exe -m pytest test_return_vs_autodeploy.py -p no:cacheprovider -q --offline -s, run from the scratch dir: 53 passed, 6 xfailed; tripwire: 0 writes attempted under the repo. The route ran through app_core.app.test_client(); app.py was not imported. The real update_spool, _merge_extras_with_existing and _build_location_match ran; only requests.patch, _get_raw_extras, get_spool and get_all_spools were faked, plus the PrusaLink probe, config and locations.json.

**Fix direction.** routes_bindings.py:656-659: pass auto_deploy=False. Return means 'park it back in its box', never 'load it'. Keep confirm_active_print=True, or apply I1-06. Update the exact-kwargs pin at tests/test_l316_charact_bindings_errors.py:236-237 (mv.assert_called_once_with(... confirm_active_print=True)) deliberately; it fails once auto_deploy=False is added. tests/test_return_and_breadcrumb.py's fake_move takes **kwargs and is unaffected.

**Regression test.** A new tests/ file shaped like scratch test_r1_return_is_not_redeployed, parametrized over S1_physical_source / S2_first_binding / S3_source_without_slot and idle / printing. POST /api/quickswap/return {toolhead:'XL-3'} through the real route and the real perform_smart_move, with an HTTP-level fake Spoolman. Assert: spool location == 'LR-MDB-1'; the spool is not direct or ghost on XL-1 or XL-3; 'auto_deployed_to' not in body['smart_move']; no 'Auto-deployed' line in state.RECENT_LOGS; perform_smart_move called exactly once, with origin 'quickswap_return'; in S3, the bystander #99 stays on XL-1. Verified: xfail(strict) on today's code for all 6 cases, passes under the simulated auto_deploy=False fix.

**Verifier.** Re-read routes_bindings.py:656-659: no auto_deploy argument is passed, the default is auto_deploy=True (logic.py:343), and the chain runs at logic.py:694-707. Re-ran I1's file: 53 passed, 6 xfailed, tripwire 0. Re-proved it with my own harness, which uses the real _build_location_match via get_all_spools and omit-means-keep extras. test_V2 output: HTTP 200 {'action': 'return_done', ... 'auto_deployed_to': 'XL-3'}; final {240: ('XL-3', 'LR-MDB-1', '3', '')}; writes [(240, 'LR-MDB-1'), (240, 'XL-3')]; undo records ['quickswap_return', 'auto_deploy_from_quickswap_return']. The Return button reaches this route (inv_quickswap.js:562-572). git: Return 965035a (2026-04-20) predates the centralized chain 47c51d5 (2026-04-21), which suggests a regression (inference).

**Corrections.** Real-world reach is stronger than stated. A read-only GET of dev Spoolman plus dev data/locations.json shows every loaded XL head on dev is in this exact state today: 57@XL-1 ghost LR-MDB-1:1 (bound XL-1), 196@XL-2 LR-MDB-1:2, 134@XL-3 LR-MDB-1:3, 242@XL-4 LR-MDB-2:1, 230@XL-5 LR-MDB-2:2. Return is a no-op round trip for all five (analysis in verify-backend/dev_data_analysis.txt).

#### I1-02 — Forwarding confirm_active_print into the chain (planned bug-A fix) makes Return undo itself mid-print too, so it must ship together with or after I1-01

*Severity red → **red** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** Return always passes confirm_active_print=True. Today, during a print, the chain drops that confirm and refuses. The spool therefore stays in the box, but only by accident, and the log and auto_deployed_to still falsely claim a deploy. With the confirm forwarded, the chain deploys the spool back onto the printing toolhead, so Return is undone mid-print. Landing the planned chain fix before Return gets auto_deploy=False turns a lying-log bug into a Return that yanks spools during a print.

**Evidence.**

- routes_bindings.py:650-659 (confirm_active_print=True, 'because the user already saw the warning')
- Q1|S1_physical_source|printing|today: final 240 location 'LR-MDB-1' container_slot '3'; response smart_move.auto_deployed_to 'XL-3'; log includes 'SUCCESS: ⚡ Auto-deployed Spool #240 ... → XL-3' although nothing deployed
- Q1|S1_physical_source|printing|confirm_forwarded: final 240 location 'XL-3'; log '🖨️ #240 -> XL-3' + 'Auto-deployed' + 'Return ... SUCCESS'; views XL-3 [(240,'','direct')], LR-MDB-1 [(240,'3','ghost')]
- Q1|S2_first_binding|printing|confirm_forwarded and Q1|S4_non_box_source|printing|confirm_forwarded: both end with 240 on XL-3
- Q1|*|printing|fix_return_auto_deploy_off (confirm forwarded AND auto_deploy=False): 240 in LR-MDB-1, only 'INFO 📦' + 'Return SUCCESS' logged, one undo record

**Proof.** The confirm_forwarded variant is a monkeypatched stand-in for logic.perform_smart_move inside the scratch test. It sets the chained call's confirm_active_print to the outer call's value and changes nothing else. logic.py was not edited.

**Fix direction.** Merge Return's auto_deploy=False (I1-01) in the same change as, or before, the chain confirm-forwarding. Run the R1 pin in the same commit.

**Regression test.** test_r1_return_is_not_redeployed[*-printing-*] run against the branch that forwards the confirm: the spool must still end in the box, and perform_smart_move must be called only once.

**Verifier.** routes_bindings.py:658 hard-codes confirm_active_print=True, so any forwarding of the confirm into logic.py:703-707 carries it into the redeploy. In my rerun, I2's simulation test_quickswap_return_after_fix_A_would_redeploy_onto_a_PRINTING_toolhead FAILED as intended, and I1's *-printing-confirm_forwarded cases passed with 240 ending on XL-3.

**Corrections.** This is a merge-order constraint on the planned fix A, not a separate live bug. Today, mid-print, the only live defect is the false Auto-deployed log and auto_deployed_to (baseline A). Same content as the second half of I2-01.

#### I1-03 — Return with a physical_source box but no slot auto-picks a slot bound to a DIFFERENT toolhead and deploys there (ejecting its spool; two spools on that head mid-print once the confirm is forwarded)

*Severity red → **orange** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** If physical_source_slot is empty, Return passes target_slot=None. The auto-slot picker then fills the lowest free slot, and the chain reads the binding of THAT slot. That slot can feed a different toolhead than the one being returned from. Return then loads the spool onto a head the user never touched. IDLE: Smart Load ejects that head's loaded spool. PRINTING today: the chain refuses but still logs a false deploy. PRINTING with the confirm forwarded: Return's blanket confirm, which was about XL-3, is applied to XL-1. The resident eject is then refused (bug B, the truthy dict) and #240 is written anyway, leaving two spools on XL-1.

**Evidence.**

- routes_bindings.py:611 found_slot = src_slot or None; logic.py:451-471 auto-slot reassigns target_slot; logic.py:694-697 chain reads bindings.get(str(target_slot)) using the auto-picked slot
- logic.py:426-441 the pre-flight runs BEFORE auto-slot, so it never sees the auto-picked slot's toolhead
- Q1|S3_source_without_slot|idle|today: final {99: 'LR-MDB-2' slot '2', 240: 'XL-1'}; response smart_move.auto_deployed_to 'XL-1'; log ['📦 #240 -> Dryer LR-MDB-1 [Slot 1]', '⚠️ Smart Load: Ejecting #99 from XL-1...', '↩️ Returned #99 -> LR-MDB-2', '🖨️ #240 -> XL-1', '⚡ Auto-deployed Spool #240 → XL-1', '↩️ Return: Spool #240 from XL-3 → LR-MDB-1 (original source)']
- Q1|S3_source_without_slot|printing|confirm_forwarded: views XL-1 [(99,'','direct'), (240,'','direct')]; undo record ejections {99: 'XL-1'} (the refused eject was recorded as an ejection); log shows 'Smart Load: Ejecting #99' with no 'Returned #99'
- Q1|S3_source_without_slot|*|fix_return_auto_deploy_off: 240 in LR-MDB-1 slot 1 as a direct spool, 99 untouched on XL-1
- The Return confirm overlay probes only the source toolhead: inv_quickswap.js:368 (_probeWithTimeout(opts.toolhead)), called with toolhead: th at :815-819 (code-trace)

**Proof.** Scratch matrix S3 × idle/printing × today/confirm_forwarded/fix; results are in results.json and run1.txt / run2.txt.

**Fix direction.** auto_deploy=False on Return (I1-01) removes the deploy and the eject. Secondary Derek decision: should a Return with no recorded slot land unslotted, or in a free slot bound to the same toolhead or unbound, rather than the lowest free slot, which can reserve another head's feed? In the planned chain fix, forward the confirm only when the caller supplied target_slot explicitly (the pre-flight then covered that exact toolhead); never forward it to an auto-picked slot's toolhead.

**Regression test.** test_r1_return_is_not_redeployed[S3_source_without_slot-idle|printing-*]: assert sm.store[99]['location'] == 'XL-1' and that #240 is neither direct nor ghost on XL-1. Add a chain-level pin: perform_smart_move(box, [sid], target_slot=None, confirm_active_print=True) with the auto-picked slot bound to a printing head must NOT write that head.

**Verifier.** routes_bindings.py:611 gives found_slot=None. The auto-slot at logic.py:451-471 runs after the pre-flight (426-442), and the chain reads the auto-picked slot's binding (694-696). My test_V3 (slot 1 bound to XL-1, slot 3 to XL-3): HTTP 200 return_done slot None, auto_deployed_to 'XL-1'; final {240: ('XL-1', ...), 99: ('LR-MDB-2', '', '', '2')}; the logs show Smart Load ejecting #99 from XL-1.

**Corrections.** Downgraded from red because it needs a precondition that is absent on dev today (analysis: 'spools on a toolhead whose box source has no slot: []'). It is still reachable: a multi-spool Bulk Move into a Dryer Box lands spools slotless (auto-slot only runs when len(spools)==1, logic.py:451; container_slot is set to '' at logic.py:574), and a later deploy copies that empty slot into physical_source_slot (logic.py:592). I1-01's auto_deploy=False removes the whole path.

#### I1-04 — Return reports return_done plus a SUCCESS log even when the box write fails

*Severity orange → **orange** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** api_quickswap_return never looks at move_result. It always writes the '↩️ Return ... SUCCESS' log and returns 200 return_done. If Spoolman rejects the box write, the spool never left the toolhead, yet the user gets a success toast. Today the chain even writes the spool to the toolhead again and logs 'Auto-deployed'.

**Evidence.**

- routes_bindings.py:656-674 (the log at :662-665 and the return_done at :666-674 are unconditional)
- Q3|return_box_write_rejected|idle|today: http 200, response action 'return_done', smart_move {'auto_deployed_to':'XL-3','failures':{'240':'HTTP 400: rejected by fake'},'status':'success'}; final 240 still 'XL-3'; log ['ERROR: ❌ Failed to move Spool #240 -> Dryer LR-MDB-1: HTTP 400...', 'INFO: 🖨️ #240 -> XL-3', 'SUCCESS: ⚡ Auto-deployed ...', 'SUCCESS: ↩️ Return: ... (original source)']
- Q3|return_box_write_rejected|idle|fix_return_auto_deploy_off: still 'return_done' plus the SUCCESS log, with the spool on XL-3
- inv_quickswap.js:570-572 success toast; :578 error toast uses 5000 ms (CLAUDE.md: error toasts >= 7 s)

**Proof.** FakeSpoolman(reject_locations={'LR-MDB-1'}) under the REAL update_spool, which sets LAST_SPOOLMAN_ERROR from the 400.

**Fix direction.** In routes_bindings.py after :659: if move_result.status != 'success' or move_result.failures has this spool, write an ERROR log with the failure text and return a non-2xx body (e.g. action 'return_failed', error = the failure). Write the SUCCESS log only on a real success. In performReturn, show the error for 7 s.

**Regression test.** POST /api/quickswap/return with the box write rejected: assert action != 'return_done', a non-2xx status, an ERROR log line naming the Spoolman error, and no 'Return:' SUCCESS line.

**Verifier.** routes_bindings.py:660-674 writes the SUCCESS log and return_done without reading move_result. I1's test_q3_return_when_the_box_write_is_rejected re-ran and passed (it is an observation test). The error toast uses 5000 ms at inv_quickswap.js:578, below the CLAUDE.md >=7 s rule.

**Corrections.** Engine-level half of the same evidence: the chain passes list(spools) (logic.py:703-704) without excluding spools in `failures`, so a spool whose box write was rejected is still deployed onto the toolhead. The planned fix A must filter the chain by per-spool success, not only gate the log.

#### I1-05 — Moves with no slot into a multi-slot bound box (Force Location, buffer location-scan) auto-deploy onto a toolhead, and during a print they skip the confirm entirely

*Severity orange → **orange** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** The active-print pre-flight uses the caller's target_slot, and it runs before the auto-slot picker fills one. A single-spool move with no slot into a multi-slot Dryer Box whose lowest free slot is bound therefore (a) when IDLE, chain-deploys onto that toolhead and Smart-Load-ejects its spool, which contradicts Force Location's 'put it exactly here'; (b) when PRINTING, never asks for a confirm: the box write lands, the chain refuses, and 'Auto-deployed'/auto_deployed_to are still reported. Forwarding the confirm does not change (b), because these callers send confirm=False.

**Evidence.**

- logic.py:426-441 pre-flight (the bound-slot walk needs target_slot) runs before logic.py:444-476 auto-slot
- Force Location: inv_details.js:1210-1216 posts manage_contents add with no slot and no confirm -> routes_scan.py:330 perform_smart_move(loc_id, [sid], target_slot=slot_arg, ...) (code-trace)
- Buffer location-scan into a non-single-occupancy location: inv_cmd.js:1635 performContextAssign(res.id) -> :1852 /api/smart_move with slot null -> print_deduct.py:256 (code-trace)
- Q2|slotless_into_bound_box|idle|today: final {99:'LR-MDB-2', 240:'XL-1'}; result auto_deployed_to 'XL-1'; log includes '⚠️ Smart Load: Ejecting #99 from XL-1...' and '⚡ Auto-deployed Spool #240 → XL-1'
- Q2|slotless_into_bound_box|printing|today and |confirm_forwarded: result {'status':'success','auto_deployed_to':'XL-1'} with no requires_confirm; final 240 'LR-MDB-1' slot 1, 99 still on XL-1; chained call result {'status':'requires_confirm',...}; log 'SUCCESS: ⚡ Auto-deployed Spool #240 → XL-1'

**Proof.** Logic-level (perform_smart_move called directly with origin='manual_override', the same call routes_scan.py:330 makes); the frontend routing is code-trace only.

**Fix direction.** Derek decision. Recommended: chain only when the caller named the slot (the chain uses the caller's target_slot, not the auto-picked one). Alternatively, move the bound-slot pre-flight after auto-slot. Force Location should not auto-deploy at all: let manage_contents 'add' accept auto_deploy and send false from inv_details.js:1210-1216.

**Regression test.** perform_smart_move('LR-MDB-1', [240], target_slot=None, origin='manual_override'), where slot 1 is bound to XL-1 and #99 is loaded there; idle and printing. Assert: 240 in LR-MDB-1; 99 still on XL-1; no chained perform_smart_move call; no 'Auto-deployed' log; no 'auto_deployed_to' in the result.

**Verifier.** My test_V8, run with XL printing and confirm_active_print=False, returned {'status': 'success', 'failures': {}, 'auto_deployed_to': 'XL-1'} with no requires_confirm. 240 landed at LR-MDB-1 slot 1 and 99 stayed on XL-1; the log still says Auto-deployed Spool #240 -> XL-1. Frontend (code-trace): inv_cmd.js:1635 calls performContextAssign(res.id) with slot null (1847), which posts to /api/smart_move. inv_details.js:1211-1216 sends no slot, and its filter at :954 admits Dryer Boxes. The planned fix A does not close this, because these callers send confirm=False.

**Corrections.** Only half (b) is a defect: no prompt during a print, plus a false deploy claim. Half (a), idle deploy on a slotless box assign, matches Derek's stated expectation ('the box and the toolhead are bound so it should have auto populated') for scans, so it is a product decision, not a bug. Derek says he WAS confirming, so his symptom 1 came through an explicit-slot path (bug A), not this one.

#### I1-06 — The active-print pre-flight checks slot bindings even when auto_deploy=False

*Severity yellow → **info** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** When auto_deploy=False nothing can reach the bound toolhead. The pre-flight still walks slot_targets and returns requires_confirm during a print, refusing a pure box move. After I1-01, Return only succeeds during a print because it hard-codes confirm_active_print=True. Any other auto_deploy=False caller with a slot would be refused for no reason.

**Evidence.**

- logic.py:426-441 (no auto_deploy check around the slot_targets walk at :429-434)
- Q3|preflight_with_auto_deploy_false|printing: perform_smart_move('LR-MDB-1',[240],target_slot='3',auto_deploy=False,confirm_active_print=False) -> {'status':'requires_confirm','active_print':{'toolhead':'XL-3',...}}, nothing written
- Q3|preflight_with_auto_deploy_false|idle: success, 240 in LR-MDB-1 slot 3, no chain

**Proof.** Logic-level scratch test, idle and printing.

**Fix direction.** logic.py:431: walk the bound slot only when auto_deploy is True (e.g. `if auto_deploy and tgt_row and ... and target_slot:`). Return can then drop its unconditional confirm for the box leg; the source-side banner stays a frontend concern.

**Regression test.** perform_smart_move(box, [sid], target_slot=bound_slot, auto_deploy=False, confirm_active_print=False) while the bound head prints: assert status 'success' and the spool is in the box.

**Verifier.** logic.py:426-441 has no auto_deploy check around the slot_targets walk. However, no current caller passes auto_deploy=False together with a target_slot: bulk move passes no slot (logic.py:1042-1044), and the chain passes target_slot=None (703-707). After I1-01, Return still passes confirm=True.

**Corrections.** Latent only, so downgraded from yellow to info.

#### I1-07 — The DRYER and GENERIC move branches pop() the ghost trail, but update_spool's merge re-sends it, so the stale ghost persists (and a fixed Return exposes it)

*Severity orange → **red** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** Both branches do new_extra.pop('physical_source')/pop('physical_source_slot'). update_spool merges the caller's extras into the existing raw extras, and an omitted key means 'keep'. So the PATCH FCC sends still carries the old physical_source. A deployed spool moved to a room or another box keeps showing as a ghost in its old slot. Today the chain on Return overwrites physical_source and hides this. With Return's auto_deploy=False, the non-box-source case (S4) leaves the spool ghosted in the room.

**Evidence.**

- logic.py:638-642 (DRYER pop), logic.py:661-668 (the 'L130 fix' GENERIC pop); spoolman_api.py:372 data['extra'] = _merge_extras_with_existing(...), with the merge at spoolman_api.py:563-593 ('existing-only keys ride along untouched')
- The same file already knows this pattern: logic.py:1545 '.pop() just removes the key, which causes PATCH to ignore it'; eject and unassign write "" instead at logic.py:1556,1615,1639,1715,1794
- Q3|deployed_spool_moved_to|CR: the PATCH body FCC sent = {'location':'CR','extra':{'container_slot':'""','physical_source':'"LR-MDB-1"','physical_source_slot':'"3"'}}; views LR-MDB-1 [(240,'3','ghost')], CR [(240,'','direct')]
- Q3|deployed_spool_moved_to|LR-MDB-2: the PATCH re-sent physical_source '"LR-MDB-1"'; views LR-MDB-1 ghost + LR-MDB-2 direct
- Q1|S4_non_box_source|*|fix_return_auto_deploy_off: final 240 {location 'LR-MDB-1', physical_source 'CR'}; views CR [(240,'3','ghost')]
- Existing pin tests/test_smart_move_spoolman.py:208-211 mocks update_spool itself and asserts .get('physical_source','') == '', which passes when the key is merely absent, so it cannot see the merge

**Proof.** patch_bodies are the exact JSON the REAL spoolman_api.update_spool handed to requests.patch; they do not depend on how the fake stores data.

**Fix direction.** logic.py:640-641 and :667-668: set new_extra['physical_source'] = '' and new_extra['physical_source_slot'] = '' instead of pop(). The delete sentinel won't work: the merge refuses it for SYSTEM_MANAGED_EXTRAS. Ship it with I1-01.

**Regression test.** A move through the REAL update_spool with only requests.patch / _get_raw_extras / get_spool faked: a deployed spool (XL-3, physical_source LR-MDB-1:3) moved to 'CR' and to 'LR-MDB-2'. Assert the PATCH extra has physical_source == '""' and physical_source_slot == '""', and get_spools_at_location_detailed('LR-MDB-1') has no ghost for it. Also the Return S4 case: no ghost in CR.

**Verifier.** Independent wire-level proof (my test_V1: REAL update_spool and REAL merge, only requests.patch, get_spool and _get_raw_extras faked). CR PATCH body: {'location': 'CR', 'extra': {'physical_source': '"LR-MDB-1"', 'physical_source_slot': '"3"', 'container_slot': '""', ...}}. LR-MDB-2 PATCH body: the same physical_source. For both, the real _build_location_match for LR-MDB-1 still returns {'is_ghost': True, 'slot': '3'}. git: the L130 pop 'fix' (30f0f6c, 2026-05-14) landed AFTER the sibling-preserving merge (b64211a, 2026-04-26), so it never worked. Its pins accept an absent key (tests/test_deployed_flag_preservation.py:346-349, tests/test_smart_move_spoolman.py:211).

**Corrections.** Raised from orange to red. Live dev already has a stale trail of this shape: spool #99 is at LR-MDB-1 slot 4 but carries physical_source CR-MDB-1 slot 1 (bound to CORE1). It renders as the 'CR-MDB-1 = 1 ghost (a deployed spool reserving its slot)' in the handoff's Bulk Move check 3 starting state, although it sits on no toolhead. That this path wrote it is inferred. Duplicate of I2-03.

#### I1-08 — Undo after a chained move is two steps (the first CMD:UNDO completes the Return), and undoing a Smart Load never puts the ejected spool back

*Severity yellow → **yellow** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** (a) The outer move and the chained move each push an undo record. After today's Return, the first undo pops the chain record and moves the spool INTO the box, doing what Return was supposed to do, while logging 'Undid: moved #240 from LR-MDB-1 -> XL-3'. The second undo puts it back on the toolhead. (b) Smart Load records the ejected spool's location AFTER the eject (logic.py:512), and perform_undo writes that same location back (logic.py:1846-1847). That is a no-op, so the resident is never restored to its toolhead. During a refused eject (bug B), the 'ejection' recorded is the toolhead the resident never left.

**Evidence.**

- logic.py:679 (outer record appended before the chain), logic.py:703 (the chain appends its own); logic.py:508-512; logic.py:1846-1847
- Q2|undo_after_return|S1_physical_source|idle|today: after_return 240 on 'XL-3'; after_undo1 240 at 'LR-MDB-1' slot '3'; after_undo2 240 on 'XL-3'; logs 'Undid: moved #240 from LR-MDB-1 -> XL-3' then 'Undid: moved #240 from XL-3 -> LR-MDB-1'
- Q2|undo_after_return|S3_source_without_slot|idle|today: undo record ejections {99: 'LR-MDB-2'}; after_undo1 99 still at 'LR-MDB-2' (it was on XL-1 before the Return), XL-1 left empty
- Q1|S3_source_without_slot|printing|confirm_forwarded: ejections {99: 'XL-1'} for a refused eject

**Proof.** The real perform_undo over the HTTP-level fake.

**Fix direction.** Record the resident's location BEFORE perform_smart_eject (read it at the loop in logic.py:500-505). Fold the chained move's undo into the parent record, or tag it and pop both in one undo. With I1-01, Return pushes a single record.

**Regression test.** (1) After a fixed Return: len(state.UNDO_STACK) == 1, and one perform_undo puts the spool back on XL-3 with physical_source LR-MDB-1:3. (2) A Smart Load onto an occupied head followed by perform_undo: the incoming spool goes back to its origin AND the resident is back on the head.

**Verifier.** (a) logic.py:679 appends the outer record before the chain, whose perform_smart_move appends its own. My V2 shows two undo records, ['quickswap_return', 'auto_deploy_from_quickswap_return']. The same happens for every successful auto-deploy (slot-QR, deposit, LM slot assign), not only Return. (b) logic.py:508-512 records the post-eject location and logic.py:1846-1847 writes it back.

**Corrections.** (b) duplicates the established test_undo_of_a_smart_load_puts_the_resident_back_on_the_head, which fails in my rerun of the established file (10 failed).

#### I1-09 — Quick-Swap Deposit into a bound slot can never succeed during a print: the backend always asks for a confirm the deposit never sends

*Severity yellow → **yellow** after review · verdict **CONFIRMED** · proof: test-run · confidence medium*

**Claim.** The deposit overlay probes the toolhead and shows the active-print banner, but the identify_scan POST it sends has no confirm_active_print. The backend pre-flight sees the bound slot's printing toolhead and returns assignment_requires_confirm. The deposit handler has no branch for that and toasts '❌ Deposit failed: assignment_requires_confirm'. Forwarding the confirm into the chain does not help until the deposit sends one.

**Evidence.**

- inv_quickswap.js:596-624 (body is {text: LOC:box:SLOT:slot, source:'quickswap_deposit'} only); inv_quickswap.js:368 probe; inv_quickswap.js:642 generic failure toast (code-trace)
- routes_scan.py:1125 reads confirm_active_print from the request (default False); routes_scan.py:1133-1136 answers assignment_requires_confirm
- Q2|explicit_bound_slot_printing|confirm=False|today: perform_smart_move('LR-MDB-1',[240],target_slot='3',confirm_active_print=False) while printing -> {'status':'requires_confirm','active_print':{'toolhead':'XL-3',...}}; 240 still in 'CR'; no log
- Q2|explicit_bound_slot_printing|confirm=True|confirm_forwarded: 240 lands on XL-3 (the intended deploy works once the confirm is sent and forwarded)

**Proof.** The backend half was proven at logic level (the same call routes_scan.py:1126 makes); the frontend half is code-trace only.

**Fix direction.** When the deposit overlay showed the active-print banner (the user confirmed it), send confirm_active_print: true in the identify_scan body, or handle assignment_requires_confirm the way inv_cmd.js:1522-1544 does. This depends on the chain forwarding the confirm, otherwise the deposit lands in the box only.

**Regression test.** Backend: POST /api/identify_scan {text:'LOC:LR-MDB-1:SLOT:3', confirm_active_print:true} with a buffered spool while XL prints, after the chain fix: action assignment_done, the spool on XL-3, a truthful auto_deployed_to. Frontend E2E (opt-in): deposit during a mocked active print shows no 'Deposit failed' toast.

**Verifier.** inv_quickswap.js:620-623 posts only {text, source}; :641-642 toasts 'Deposit failed'. routes_scan.py:1125-1142 turns the refusal into assignment_requires_confirm. I2's test_ok_deposit_scan_without_confirm_flag_is_refused_for_a_printing_bound_toolhead passed in my rerun.

**Corrections.** Not silent: the user gets an error toast and nothing is written. Duplicate of I2-14.

#### I1-10 — An E2E cleanup relies on Return, so on live dev it silently leaves the swapped spool on the toolhead

*Severity info → **info** after review · verdict **PLAUSIBLE** · proof: code-trace-only · confidence medium*

**Claim.** test_quickswap_refreshes_manage_view_after_yes quick-swaps a spool from a BOUND box slot onto its toolhead. It then 'restores' with POST /api/quickswap/return inside a bare try/except. By I1-01, an idle-printer Return into a slot bound to that toolhead redeploys the spool, so the restore does nothing. Every run would leave the spool on the toolhead and drift shared dev state (the sweep-contamination family).

**Evidence.**

- tests/test_return_overlay_and_refresh.py:83-95 (_find_bound_and_loaded only selects slots with a target); :167-175 (the Return cleanup with except Exception: pass)
- The I1-01 proof (S1/S2 idle today)

**Proof.** Inferred from the I1-01 proof. E2E tests were not run (hard rule: no dev-data mutation).

**Fix direction.** Covered by I1-01. Until then, the cleanup should restore with an explicit move and auto_deploy off, or assert the spool's location after cleanup.

**Regression test.** Once I1-01 lands, have the E2E assert after cleanup that the spool's location is the original box (run only in an opted-in E2E sweep).

**Verifier.** tests/test_return_overlay_and_refresh.py:83-95 selects bound slots holding a spool; :167-175 restores through /api/quickswap/return inside a bare try/except. By V2, and given dev's current S1 state on all five XL heads, that restore would redeploy. Not run: E2E is forbidden.

**Corrections.** None.

**Ruled out (I1).**

- *perform_smart_eject's return-home goes through perform_smart_move and re-triggers auto-deploy into the bound slot* — It writes Spoolman directly (logic.py:1617). Q2|eject_return_home|idle and |printing: result True, perform_smart_move_calls [], 240 at LR-MDB-1 container_slot '3', physical_source '' (explicit empty at logic.py:1615), no ghost on XL-3.
- *perform_undo restoring a spool into a bound dryer slot triggers the chain* — perform_undo writes each spool through spoolman_api.update_spool (logic.py:1806-1850) and never calls perform_smart_move. Q2|undo_into_bound_slot|idle and |printing: calls_during_undo [], 240 back at LR-MDB-1 slot '3', nothing on XL-3.
- *Weigh-out / archive paths deploy a spool* — inv_weigh_out.js:490-493 sends manage_contents force_unassign with location '' -> logic.py:1770-1799 writes directly. Q2|force_unassign: calls [], location ''. The auto-unarchive restore (spoolman_api.py:282-287) is a payload tweak inside update_spool, and spoolman_api never imports logic (grep), so no chain (code-trace).
- *Bulk move chain-deploys into a bound box slot* — logic.py:1042-1043 passes auto_deploy=False and target_slot is never set, so the pre-flight slot walk is skipped too. Already pinned by tests/test_bulk_move.py:144 and tests/test_bulk_move_session.py:201,650 (code-trace + existing pins, not re-run).
- */api/quickswap (box slot -> toolhead) re-enters the chain* — Its target is a toolhead; the chain requires a Dryer Box target (logic.py:694). Its Smart Load resident eject returns home by direct write (proven by the eject test). Code-trace for the endpoint.
- *The 'Return undone' result is an artefact of the fake Spoolman* — test_seed_S1_is_what_a_real_forward_autodeploy_leaves PASSED (the seed equals a real forward deploy), and the round-trip test ran deposit + Return in one store. The real update_spool / merge / _build_location_match ran; only the HTTP transport was faked. The chain decision (logic.py:694-707) happens before any storage question.
- *Return with auto_deploy=False would be refused during a print* — Not with the endpoint as written: it passes confirm_active_print=True, and Q1|*|printing|fix_return_auto_deploy_off all succeeded with the spool in the box. Only true if that confirm is ever dropped (see I1-06).
- *This agent modified inventory-hub/tests/test_universal_fallback.py* — The audit-hook tripwire recorded 0 write attempts under the repo in both runs (repo_write_tripwire.json == []). The file's mtime 2026-09-12 19:48:38 predates my first scratch write (19:57:13). The diff is someone else's bug-B test adjustment (perform_smart_eject return_value=True).

**Checked correct (I1).**

- Return destination selection works as documented: physical_source when it names a Dryer Box (routes_bindings.py:604-613), otherwise first_binding (:616-628). The response box/slot/source fields were correct in every scenario (S1 physical_source/'3', S2 first_binding/'3', S3 physical_source/None, S4 first_binding/'3').
- Deposit, slot-QR assignment and Location Manager slot assign are MEANT to deploy (commit 47c51d5 centralised the chain for exactly that). With the confirm forwarded they deploy correctly during a confirmed print: Q2|explicit_bound_slot_printing|confirm=True|confirm_forwarded -> 240 on XL-3 with ghost LR-MDB-1:3. Without a confirm, the pre-flight refuses before any write (confirm=False -> requires_confirm, 240 still in CR).
- The slot-QR retry path sends confirm_active_print: true (inv_cmd.js:1522-1544), and Location Manager doAssign retries with the confirm after the backend asks (inv_loc_mgr.js:1420-1447), so forwarding the confirm into the chain covers both.
- Hermeticity: 0 locations.json saves (save_locations_list MagicMock never called), 0 unexpected HTTP get/post, network sockets blocked, the repo-write tripwire recorded 0 attempts in both runs; app.py (startup migrations) was never imported; git status unchanged by this agent.
- The 6 R1 pins are strict xfails on today's code and pass under the simulated Return auto_deploy=False fix (with the confirm also forwarded), across S1/S2/S3 × idle/printing.

**Open questions (I1).**

- Derek: should a move with no slot into a multi-slot bound box (Force Location via inv_details.js, a buffer location-scan) ever auto-deploy? My recommendation is to chain only when the caller named the slot (I1-05).
- Derek: when Return has a physical_source box but no recorded slot, should it land unslotted, or in a free slot bound to the same toolhead or unbound, instead of the lowest free slot, which may be bound to another head (I1-03)?
- Should the chained move's undo fold into the parent record so one CMD:UNDO reverts one user action (I1-08)? That matters for the Bulk Move manual check 1 (Undo) whenever a bound box is involved.
- Merge order: the planned chain confirm-forwarding must not land before Return gets auto_deploy=False (I1-02). Whoever builds bug A should take I1-01 and I1-07 in the same change.
- Another agent/session is editing the working tree concurrently: inventory-hub/tests/test_universal_fallback.py shows as modified since 19:48:38 (a bug-B test tweak). logic.py and routes_bindings.py were unchanged as of 19:58, so all line numbers above are valid for that tree.
- Not investigated (outside this question): the slot-card eject no-ops. Nothing here implicates or clears Bootstrap.

### I2 — result-trust-audit

Result-trust audit of every consumer of perform_smart_move, perform_smart_eject, perform_force_unassign, perform_toolhead_delete_cascade, execute_bulk_move / commit_bulk_move_session and perform_undo, on the backend and in the frontend JS. Nothing in the repo was edited and no dev data was touched. Evidence comes from 20 hermetic scratch tests (16 fail, each proving a defect; 4 control tests pass) and one standalone Bootstrap 5.3.0 browser run.

Baseline, already pinned: A (the auto-deploy chain drops confirm_active_print and still logs Auto-deployed) and B (the Smart Load resident eject treats truthy refusals as success).

New findings: 10 red, 5 orange, 3 yellow.

Headlines:
1. POST /api/quickswap/return sends the spool back onto the toolhead it came from. It calls perform_smart_move on the bound box slot with auto_deploy still on, so on an idle printer the auto-deploy chain re-deploys it, while the route answers return_done and logs SUCCESS.
2. **Warning for planned fix A.** That route hard-codes confirm_active_print=True. Once A forwards the confirm into the chain, Return will re-deploy even onto a PRINTING head. I proved this by simulating the fix in a test.
3. Return can act on a ghost resident. In the test it moved the XL-3 spool onto XL-1 and knocked XL-1's own spool off unslotted.
4. The Dryer and Room/Cart (generic) move branches clear the ghost trail with dict.pop. update_spool keeps omitted keys, so the old box link (physical_source) survives. The real PATCH body was captured; the two repo tests that pin this mock update_spool and accept a missing key as cleared.
5. clear_location answers success:true while ejecting nothing, for a Room, for an idle toolhead whose spool has no home, and for a rejected write.
6. The bulk-move tally trusts a fail-open readback over the engine's own failures map: all writes rejected plus a Spoolman outage gives success, moved 2, failed 0.
7. The slot-QR assignment, /api/quickswap and every frontend check of status==='success' ignore per-spool failures. They toast success and drop the spool from the buffer.
8. A failed unseat double-books a slot while the move reports a clean success.
9. perform_undo reports success when every restore write fails, and the frontend ignores the undo response entirely.
10. A toolhead delete removes the row and answers success while the spool still points at the deleted toolhead.

Frontend confirm dead ends: Eject-all never checks require_confirm and toasts 'Cleared!'. deleteLoc ignores the 409. The Quick-Swap deposit posts without the confirm flag the user just gave. The spool-details Force Location Override never sends a confirm.

Eject no-ops (candidate, not a root cause): an eject from a toolhead can chain up to three Bootstrap confirms, each re-armed inside the previous one's callback. In a standalone page with the same 'modal fade' markup, Bootstrap 5.3.0 silently drops a show() issued 0-120 ms after hide(); from 200 ms it shows. That can leave an invisible, still-armed confirm. Whether Derek's round-trips were fast enough is not established, so Bootstrap is neither ruled in nor ruled out.

Scratch artifacts are in the result-trust-audit scratch dir. Run the tests from that dir: PYTHONIOENCODING=utf-8 "C:/Python314/python.exe" -m pytest test_i2_result_trust.py -p no:cacheprovider -q --offline. A scratch conftest.py only registers --offline, so the repo conftest's session fixtures never load.

#### I2-BASE-A — Baseline A: the auto-deploy chain drops confirm_active_print and claims a deploy it did not make

*Severity info → **info** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** Already established and pinned in tests/test_active_print_chain_confirm.py; listed here as baseline only.

**Evidence.**

- logic.py:703-707 chained perform_smart_move without confirm_active_print
- logic.py:708-713 logs SUCCESS for every spool unconditionally
- logic.py:725-726 sets auto_deployed_to whenever the result is non-None

**Proof.** Pinned by the 3 section-A tests in inventory-hub/tests/test_active_print_chain_confirm.py. My scratch test test_ok_quickswap_return_today_during_print_stays_in_box_but_logs_autodeploy also shows the false '⚡ Auto-deployed Spool #240 → XL-3' SUCCESS line while the spool stays in LR-MDB-1.

**Fix direction.** As planned. See I2-01 for a consumer that the confirm forwarding would make worse.

**Regression test.** inventory-hub/tests/test_active_print_chain_confirm.py (section A)

**Verifier.** Baseline: the established file re-run gives 10 failed, including the three section-A tests. logic.py:703-713 and 725-726 match.

**Corrections.** None.

#### I2-BASE-B — Baseline B: the Smart Load resident eject treats truthy refusals and False as success

*Severity info → **info** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** Already established and pinned; listed as baseline only.

**Evidence.**

- logic.py:508 `if perform_smart_eject(rid):` without confirm_active_print or confirmed_unassign

**Proof.** Pinned by the 3 section-B tests in inventory-hub/tests/test_active_print_chain_confirm.py.

**Fix direction.** As planned.

**Regression test.** inventory-hub/tests/test_active_print_chain_confirm.py (section B)

**Verifier.** Baseline: logic.py:508 is `if perform_smart_eject(rid):` with no confirm arguments. The established section-B tests fail in my rerun.

**Corrections.** None.

#### I2-01 — POST /api/quickswap/return re-deploys the returned spool back onto the toolhead, while reporting return_done

*Severity red → **red** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** api_quickswap_return calls perform_smart_move(found_box, [sid], target_slot=found_slot, confirm_active_print=True) with auto_deploy left at its default of True. found_slot is normally the slot bound to that same toolhead: always for 'first_binding', and for 'physical_source' whenever the spool was auto-deployed from that slot. So the auto-deploy chain immediately moves the spool back onto the toolhead. On an idle printer 'Return' is therefore a round trip that ends where it started, yet the route logs '↩️ Return … → LR-MDB-1:SLOT:3' SUCCESS and the UI toasts '↩️ Spool #240 → LR-MDB-1:SLOT:3'. During a print, bug A's refused chain accidentally leaves the spool in the box. Planned fix A would change that: the route hard-codes confirm_active_print=True, so once the confirm is forwarded into the chain, Return re-deploys onto the PRINTING head.

**Evidence.**

- routes_bindings.py:656-659 perform_smart_move(found_box, [spool_id], target_slot=found_slot, origin='quickswap_return', confirm_active_print=True); auto_deploy not passed
- routes_bindings.py:615-628 fallback picks the slot whose target == active_toolhead
- logic.py:694-707 chain fires for any Dryer Box target_slot bound to a toolhead
- routes_bindings.py:662-674 SUCCESS log + action return_done regardless of where the spool ended
- inv_quickswap.js:570-572 success toast on return_done
- Test output: HTTP 200 {'action': 'return_done', 'box': 'LR-MDB-1', 'slot': '3', 'smart_move': {'auto_deployed_to': 'XL-3', ...}} FINAL {'location': 'XL-3', ...}; writes = [(240, {'location': 'LR-MDB-1', ...}), (240, {'location': 'XL-3', ...})]
- Simulated fix A, XL printing: 'with fix A applied, Return put #240 back on the PRINTING head: {'location': 'XL-3', ...}'
- Why unseen: tests/test_return_and_breadcrumb.py:65,99,135 mock perform_smart_move; tests/test_return_overlay_and_refresh.py:167-175 calls /api/quickswap/return as a 'restore' inside try/except with no assertion (so the E2E sweep leaves the dev spool re-deployed)

**Proof.** Scratch tests test_quickswap_return_route_redeploys_the_spool_back_onto_the_toolhead (idle) and test_quickswap_return_after_fix_A_would_redeploy_onto_a_PRINTING_toolhead, both FAILED as expected. They drive the Flask route through app_core with the real perform_smart_move and a fake Spoolman whose extras follow the real omit-means-keep merge. The second wraps logic.perform_smart_move to add the confirm only on origin 'auto_deploy_from_*', simulating fix A without editing the repo. The mid-print control test test_ok_quickswap_return_today_during_print_stays_in_box_but_logs_autodeploy passed.

**Fix direction.** Pass auto_deploy=False on the return call: a return means 'put it back in its box', not 'load it'. Land this before or together with fix A. Gate the Return SUCCESS log and return_done on smart_move.status == 'success' with empty failures, and confirm the final location. Audit any other 'send home' caller that targets a bound slot.

**Regression test.** Route test through /api/quickswap/return with the real perform_smart_move, a bound physical_source slot and an idle printer, asserting the spool ends at the box; then the same with XL printing plus fix A applied.

**Verifier.** Same mechanism as I1-01, independently re-proved by my test_V2. I2's two Return tests FAILED as intended in my rerun (16 failed / 4 passed overall, matching the report).

**Corrections.** Duplicate of I1-01 (idle half) and I1-02 (fix-A half).

#### I2-02 — Quick-swap Return can act on a GHOST resident, pulling a spool off a different toolhead

*Severity red → **orange** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** api_quickswap_return picks residents[0] from get_spools_at_location(toolhead), and that reader also returns ghosts (spools whose physical_source equals the toolhead). A spool moved directly from one toolhead to another gets physical_source = the old toolhead. Returning that old toolhead can therefore grab the spool now loaded elsewhere. In the test, Return on XL-1 moved #60 (loaded on XL-3) into the box and, via the chain, onto XL-1. XL-1's real spool #61 was Smart-Load ejected and landed unslotted, and XL-3 was emptied. The route answered return_done 'moved 60'. The overlay's _resolveReturnDestination has the same items[0] choice, so it can name the wrong spool too.

**Evidence.**

- routes_bindings.py:568-573 `residents = spoolman_api.get_spools_at_location(th)` → `spool_id = int(residents[0])`
- spoolman_api.py:1470-1479 ghost match on physical_source; spoolman_api.py:1522-1523 get_spools_at_location = all detailed ids, ghosts included
- logic.py:590-592 PRINTER MOVE sets physical_source = current_loc (a toolhead when moving head→head)
- inv_quickswap.js:735-738 `const resident = (items || [])[0]`
- Test output: HTTP 200 {'action': 'return_done', 'moved': 60, 'slot': '1', 'source': 'first_binding', 'toolhead': 'XL-1'} FINAL {60: {'location': 'XL-1', ...}, 61: {'location': 'LR-MDB-1', 'extra': {'physical_source': '', 'container_slot': ''}}}
- Contrast: spoolman_api.py:1531-1567 select_deduct_targets already applies 'DIRECT wins' for exactly this ghost-vs-direct ambiguity

**Proof.** Scratch test test_quickswap_return_can_act_on_a_ghost_resident_instead_of_the_loaded_spool FAILED. It depends on order: the ghost must be listed before the direct resident. The fake lists by spool id; real Spoolman list order was not verified.

**Fix direction.** Choose among direct (non-ghost) residents only, as select_deduct_targets does, and do the same in _resolveReturnDestination. Refuse with a warning when two direct residents exist.

**Regression test.** /api/quickswap/return where a lower-id ghost (physical_source = the toolhead) precedes the direct resident; assert moved == the direct resident and the ghost spool's location is unchanged.

**Verifier.** routes_bindings.py:568-573 takes residents[0] from get_spools_at_location, which includes ghosts (spoolman_api.py:1470-1479, 1522-1523). test_quickswap_return_can_act_on_a_ghost_resident... FAILED as intended in my rerun. The order dependence is real: the read-only dev GET returned spools ordered by id ascending, so a lower-id ghost beats the direct resident. The toolhead-valued physical_source precondition is produced by logic.py:591 (my V4: after moving XL-1 to XL-2, 77 stored ('XL-2', 'XL-1', ...)).

**Corrections.** Downgraded from red: dev today has no toolhead-valued physical_source ('TOOLHEAD-valued physical_source: []'). Same root as I5-3, I5-4 and I5-14.

#### I2-03 — Dryer and Room/Cart (generic) moves 'clear' the ghost trail with dict.pop, which update_spool treats as KEEP, so physical_source survives

*Severity red → **red** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** perform_smart_move's DRYER MOVE and GENERIC MOVE branches remove physical_source and physical_source_slot with new_extra.pop(). update_spool read-merge-writes extras, and an omitted key means keep. The PATCH actually sent still carries the old physical_source. A spool moved off a toolhead into a Room, Cart or another box therefore still matches its old box as a ghost. It shows as deployed or ghosted in its old slot, plan_bulk_move skips it as 'deployed to a live toolhead', a later eject 'returns' it to the old box, and slot collisions appear (the Group 13.2 family, which is also bulk-move triage candidate 2(c)). perform_smart_eject already knows pop does not clear and writes '' instead. This is outside the result-trust brief (found incidentally), but it is a silent data inconsistency on every move off a toolhead.

**Evidence.**

- logic.py:640-642 DRYER MOVE pops physical_source + physical_source_slot
- logic.py:667-668 GENERIC MOVE pops them (the L130 fix)
- spoolman_api.py:353-372 update_spool merges caller extras over _get_raw_extras
- spoolman_api.py:577-594 `merged = dict(existing_extras)`; only DELETE_EXTRA_SENTINEL pops, and never for SYSTEM_MANAGED_EXTRAS
- logic.py:1544-1546 comment: '.pop() just removes the key, which causes PATCH to ignore it (keeping the old value)'
- Captured PATCH (real update_spool, HTTP faked): {'location': 'CR', 'extra': {'physical_source': '"LR-MDB-1"', 'physical_source_slot': '"2"', 'container_slot': '""', ...}}
- Why unseen: tests/test_deployed_flag_preservation.py:346-349 and tests/test_smart_move_spoolman.py:211 mock update_spool and accept an ABSENT key as cleared

**Proof.** Scratch test test_generic_move_pop_does_not_clear_physical_source_on_the_wire FAILED. It runs the real logic.perform_smart_move plus the real spoolman_api.update_spool, with requests.get/patch faked at spoolman_api.requests, and asserts on the PATCH body. That the stored Spoolman record keeps the value is inferred from the PATCH body plus the documented whole-extra PATCH contract; no live Spoolman was touched. The DRYER branch was code-traced, not run: it is the same pop.

**Fix direction.** Write physical_source = '' and physical_source_slot = '' explicitly in both branches, as perform_smart_eject and perform_force_unassign do. Change the two repo tests to assert an explicit empty value, not an absent key, or run them through the real merge. Consider a read-only dev/prod count of spools whose physical_source is set but whose location is not a toolhead, to size existing drift.

**Regression test.** The scratch test above, plus a DRYER-branch twin (toolhead spool → LR-MDB-2 slot 1, asserting the PATCH extra carries physical_source '""').

**Verifier.** Independently re-proved at the wire (my test_V1, for both the GENERIC and DRYER branches).

**Corrections.** The DRYER branch is now test-run too, not just code-traced (V1 dest=LR-MDB-2). git shows the L130 pop postdates the merge, and live dev spool #99 carries such a trail. Duplicate of I1-07.

#### I2-04 — clear_location (Eject-all) answers success:true while ejecting nothing

*Severity red → **orange** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** The clear_location action calls perform_smart_eject(spool, confirm_active_print=True), discards the result, appends the id to ejected_ids and returns {'success': True}. perform_smart_eject declines in three common cases, and all of them look like a successful clear:
- A Room id has no dash, so get_room_from_location returns '' and the eject answers 'REQUIRE_CONFIRM'. 'Nuke all unslotted in CR' ejects nothing.
- A toolhead spool with no physical_source hits the protected unassign and gets 'REQUIRE_CONFIRM'.
- A Spoolman rejection returns False.
The fail-open contents reader turns a Spoolman outage into an empty list, which also yields success. The frontend then toasts 'Cleared!'.

**Evidence.**

- routes_scan.py:254-257 `logic.perform_smart_eject(spool['id'], confirm_active_print=True)` then `ejected_ids.append(spool['id'])` unconditionally
- routes_scan.py:279 `return jsonify({"success": True})`
- logic.py:1476-1477 get_room_from_location returns '' when '-' not in id; logic.py:1627-1636 printer or empty room → REQUIRE_CONFIRM unless confirmed_unassign
- routes_scan.py:233 get_spools_at_location_detailed, fail-open per spoolman_api.py:1518-1520
- inv_loc_mgr.js:1657-1661 toasts 'Cleared!' unless skipped_slotted
- Test output: clear CR → HTTP 200 {'success': True} FINAL {50: {'location': 'CR'}} WRITES []
- Test output: clear XL-1 (idle) → HTTP 200 {'success': True} FINAL {42: {'location': 'XL-1'}} WRITES []
- Test output: clear CR-CT-1 with rejection → HTTP 200 {'success': True}; log '❌ Failed to eject Spool #51'

**Proof.** Scratch tests test_clear_location_room_reports_success_but_ejects_nothing, test_clear_location_idle_toolhead_reports_success_but_ejects_nothing and test_clear_location_reports_success_when_eject_write_rejected, all FAILED, exercised through the Flask route. The fail-open reader case is code-trace only.

**Fix direction.** Branch on each result (True / 'REQUIRE_CONFIRM' / requires-confirm dict / False) and return ejected, needs_unassign_confirm and failed lists, with success only when nothing was left behind for a reason other than a deliberate slot skip. Use get_spools_at_location_detailed_strict and fail closed. Make the frontend toast the real counts. Decide whether room-level spools should get one batch unassign confirm.

**Regression test.** The three scratch tests, plus a strict-reader outage case asserting success is false.

**Verifier.** routes_scan.py:256-257 appends ejected_ids regardless of the result, and :279 returns success. logic.py:1476-1477 plus 1627-1636 give REQUIRE_CONFIRM for a Room or a homeless toolhead spool. All three I2 clear_location tests FAILED as intended in my rerun. Nothing is corrupted: the success is simply false.

**Corrections.** Downgraded from red. Unreported side effect: perform_smart_eject detaches single-slot boxes BEFORE its REQUIRE_CONFIRM return (logic.py:1531-1539 vs 1634-1636, my V5). A 'Cleared!' on a homeless toolhead spool can therefore silently unbind its PolyDryer while the spool stays. I5-18 is a subset of this finding.

#### I2-05 — execute_bulk_move trusts a fail-open readback over the engine's own failures map

*Severity red → **orange** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** The tally only looks at move_result['failures'] when the source readback finds spools still in place. The readback uses the fail-open get_spools_at_location_detailed, which returns [] on any Spoolman error. When Spoolman is flapping, the same condition that makes the writes fail, every rejected spool is counted as moved: success True, failed [], a SUCCESS '🔀 Bulk move … moved 2, skipped 0, failed 0' log line, the panel toast 'Moved 2 spool(s)', and the session is reset.

**Evidence.**

- logic.py:1063-1068 moved_ids defaults to all movable ids; the readback uses get_spools_at_location_detailed (non-strict)
- logic.py:1079-1088 per-spool failures consulted only `if stuck:`
- spoolman_api.py:1511-1520 exception swallowed → `return found` (empty)
- logic.py:1094-1101 SUCCESS summary + success=len(failed)==0; logic.py:1465 reset_bulk_move
- Test output: RESULT {'success': True, 'moved': 2, 'moved_ids': [51, 52], 'failed': []} FINAL {51: {'location': 'CR-CT-1'}, 52: {'location': 'CR-CT-1'}} LOGS [...'❌ Failed to move Spool #51 -> CR-CT-2'..., '🔀 Bulk move CR-CT-1 → CR-CT-2: moved 2, skipped 0, failed 0' (SUCCESS)]
- Control passed: with a working readback → {'success': False, 'failed': [{'id': 51, 'err': '400: rejected by test'}, {'id': 52, ...}]}

**Proof.** Scratch test test_bulk_move_tally_trusts_a_fail_open_readback_over_engine_failures FAILED. It uses the REAL get_spools_at_location_detailed with spoolman_api.get_all_spools raising. Control test test_ok_bulk_move_tally_is_honest_when_the_readback_works PASSED.

**Fix direction.** Always union move_result['failures'] into failed. Use the _strict reader for the readback, and on an exception report the tally as unverified with a warning, never as a clean success.

**Regression test.** The scratch test above; also assert the Activity Log summary is WARNING, not SUCCESS.

**Verifier.** logic.py:1066-1088 consults failures only when the non-strict readback finds stuck spools. get_spools_at_location_detailed swallows errors and returns [] (spoolman_api.py:1511-1520), so the except at logic.py:1089 is never reached for it. The I2 test FAILED as intended; the control passed.

**Corrections.** Downgraded from red. It needs Spoolman readable for the live re-plan (strict reader), then failing for both the writes and the readback. Derek chose the Activity Log as authoritative on 2026-07-11, but the summary line 'failed 0' still contradicts the per-spool ERROR lines, and the session resets.

#### I2-06 — Slot-QR / deposit assignment reports a load and drops the spool from the buffer when the write was rejected

*Severity red → **orange** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** The LOC:X:SLOT:Y branch of api_identify_scan handles only requires_confirm. For any other result it logs '✅ Spool #N → X:SLOT:Y' SUCCESS, removes the spool from GLOBAL_BUFFER and returns assignment_done, even when smart_move.failures names that spool. Three frontend paths trust it: the scan branch toasts '✅ Loaded #N into …', the post-confirm replay does the same, and the Quick-Swap deposit toasts '⬇️ … → box:SLOT'. The scan paths also drop the spool from heldSpools, and 21.6's mark-assigned-out bookkeeping stops the pulse from bringing it back. The spool is still where it was but vanishes from the buffer.

**Evidence.**

- routes_scan.py:1133-1142 only requires_confirm is checked
- routes_scan.py:1146-1173 buffer removal + SUCCESS log + assignment_done
- inv_cmd.js:1465-1482 and inv_cmd.js:1558-1571 filter heldSpools + _markAssignedOut + success toast
- inv_quickswap.js:627-638 deposit success toast + buffer filter
- Test output: HTTP 200 {'action': 'assignment_done', 'moved': 42, 'remaining_buffer': 0, 'smart_move': {'failures': {'42': '400: rejected by test'}, 'status': 'success'}} BUFFER [] LOGS ['❌ Failed to move Spool #42 -> Dryer LR-MDB-1' (ERROR), '✅ Spool #42 → <b>LR-MDB-1:SLOT:2</b>' (SUCCESS)]

**Proof.** Scratch test test_slot_qr_assignment_claims_done_when_box_write_rejected FAILED (Flask route, real engine, fake Spoolman). The frontend handling is code-traced.

**Fix direction.** When move_result.failures contains the spool, keep it in the buffer, log ERROR and return an 'assignment_failed' action with the error. Add that branch to the three frontend handlers with a 7 s error toast.

**Regression test.** The scratch test above, asserting action != assignment_done and the buffer is unchanged.

**Verifier.** routes_scan.py:1133-1173 checks only requires_confirm, then drops the spool from the buffer and logs SUCCESS. inv_cmd.js:1465-1482 then filters heldSpools and calls _markAssignedOut. The I2 test FAILED as intended.

**Corrections.** Downgraded from red: it needs a Spoolman rejection. Rejections include the Group 36 refusal when the pre-merge extras read fails (spoolman_api.py:353-369), so read blips count, not only 400s.

#### I2-07 — POST /api/quickswap logs and returns quickswap_done when the toolhead write was rejected

*Severity red → **orange** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** api_quickswap never inspects move_result. A Spoolman rejection of the toolhead write still produces a '⚡ Quick-swap' SUCCESS log and quickswap_done, and the UI toasts '⚡ Spool #N → XL-3'.

**Evidence.**

- routes_bindings.py:743-756 log SUCCESS + quickswap_done unconditionally
- inv_quickswap.js:541-543 success toast on quickswap_done
- Test output: HTTP 200 {'action': 'quickswap_done', 'smart_move': {'failures': {'240': '400: rejected by test'}, 'status': 'success'}} LOGS ['❌ Failed to slot Spool #240 -> XL-3' (ERROR), '⚡ Quick-swap: Spool #240 …' (SUCCESS)]

**Proof.** Scratch test test_quickswap_route_claims_done_when_toolhead_write_rejected FAILED.

**Fix direction.** Return a quickswap_failed action (non-2xx or explicit) carrying the failure string whenever smart_move.status != 'success' or failures is non-empty; the frontend's existing else branch already toasts it as an error.

**Regression test.** The scratch test above.

**Verifier.** routes_bindings.py:743-756 is unconditional. The I2 test FAILED as intended.

**Corrections.** Downgraded from red: it needs a Spoolman rejection.

#### I2-08 — Frontend 'status === success' consumers claim success and mutate the buffer despite per-spool failures

*Severity red → **orange** after review · verdict **CONFIRMED** · proof: code-trace-only · confidence high*

**Claim.** perform_smart_move answers {status:'success', failures:{…}} even when every write was rejected. Four frontend sites check only status:
- performContextAssign toasts 'Assigned N items!' and removes all N from the buffer.
- _doAssignFinalize toasts 'Assigned', splices the buffer, and in Swap mode pushes the displaced spool into the buffer although nothing moved.
- The spool-details Force Location Override toasts 'Location updated via override'.
None of them read failures.

**Evidence.**

- Backend shape (test output): POST /api/manage_contents add → HTTP 200 {'failures': {'42': '400: rejected by test'}, 'status': 'success'}
- inv_cmd.js:1870-1884 success branch removes every spoolId + _markAssignedOut
- inv_loc_mgr.js:1451-1475 success branch: buffer splice + swapDisplaced push
- inv_details.js:1226-1229 `res.status === 'success' || res.success` → success toast
- logic.py:717-724 status is always 'success' past the early exits

**Proof.** The response shape was proven by scratch test test_manage_contents_add_returns_status_success_with_failures (FAILED). The frontend branches were code-traced; no browser run, because the app's E2E tests are off-limits.

**Fix direction.** Either make the engine's status 'partial' / 'error' when failures is non-empty (and update the backend consumers), or have each consumer remove from the buffer only the spools absent from res.failures and toast the failure strings at 7 s.

**Regression test.** A JS-level test (or backend contract test) that a failures-bearing response leaves the failed ids in the buffer and raises an error toast.

**Verifier.** Re-read inv_cmd.js:1870-1885, inv_loc_mgr.js:1451-1475 and inv_details.js:1226-1229: each branches only on status/success. The backend returns status success with a non-empty failures map (logic.py:717-724); I2's test for that shape FAILED as intended. Frontend behaviour is code-traced; the lines are unambiguous.

**Corrections.** Downgraded from red: it needs a rejection. Overlaps I2-15 on the Force Location toast.

#### I2-09 — A failed slot unseat is not recorded, so the slot is double-booked while the move reports a clean success

*Severity red → **orange** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** When target_slot is occupied, perform_smart_move first clears the occupant's container_slot. If that write is rejected it only logs ERROR. It does not add to failures and does not stop, so the incoming spool is written into the same slot. The result is {status:'success', failures:{}}, which every consumer shows as a clean success, and two spools now claim one slot (the Group 13.2 collision class).

**Evidence.**

- logic.py:564-569 unseat failure → log only
- logic.py:571 incoming container_slot still set; logic.py:644-646 write proceeds
- Test output: RESULT {'status': 'success', 'failures': {}} SLOT2 [7, 42] LOGS ['❌ Failed to unseat Spool #7 from slot' (ERROR), '📦 #42 -> Dryer LR-MDB-1 [Slot 2]']

**Proof.** Scratch test test_slot_unseat_failure_is_not_reported_and_double_books_the_slot FAILED.

**Fix direction.** On an unseat failure, record failures[sid] and skip placing the incoming spool into that slot. Refusing is the single-occupancy analogue of the planned resident-eject rule.

**Regression test.** The scratch test above.

**Verifier.** logic.py:564-569 only logs the unseat failure, and 571 plus 644 still write the incoming spool into the slot. The I2 test FAILED as intended (SLOT2 [7, 42]).

**Corrections.** Downgraded from red: it needs a rejection of the unseat write.

#### I2-10 — Location delete reports success and orphans spools when the unassign writes fail

*Severity red → **yellow** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** Toolhead delete: the cascade collects per-spool errors, but the route still removes the row, saves locations.json and returns success True. The spool keeps location 'XL-1', which no longer exists. Non-toolhead delete (Box / Room / Cart): unassign failures go only to hub.log via logger.warning, never the Activity Log, and the route returns success True. The cascade's contents listing is also fail-open (a Spoolman error becomes 'no spools', so the delete runs having unassigned nothing).

**Evidence.**

- routes_locations.py:427-431 cascade then save, without checking errors
- routes_locations.py:443-447 errors logged but `success: True`
- routes_locations.py:452-464 `state.logger.warning(...)` only; routes_locations.py:477 success
- logic.py:1701-1705 non-strict listing (an exception only on the raise path; the fail-open reader returns [])
- Test output (toolhead): HTTP 200 {'cascade': {'errors': ['spool #99 unassign failed: 400: rejected by test'], ...}, 'success': True} SAVED_IDS ['XL-3', 'LR-MDB-1', ...] FINAL {99: {'location': 'XL-1'}}
- Test output (cart): HTTP 200 {'success': True} FINAL {51: {'location': 'CR-CT-1'}} LOGS ['🗑️ Deleted: CR-CT-1' only]

**Proof.** Scratch tests test_toolhead_delete_reports_success_and_orphans_a_spool_when_unassign_rejected and test_non_toolhead_delete_failure_never_reaches_the_activity_log, both FAILED (DELETE /api/locations via Flask, save_locations_list mocked). The fail-open listing is code-trace only.

**Fix direction.** Refuse the delete (or keep the row) when any referencing spool could not be re-homed, and return the errors; write each non-toolhead failure to the Activity Log at ERROR. Use the strict reader and fail closed.

**Regression test.** The two scratch tests.

**Verifier.** routes_locations.py:427-447 (toolhead) and 452-477 (non-toolhead) match. Both I2 tests FAILED as intended.

**Corrections.** The toolhead branch DOES write an ERROR Activity Log line (routes_locations.py:443-446); only the non-toolhead branch is logger-only. It is rare (a delete plus a rejection), so downgraded from red.

#### I2-11 — perform_undo reports success when restore writes fail; the frontend ignores the undo response

*Severity red → **yellow** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** perform_undo logs each failed restore at ERROR but always returns {success: True} and logs '↩️ Undid: moved …' as if it worked. triggerUndo, used by the deck button and CMD:UNDO, never reads the response: no toast on failure, and no feedback at all for 'Nothing to undo' (which is returned without any log line). The undo record is also pushed even when every write of the original move failed.

**Evidence.**

- logic.py:1837-1851 failures logged; logic.py:1887-1888 WARNING 'Undid' + `return {"success": True}`
- logic.py:1807 'Nothing to undo' returned with no Activity Log entry
- inv_cmd.js:1890 `fetch('/api/undo', {method:'POST'}).then(() => {...})`; callers inv_cmd.js:1421, inv_cmd.js:1454, dashboard.html:180
- logic.py:679 UNDO_STACK.append regardless of failures
- Test output: RESULT {'success': True} FINAL {42: {'location': 'CR-CT-2'}} LOGS ['❌ Undo: failed to restore Spool #42 → CR-CT-1' (ERROR), '↩️ Undid: moved #42 from CR-CT-1 -> CR-CT-2' (WARNING)]

**Proof.** Scratch test test_undo_reports_success_when_every_restore_write_fails FAILED. triggerUndo was code-traced.

**Fix direction.** Return success False (or partial) with the failed ids and word the summary line accordingly. Have triggerUndo toast res.msg on failure and on nothing-to-undo. Skip pushing an undo record for spools that never moved.

**Regression test.** The scratch test above.

**Verifier.** logic.py:1837-1851 logs failures, but 1887-1888 always returns success. triggerUndo (inv_cmd.js:1890) discards the response. The I2 test FAILED as intended.

**Corrections.** ERROR lines are written, so the failure is not invisible in the Activity Log. Downgraded from red.

#### I2-12 — Eject-all never handles require_confirm and never sends confirm_active_print, so a printing toolhead shows 'Cleared!'

*Severity orange → **orange** after review · verdict **CONFIRMED** · proof: code-trace-only · confidence high*

**Claim.** triggerEjectAll posts clear_location without confirm_active_print and never checks res.success or res.require_confirm. On a toolhead whose printer is active, the backend refuses with success False and require_confirm True, and the UI still toasts 'Cleared!'. There is no path to confirm.

**Evidence.**

- inv_loc_mgr.js:1647 body {action:'clear_location', location} — no confirm flag
- inv_loc_mgr.js:1649-1661 only skipped_slotted is inspected, otherwise 'Cleared!'
- routes_scan.py:237-246 active-print refusal shape

**Proof.** Read-only trace; not run in a browser.

**Fix direction.** Branch on require_confirm and confirm through mountOverlay (not a nested Bootstrap confirm), then retry with confirm_active_print; toast res.msg on !success.

**Regression test.** Playwright (with Derek's OK) or a JS unit test stubbing fetchT to return the require_confirm shape and asserting no 'Cleared!' toast.

**Verifier.** inv_loc_mgr.js:1647 sends no confirm flag, and 1649-1661 never checks success or require_confirm. The backend refusal shape is at routes_scan.py:237-246.

**Corrections.** The EJECT ALL badge renders only inside renderUnslotted (inv_loc_mgr.js:1144-1180). On a toolhead view the path is the CMD:EJECTALL scan (inv_cmd.js:1458), which hits the same handler.

#### I2-13 — deleteLoc ignores the 409 active-print refusal and the cascade errors

*Severity orange → **yellow** after review · verdict **CONFIRMED** · proof: code-trace-only · confidence high*

**Claim.** window.deleteLoc does fetch(DELETE).then(fetchLocations) and never reads the body or status. Deleting a toolhead on a printing printer returns 409 requires_confirm; fetch does not reject on 409, so the table silently refreshes and nothing happens, with no prompt. Cascade errors (I2-10) are likewise never shown.

**Evidence.**

- inv_loc_mgr.js:2219 `fetch(`/api/locations?id=${id}`, { method: 'DELETE' }).then(fetchLocations)`
- routes_locations.py:428-429 `return jsonify({"success": False, **result}), 409`
- grep: no other caller of the DELETE /api/locations endpoint in static/js or templates

**Proof.** Backend refusal shape read at routes_locations.py:428-429; frontend code-traced.

**Fix direction.** Parse the response. On 409 active_print, confirm and retry with ?confirm_active_print=1; on cascade.errors, toast at 7 s.

**Regression test.** JS or E2E check that a 409 produces a confirm and no silent refresh.

**Verifier.** inv_loc_mgr.js:2219: fetch(DELETE).then(fetchLocations) never reads the response. The 409 comes from routes_locations.py:428-429.

**Corrections.** Silent no-op, no data harm, so downgraded from orange.

#### I2-14 — Quick-Swap deposit drops the active-print confirm the user just gave, then reports 'Deposit failed'

*Severity orange → **yellow** after review · verdict **CONFIRMED** · proof: code-trace-only · confidence high*

**Claim.** quickSwapDeposit shows showConfirmOverlay, which probes the bound toolhead and shows the 'X is PRINTING' banner. When the user confirms, it posts LOC:box:SLOT:n to /api/identify_scan without confirm_active_print. The backend pre-flight checks the slot's bound toolhead and answers assignment_requires_confirm. The deposit handler has no branch for that and toasts '❌ Deposit failed: assignment_requires_confirm', so a deposit during a print is impossible.

**Evidence.**

- inv_quickswap.js:368-373 probe + banner; inv_quickswap.js:608-615 deposit uses that overlay
- inv_quickswap.js:617-623 POST body {text, source} — no confirm_active_print
- inv_quickswap.js:641-642 else → '❌ Deposit failed: ${body.action}'
- logic.py:426-442 pre-flight walks the slot binding
- Test output (same body, XL printing): HTTP 200 {'action': 'assignment_requires_confirm', 'active_print': {'printer_name': 'XL', 'state': 'PRINTING', 'toolhead': 'XL-3'}, ...} FINAL {'location': 'CR'}

**Proof.** The backend half was proven by the passing characterization test test_ok_deposit_scan_without_confirm_flag_is_refused_for_a_printing_bound_toolhead; the frontend omission was read.

**Fix direction.** Send confirm_active_print: !!stateInfo, the overlay's probe result. Handle assignment_requires_confirm by re-confirming, as inv_cmd.js:1522-1589 does. Note that after fix A this confirm must also reach the chained deploy.

**Regression test.** JS or E2E: deposit with a mocked active probe sends confirm_active_print=true.

**Verifier.** Same as I1-09; the backend half passed as a characterization test in my rerun.

**Corrections.** An error toast is shown, so it is not silent. Duplicate of I1-09.

#### I2-15 — Force Location Override has no active-print path: no probe, no confirm flag, refusals shown as errors

*Severity orange → **yellow** after review · verdict **PLAUSIBLE** · proof: code-trace-only · confidence medium*

**Claim.** The spool-details override posts manage_contents 'add' or 'force_unassign' with no confirm_active_print and runs no printer-state probe. Moving onto, or force-unassigning from, a printing toolhead returns a requires_confirm shape, which the handler shows as an error toast of the backend message with no way to proceed. Combined with I2-08, a rejected write shows 'Location updated via override'.

**Evidence.**

- inv_details.js:1211-1216 payload {action, location, spool_id, origin} — no confirm_active_print
- grep of inv_details.js: no confirm_active_print and no fetchPrinterStateForToolhead
- inv_details.js:1226-1232 success only on status/success, else showToast(res.msg, 'error')
- routes_scan.py:317-324 force_unassign requires_confirm shape; logic.py:436-442 add requires_confirm shape

**Proof.** Read-only trace.

**Fix direction.** On a requires_confirm response, show a mountOverlay confirm and retry with confirm_active_print; treat non-empty failures as an error.

**Regression test.** JS or E2E: override onto a printing toolhead yields a confirm, then a successful retry.

**Verifier.** inv_details.js:1211-1232 sends no confirm and treats any non-success as an error. The filter at :954 hides tool/mmu/direct-load rows but not Printer rows (dev CORE1 is Printer, Max 1, a printer_map key), and it allows Dryer Boxes. Code-trace only; not run.

**Corrections.** Moving onto a Dryer Box never triggers the refusal at all: the pre-flight cannot see an auto-picked slot (my V8). The refusal UX gap is real only for Printer-row or force_unassign targets.

#### I2-16 — Candidate for the eject no-ops: chained Bootstrap confirms can be silently dropped, leaving an invisible armed confirm

*Severity orange → **orange** after review · verdict **PLAUSIBLE** · proof: browser-run · confidence medium*

**Claim.** An eject from the Location Manager can walk up to three Bootstrap #confirmModal prompts:
1. 'Eject spool #N?'
2. The backend active-print refusal.
3. For a toolhead spool with no physical_source, a second refusal worded 'Spool is already in a room. Confirm true unassign to nowhere?', which is wrong for a toolhead.
Each later prompt is raised from the previous one's callback: confirmAction calls closeModal (Bootstrap hide()), then the callback, then an async fetch, then requestConfirmation → show(). In a standalone Bootstrap 5.3.0 page with the same 'modal fade' markup, show() issued 0, 50 or 120 ms after hide() was dropped (not visible, no shown event), while 200 ms and more worked; Bootstrap's own show() returns while _isTransitioning. requestConfirmation still sets pendingConfirm and activeModal after a dropped show(), so the user sees nothing and the eject does nothing. The hidden.bs.modal handler releases the scan gate 400 ms later but leaves pendingConfirm armed, so a later CMD:CONFIRM scan would fire that stale eject. What is NOT established: that Derek's round-trips were under ~150 ms. The unassign re-prompt skips the PrusaLink probe, making it the likeliest to be fast. Bootstrap is neither ruled in nor ruled out as the cause.

**Evidence.**

- inv_loc_mgr.js:1500 first confirm → doEject; inv_loc_mgr.js:1530-1543 chained requestConfirmation from the fetch callback
- inv_core.js:1227 requestConfirmation sets pendingConfirm + activeModal after show(); inv_core.js:1228 confirmAction: closeModal (hide) then pendingConfirm()
- inv_core.js:1566-1581 hidden handler releases only activeModal; inv_cmd.js:1456 CMD:CONFIRM fires a pending confirm
- templates/components/modals_core.html:18 `class="modal fade"`; scripts.html:114-118 default Modal options; Bootstrap 5.3.0 js/src/modal.js show(): `if (this._isShown || this._isTransitioning) { return }`
- Browser run: {'delayMs': 0, 'visible': False, 'shownEvents': 0} {'delayMs': 50, 'visible': False} {'delayMs': 120, 'visible': False} {'delayMs': 200, 'visible': True, 'shownEvents': 1} … {'delayMs': 800, 'visible': True}
- Backend chain (test run): R1 {'confirm_type': 'active_print', 'require_confirm': True} R2 {'msg': 'Spool is already in a room. Confirm true unassign to nowhere?', 'require_confirm': True} R3 {'success': True}; logic.py:1518 probe skipped once confirmed; routes_scan.py:309-310 message

**Proof.** The Bootstrap drop was reproduced with scratch bs_modal_race.py (Playwright + Bootstrap 5.3.0 from the CDN, standalone page, NOT the FCC app, no container). The backend confirm chain was proven by the passing scratch test test_ok_eject_from_printing_head_without_home_needs_two_backend_confirms. The link to Derek's actual no-op is inference.

**Fix direction.** Move the eject confirms to mountOverlay per project convention, or defer a chained requestConfirmation until hidden.bs.modal. Clear pendingConfirm whenever a show is dropped. Let the backend accept both flags in one prompt, or word the unassign prompt for a toolhead. Repro on dev with DevTools Network open, and record the remove round-trip times.

**Regression test.** Playwright against a stubbed page (or the app, with Derek's OK): a chained confirm raised within 100 ms of dismissal must become visible.

**Verifier.** Mechanism verified against the app code. inv_core.js:1226-1228 calls hide() and then runs the callback that raises the next confirm. inv_core.js:1557-1560 documents the ~155 ms re-show timing itself. Bootstrap 5.3 show() returns early while _isTransitioning. A different group's in-app run (eject-reconfirm-race/sweep_baseline.txt, read but NOT re-run by me) shows the second show() early-returning and staying invisible for hide-to-show at 14-142 ms, visible from 161 ms, and a stale CMD:CONFIRM firing the eject. Its latency file shows get_spool median 15.5 ms and a paired p90 of 146.7 ms. I did not re-run bs_modal_race.py (it needs the CDN and a browser).

**Corrections.** Neither ruled in nor out as the cause of Derek's no-op: the timing on his session is unknown, and triage candidate (a), a hung refreshManageView, was not tested by anyone in this group.

#### I2-17 — Moving a spool OFF a printing toolhead is never guarded (single-move path)

*Severity yellow → **yellow** after review · verdict **CONFIRMED** · proof: test-run · confidence medium*

**Claim.** perform_smart_move's active-print pre-flight checks only the destination (and a bound slot's toolhead). Moving a spool that is loaded on a printing toolhead to a Room or box, via buffer assign, manage_contents add, force override or Quick-Swap of a ghost deployed elsewhere, raises no confirm. perform_smart_eject and perform_force_unassign do guard the spool's current location. The gap is acknowledged in a plan_bulk_move comment.

**Evidence.**

- logic.py:426-442 guard checks only target / bound_th
- logic.py:1516-1526 eject guards current_location
- logic.py:928-929 'The single-move path guards only the DEST.'
- inv_quickswap.js:368 overlay probes only opts.toolhead (the destination)
- Test output: RESULT {'status': 'success', 'failures': {}} FINAL {'location': 'CR', 'extra': {'physical_source': 'LR-MDB-1', ...}} with XL printing

**Proof.** Scratch test test_move_off_a_printing_toolhead_is_not_guarded FAILED. The final extra also shows I2-03: physical_source kept.

**Fix direction.** Product decision: also probe each moving spool's current toolhead, excluding the auto-deploy / Smart Load internal hops once they forward the caller's confirm.

**Regression test.** The scratch test above.

**Verifier.** logic.py:426-442 guards only the destination; the gap is acknowledged at logic.py:928. The I2 test FAILED as intended.

**Corrections.** None.

#### I2-18 — Weigh-out archive: the fire-and-forget force_unassign can silently leave an archived spool on a printing toolhead

*Severity yellow → **info** after review · verdict **REFUTED** · proof: code-trace-only · confidence low*

**Claim.** When the frontend's own verdict (remainingAfter from details.initial) says archive, it sends archived:true and then fires force_unassign, ignoring the result. update_spool clears location only when its own effective remaining is ≤ 0. If the two disagree (different effective initial weight), location is not cleared, and force_unassign on a printing toolhead returns requires_confirm, which is ignored, leaving an archived spool loaded.

**Evidence.**

- inv_weigh_out.js:383-389 local autoArchive verdict; inv_weigh_out.js:415-417 updates.archived = true
- inv_weigh_out.js:489-494 `.then(() => finalize()).catch(() => finalize())`
- spoolman_api.py:212-213 early return when remaining > 0; spoolman_api.py:217-227 location '' only past that check

**Proof.** Latent edge case; not run. In the common case the backend already unassigns, so the ignored call is harmless.

**Fix direction.** Check the force_unassign response; on requires_confirm, prompt; or have /api/spool/update own the unassign when archived is explicitly set.

**Regression test.** Backend test: /api/spool/update with archived:true and remaining > 0 on a toolhead spool, then force_unassign during a print → assert the frontend contract surfaces it.

**Verifier.** The disagreement premise does not hold. The frontend resolves initial as Number(d.initial_weight) || Number(d.filament?.weight) || 0 (inv_weigh_out.js:47, :549), the same fallback update_spool uses (spoolman_api.py:204-205, 272-273). When both sides say archive, update_spool already sets location '' (217-227), so the ignored force_unassign acts on an unassigned spool whose active-print check cannot fire. The only divergence, initial_weight exactly 0, runs the other way: the backend archives, the frontend does not.

**Corrections.** Not an archived-spool-left-on-a-printing-head path as stated.

**Ruled out (I2).**

- *execute_bulk_move blaming spools on the stale LAST_SPOOLMAN_ERROR global* — Fixed: logic.py:1085-1088 reads the per-spool failures map captured next to each write. The control test test_ok_bulk_move_tally_is_honest_when_the_readback_works passed with err='400: rejected by test' per spool.
- *Bulk move dropping the active-print confirm on an internal hop* — commit_bulk_move_session re-plans with the confirm (logic.py:1438) and passes it to execute_bulk_move → perform_smart_move (logic.py:1462, 1042-1044), with auto_deploy=False, so no chain hop exists and baseline A cannot reach bulk move.
- *A bogus undo record pushed for a move refused with requires_confirm* — _perform_smart_move_impl returns at logic.py:437-442, before UNDO_STACK.append at logic.py:679.
- *manage_contents 'remove' → 'Ejected' toast lying about a refused or failed eject* — routes_scan.py:301-314 maps each perform_smart_eject shape correctly and returns success True only for `result is True`; doEject toasts 'Ejected' only past `!res.success` (inv_loc_mgr.js:1545-1550). Its problem is the chained-confirm delivery (I2-16), not trust.
- *perform_smart_eject detaching the single-slot box before the return write fails* — Real (logic.py:1531-1539 runs before logic.py:1617), but already filed in Feature-Buglist.md (PolyDryer entry, item 3). Not new.
- *Weigh-out force_unassign in the normal archive case* — update_spool's auto-archive already sets location '' when remaining ≤ 0 (spoolman_api.py:217-227), so ignoring that result is harmless except for the edge case in I2-18.
- *print_monitor.py treating a move or eject refusal as success* — It does not call any of the audited engines (grep for smart_move / smart_eject / force_unassign / update_spool / requires_confirm in print_monitor.py returned nothing).
- *Bootstrap as the established cause of Derek's eject no-ops* — NOT ruled out and NOT ruled in. Proven: Bootstrap 5.3.0 drops a show() within ~120 ms of hide(), and eject chains confirms that way. Unproven: Derek's round-trip latency. The other triage candidates (the hung refreshManageView inflight guard, stale render hash, and slot/ghost inconsistency now made more likely by I2-03) were outside this audit's scope and not tested.

**Checked correct (I2).**

- routes_scan.py:294-314 manage_contents 'remove': handles the requires_confirm dict, the 'REQUIRE_CONFIRM' string, True, and everything else as an error
- routes_scan.py:315-327 manage_contents 'force_unassign': the requires_confirm dict, truthy True, and False are each handled distinctly
- routes_scan.py:1125-1142 slot-QR: forwards confirm_active_print and passes requires_confirm through as assignment_requires_confirm
- inv_cmd.js:1522-1589 scan assignment_requires_confirm → mountOverlay → replays the scan with confirm_active_print:true
- routes_scan.py:369-387 /api/bulk_move: passes require_confirm, blocked, capacity and nothing-to-move through faithfully
- logic.py:1048-1055 execute_bulk_move: passes the engine's requires_confirm and error shapes through
- logic.py:1421-1469 commit_bulk_move_session: re-plans live, handles require_confirm / blocked / empty, serialized by lock
- logic.py:1281-1303 process_bulk_move_scan CMD:DONE: a partial failure (success False, no msg) is turned into an error
- routes_scan.py:441-458 bulk_move_session set_dest / commit passthrough
- inv_cmd.js:437-478 commitBulkMove: require_confirm re-renders the in-panel confirm; a partial tally is toasted honestly
- logic.py:1063-1088 bulk tally is correct when the readback succeeds (control test passed)
- print_deduct.py:253-262 /api/smart_move forwards confirm_active_print
- inv_cmd.js:1862-1868 performContextAssign: requires_confirm → overlay → retry with confirm and the same spool subset
- inv_loc_mgr.js:1255-1282, 1296-1326, 1443-1450 doAssign probe → _confirmActivePrintAssign → _doAssignFinalize(confirm=true), with a backend safety-net retry
- inv_loc_mgr.js:1530-1548 doEject distinguishes the active-print and unassign confirms and forwards both flags on retry
- routes_bindings.py:656-659 and routes_bindings.py:743-746 forward the confirm on the first hop (hard-coded True after the UI overlay)
- logic.py:1686-1695 perform_toolhead_delete_cascade refuses before any write; routes_locations.py:428-429 maps that to 409
- logic.py:1516-1526 and logic.py:1781-1789 eject and force-unassign guard the spool's CURRENT location
- logic.py:1328-1333 bulk-move destination scan: require_confirm is logged and the session stays committable
- print_monitor.py: no consumers of the audited engines

**Open questions (I2).**

- I2-01: what should 'Return' mean for a spool whose source slot is bound to the same toolhead — staged back in the box (auto_deploy=False) or something else? The fix should land before or together with planned fix A, because A turns today's accidental mid-print 'stays in box' into a re-deploy onto a printing head.
- Planned Smart Load 'no home → Room' fallback: perform_smart_eject hard-codes Unassigned for printer_map toolheads (logic.py:1627-1628), while get_room_from_location on a toolhead already walks to the printer's room (logic.py:1483-1487, resolve_room). The fix must bypass that printer special-case, and the eject's REQUIRE_CONFIRM must not be what the Smart Load hop checks.
- I2-02 reproducibility depends on Spoolman's /api/v1/spool list order (ghost listed before the direct resident); not verified against a live Spoolman.
- I2-03 blast radius: how many dev/prod spools already carry a stale physical_source from earlier moves off a toolhead? A read-only Spoolman query could count them; not run (no live access in this audit).
- I2-16: were Derek's manage_contents remove round-trips under ~150 ms? Capture DevTools Network timings in the repro before attributing the no-op to the dropped Bootstrap re-show.
- Should clear_location on a Room offer ONE batch unassign confirm (spools in a room have no fallback destination), or skip those spools with an explicit count?

### I5 — double-occupancy-paths

Q1: Bug B is confirmed as the cause for Derek's flow, proven at the endpoint level. Clicking a printer-status toolhead opens the toolhead's Location Manager, which is a list view. From there all three affordances end with a second spool on the head during a print, and none of them produces an error: the DEPOSIT HERE card (doAssign -> confirm overlay -> _doAssignFinalize with confirm -> /api/manage_contents add), a scan of that view's LOC QR with a spool held (L124 -> /api/smart_move -> confirm retry), and a Quick-Swap tile, which always sends confirm_active_print=True. Every path reaches logic.py:508 with confirm=True, perform_smart_eject returns its truthy active-print dict, and the incoming spool is written anyway.

Q2: 8 more paths are proven hermetically:
- **Ghost trail (idle printer):** a toolhead->toolhead move leaves physical_source=<old head>. The real matcher lists that spool as a ghost resident of the old head. Smart Load's eject then "returns" it onto the target. The eject succeeds, so none of the planned fixes cover this.
- **Eject return-home:** lands on an occupied toolhead.
- **Idle box-slot chain with a homeless resident:** two spools on the head, and the result still reports the deploy.
- **Printer-row target (e.g. dev "XL"):** no confirm is ever asked. Smart Load's flat prefix matcher mass-ejects every XL-n spool when idle, and stacks spools on XL during a print.
- **Multi-spool /api/smart_move:** the L124 guard is frontend-only.
- **Auto-unarchive:** restores fcc_pre_archive_location onto an occupied head.
- **Undo:** restores a spool onto an occupied head.
- **Fixing bug A without B:** turns today's silent skip into double occupancy.

Code-trace only: the wizard and Force Location both offer Printer-type rows (CORE1). Ruled out: bulk move, print_monitor, print_deduct writes, the identify_scan location branch, Quick-Swap deposit during a print, and the confirmed slot-QR scan (bug A currently prevents the toolhead write there).

Q3:
- **Deduct:** two direct spools on a head means neither is charged (the position is warned and skipped), and the 22.3 swap snapshot reads None. A toolhead ghost trail double-charges a spool that sits on another head.
- **Eject:** acts on the spool you clicked, but the Group 20.2 box detach fires for the other spool's box too. Ejecting a homeless resident on a printing head takes 3 round-trips, each opening a new Bootstrap confirm from inside the previous one's callback.
- **Displays:** the status bar shows only items[0]. Quick-Swap Return acts on residents[0].
- **Idle Smart Load:** ejects both residents, so the head self-heals.

Incidental: Quick-Swap Return to a bound slot immediately redeploys the same spool, because the chain runs and every return test mocks the engine. Also, the established test file grew from 6 to 10 failing tests during this session (edited concurrently). logic.py line numbers are unchanged, and I edited no repo file.

#### I5-1 — Derek's flow confirmed: toolhead view -> assign (deposit card or LOC-QR scan) -> endpoint -> Smart Load bug B -> two spools, reported as success

*Severity red → **red** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** Printer-status toolhead click opens the toolhead Location Manager (list view). Both the DEPOSIT HERE card and a scan of that view's LOC QR with a held spool reach perform_smart_move with confirm_active_print=True. The resident eject at logic.py:508 drops the confirm, perform_smart_eject returns its truthy active-print dict, and the incoming spool is still written. The endpoint returns status success with empty failures, so the UI toasts 'Assigned'. The Activity Log shows 'Smart Load: Ejecting #rid' although nothing was ejected.

**Evidence.**

- inv_printer_status.js:458-459 data-toolhead click -> window.openManage(tid)
- inv_loc_mgr.js:172 isGrid false for Tool Head (Max 1) -> renderList; :1015 depositCard.onclick = doAssign(locId, item.id, null)
- inv_loc_mgr.js:1255-1277 doAssign: toolhead target -> fetchPrinterStateForToolhead -> _confirmActivePrintAssign; :1322-1326 proceed -> _doAssignFinalize(..., true)
- inv_loc_mgr.js:1420-1433 POST /api/manage_contents {action:'add', location, spool_id:'ID:'+spool, slot, origin, confirm_active_print}; :1451-1452 status success -> showToast('Assigned')
- routes_scan.py:328-334 action add -> logic.perform_smart_move(loc_id, [spool_id], target_slot=slot_arg, origin, confirm_active_print)
- inv_loc_mgr.js:1127-1129 deposit QR = 'LOC:'+locId; inv_cmd.js:1605-1636 L124 -> performContextAssign(res.id, null, false, [top.id]); :1862-1867 requires_confirm -> _confirmActivePrintScan -> retry with true; print_deduct.py:253-262 /api/smart_move forwards the flag
- logic.py:426 pre-flight skipped when confirmed; :498-512 Smart Load; :504 WARNING 'Ejecting #rid' logged before the eject; :508 `if perform_smart_eject(rid):` with no confirm; logic.py:1518-1526 active-print dict returned (truthy); :615 incoming written to the toolhead

**Proof.** Scratch test_REPRO_manage_contents_add_exact_doAssignFinalize_payload_during_print (Flask test client, exact frontend payload, XL printing): "manage_contents add -> {'failures': {}, 'status': 'success'} | XL-1 direct: [42, 99]". test_REPRO_smart_move_confirm_retry_payload_during_print: "smart_move first -> requires_confirm | retry -> {'failures': {}, 'status': 'success'} | XL-1: [42, 99]". The frontend half of the chain is code-trace only (no browser run is allowed).

**Fix direction.** Planned fix B: forward confirm_active_print (and a resolved homeless-resident destination) into the resident eject, and branch on its real return value (True only), never on truthiness. Log 'Ejecting #rid' only after the eject succeeds.

**Regression test.** Flask-client test posting the exact _doAssignFinalize body (action add, spool_id 'ID:42', slot null, origin buffer, confirm_active_print true) against a printing head with a homed resident. Assert the resident leaves and the head holds exactly one spool. Add the same test for the /api/smart_move confirm-retry body.

**Verifier.** Re-read the chain. inv_loc_mgr.js:1006-1015: the deposit card calls doAssign. 1255-1281: a toolhead target is probed. 1322-1326 and 1432 forward the confirm to /api/manage_contents add (routes_scan.py:328-334), which reaches logic.py:508. The I5 REPRO tests passed in my rerun (20 passed). This matches Derek's words ('toolhead locations accessed from the print status bar ... assign it directly' + '2 spools attached to one toolhead').

**Corrections.** This is baseline B plus its reachability, not a new defect. Dev no longer shows a doubled head (analysis: 'TOOLHEADS WITH >1 DIRECT SPOOL: {}'), so the session state cannot be inspected now.

#### I5-2 — Quick-Swap on the toolhead view ALWAYS double-occupies during a print (the endpoint hard-codes confirm_active_print=True)

*Severity red → **red** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** The Quick-Swap grid renders on the same toolhead manage view. Its confirm overlay only shows a warning banner and never blocks. /api/quickswap then calls perform_smart_move with confirm_active_print=True unconditionally. Whenever the head is loaded and the printer is printing, bug B leaves both spools on the head, while the UI toasts success and the overlay text promises the old spool 'gets auto-returned'.

**Evidence.**

- inv_loc_mgr.js:197 openManage -> renderQuickSwapSection(loc)
- inv_quickswap.js:368-378 active-print probe only builds a banner; :496 yes.onclick -> onConfirm; :657-692 quickSwapTap -> performSwap; :689-690 body text 'Any spool currently on the toolhead gets auto-returned'
- routes_bindings.py:743-746 perform_smart_move(toolhead, [spool_id], target_slot=None, origin='quickswap', confirm_active_print=True)
- logic.py:508 resident eject without confirm

**Proof.** Scratch test_REPRO_quickswap_during_print_always_double_occupies: "quickswap -> 200 quickswap_done {'failures': {}, 'status': 'success'} | XL-3: [99, 240]".

**Fix direction.** Covered by planned fix B, since the confirm reaches the engine. Also make api_quickswap report the smart_move failures and whether the resident actually left, instead of an unconditional quickswap_done plus a SUCCESS log (routes_bindings.py:747-756).

**Regression test.** Flask-client /api/quickswap with the printer PRINTING and a homed resident. Assert the head holds only the incoming spool and the resident is back in its box.

**Verifier.** routes_bindings.py:743-746 always passes confirm True, and logic.py:508 drops it. test_REPRO_quickswap_during_print_always_double_occupies passed in my rerun.

**Corrections.** 'Always' means whenever the user confirms a Quick-Swap onto a loaded printing head. It belongs to the baseline B family and is covered by the planned fix B.

#### I5-3 — A toolhead-valued ghost trail makes Smart Load 'eject' a spool from ANOTHER head back onto the target, giving two spools on an idle printer. Not covered by the planned fixes.

*Severity red → **red** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** Moving a spool directly from one toolhead to another stores physical_source=<old head>. The real location matcher treats that as a GHOST resident of the old head, and Smart Load iterates ghosts as residents. perform_smart_eject then 'returns' the spool to its saved source, which is the head being loaded, and returns True. The incoming spool is written there too. Result: two direct spools on the target, and the other head silently empties in the database. No active print or homeless resident is involved, so forwarding confirms, the homeless->room fallback, and hard-fail refusal all leave this open.

**Evidence.**

- logic.py:585-592 PRINTER MOVE: not already here -> new_extra['physical_source'] = current_loc (the old toolhead)
- spoolman_api.py:1470-1479 physical_source == target -> match, is_ghost=True
- logic.py:500 residents = spoolman_api.get_spools_at_location(target) (includes ghosts); :501-508 each non-incoming resident is passed to perform_smart_eject
- logic.py:1548-1619 saved_source used as the return destination with no occupancy or type check -> update_spool(location=saved_source) -> return True
- Also reachable via Quick-Swap of a slot whose spool is currently ghost-deployed on a different head: find_spool_in_slot includes ghosts (logic.py:2059-2074), then logic.py:591 stores that head as physical_source (code-trace)

**Proof.** Scratch test_REPRO_ghost_trail_resident_is_returned_ONTO_the_target_idle_printer uses the REAL spoolman_api matcher over an in-memory Spoolman: "after XL-1->XL-2 physical_source= XL-1 | XL-1 residents seen: [(77, True)] | r2= {'status': 'success', 'failures': {}} | XL-1: [42, 77] XL-2: []". Whether Derek's session had such a trail is NOT established.

**Fix direction.** In Smart Load, only eject DIRECT residents (is_ghost False). For a ghost resident, clear its stale physical_source/physical_source_slot instead of calling perform_smart_eject. Never store a toolhead or single-occupancy location as physical_source (keep the original box trail or clear it). perform_smart_eject return-home should refuse or redirect when saved_source is a single-occupancy location.

**Regression test.** Hermetic test with the real get_spools_at_location_detailed: move #77 XL-1->XL-2, then load #42 onto XL-1. Assert XL-1 == [42] and #77 is still on XL-2.

**Verifier.** Independently re-proved. My test_V4: after XL-1 -> XL-2, 77 stores ('XL-2', 'XL-1', '', ''). Loading 42 onto XL-1 then gives XL-1=[42, 77], XL-2=[]; logs 'Smart Load: Ejecting #77 from XL-1' then 'Returned #77 -> XL-1'. Not covered by any planned fix: the eject returns True.

**Corrections.** Missed side effect: the same Smart Load DETACHED XL-2's single-slot box (detach calls=[call('XL-2')]), because perform_smart_eject detaches at the ghost's real location (logic.py:1531-1533). The precondition is absent on dev today ('TOOLHEAD-valued physical_source: []'), but a head-to-head move is an ordinary action.

#### I5-4 — Eject return-home lands on an occupied toolhead (no destination occupancy check)

*Severity orange → **orange** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** A direct eject (Location Manager eject, CMD:EJECT, Eject All) of a spool whose physical_source is a toolhead writes it onto that toolhead even when another spool is loaded there. The endpoint returns success.

**Evidence.**

- routes_scan.py:294-314 remove -> perform_smart_eject
- logic.py:1574-1619 return-home write with no check of what is at saved_source
- routes_scan.py:256 Eject All calls the same function

**Proof.** Scratch test_REPRO_eject_return_home_lands_on_an_occupied_toolhead: "eject -> {'success': True} | XL-1: [42, 99]". It shares I5-3's precondition (a toolhead-valued physical_source).

**Fix direction.** Same root as I5-3. Additionally, when the return destination is a single-occupancy location that already holds a spool, fall back to the room or Unassigned with a warning.

**Regression test.** Hermetic /api/manage_contents remove for a spool on XL-2 with physical_source XL-1 while XL-1 is occupied. Assert XL-1 still holds exactly one spool.

**Verifier.** logic.py:1574-1619 performs no occupancy check at saved_source. The REPRO test passed in my rerun.

**Corrections.** Same root as I5-3 and I2-02 (toolhead-valued physical_source).

#### I5-5 — Targeting a Printer row (e.g. dev 'XL', Max 0) needs no confirm; idle it mass-ejects every toolhead of that printer, and during a print it stacks spools on the row

*Severity orange → **orange** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** 'XL' is Type Printer, so Smart Load treats it as single-occupancy. It is not a printer_map key, so both the UI pre-probe and the backend pre-flight return 'not active' and never ask for a confirm. Smart Load's residents query uses the flat first-segment prefix, so it returns every spool on XL-1..XL-n and ejects them all. During a print those ejects are refused (truthy dict) and every buffered spool lands on 'XL', because L124 does not classify a 'printer' type with Max 0 as single-occupancy. Dev data confirms XL is a Printer row with Max 0 and toolheads XL-1..XL-5.

**Evidence.**

- logic.py:488 is_toolhead includes 'Printer'; :500 residents via get_spools_at_location(target)
- spoolman_api.py:1467 location_prefix(sloc) == target -> XL-1..XL-5 match 'XL'
- logic.py:29-31 printer_map.get('XL') None -> no active-print info; routes_bindings.py:134-137 /api/printer_state -> known false (frontend pre-probe null, inv_loc_mgr.js:1264-1266)
- inv_cmd.js:1623-1635 L124 single-occupancy test misses a 'printer' type with Max 0 -> whole buffer
- inv_details.js:951-953 Force Location filter excludes tool/mmu/direct load but not printer
- dev data/locations.json (read-only): 'XL | Printer |Max 0 | ths [XL-1..XL-5]'

**Proof.** Scratch test_REPRO_printer_row_target_idle_mass_ejects_every_toolhead: "XL row idle -> {'status': 'success', 'failures': {}} | XL-1..3: [[], [], []] | LR-MDB-1: [10, 11, 12] | XL: [42]". test_REPRO_printer_row_target_during_print_stacks_without_any_confirm: "XL row printing -> {'status': 'success', 'failures': {}} | XL: [42, 43] | XL-1: [10]". UI reachability (XL row deposit card, LOC:XL scan, Force Location) is code-trace.

**Fix direction.** Refuse spool placement on a Printer row that is not itself a printer_map toolhead (Max 0 / has toolheads[]). Scope Smart Load's resident query to exact-location matches, never the prefix matcher. Add Printer rows with toolheads to the wizard, Force Location and L124 filters.

**Regression test.** Hermetic perform_smart_move('XL', [42]) with spools on XL-1..3. Assert it is refused (or ejects nothing) and no XL-n spool moves.

**Verifier.** Re-proved. My V6b (idle): {10: ('LR-MDB-2', ...), 11: ('LR-MDB-2', ...), 42: ('XL', ...)}. My V6 (XL printing): success with no confirm; 42 at 'XL', 10 and 11 still on XL-1/XL-2. location_prefix is the flat first segment (locations_db.py:543), and 'XL' is not a printer_map key (logic.py:29-31). Dev data read-only: XL = ('Printer', '0', [XL-1..XL-5]); CORE1 = ('Printer', '1', ['CORE1']).

**Corrections.** UI reachability (Force Location filter inv_details.js:954; the renderList deposit card for a non-grid row, inv_loc_mgr.js:172, 1006-1015) is code-trace only.

#### I5-6 — Idle box-slot assign chains onto a bound toolhead whose resident has no home, giving two spools plus an 'auto_deployed_to' claim

*Severity orange → **orange** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** With no print running, any assign into a bound dryer-box slot chains a toolhead move. That includes a slot QR scan, Quick-Swap deposit, a Location Manager grid slot tap, or manage_contents add with a slot. If the toolhead's resident has no physical_source, perform_smart_eject returns the truthy 'REQUIRE_CONFIRM', so both spools stay on the head and the result still reports the deploy. Derek's manually resynced dev residents could be homeless like this; that is inference only.

**Evidence.**

- logic.py:694-707 chain -> perform_smart_move(bound_toolhead, ...)
- logic.py:1624-1636 on a printer_map head target_loc '' -> return 'REQUIRE_CONFIRM'
- logic.py:725-726 auto_deployed_to set on any non-None result
- inv_quickswap.js:617-624 deposit posts LOC:box:SLOT:n; routes_scan.py:1126-1129

**Proof.** Scratch test_REPRO_idle_box_slot_assign_chain_with_homeless_resident: "box slot 3 -> {'status': 'success', 'failures': {}, 'auto_deployed_to': 'XL-3'} | XL-3: [99, 240]".

**Fix direction.** Planned fix B (homeless resident -> printer's room or Unassigned with a warning), plus the planned gating of auto_deployed_to on a real deploy.

**Regression test.** Hermetic box-slot move into a slot bound to XL-3 with a homeless resident on XL-3. Assert XL-3 holds only the incoming spool, the resident is in the room or Unassigned, and a WARNING names it.

**Verifier.** logic.py:1627-1636 gives REQUIRE_CONFIRM for a homeless printer_map resident, and 725-726 still sets auto_deployed_to. The REPRO test passed.

**Corrections.** Duplicate of established tests test_smart_load_resident_without_a_home_does_not_double_occupy and section A. Dev today has no homeless toolhead spool.

#### I5-7 — Fix-ordering hazard: shipping fix A (forward confirm into the chain) without fix B converts the silent skip into double occupancy

*Severity orange → **orange** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** Today bug A actually PREVENTS double occupancy on the confirmed box-slot paths: the chained toolhead move bounces off the guard. Forwarding the confirm alone lets the chain reach Smart Load, where bug B leaves the resident on the printing head.

**Evidence.**

- logic.py:703-707 chained call has no confirm today
- inv_cmd.js:1531-1546 confirmed slot-QR replay; routes_scan.py:1125-1129
- logic.py:508 resident eject drops the confirm

**Proof.** Scratch test_REPRO_fixing_A_alone_turns_the_silent_skip_into_double_occupancy wraps the module-global perform_smart_move so nested calls carry confirm=True: "fix-A-only -> {'status': 'success', 'failures': {}, 'auto_deployed_to': 'XL-3'} | XL-3: [99, 240]".

**Fix direction.** Land A and B in the same commit and pin the combined shape.

**Regression test.** Confirmed box move (XL printing) into a slot bound to a loaded XL-3 with a homed resident. Assert XL-3 == [incoming] and the resident is back in its box.

**Verifier.** With the confirm forwarded, the chain reaches Smart Load, and logic.py:508 still drops the confirm, so the truthy dict leaves both spools on the head. The REPRO test passed ('XL-3: [99, 240]').

**Corrections.** Sibling of I1-02: fixes A, B and Return's auto_deploy=False must land together.

#### I5-8 — /api/smart_move places several spools on one toolhead; the L124 single-occupancy guard exists only in the frontend

*Severity yellow → **yellow** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** The backend accepts spools:[a,b] onto a toolhead and writes both. Only inv_cmd.js's location-scan branch trims the list, and its type heuristic misses Printer rows with blank or 0 Max Spools.

**Evidence.**

- print_deduct.py:253-262 no occupancy check
- logic.py:523-615 per-spool loop writes every spool
- inv_cmd.js:1623-1633 frontend-only trim

**Proof.** Scratch test_REPRO_smart_move_endpoint_multi_spool_onto_one_toolhead_idle: "smart_move [42,43] -> {'failures': {}, 'status': 'success'} | XL-1: [42, 43]".

**Fix direction.** Reject (or trim to the first spool with a warning) a multi-spool move whose target is single-occupancy, inside perform_smart_move (the same rule plan_bulk_move already applies).

**Regression test.** Hermetic /api/smart_move with two spools to XL-1. Assert it is refused or XL-1 holds one.

**Verifier.** print_deduct.py:253-262 and logic.py:523-615 have no single-occupancy check. The REPRO test passed. The frontend L124 guard (inv_cmd.js:1623-1633) covers the tool/mmu/direct-load types.

**Corrections.** From the UI it is reachable only through Printer rows (I5-5); otherwise only via a direct API call.

#### I5-9 — Auto-unarchive restores a spool onto the toolhead it was archived from, even if that head is now occupied

*Severity orange → **orange** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** A print deduct can drive a loaded spool to 0 g. Auto-archive then plants fcc_pre_archive_location=<toolhead> and unassigns it. After the user loads a new spool, any later weight correction on the old spool (weigh-out, quick-weigh, wizard, /api/spool/update) auto-unarchives it and PATCHes location=<toolhead>. There is no occupancy check and no Smart Load, and the only signal is an INFO log.

**Evidence.**

- spoolman_api.py:217-227 breadcrumb plus location ''
- spoolman_api.py:282-287 location = fcc_pre_archive_location
- spoolman_api.py:337-343 INFO 'Auto-unarchived ... restored to'
- print_deduct.py:336 deduct writes used_weight through update_spool

**Proof.** Scratch test_REPRO_auto_unarchive_restores_location_onto_an_occupied_toolhead drives the real update_spool with HTTP PATCH mocked and get_all_spools set to raise (proving no occupancy read happens): "unarchive PATCH body -> {'used_weight': 700.0, 'archived': False, 'location': 'XL-1'}".

**Fix direction.** When the breadcrumb names a single-occupancy location, restore only if it is empty; otherwise restore to the room or Unassigned and WARN. Alternatively, never plant a toolhead breadcrumb (use the spool's box trail).

**Regression test.** update_spool refill on an archived spool with breadcrumb XL-1 while XL-1 is occupied. Assert the PATCH does not set location XL-1.

**Verifier.** spoolman_api.py:282-287 restores fcc_pre_archive_location with no occupancy read. The REPRO test (get_all_spools raising, which proves no read happens) passed.

**Corrections.** Proven at the update_spool level. The end-to-end flow (a deduct to 0 auto-archives a loaded spool, a new spool is loaded, the weight is later corrected) is inference, but realistic.

#### I5-10 — perform_undo restores a spool's origin location with no occupancy check

*Severity yellow → **yellow** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** If a spool was moved off a toolhead and another spool was later placed there by a writer that pushes no undo record (auto-unarchive, eject return-home, wizard, a direct Spoolman edit), CMD:UNDO writes the first spool back, leaving two on the head. This is a different defect from the established test_undo_of_a_smart_load_puts_the_resident_back_on_the_head (the ejections record at logic.py:510-512 stores the post-eject location).

**Evidence.**

- logic.py:1826-1841 update_spool(sid, {location: loc, ...}) for each recorded move, no occupancy read

**Proof.** Scratch test_REPRO_undo_restores_onto_an_occupied_toolhead (the second spool is injected directly as a non-recording placement): "undo -> {'success': True} | XL-1: [42, 77]".

**Fix direction.** Before restoring onto a single-occupancy location, check it is empty; otherwise route through Smart Load or refuse with an ERROR log.

**Regression test.** Move #77 off XL-1, place #42 on XL-1 without an undo record, run perform_undo. Assert XL-1 holds one spool or the undo reports failure.

**Verifier.** logic.py:1826-1841 performs no occupancy check. The REPRO test passed.

**Corrections.** None.

#### I5-11 — The wizard and Force Location offer Printer-type rows; wizard edit writes location straight to Spoolman, bypassing Smart Load and the active-print guard

*Severity yellow → **yellow** after review · verdict **PLAUSIBLE** · proof: code-trace-only · confidence medium*

**Claim.** Both location lists exclude tool, mmu and direct-load types but not 'printer'. So the dual-role CORE1 (Type Printer, Max 1, a printer_map key) and the XL row are selectable. The wizard sends location in edit and create modes, and api_edit_spool_wizard forwards a changed location through update_spool, giving double occupancy on CORE1 with no confirm. Force Location goes through manage_contents add without confirm: idle it hits Smart Load (bug B for a homeless resident); printing it shows 'Override failed' with no way to confirm.

**Evidence.**

- inv_wizard.js:1509-1511 filter; :2948 location in sp_payload; :3131 edit -> /api/edit_spool_wizard
- routes_inventory.py:633-636 location diffed as a plain key; :660 update_spool(spool_id, spool_data)
- routes_inventory.py:502-503 create passes location through
- inv_details.js:951-953 filter; :1211-1228 manage_contents add with no confirm_active_print; :1234-1236 non-success -> 'Override failed'
- dev data/locations.json (read-only): 'CORE1 | Printer |Max 1 | ths ['CORE1']'

**Proof.** Read the listed lines; no test run for the wizard or Force Location surfaces.

**Fix direction.** Exclude single-occupancy Printer rows (printer_map keys or Printer rows with toolheads) from both lists. Make api_edit_spool_wizard refuse, or route through perform_smart_move, any location change to a single-occupancy target.

**Regression test.** Hermetic /api/edit_spool_wizard with spool_data.location='CORE1' while CORE1 is occupied. Assert it is refused.

**Verifier.** Code-trace, verified. inv_wizard.js:1509 filters tool/mmu/direct-load only; :2948 puts location in the payload; :3131 edit posts to /api/edit_spool_wizard. routes_inventory.py:633-636 diffs location as a plain key and :660 calls update_spool, with no Smart Load or active-print guard. Dev CORE1 is a Printer row with Max 1 that is also a toolhead. Not run.

**Corrections.** None.

#### I5-12 — Quick-Swap Return to a bound slot immediately re-deploys the same spool back onto the toolhead

*Severity orange → **red** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** api_quickswap_return moves the spool to its box slot with perform_smart_move and the default auto_deploy=True. When that slot is bound to the same toolhead (the common case), the chain writes the spool straight back to the toolhead, so 'Return' does nothing net. On a doubled head it acts on residents[0], re-deploys that spool, and Smart Load ejects the other. Every hermetic return test mocks perform_smart_move, so this never shows. Return was added in 965035a (2026-04-20) and the chain was centralized in 47c51d5 (2026-04-21), which suggests a regression (inference).

**Evidence.**

- routes_bindings.py:656-659 perform_smart_move(found_box, [spool_id], target_slot=found_slot, origin='quickswap_return', confirm_active_print=True) without auto_deploy=False
- routes_bindings.py:568-573 residents[0]
- logic.py:694-707 chain
- tests/test_quickswap_api.py:70-174, tests/test_return_and_breadcrumb.py:65/99/135, tests/test_l316_charact_bindings_errors.py return tests all patch logic.perform_smart_move
- git log -S: 965035a 2026-04-20 (return), 47c51d5 2026-04-21 'Auto-deploy for every caller'

**Proof.** Scratch test_REPRO_quickswap_return_to_a_bound_slot_redeploys_the_same_spool: "single return -> 200 {'action': 'return_done', ... 'smart_move': {'auto_deployed_to': 'XL-3', ...}, 'source': 'physical_source'} | 99@ XL-3 ... | writes: [(99, 'LR-MDB-1'), (99, 'XL-3')]". Doubled head, test_CONSEQ_quickswap_return_acts_on_residents_zero_only: "return -> 200 {... 'moved': 42, 'source': 'first_binding' ...} | XL-3: [42] ... | 99@ LR-MDB-1".

**Fix direction.** Pass auto_deploy=False in api_quickswap_return. Add an unmocked engine test for the return path.

**Regression test.** Flask-client /api/quickswap/return with the real perform_smart_move and a resident whose physical_source slot is bound to the toolhead. Assert the spool ends in the box and the toolhead is empty.

**Verifier.** Same as I1-01 (my V2).

**Corrections.** Duplicate of I1-01 and I2-01. Raised from orange to match.

#### I5-13 — Consequence, deduct: with two direct spools on a head NEITHER spool is charged, and spool-swap detection goes blind

*Severity orange → **yellow** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** _apply_usage_to_printer finds more than one spool, select_deduct_targets returns both as ambiguous, and the position is WARNed and skipped. No used_weight is written, so the grams become a shortfall. _snapshot_active_spools records None for that position, so a mid-print swap cannot be detected. _resolve_active_locs_for_printer only orders MMU aliases and never looks at spools. But because a position counts as processed once any spools are found, a real spool on the other alias would not be tried (code-trace).

**Evidence.**

- print_deduct.py:309-327 ambiguous -> WARNING + continue
- print_deduct.py:436-442 snapshot -> None
- spoolman_api.py:1553-1567 direct wins; 2+ distinct -> ambiguous
- print_deduct.py:41-84 alias ordering only; :312 processed_positions.add before the ambiguity check
- print_deduct.py:1105-1108 cancel-review preview keeps both rows (flagged)

**Proof.** Scratch test_CONSEQ_deduct_skips_the_position_entirely: "deduct -> 0 [] | writes: [] | snapshot: {0: None} | warn: [... '⚠️ XL: toolhead XL-1 has 2 spools assigned (sids [42, 99]) — can't tell which is loaded; 12.50g not deducted, weigh the spool to true up.']".

**Fix direction.** No deduct change needed. Removing the double-occupancy paths removes this. Optionally have the Activity Log line point at the toolhead's manage view.

**Regression test.** Already characterized. Keep one hermetic test pinning 'no write + WARNING' for two direct spools.

**Verifier.** print_deduct.py:309-327 warns and skips when ambiguous; 312 adds processed_positions before that check. The CONSEQ test passed.

**Corrections.** A consequence of double occupancy, and it warns rather than corrupting data, so downgraded from orange.

#### I5-14 — Consequence, deduct: a toolhead ghost trail charges a spool that is on a different head, double-charging it

*Severity orange → **yellow** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** When a head has no direct spool but a stale toolhead-valued ghost (I5-3's precondition), select_deduct_targets' ghost-only fallback charges that ghost for the head's grams. That spool is also charged for the head it is really on. The printer-status bar likewise shows the ghost as the loaded spool (items[0]).

**Evidence.**

- spoolman_api.py:1561 chosen = direct if direct else ghost
- print_deduct.py:309-336
- inv_printer_status.js:118-119 item = items[0]

**Proof.** Scratch test_CONSEQ_deduct_with_a_toolhead_ghost_charges_a_spool_on_another_head: "ghost deduct -> 2 [{'sid': 77, 'grams': 10.0, 'remaining': 990.0}, {'sid': 77, 'grams': 5.0, 'remaining': 985.0}] | #77 used: 15.0".

**Fix direction.** Same root fix as I5-3 (never persist a toolhead as physical_source). Optionally drop ghosts whose real location is another printer_map toolhead in select_deduct_targets.

**Regression test.** #77 on XL-2 with physical_source XL-1 and usage {0:10, 1:5}. Assert #77 is charged 5 g only.

**Verifier.** spoolman_api.py:1561 picks ghosts only when there is no direct spool. The CONSEQ test passed ('#77 used: 15.0').

**Corrections.** Needs a toolhead-valued ghost (none on dev today), so downgraded from orange. Same root as I5-3.

#### I5-15 — Consequence, eject: acts on the clicked spool but detaches the single-slot box that the OTHER, still-loaded spool uses

*Severity yellow → **yellow** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** The Location Manager eject removes exactly the clicked sid, so the target is correct. But the Group 20.2 detach is keyed on the toolhead, not the spool. Ejecting the wrong spool of a doubled head therefore unbinds the PolyDryer feeding the spool that stays.

**Evidence.**

- routes_scan.py:294-314 remove acts on spool_id
- logic.py:1531-1537 detach_single_slot_boxes_from_toolhead(current_location) regardless of which spool

**Proof.** Scratch test_CONSEQ_eject_acts_on_the_clicked_spool_and_detaches_the_box_the_other_one_uses: "eject #42 -> {'success': True} | XL-1: [99] | detach calls: [call('XL-1')]".

**Fix direction.** Detach only boxes whose slot-1 binding belongs to the spool being ejected (its physical_source), or skip the detach while another direct spool remains on the head.

**Regression test.** Eject #42 from a head also holding #99 (physical_source PM-DB-1). Assert PM-DB-1 stays attached.

**Verifier.** logic.py:1531-1537 detaches by toolhead, not by spool. The CONSEQ test passed.

**Corrections.** A wider issue than stated: the detach also fires on REFUSED ejects (REQUIRE_CONFIRM, my V5) and on a ghost resident's real head (my V4). See missed item 1.

#### I5-16 — Consequence, eject UX on a printing head: a homeless resident needs 3 round-trips with confirms chained from inside confirm callbacks, and the 2nd message is wrong

*Severity info → **info** after review · verdict **CONFIRMED** · proof: test-run · confidence medium*

**Claim.** Round-trip 1 returns the active-print confirm. Round-trip 2 (confirm_active_print) returns 'Spool is already in a room. Confirm true unassign to nowhere?' for a spool that is on a toolhead. Round-trip 3 succeeds. doEject opens each new requestConfirmation from inside the previous confirm's callback. This is recorded as a fact bearing on the 'eject did nothing' report, NOT as its established cause.

**Evidence.**

- inv_loc_mgr.js:1500 first requestConfirmation; :1530-1543 each refusal opens another requestConfirmation
- inv_core.js:1226-1228 confirmAction -> closeModal (Bootstrap hide) then runs the callback
- routes_scan.py:309-310 REQUIRE_CONFIRM message text

**Proof.** Scratch test_CONSEQ_eject_homeless_resident_during_print_needs_three_round_trips: "r1: {... 'confirm_type': 'active_print', ... 'require_confirm': True ...}" / "r2: {'msg': 'Spool is already in a room. Confirm true unassign to nowhere?', 'require_confirm': True, 'success': False}" / "r3: {'success': True} | XL-1: [42]". The frontend confirm behaviour is code-trace only.

**Fix direction.** Collapse both opt-ins into one confirm (send confirm_active_print and confirmed together once the user has agreed), and fix the message for toolhead residents.

**Regression test.** Flask-client sequence asserting a single confirmed call ejects a homeless resident from a printing head.

**Verifier.** The backend three-round-trip sequence is proven by the CONSEQ test in my rerun. The wording 'Spool is already in a room' comes from routes_scan.py:310.

**Corrections.** Related to I2-16. The frontend chaining is code-trace (inv_loc_mgr.js:1530-1543).

#### I5-17 — Consequence, displays: the Location Manager shows both cards, the printer-status bar shows only items[0], Quick-Swap Return acts on residents[0], and an idle Smart Load self-heals

*Severity info → **info** after review · verdict **PLAUSIBLE** · proof: test-run · confidence medium*

**Claim.** renderList groups by location, so both direct spools render as cards on the toolhead view. The printer-status block renders only the first item, so the second spool is invisible there. Quick-Swap Return picks residents[0], in the same Spoolman order on the frontend and backend. An idle Smart Load onto the doubled head ejects every resident, restoring single occupancy when both have homes. During a print, bug B would make it three.

**Evidence.**

- inv_loc_mgr.js:1041-1111 grouped render
- inv_printer_status.js:118-119 items[0]
- routes_bindings.py:568-573; inv_quickswap.js:738 items[0]
- logic.py:500-508 loop over all residents

**Proof.** Self-heal proven by scratch test_CONSEQ_idle_smart_load_onto_a_doubled_head_ejects_both_residents: "idle quickswap onto doubled head -> quickswap_done | XL-3: [240] | 99@ LR-MDB-1 42@ CR". Rendering claims are code-trace only.

**Fix direction.** Show a 'N spools on a single-spool head' warning chip on the status bar and the toolhead view so double occupancy is visible.

**Regression test.** None beyond the self-heal test.

**Verifier.** The self-heal test passed in my rerun. The render claims (inv_printer_status.js items[0], renderList grouping) are code-trace only.

**Corrections.** None.

#### I5-18 — Eject All (clear_location) reports homeless spools as ejected although perform_smart_eject refused

*Severity info → **info** after review · verdict **CONFIRMED** · proof: code-trace-only · confidence medium*

**Claim.** clear_location ignores perform_smart_eject's return value and appends every unslotted spool to ejected_ids. A homeless spool returns 'REQUIRE_CONFIRM' (confirmed_unassign is not passed) and stays put, yet the location is reported cleared. This is the same truthy-refusal family as bug B; it is not a double-occupancy path.

**Evidence.**

- routes_scan.py:255-257 perform_smart_eject(spool['id'], confirm_active_print=True); ejected_ids.append(...) unconditionally
- logic.py:1633-1636

**Proof.** Read the listed lines; no test run.

**Fix direction.** Append only on `is True`; collect refusals and failures into the response and the log.

**Regression test.** Hermetic clear_location on a room holding a homeless spool. Assert it is not in ejected and a warning is returned.

**Verifier.** routes_scan.py:255-257.

**Corrections.** Duplicate of I2-04 (subset).

**Ruled out (I5).**

- *Bulk move onto a toolhead or Printer row* — plan_bulk_move blocks dest in printer_map or a single-occupancy Type before reading the source (logic.py:820-826). Execute uses auto_deploy=False (logic.py:1042-1044) and skips toolhead-loaded source spools (logic.py:878-885). Proven by scratch test_RULEDOUT_bulk_move_refuses_a_toolhead_destination: "bulk XL-1 -> single_occupancy | bulk XL -> single_occupancy".
- *print_monitor* — It makes no spoolman_api or perform_* calls at all (grep of print_monitor.py for spoolman_api./logic.perform returned nothing).
- *print_deduct write surfaces* — They write only spool_weight/used_weight (print_deduct.py:232, 336, 1533). A rising used_weight can only auto-archive, which clears location; it can never auto-unarchive. The only placement surface in the module is the /api/smart_move route (253-262), covered by I5-1 and I5-8.
- *identify_scan LOCATION branch* — Read-only: it returns contents (routes_scan.py:918-922). Placement happens only in the frontend follow-up to /api/smart_move (I5-1, I5-8).
- *Quick-Swap deposit during a print* — It sends no confirm_active_print (inv_quickswap.js:617-624). The backend pre-flight walks the slot binding (logic.py:426-442), so the answer is assignment_requires_confirm, the UI toasts 'Deposit failed', and nothing is written. Idle deposit is I5-6. Code-trace.
- *Confirmed slot-QR scan during a print (today)* — The confirmed box move chains without the confirm (bug A), so the toolhead move returns requires_confirm and writes nothing to the head. No double occupancy today; it becomes one if A is fixed without B (I5-7).
- *13.6 reverse-binding ghost (physical_source = bound BOX) counting as toolhead occupancy* — That ghost matches the BOX, not the toolhead (spoolman_api.py:1473-1479 matches physical_source against the queried id), so it never inflates a toolhead's residents. It does reserve the box slot (logic.py:458-467 auto-slot, 913-914 bulk capacity). The ghost that DOES count as toolhead occupancy is a toolhead-valued physical_source (I5-3).
- *Toolhead delete cascade / location delete / merge / audit auto-park* — They only unassign, change filament_id, or move to UNKNOWN (logic.py:1719-1731, routes_locations.py:458, routes_locations.py:628, logic.py:1943-1946). None can place a spool on a head.
- *Group 20.2 box attach creating occupancy* — attach_single_slot_box_to_toolhead only edits locations.json slot_targets (locations_db.py:1628-1658); no spool location is written.

**Checked correct (I5).**

- The frontend correctly threads the user's active-print confirm to the backend on every Derek-flow affordance (inv_loc_mgr.js:1322-1326 + 1432; inv_cmd.js:1866; routes_bindings.py:743-746). The defect is backend-internal (logic.py:508).
- The Smart Load gate covers all four single-occupancy types (logic.py:488, TOOLHEAD_TYPES | Printer).
- The Location Manager eject acts on the exact spool id clicked (routes_scan.py:294-314); proven in test_CONSEQ_eject_acts_on_the_clicked_spool...
- select_deduct_targets refuses to guess between two direct spools: it warns and skips rather than over-deducting (spoolman_api.py:1553-1567, print_deduct.py:319-327).
- An idle Smart Load onto a doubled head ejects every homed resident and self-heals (proven).
- Bulk move's single-occupancy destination guard and auto_deploy=False (proven for XL-1 and XL).
- logic.py line numbers cited match the current working tree (anchors re-grepped after the concurrent test-file change; git status shows only tests/test_universal_fallback.py modified and the untracked established test, neither by me).
- The established file tests/test_active_print_chain_confirm.py now holds 10 tests, all failing on the current tree (run: '10 failed in 0.51s'). Four were added during this session (room fallback, Unassigned fallback, refuse incoming, undo of a Smart Load).

**Open questions (I5).**

- Which affordance did Derek actually use: deposit card, LOC-QR scan, or Quick-Swap tile? All three converge on bug B during a print. The Activity Log or hub.log can tell them apart: Quick-Swap logs '⚡ Quick-swap: Spool #N from <box>:SLOT' (routes_bindings.py:747-750), while the other two log only '🖨️ #N -> XL-n'. The bug-B signature is a '⚠️ Smart Load: Ejecting #rid' line (logic.py:504) with NO following '↩️ Returned #rid' / '⏏️ Ejected #rid' line.
- Did any spool in Derek's session carry a toolhead-valued physical_source (the I5-3 precondition)? A read-only check of dev Spoolman extras, looking for physical_source in {XL-1..XL-5, CORE1}, would say whether I5-3 also contributed.
- 'Eject did nothing until I left and came back' (not established; Bootstrap neither assumed nor ruled out): on a printing head, doEject opens a second requestConfirmation from inside confirmAction's callback, right after closeModal started a Bootstrap 5.3.0 hide (inv_core.js:1226-1228, inv_loc_mgr.js:1530-1537). Bootstrap's Modal.show() is a no-op while a hide transition is running, which would leave state.activeModal='confirm' with no visible dialog if the eject POST returns within the fade. This is unverified: a DevTools repro should check whether the second POST with confirm_active_print:true is ever sent.
- Is the Quick-Swap Return redeploy (I5-12) a regression from 47c51d5 or intended? Commit order suggests a regression; confirm with Derek before changing it.
- For a Printer-row target (I5-5), should the planned 'homeless resident -> printer's room' rule even apply? The 'residents' there are other toolheads' loaded spools, so refusing placement on Max-0 Printer rows looks like the right shape. Derek's call.

### Backend: Verifier challenges to ruled-out items

- I5 ruled out the '13.6 reverse-binding ghost (physical_source = a BOX)'. That is correct for toolhead occupancy, but a STALE box-valued ghost is live on dev right now (read-only GET): spool #99 sits in LR-MDB-1 slot 4 but carries physical_source CR-MDB-1 slot 1, and that slot is bound to CORE1. find_spool_in_slot includes ghosts (logic.py:2070-2074), so a Quick-Swap CR-MDB-1:1 -> CORE1 would pull #99 out of LR-MDB-1 onto CORE1 (code-trace). plan_bulk_move skips #99 from CR-MDB-1 as 'deployed to a live toolhead' (logic.py:866-868) although it is on no toolhead, so handoff Bulk Move check 3 would 'pass' for the wrong reason.
- I2 ruled out 'manage_contents remove -> Ejected toast lying'. The toast mapping is correct, but an eject that returns True can still create double occupancy: return-home onto an occupied head (I5-4, re-run passed). A refused REQUIRE_CONFIRM eject still unbinds the toolhead's single-slot box (my V5: perform_smart_eject(99) -> 'REQUIRE_CONFIRM', detach ['XL-1'], 99 still on XL-1). Cancelling the 'true unassign' prompt therefore leaves the PolyDryer detached.
- I2 ruled out 'perform_smart_eject detaching the single-slot box before the return write fails' as already filed. Feature-Buglist.md:32 (PolyDryer item 3) covers only the WRITE-FAILURE case. The detach also precedes the protected-unassign refusal (logic.py:1531-1539 vs 1634-1636), proven by my V5; I found that case filed nowhere.
- I1 ruled out that eject return-home re-triggers auto-deploy. The no-chain claim is correct, but the same return-home has no occupancy check at its destination (I5-4), and when saved_source is a toolhead it detaches a box before any refusal (my V4 detached XL-2's box during a load onto XL-1).
- I2's 'Bootstrap as the established cause' stays open, as required. An in-app run by a different group (eject-reconfirm-race/sweep_baseline.txt, read, not re-run) shows the chained confirm is dropped and invisible when the second show() comes 14-142 ms after hide(), visible from 161 ms, with a stale CMD:CONFIRM later firing the eject. That group's latency sample puts a get_spool round trip at median 15.5 ms. The mechanism is therefore live in the real app. Whether Derek's no-op was this, the hung refreshManageView guard (triage candidate a), or stale render state is still unestablished; none of this group tested (a) or (b).
- I5 ruled out the 'print_deduct write surfaces' as double-occupancy paths. Not a dismissal of Derek's symptom, but incomplete: a deduct to 0 g auto-archives and UNASSIGNS a spool on a PRINTING toolhead with no active-print guard (spoolman_api.py:212-227 via print_deduct.py:336). That seeds the I5-9 chain that later restores it onto an occupied head.

### Backend: Duplicates

- I1-01 = I2-01 = I5-12 (Quick-Swap Return redeployed by the auto-deploy chain; auto_deploy default True at routes_bindings.py:656-659)
- I1-02 overlaps the second half of I2-01 (forwarding the confirm, fix A, makes Return redeploy mid-print); I5-7 is a distinct sibling ordering hazard (fix A without fix B -> double occupancy)
- I1-07 = I2-03 (DRYER/GENERIC pop() never clears physical_source through update_spool's merge)
- I1-09 = I2-14 (Quick-Swap deposit omits confirm_active_print)
- I5-18 is a subset of I2-04 (clear_location ignores perform_smart_eject's result)
- I5-1, I5-2, I5-6 are reachability instances of baseline B (I2-BASE-B / established tests); I5-6 also restates baseline A
- I1-08(b) duplicates the established test_undo_of_a_smart_load_puts_the_resident_back_on_the_head
- I2-16 and I5-16 describe the same chained eject-confirm sequence (frontend mechanism vs backend round trips)
- I2-02, I5-3, I5-4, I5-14 share one root: a toolhead-valued physical_source written at logic.py:591
- I5-5, I5-8, I5-11 share the Printer-row-as-spool-target root
- I2-08 overlaps I2-15 on the Force Location 'Location updated via override' success toast

### Backend: found by the verifier, missed by every investigator

#### A refused eject still detaches the toolhead's single-slot box; a Smart Load can detach a DIFFERENT head's box

**Claim.** perform_smart_eject calls detach_single_slot_boxes_from_toolhead(current_location) before its protected-unassign REQUIRE_CONFIRM return. It also runs before the write-failure path (already filed). Consequences: (1) In bug B's homeless-resident case the resident stays on the head, but its PolyDryer binding is removed from locations.json. (2) Every Location Manager eject that ends at the 'true unassign' prompt unbinds the box even if the user cancels. (3) Smart Load onto head A, when a ghost resident's real location is head B, detaches head B's box. None of I1/I2/I5 lists (1)-(3). The only filed item covers a failed return write.

**Evidence.** Code: logic.py:1531-1539 (detach) precedes logic.py:1634-1636 (return 'REQUIRE_CONFIRM'). Test-run, my verify-backend/test_verify_backend.py::test_V5: 'perform_smart_eject(99) -> REQUIRE_CONFIRM, detach [XL-1]; 99 still XL-1' and 'smart load -> {status: success, failures: {}}, XL-1=[42, 99], detach [XL-1]'. test_V4: loading onto XL-1 gave 'detach calls=[call(XL-2)]'. Tripwire: 0 repo writes. Filed coverage checked at Feature-Buglist.md:32 (write-failure only). A different group's scratch file eject-reconfirm-race/test_refused_eject_detaches.py suggests it may be reported there too.

#### Live dev data already carries a stale ghost trail, which invalidates the premise of Bulk Move manual check 3

**Claim.** Spool #99 is at LR-MDB-1 slot 4 but still has physical_source CR-MDB-1 / physical_source_slot 1, and CR-MDB-1 slot 1 is bound to CORE1. It is on no toolhead, yet the flat matcher shows it as a deployed ghost reserving CR-MDB-1 slot 1. That is the '1 ghost (a deployed spool reserving its slot)' the handoff's check 3 expects to be skipped as deployed. The check would pass for the wrong reason, and a Quick-Swap CR-MDB-1:1 -> CORE1 would pull #99 out of LR-MDB-1. That the I1-07/I2-03 pop bug wrote this record is inferred, not proven.

**Evidence.** Read-only GET http://192.168.1.29:7913/api/v1/spool saved to verify-backend/dev_spools_readonly.json (237 spools) and analysed by verify-backend/analyze_dev_data.py against inventory-hub/data/locations.json opened read-only. Output: 'STALE ghost trail ...: 1 / id=99 loc=LR-MDB-1(Dryer Box) physical_source=CR-MDB-1(Dryer Box) ps_slot=1 container_slot=4'; 'CR-MDB-1: direct=[] ghosts=[(99, LR-MDB-1, 1)]'; 'bound boxes: CR-MDB-1 {1: CORE1}'. Skip rule logic.py:866-868; ghost-inclusive slot lookup logic.py:2070-2074.

#### The auto-deploy chain deploys spools whose box write FAILED; the planned fix A must filter per spool

**Claim.** The chain passes list(spools) to perform_smart_move(bound_toolhead, ...) without consulting `failures`. A spool whose Dryer Box write Spoolman rejected is still written onto the toolhead. The planned fix only gates the log and auto_deployed_to on the chained result, which would still let this happen.

**Evidence.** Code: logic.py:633/649/674 populate failures; logic.py:703-704 chain on list(spools) unconditionally. Test-run evidence in I1's Q3 case (re-run passed): log '[ERROR] Failed to move Spool #240 -> Dryer LR-MDB-1: HTTP 400...' followed by '#240 -> XL-3' and 'Auto-deployed ...' with failures {'240': ...} and final location XL-3.

#### Latent: a multi-spool move with an explicit bound slot chains every spool onto one toolhead

**Claim.** perform_smart_move(box, [a, b], target_slot=bound) seats a, unseats it for b, then chains both onto the bound toolhead, so both spools sit on one head. The current UI cannot reach this: every performContextAssign caller sends slot null, and manage_contents add and slot-QR are single-spool. A direct /api/smart_move call can. Info only; worth a guard when fix A touches the chain.

**Evidence.** Test-run, my test_V7: 'result={status: success, failures: {}, auto_deployed_to: XL-3} XL-3=[240, 241]'. Reachability: grep of performContextAssign callers, inv_cmd.js:1633, 1635, 1866 (slot null or propagated null); logic.py:703-704.

## Frontend

### I3 — eject-reconfirm-race

ROOT CAUSE PROVEN in the live UI, read-only (every POST was intercepted and answered with a synthetic response). The eject "did nothing" because the active-print re-confirm is silently dropped.

Sequence: ejectSpool asks "Eject spool #N?". The user clicks YES, and confirmAction (inv_core.js:1228) calls closeModal, which starts Bootstrap's fade-out of #confirmModal. It then runs doEject straight away, which POSTs /api/manage_contents. The backend answers require_confirm / active_print, and doEject calls requestConfirmation, which calls show() on the SAME element (inv_loc_mgr.js:1530-1537). Bootstrap 5.3.0's live Modal.show source begins `this._isShown||this._isTransitioning||...`, and _isTransitioning is only cleared in _hideModal, about 150 ms after hide().

Sweep on XL-1's contents-list EJECT badge (Quick-Swap card eject also reproduced it on retry):
- Gap from hide() to the second show() of 14.5 / 64.5 / 113.3 / 142.2 ms: show() returned early, no dialog appeared, and no confirm_active_print:true retry was sent. Retrying the eject in the same view failed the same way, so 8 of 8 were swallowed.
- Gap of 161.5 ms up to 1013.9 ms: the dialog showed, YES sent the retry, and an "Ejected" toast appeared (8 of 8).

Controls:
- reduced_motion=reduce (fade about 5 ms): the dialog shows even at 0 ms (2 of 2).
- Fade widened to 1 s on #confirmModal only: swallowed even with a 400 ms response delay.
- In-page prototype that defers the re-show until hidden.bs.modal: the dialog shows at every delay (9 of 9).

Real latency: both printers were PRINTING during this session. GET /api/printer_state/XL-1 (printer map + PrusaLink probe) had a median of 61.8 ms and p90 of 93.5 ms over 40 samples. get_spool had a median of 15.5 ms. The paired upper estimate for the require_confirm path is a median of 80.3 ms and p90 of 146.7 ms, with 36 of 40 under 150 ms. So during a real print the re-confirm is dropped about 90% of the time.

It is not a Bootstrap bug: Bootstrap ignores show() mid-transition by design. The defect is FCC re-showing a modal from inside its own close callback without waiting for hidden.bs.modal.

Consequences:
- A dropped re-confirm leaves state.pendingConfirm holding the confirm_active_print:true callback. A later CMD:CONFIRM scan fired that eject with no dialog on screen (proven).
- A double-occupied head's resident with no saved home adds a second chained hop, true-unassign, with no probe in its path. Its latency is well inside the window (code-trace).
- A refused REQUIRE_CONFIRM eject has already detached the single-slot boxes (hermetic test).

Why "leaving and coming back" worked: navigating away and back does not touch the confirm state, and a retry in the same view failed the same way (proven). The likely difference is that the print had finished, so the backend skipped the re-confirm (inference).

Other candidates:
- (a) Hung refresh guard: ruled out. With it wedged, both confirms, both POSTs and the "Ejected" toast still happened, and the 5 s pulse re-renders without that guard.
- (b) Stale render hash: ruled out as a no-op cause.
- (c) Wrong record: ruled out, because the backend's remove is keyed on spool_id. Double occupancy only adds a hop.

Minimal fix: in requestConfirmation / promptSafety, keep the synchronous arming, but defer show() until hidden.bs.modal when the modal is mid-hide. Also stop inv_cmd.js:1456 from firing confirmAction when no confirm dialog is actually visible.

#### I3-1 — Active-print re-confirm after an eject is silently dropped: Bootstrap show() is a no-op while the first confirm is still fading out

*Severity orange → **orange** after review · verdict **CONFIRMED** · proof: browser-run · confidence high*

**Claim.** When the backend's require_confirm answer arrives within about 150 ms of the user clicking YES on the first confirm, the second confirm is never shown. There is no toast, no log line and no request, so the eject 'does nothing'. confirmAction calls closeModal, which starts hide(), then runs the doEject callback synchronously. doEject's require_confirm branch calls requestConfirmation, which calls modals.confirmModal.show() on the same instance while Bootstrap 5.3.0 still has _isTransitioning=true, so show() returns early. The backend's real require_confirm latency during a print is usually shorter than that window.

**Evidence.**

- inv_core.js:1226 closeModal = hide() then activeModal=null; :1227 requestConfirmation arms pendingConfirm, bumps _confirmGeneration, calls modals.confirmModal.show(), sets activeModal='confirm'; :1228 confirmAction = closeModal('confirmModal') then pendingConfirm() synchronously
- inv_loc_mgr.js:1500 ejectSpool -> requestConfirmation('Eject spool #N?', doEject); :1505-1507 doEject -> fetchT POST /api/manage_contents; :1521 setProcessing(false); :1530-1537 require_confirm && confirm_type==='active_print' -> requestConfirmation(..., () => doEject(sid, loc, isConfirmed, true))
- Live in-page source of bootstrap.Modal (VERSION 5.3.0, scripts.html:1): show(t){this._isShown||this._isTransitioning||P.trigger(...)...}; hide(){...this._isTransitioning=!0,...this._queueCallback(()=>this._hideModal(),this._element,this._isAnimated())}; _hideModal(){...this._isTransitioning=!1,this._backdrop.hide(...)}
- Browser sweep, baseline (race_probe.py baseline; XL-1 contents-list EJECT badge, spool #57; POSTs answered synthetically). Event trace at delay 0: hide-call t=3859.2, mc-fetch-start 3860.1, mc-fetch-resolved 3871.9, then show-call t=3873.7 {isTransitioning:true, willEarlyReturn:true} with no evt-show after it. The snapshot 1.6 s later shows confirmHasShow=false, activeModal=None, pendingConfirm=fn, and no confirm_active_print:true POST.
- Sweep summary lines: 'delay=0 hide->2nd show()=14.5ms early-return=True visible=False', '50 ... 64.5ms True False', '100 ... 113.3ms True False', '120 ... 142.2ms True False'. Versus: '140 ... 161.5ms False True ... confirm_active_print:true POST sent=True', and likewise for 160, 180, 200, 250, 300, 400 and 1000 ms. Toast after the second YES at 160/180/200 ms: ['Ejected'].
- Retry in the same view (the user clicking eject again) at delays 0/50/100/120: the first confirm 'Eject spool #57?' showed normally, and the second was swallowed again (visible_after_yes=False). The delay-0 retry went through the Quick-Swap card's eject (onclick ejectSpool(57,'LR-MDB-1',false), ui_builder.js:359) and was swallowed too.
- Control, reduced_motion='reduce' (Bootstrap's .fade collapses to about 5 ms): 'delay=0 hide->2nd show()=10.1ms early-return=False visible=True ... POST sent=True'; 'delay=50 ... visible=True'
- Control, fade widened to 1 s on #confirmModal only: 'wide delay=400 hide->2nd show()=422.6ms early-return=True visible=False' (swallowed at a delay that normally works)
- Fix prototype (FIX_JS defers show until hidden.bs.modal): 'fixed' at delays 0/50/100/140/160/200/300 and 'widefixed' at 0/400 all visible=True with the confirm_active_print:true POST sent. The delay-0 trace shows fix-deferred t=3834.2, evt-hidden 4146.2, fix-reshow 4146.4, evt-shown 4614.5, the retry POST, and toast ['Ejected'].
- Real latency (latency.py, GET only, XL and Core One both reporting state PRINTING): fcc_printer_state(map+probe) n=40 min 33.2, med 61.8, p90 93.5, max 272.2 ms; fcc_spool_details(get_spool) med 15.5, p90 31.9 ms; paired upper estimate med 80.3, p90 146.7 ms, 36/40 under 150 ms, 40/40 under 310 ms. The backend path is logic.py:1511 get_spool, then :1518-1527 _active_print_info_for_location, then prusalink_api.py:468 requests.get(.../api/v1/status, timeout=2), with no cross-request memo (prusalink_api.py:421-437).
- Screenshots: baseline_d0_after_first_yes.png shows the XL-1 view unchanged with no dialog 1.6 s after YES; baseline_d500_after_first_yes.png shows the 'XL is PRINTING' confirm visible.

**Proof.** race_probe.py drove Playwright (sync API, chromium, 1600x1300) against http://localhost:8000. context.route was installed before navigation; every non-GET was fulfilled synthetically and logged, and the POST bodies above come from that log. The delay was applied in-page after the synthetic answer, and Bootstrap show/hide were instrumented via the prototype. Variants: baseline (12 delays + retries), fixed (7), reduced (2), wide (2), widefixed (2). Latency came from GET-only sampling with latency.py (n=40). The real POST was deliberately NOT timed, because if the print had ended it would have ejected spool #57 for real.

**Fix direction.** Minimal, central fix in inv_core.js covering every chained confirm (the active-print re-prompt, eject's true-unassign, and any promptSafety chain). At init, register hide.bs.modal / hidden.bs.modal listeners on #confirmModal and #safetyModal that set and clear a 'hiding' flag. In requestConfirmation / promptSafety, keep msg + pendingConfirm + _confirmGeneration++ + activeModal synchronous, but if the element is hiding, call show() from a {once:true} hidden.bs.modal listener registered after the flag-clearing listener, instead of immediately. Use the events, not Bootstrap's private _isTransitioning. This is compatible with the generation-counter gate release at inv_core.js:1554-1582: the prototype trace kept activeModal='confirm' and YES worked. The alternative per CLAUDE.md, routing the active-print re-confirm through window.mountOverlay, avoids the same-element re-show only for that one hop; the true-unassign re-prompt (inv_loc_mgr.js:1539-1543) would still race, so the central deferral is needed either way. Also add an Activity Log / toast when a require_confirm arrives, so a future dropped dialog is not totally silent.

**Regression test.** New E2E, e.g. tests/test_eject_reconfirm_race_e2e.py, using the `page` + `require_server` fixtures with no dev writes.
(1) context.route('**/*'): continue GETs, fulfill every non-GET. For /api/manage_contents, return {success:true} if the body has confirm_active_print:true, otherwise the require_confirm / active_print JSON. Record the bodies.
(2) After load, inject `#confirmModal.fade{transition:opacity 1s linear !important}` so the hide window is about 1 s regardless of host load. Proven: current code swallows even at a 400 ms delay, and the fix still shows.
(3) Call `ejectSpool(999999,'XL-1',false)` via page.evaluate so no dev spool is needed (the route answers the POST), wait for #confirmModal.show, wait 600 ms for the fade-in, then click '#confirmModal .btn-success'.
(4) Assert within 3 s that #confirmModal has .show and #confirm-msg contains 'PRINTING'. This fails on current code.
(5) Click YES and assert a recorded POST with confirm_active_print:true.
Parametrize the backend's second answer as a true-unassign {success:false, require_confirm:true} and assert the third dialog shows and YES posts confirmed:true. Use `typeof state.pendingConfirm`, never the raw value; Playwright serializes functions to None (test_scan_path_integrity.py:465-470).

**Verifier.** I reproduced this myself. I wrote my own probe (verify-frontend/vf_probe.py) that works differently from I3's on purpose: it does not wrap Bootstrap's prototype, it observes only the public show/hide events plus a MutationObserver on #confirm-msg, and it delays at the route level so the page sees it as server latency. Every non-GET request was intercepted.

On the live page, bootstrap.Modal.VERSION is 5.3.0. Live show() source begins `this._isShown||this._isTransitioning||...` and the #confirmModal transition is `opacity 0.15s linear`.

In real clicks on the XL-1 contents EJECT badge (`ejectSpool(57, 'XL-1', false)`), the gap from hide to re-arm decided the outcome:
- 10.4, 12.3, 66.6, 106.2, 106.8 and 131.2 ms: `isShown_after_rearm False`, second_visible=False, activeModal=None, pending=function, and only the first POST (`confirm_active_print:false`) was sent.
- 161.3, 183.9, 228.4, 228.6 and 409.3 ms: the second confirm was visible, and YES sent `confirm_active_print:true` with toast ['Ejected'].

That matches I3's threshold between 142 and 161 ms. Code read: inv_core.js:1226-1228, inv_loc_mgr.js:1500/1530/1539.

Real latency is still an estimate. My 15 GET samples of printer_state plus spool summed to 50-650 ms, 13/15 under 150 ms and a median of about 106 ms. They were taken while a headless browser was running, so they skew high. No real POST was timed, so "dropped about 90% of the time" is an inference, not a measurement.

**Corrections.** The inv_core.js gate-release timer is the setTimeout at :1567, inside the hidden.bs.modal block at :1554-1582. The scope is wider than an active print: the same drop hits the plain true-unassign re-prompt with no print running (see missed). The 90% figure is an estimate built from GET timings, not a POST measurement.

#### I3-2 — A swallowed re-confirm leaves a live confirm_active_print:true callback in state.pendingConfirm, and a later CMD:CONFIRM scan fires it with no dialog on screen

*Severity orange → **orange** after review · verdict **CONFIRMED** · proof: browser-run · confidence high*

**Claim.** After I3-1, requestConfirmation has already stored the retry callback (doEject(..., confirmActivePrint=true)) even though its dialog never appeared. The hidden.bs.modal handler releases only activeModal, deliberately leaving pendingConfirm set. A subsequent CMD:CONFIRM scan reaches the backend, which answers {type:'command', cmd:'confirm'}. inv_cmd.js:1456 then calls confirmAction(true) because pendingConfirm is set, which POSTs an eject with confirm_active_print:true: the exact print-disrupting action the confirm exists to gate, performed without the user ever seeing it. During the ~400 ms before the gate is released, activeModal is still 'confirm', and inv_cmd.js:1429 routes any CONFIRM scan straight to confirmAction(true) too (code-trace).

**Evidence.**

- inv_cmd.js:1456 `else if (res.cmd === 'confirm' && state.pendingConfirm) confirmAction(true);` (no check that #confirmModal is showing); inv_cmd.js:1429 activeModal==='confirm' -> confirmAction(true)
- logic.py:179 `if "CMD:CONFIRM" in upper_text: return {'type': 'command', 'cmd': 'confirm'}`
- inv_core.js:1566-1581: the gate-release timer sets only state.activeModal=null; the comment at :1574-1579 says pendingConfirm is deliberately not cleared
- Browser, baseline delay 0 after the swallowed re-confirm (snapshot activeModal=None, pendingConfirm=fn): page.evaluate processScan('CMD:CONFIRM','barcode'), with /api/identify_scan fulfilled as {type:'command',cmd:'confirm'} (the logic.py:179 shape). Intercepted requests: POST /api/identify_scan {"text":"CMD:CONFIRM","source":"barcode"}, then POST /api/manage_contents {"action":"remove","location":"LR-MDB-1","spool_id":57,"confirmed":false,"confirm_active_print":true}. The event trace shows hide-call {isShown:false} with no evt-show anywhere before it.

**Proof.** Same race_probe.py run (baseline, delay 0). identify_scan was fulfilled synthetically with the shape logic.py:179 returns. The manage_contents POST was intercepted, so nothing reached the server.

**Fix direction.** (1) The I3-1 deferral removes the way the callback gets orphaned. (2) Defense in depth: at inv_cmd.js:1456, only call confirmAction when #confirmModal actually has .show. (3) Optionally, in the hidden.bs.modal timer, also null pendingConfirm when the generation is unchanged AND no gating modal is showing. That condition is exactly the orphaned case, and it avoids the de390a0 regression, which cleared the callback without the generation check. Verify it against the chained re-prompt E2E before relying on it.

**Regression test.** E2E with the same routes and widened fade as I3-1. Get the second confirm on screen (after the fix), dismiss it with NO, then page.evaluate processScan('CMD:CONFIRM') with identify_scan fulfilled as {type:'command',cmd:'confirm'}. Assert NO manage_contents POST with confirm_active_print:true was recorded. A pre-fix variant can mark the swallowed state xfail to document the hazard.

**Verifier.** Re-proven twice, once per delay-0 trial. After the dropped re-confirm, pendingType is 'function' and activeModal is None. Then processScan('CMD:CONFIRM','barcode') sent POST /api/identify_scan and then POST /api/manage_contents `{"action":"remove","location":"XL-1","spool_id":57,"confirmed":false,"confirm_active_print":true}`. The identify_scan answer was synthetic; the {cmd:'confirm'} mapping is from reading logic.py:179. Code cites checked: inv_cmd.js:1456 and :1429, and inv_core.js:1567-1581, which releases only activeModal.

**Corrections.** It is wrong that the I3-1 deferral 'removes the way the callback gets orphaned'. I proved two other routes that orphan it with no race: dismissing a visible confirm by clicking its backdrop, and a stale session-scoped CMD:CONFIRM:<sid> scan that falls through (see missed). So the inv_cmd.js:1456 visibility guard, or nulling on dismissal with a generation check, is REQUIRED, not defence in depth.

#### I3-3 — The true-unassign re-prompt after the active-print confirm is a second hop of the same race, with an even faster backend answer

*Severity yellow → **orange** after review · verdict **CONFIRMED** · proof: code-trace-only · confidence medium*

**Claim.** The resident spool of a double-occupied toolhead is typically the one with no physical_source. Ejecting it during a print needs two chained re-shows of #confirmModal. The first is the active-print re-confirm (I3-1). The second: the retry with confirm_active_print:true makes perform_smart_eject return 'REQUIRE_CONFIRM' for a toolhead spool with no home, and doEject calls requestConfirmation again. That retry skips the PrusaLink probe, so the response is roughly get_spool plus local reads (tens of ms), which almost always lands inside the fade-out. Even after the print ends, this spool's first eject still has one racy hop (probe about 60 ms, then REQUIRE_CONFIRM). This part is code-trace; the mechanism is the one proven in I3-1.

**Evidence.**

- inv_loc_mgr.js:1539-1543 res.require_confirm (no confirm_type) -> requestConfirmation(..., () => doEject(sid, loc, true, confirmActivePrint)) from inside the fetch continuation
- logic.py:1518 `if not confirm_active_print:` guards the only probe; with the flag set, the path goes on to :1531-1539 detach and then :1636 `return "REQUIRE_CONFIRM"` when current_location is in printer_map and there is no saved_source
- routes_scan.py:294 remove branch -> perform_smart_eject(spool_id, confirmed_unassign, confirm_active_print); REQUIRE_CONFIRM maps to {success:false, require_confirm:true}
- Measured get_spool via GET /api/spool_details: median 15.5 ms, p90 31.9 ms (n=40); the proven swallow threshold is a gap of 142 ms or less

**Proof.** This hop was not driven in the browser; the identical requestConfirmation-to-show mechanism was driven for the active-print hop in I3-1. Latency of the no-probe path is inferred from the measured get_spool plus local file reads.

**Fix direction.** Covered by the central deferral in I3-1. No per-call-site change is needed.

**Regression test.** Parametrize the I3-1 E2E so the confirm_active_print:true POST answers {success:false, require_confirm:true, msg:'Spool is already in a room...'}. Assert a third confirm becomes visible and its YES posts confirmed:true with confirm_active_print:true.

**Verifier.** I upgraded the frontend part from code-trace to a browser run (vf_probe.py unassign). The first answer was active_print at 600 ms, which showed; YES then produced a second answer of {success:false, require_confirm:true}.
- second_delay=0: gap 10.6 ms, `isShown_after_rearm False`, unassign_visible=False, activeModal=None, and only 2 POSTs (no confirmed:true).
- second_delay=40: gap 47.1 ms, same result.
- Control second_delay=400: third dialog visible, YES sent `{"confirmed":true,"confirm_active_print":true}` with toast ['Ejected'].

Backend path, from reading: with confirm_active_print set, logic.py:1518 skips the probe, :1533 detaches, and :1636 returns REQUIRE_CONFIRM; routes_scan.py:308-309. That the real no-probe answer is this fast is inferred from get_spool GET timings (I3 median 15.5 ms; my samples 14-84 ms).

**Corrections.** Proof is now browser-run for the frontend hop, and the backend latency remains an inference. Severity is raised to orange: this hop turns Derek's homeless-resident eject into a silent no-op even after he gets past the active-print prompt. It shares I3-1's root cause and fix.

#### I3-4 — A refused eject (REQUIRE_CONFIRM) has already auto-detached single-slot boxes from the toolhead

*Severity yellow → **yellow** after review · verdict **CONFIRMED** · proof: test-run · confidence high*

**Claim.** perform_smart_eject runs the Group 20.2 detach_single_slot_boxes_from_toolhead, a locations.json write, before deciding whether the eject is a protected unassign. When it then returns 'REQUIRE_CONFIRM', nothing about the spool is written, yet the box binding is already gone. With the confirm chain in I3-1 / I3-3 dropping dialogs, a user can repeat this refused path several times, which leaves the box and toolhead stores disagreeing. This is relevant to candidate (c) (double occupancy leaving state inconsistent). The active-print refusal, by contrast, happens correctly before the detach.

**Evidence.**

- logic.py:1518-1527 active-print refusal returns before the detach; logic.py:1528-1539 detach when current_location is in printer_map; logic.py:1636 return "REQUIRE_CONFIRM" comes later
- Scratch hermetic test test_refused_eject_detaches.py: test_active_print_refusal_happens_before_detach (detach.call_count==0) and test_require_confirm_refusal_has_already_detached_boxes (result=='REQUIRE_CONFIRM', update_spool.call_count==0, detach.call_count==1). Output: '2 passed in 0.27s'

**Proof.** "C:/Python314/python.exe" -m pytest test_refused_eject_detaches.py -p no:cacheprovider -q was run from the scratch dir. The first attempt with --offline was rejected ('unrecognized arguments: --offline', because the repo conftest is not loaded outside the repo). The test is fully hermetic: Spoolman, config, printer map, the detach, save_locations_list, the log and the PrusaLink probe are all mocked. Result: 2 passed.

**Fix direction.** Move the Group 20.2 detach below the protected-unassign decision (after `if not confirmed_unassign: return "REQUIRE_CONFIRM"`), or run it only once a spool write has succeeded. This also ties into the buglist's PolyDryer note that the detach runs before the return-home write (logic.py:1533 vs the update_spool).

**Regression test.** Promote test_require_confirm_refusal_has_already_detached_boxes into tests/ with the assertion inverted (detach.call_count == 0 on a REQUIRE_CONFIRM refusal). Keep test_active_print_refusal_happens_before_detach as a sibling pin.

**Verifier.** I re-ran scratchpad/eject-reconfirm-race/test_refused_eject_detaches.py with C:/Python314 -p no:cacheprovider -q: '2 passed in 0.28s'. I read the test first: Spoolman, config, printer map, detach, save_locations_list, the log and prusalink_api.get_printer_state are all mocked.

Code read: the detach at logic.py:1528-1539 writes via locations_db.py:1683 save_locations_list, and it runs before `return "REQUIRE_CONFIRM"` at logic.py:1636. The active-print refusal at :1518-1527 comes before the detach.

**Corrections.** Two overstatements. 'A user can repeat this refused path several times': the detach is idempotent, so a second refusal finds nothing left to detach and the inconsistency does not grow. It is also not silent: logic.py:1534-1536 writes a '🔓 Single-slot box(es) auto-detached' Activity Log line. Reaching it requires a single-slot box bound to the toolhead while the ejected spool has no physical_source (double occupancy or a manual binding). It is backend (logic.py), not frontend.

#### I3-5 — Why 'navigate away and come back' appeared to fix it: nothing in the view was wedged; the backend answer changed

*Severity info → **info** after review · verdict **PLAUSIBLE** · proof: browser-run · confidence medium*

**Claim.** The swallowed state does not persist in the view. activeModal is released within ~400 ms, and the next requestConfirmation overwrites the orphaned callback. A retry in the same view shows the first confirm normally and fails at the same hop, so Derek's repeated clicks would each fail identically while the print ran. Navigation (openManage) never touches #confirmModal, pendingConfirm or the Bootstrap instance. The most likely difference on the later attempt is that the XL was no longer PRINTING/PAUSING/RESUMING (his report says the print finished during the session). The first POST then skips the active-print re-confirm, and a spool with a physical_source ejects on the first YES. A less likely alternative is an occasional slow probe past about 150 ms (4 of 40 paired samples). These last two points are inference.

**Evidence.**

- Browser: baseline retry at delays 0/50/100/120 shows first_msg='Eject spool #57?' then visible_after_yes=False (the same failure on every attempt; the view was not dead)
- inv_loc_mgr.js:138-213 openManage: fetch contents, render, manageModal.show(); no reference to confirmModal / pendingConfirm / _confirmGeneration
- inv_core.js:1566-1581 gate release after 400 ms; inv_core.js:1227 each requestConfirmation overwrites pendingConfirm
- prusalink_api.py:458 _ACTIVE_PRINT_STATES = {PRINTING, PAUSING, RESUMING}; logic.py:1518-1527 only an active state triggers the re-confirm
- Feature-Buglist.md raw report: 'the print I had going finished while I was trying to get it set up to test'

**Proof.** The repeat-failure part was driven in the browser (the retries). That the print ending changed the outcome is inferred from code plus Derek's report; it cannot be recovered after the fact.

**Fix direction.** No separate fix. Once I3-1 lands, the eject works during the print as well.

**Regression test.** Covered by the I3-1 E2E. Optionally assert that two consecutive eject attempts both reach the confirm_active_print:true POST.

**Verifier.** The repeat-failure part holds. My two delay-0 trials, each on a fresh page load, failed identically, and openManage (inv_loc_mgr.js:138) does not touch the confirm state. The 'print ended' explanation is only one of several I could not tell apart:
(1) It works only if the wrong spool HAD a physical_source. A resident with no home still gets the fast REQUIRE_CONFIRM hop after the print ends (probe plus detach write), and that hop is often dropped too.
(2) Latency varies: 2/15 of my GET sums were over 150 ms, so an occasional attempt succeeds by chance.
(3) A different eject surface: an eject-mode scan (inv_cmd.js:1668 -> ejectSpool(id,'Scan') -> no first confirm, inv_loc_mgr.js:1500) shows the active-print prompt reliably even at 0 ms. vf_scaneject.py showed first_prompt_visible=true, and YES sent confirm_active_print:true with toast 'Ejected'.

**Corrections.** Present it as the leading candidate among three (print ended, latency variance, different eject surface), not as the likely cause.

**Ruled out (I3).**

- *(a) refreshManageView's _refreshManageViewInflight guard around a bare fetch (inv_loc_mgr.js:845-857) making later ejects look dead* — Browser (race_probe.py hungrefresh): with /api/get_contents held unanswered (10 GETs held, including the explicit refreshManageView('XL-1')), clicking EJECT still showed the first confirm. It sent POST manage_contents confirm_active_print:false, showed the second confirm (at a 500 ms delay), sent POST confirm_active_print:true, and raised toast ['Ejected']. The guard only suppresses the re-render. Also: ejectSpool/doEject never call it before sending (inv_loc_mgr.js:1481-1545). The open manage view is re-rendered by the pulse through _renderManagePayload directly, bypassing the flag (inv_core.js:1333-1344 adds 'manage' while #manageModal is shown; :1423-1424 renders it). The server side of get_contents is bounded by get_all_spools timeout=5 (spoolman_api.py:99).
- *(b) anti-wiggle state.lastLocRenderHash showing stale cards so eject acts on out-of-date state* — Code-trace: the hash covers the full contents JSON plus the buffer ids (inv_loc_mgr.js:821-834), so it only skips truly identical data, and a successful eject nulls it (:1554). More importantly, the backend's remove ignores the card's location. routes_scan.py:294 passes only spool_id to perform_smart_eject, which acts on the spool's CURRENT location. Proven in the browser: the Quick-Swap card sent location 'LR-MDB-1' for spool #57 on XL-1, and the flow was unchanged. A stale card therefore produces a real (possibly surprising) eject or a confirm, never a silent no-op.
- *(c) double occupancy making eject act on the wrong record* — Each card calls ejectSpool with its own spool id (ui_builder.js:177, :359), and the backend is keyed on spool_id (routes_scan.py:294-296), so the clicked record is the one acted on. Double occupancy does matter, but differently. The resident without a home adds a second racy confirm hop (I3-3), and a refused eject has already detached boxes (I3-4, test-run).
- *Confirm rendering behind another layer (z-order / backdrop) on the toolhead manage view* — global.css:1086-1088 gives #confirmModal z-index 1100 !important. In every run where the second confirm was shown, elementFromPoint at the YES centre returned BUTTON.btn-success insideConfirm=true, including the 140-250 ms runs where only one backdrop remained. The real Playwright click passed its hit-target check and sent the retry. setProcessing(false) runs before requestConfirmation (inv_loc_mgr.js:1521). This holds for the manage view without an open bulk-move panel; the bulk-move-panel case (buglist item 1) was not in scope.
- *A Bootstrap defect* — Bootstrap behaves as its source reads: show() is ignored while _isTransitioning. The reduced-motion control shows the dialog at 0 ms, and deferring the re-show until hidden.bs.modal fixes every delay. The defect is FCC re-showing the same modal instance from inside its own close callback without awaiting hidden.

**Checked correct (I3).**

- The generation-counter gate release (inv_core.js:1554-1582, commit de390a0) is correct whenever Bootstrap ACCEPTS the re-show. In the traces at 140 and 250 ms, evt-hidden fires after the second evt-show, activeModal stays 'confirm', YES works and the retry POST is sent. Its only gap is the dropped-show case (I3-2).
- 13.8 flag separation works: YES on the active-print re-confirm retries with confirm_active_print:true (proven POST bodies), and the true-unassign retry preserves confirmActivePrint (inv_loc_mgr.js:1541, code-trace).
- In the 155-310 ms window the second confirm shows with a single remaining backdrop, yet it is topmost and fully usable (elementFromPoint inside the confirm; toast 'Ejected' after YES at 160/180/200 ms).
- doEject uses fetchT with a 15 s AbortSignal timeout (inv_core.js:306-307) and clears the processing overlay in both then and catch (inv_loc_mgr.js:1521, :1564), so it cannot strand the z-9999 overlay.
- The backend's active-print refusal in perform_smart_eject returns before any write or detach (logic.py:1518-1527; hermetic test_active_print_refusal_happens_before_detach passed).
- The eject button count and markup on the XL-1 manage view: contents-list EJECT badge `ejectSpool(57, 'XL-1', false)` (ui_builder.js:177) plus Quick-Swap card ejects (ui_builder.js:359). Both reach the same doEject chain, and both reproduced the race.

**Open questions (I3).**

- Which refusal actually produced Derek's double occupancy: the active-print dict or 'REQUIRE_CONFIRM'? Relatedly, did the 'wrong' spool have a physical_source? That decides whether his eject needed one racy hop or two. The Activity Log / hub.log for 2026-09-12 (lines like '↩️ Returned #N ->' or '🔓 Single-slot box(es) auto-detached') may show it.
- Does Derek's Windows have 'Animation effects' turned off? If so, Chrome reports prefers-reduced-motion: reduce, the fade window collapses to about 5 ms, and this race becomes unlikely (proven by the reduced-motion control). Windows defaults to animations on.
- Other requestConfirmation / promptSafety calls made from inside an async continuation of a confirm callback would share this race. Only the eject active-print and true-unassign hops were examined; for example, inv_loc_mgr.js:1626 and any promptSafety chain were not individually checked. The central deferral would cover them all.
- Code-trace only, not driven: a successful eject from a Quick-Swap card passes the BOX id as loc (ui_builder.js:359), so doEject calls refreshManageView(box). _renderManagePayload(box) then retitles and, for a single-slot box, renders box contents into the toolhead's manage view until the next pulse corrects it.
- The real POST latency was not measured end-to-end on purpose: a real POST would eject spool #57 if the print ended between the probe and the request. The server-side estimate is the sum of measured GET components.

### I4 — bulkmove-timeout-eject

Bulk move is not the cause. The client bulk-move state was driven through every candidate shape: armed from the LM or the deck, panel hidden or left open, the session ending server-side, and a stale still-armed session. The dryer-box slot-card eject behaved exactly like the no-bulk-move control each time: the confirm was on top, YES was the hit target, and the POST was sent. That rules out candidates (a) and (b), and (c) and (d) as they relate to the timeout.

What actually makes a slot-card eject silently do nothing is an app-side sequencing bug. doEject re-prompts on the same #confirmModal from inside the first confirm's YES callback, while Bootstrap is still fading that modal out. Bootstrap 5.3.0 `Modal.show()` returns early while `_isTransitioning` is set, so the second prompt is dropped.

Measured live, in-page with no network: a re-prompt at 0/50/104/133 ms after YES is dropped with `_isTransitioning: true`, and one at 171 ms or later shows. Clicking a DEPLOYED slot card's eject when the active-print re-prompt arrives in about 6 ms: no second confirm, no toast, no second POST. It fails the same way on a second try, and identically after a simulated bulk-move timeout. With 600 ms latency the same flow works.

Real dev latencies fall inside that window: spool read 14-36 ms, printer-state probe 36-238 ms (typically 40-80 ms). XL reports PRINTING on dev right now. So on Derek's setup, ejecting a deployed card (a spool on XL-n) from the LR-MDB-1/2 grids during a print will usually drop the prompt. The same applies to the "true unassign" prompt that TST-/PM-/PJ- box residents always get (code-trace).

Aggravating effect, proven live: the dropped prompt leaves `state.pendingConfirm` holding the retry callback. A later CMD:CONFIRM scan, with no dialog on screen, fired POST /api/manage_contents with `confirm_active_print: true`.

Confounder, proven live: after the window loses focus, the first click on return is absorbed by #focus-guard. That fits a 30-minute wait, but it fails only once, not persistently.

No server writes occurred. Every non-GET was intercepted and logged, the server session is still `{"active":false,"stage":"idle"}`, and LR-MDB-1's contents are unchanged. Nothing in the repo was edited.

#### I4-1 — Chained eject confirm is silently dropped when the backend's require_confirm arrives during the first confirm's hide fade (Bootstrap show() ignored while transitioning)

*Severity orange → **orange** after review · verdict **CONFIRMED** · proof: browser-run · confidence high*

**Claim.** The slot-card eject goes ejectSpool, then requestConfirmation, then YES, then confirmAction(true). That calls closeModal('confirmModal'), which starts Bootstrap's hide, and synchronously runs pendingConfirm, which is doEject. When /api/manage_contents answers require_confirm (active_print or true-unassign), doEject calls requestConfirmation again on the same modal instance. If that happens before Bootstrap's `_hideModal` (~130-170 ms after hide), `Modal.show()` returns early. requestConfirmation still sets `pendingConfirm` and `activeModal='confirm'`, but nothing is visible. Result: no dialog, no toast, no second request, and it repeats on every attempt while the server answers fast. The bulk-move session plays no part. The failure is not z-order: in every run the confirm was on top and YES was the hit target. It is the app calling show() on a modal that is still mid-hide, which Bootstrap's transition guard ignores.

**Evidence.**

- inv_core.js:1226 closeModal calls modals[id].hide(); inv_core.js:1227 requestConfirmation calls modals.confirmModal.show() with no settle check, then sets state.activeModal='confirm'; inv_core.js:1228 confirmAction runs pendingConfirm synchronously right after hide()
- inv_loc_mgr.js:1500 requestConfirmation(`Eject spool #${sid}?`, () => doEject(sid, loc)); inv_loc_mgr.js:1530-1543 the active_print and require_confirm branches call requestConfirmation from inside the fetch .then
- Bootstrap 5.3.0 js/dist/modal.js (fetched from jsdelivr): show() at lines 89-92 returns if `this._isShown || this._isTransitioning`; hide() at 115-118 sets `_isTransitioning = true` and queues _hideModal on the element's .fade transition (opacity .15s, bootstrap.css:3354-3356); _hideModal at 203-208 is the only place that clears it
- Live experiment A (results_chain.json, in-page, no network), re-prompt t ms after confirmAction(true): t=0 -> {isTransitioning: true, secondVisible: false}; t=50 -> false; t=104 -> false; t=133 -> false; t=171 -> {isTransitioning: false, secondVisible: true}; t=261 -> true; t=402 -> true. Every row: pendingConfirm_after1200 'function'
- Live experiment B0, a real mouse click on ghost card #57's eject in LR-MDB-1, synthetic reply active_print require_confirm at 0 ms: confirm1 'Eject spool #57?', confirm2_visible False, exactly 1 POST {confirm_active_print:false}, toasts [], probe shows fetchT:resolved 7 ms after the YES click and no second show.bs.modal. try2 is identical (repeatable)
- Live experiment B600, same reply at 600 ms: second confirm shows, the retry POST carries confirm_active_print:true, toast 'Ejected'
- Live experiment C, B0 after LM arm, Hide and a simulated server-side timeout (client synced in 3.73 s): identical to B0 (confirm2_visible False, 1 POST, try2 same)
- Real dev latencies (curl, 5 samples each): GET /api/spools/57 14-36 ms; GET /api/printer_state/XL-1 38-238 ms (4 of 5 ≤53 ms); XL-3 36-80 ms. /api/printer_state/XL-1 returned is_active:true, state PRINTING. perform_smart_eject performs these same reads before answering (logic.py:1496 onward, `_active_print_info_for_location` at logic.py:13; prusalink_api.get_printer_state is only memoized inside an explicit probe-cache scope)
- Which slot cards chain a second prompt: deployed/ghost cards (spool location is a printer_map toolhead -> active_print, logic.py:1519-1525) and any spool whose room resolves to '' -> 'REQUIRE_CONFIRM' (logic.py:1636, routes_scan.py:309). PSEUDO_ROOM_PREFIXES = {TST, TEST, PM, PJ} (locations_db.py:600) makes every TST-MDB-1 / PM-DB-n resident take that path (code-trace)

**Proof.** repro_chain.py experiments A, B0, B600 and C against http://localhost:8000. All POSTs fulfilled synthetically via page.route, and every intercepted request was logged. The in-page drop window (A) needs no network. The real-server latencies were measured with GET-only curl.

**Fix direction.** Minimal, one place (inv_core.js:1226-1228): never call show() on a gating modal that is still hiding. Track hiding via public events: set a flag on hide.bs.modal and clear it on hidden.bs.modal. In requestConfirmation (and promptSafety/promptAction), if the target modal is hiding, register a one-shot hidden.bs.modal listener on that element that calls show(). Otherwise show() now. Keep setting msg, pendingConfirm, the _confirmGeneration bump and activeModal synchronously. The element-level once-listener fires before the document-level scan-gate release (inv_core.js:1536-1580), which then sees `.show` restored and keeps activeModal; verify that ordering in the test. Do not use the private _isTransitioning. A related quirk worth folding in: Bootstrap also ignores hide() during the ~450 ms show fade (modal.js:106-108; already noted in tests/test_scan_path_integrity.py:417-421). So confirmAction should likewise defer the hide until shown.bs.modal if called mid-show.

**Regression test.** Deterministic Playwright test in the existing style (page + require_server; all network stubbed, so no dev writes). (1) Unit-level, in-page, no network: register requestConfirmation('first', () => requestConfirmation('second', cb)). Wait for shown.bs.modal, call confirmAction(true) (t=0 is the worst case and fully deterministic, since it runs in the same tick as hide()). Assert #confirmModal regains `.show` within 1500 ms and #confirm-msg is 'second'. Then click YES and assert cb ran exactly once. Repeat with a 100 ms delay before the second requestConfirmation. (2) End-to-end, no fixture data needed: page.route('**/api/manage_contents') fulfils the first call immediately with {success:false, require_confirm:true, confirm_type:'active_print', active_print:{printer_name:'XL',state:'PRINTING'}} and the retry with {success:true}. Call window.doEject(1,'FAKE-LOC') via evaluate, or ejectSpool(1,'FAKE-LOC',false) then click YES. Assert the active-print confirm becomes visible, click YES, and assert a second request body with confirm_active_print:true plus an 'Ejected' toast. Pre-fix this fails at 'visible' (proven: B0).

**Verifier.** This is the same root cause as I3-1, and my own run reproduced it (evidence under I3-1). The in-page show-is-ignored window and the no-network B0 drop fit my route-delay sweep. Code cites checked: inv_core.js:1226-1228, inv_loc_mgr.js:1500 and :1530-1543, and routes_scan.py:294-312. The true-unassign branch is also reproduced: my unassign-hop trial dropped the third dialog at 0 and 40 ms.

**Corrections.** 'Every TST-MDB-1 / PM-DB-n resident takes that path' depends on the data. It only applies when the spool has no physical_source and its room walk ends at a pseudo prefix. For dev PM-DB-2 #18 that is true (GET shows no physical_source, and /api/locations gives PM-DB-2 parent PM). Spools floating directly in a room (for example LR #24) take the same path, which I4 did not name. The fix_direction's hide-during-show quirk is accurate but separate.

#### I4-2 — A dropped re-prompt leaves a live pendingConfirm that a later CMD:CONFIRM scan fires, ejecting from a printing toolhead with the active-print override and no dialog shown

*Severity red → **orange** after review · verdict **CONFIRMED** · proof: browser-run · confidence high*

**Claim.** After I4-1 drops the active-print re-prompt, the hidden.bs.modal scan-gate release sets activeModal to null but deliberately leaves pendingConfirm, which holds the retry `doEject(sid, loc, false, true)`. A later CMD:CONFIRM scan passes processScan's modal gates, gets {type:'command', cmd:'confirm'} from the backend, and inv_cmd.js:1456 calls confirmAction(true). That fires the retry with confirm_active_print:true on a toolhead whose printer is PRINTING, although the user never saw or acknowledged the active-print warning. The confirm modal's own YES QR encodes CMD:CONFIRM, so any stray scan of it (or of a printed CMD:CONFIRM label) triggers this.

**Evidence.**

- Live check F (results_dangling.json): after B0's silent drop, pendingConfirm_before_scan 'function', any_modal_visible_before_scan []. processScan('CMD:CONFIRM','barcode') then produced POST /api/identify_scan (synthetic {type:'command',cmd:'confirm'}) followed by POST /api/manage_contents body {"action":"remove","location":"LR-MDB-1","spool_id":57,"confirmed":false,"confirm_active_print":true}; probe: call:doEject [57,"LR-MDB-1",false,true]
- logic.py:179 maps any text containing CMD:CONFIRM to {'type':'command','cmd':'confirm'}; inv_cmd.js:1456 `else if (res.cmd === 'confirm' && state.pendingConfirm) confirmAction(true);`
- templates/components/scripts.html:160 'qr-confirm-yes': 'CMD:CONFIRM'
- inv_core.js:1574-1580 releases only activeModal and deliberately keeps pendingConfirm; B0 snapshots show activeModal null plus pendingConfirm 'function'

**Proof.** repro_dangling.py against http://localhost:8000. identify_scan and manage_contents were fulfilled synthetically, and the scan was delivered through the real processScan router via page.evaluate. No request reached the server.

**Fix direction.** Fixing I4-1 removes the main trigger. Defence in depth: make inv_cmd.js:1456 fire confirmAction only while a gating dialog is actually visible (#confirmModal has .show and activeModal === 'confirm'). Or clear pendingConfirm when a requestConfirmation's show never produced shown.bs.modal, for example via a generation-tagged check about 1 s later.

**Regression test.** Same stubbed E2E as I4-1 (2), but on pre-fix behaviour: force the drop (manage_contents stub replies instantly), then stub /api/identify_scan to {type:'command',cmd:'confirm'} and call processScan('CMD:CONFIRM','barcode'). Assert NO manage_contents request with confirm_active_print:true is issued while no dialog is visible. It fails today (proven by F).

**Verifier.** Duplicate of I3-2, and re-proven the same way. I lowered it from red: it takes a later stray CMD:CONFIRM scan to fire. The eject was user-initiated and had already been confirmed once ('Eject spool #57?'); only the active-print acknowledgement is bypassed. The result is a Spoolman record change: the spool shows as ejected from a printing toolhead, so the completion deduct can mis-attribute grams. It does not physically interrupt the print. That is data integrity, not data loss or a safety issue.

**Corrections.** Downgrade to orange. Reachability is actually wider than stated. Besides a scan of the confirm modal's own QR, a stale session-scoped `CMD:CONFIRM:<sid>` QR also fires it: routeConfirmScan returns false for an unknown sid (inv_core.js:468), and logic.py:179 substring-matches it. A backdrop-dismissed confirm also leaves the callback armed.

#### I4-3 — The bulk-move timeout does not affect slot-card eject: all candidate client states behave like the control

*Severity info → **info** after review · verdict **PLAUSIBLE** · proof: browser-run · confidence high*

**Claim.** Simulating the server-side idle timeout while the panel is hidden, whether armed from the Location Manager or the deck, gives the same result as the no-bulk-move control. So does a timeout with the panel left open, and a stale still-armed client. In each case the eject button is the hit target and passes actionability, the Bootstrap confirm shows and YES is topmost inside #confirmModal, the POST /api/manage_contents is sent, and 'Ejected' is toasted. After the timeout the client fully unwinds: no overlay mount remains, the pill is display:none, processing is false, and activeModal is null. Candidates (a) confirm behind overlay, (b) stale client state, (c) stuck guard and (d) backend refusal are all ruled out as consequences of the bulk-move session.

**Evidence.**

- results.json v0 control: eject_btn_top div.fcc-card-action-btn, actionability ok, confirm_appeared true, yes_hit button.btn.btn-lg.btn-success inConfirmModal true, 1 POST, toasts ['Ejected']
- v1 (LM 'Move all →' real click, Hide, sim timeout, client sync 4.28 s): armed_snap overlayMounts [fcc-bulkmove-panel-overlay z20000], pill flex; hidden_snap overlayMounts [], pill flex; after_timeout_snap bulkMoveActive false, stage idle, overlayMounts [], pill none, processing false, activeModal null, deckLabel 'BULK MOVE'; eject: same as control, POST body {action:remove, location:LR-MDB-1, spool_id:99, ...}
- v2 (deck toggleBulkMove, Hide, timeout, then open box; sync 1.3 s), v3 (panel left OPEN over the LM; the panel poll closed it within 0.19 s) and v4 (still armed and hidden, never timed out): all identical to control (confirm_appeared true, YES topmost, 1 POST, 'Ejected')
- Code: on the idle edge, inv_core.js:1190-1198 _syncBulkMoveSignal calls updateBulkMoveVisuals (inv_cmd.js:303), which runs shapeshift idle onEnter (inv_cmd.js:288) -> closeBulkMovePanel (inv_cmd.js:1013), and cleanup removes every listener mountOverlay added (overlay_mount.js:195-204). The panel installs no other document or window listeners (inv_cmd.js 590-975: only a per-element 'toggle' listener at :921)
- Backend: the manage_contents remove branch (routes_scan.py:294-312) and perform_smart_eject (logic.py:1496-1680) contain no BULK/bulk reference (grep); the watchdog (routes_state_pulse.py:176-210) only calls state.reset_bulk_move(), an in-place dict update (state.py:148-165)

**Proof.** repro_eject.py variants v0-v4 (results.json, results_v0.json, v*_*.png). /api/bulk_move_session was served from an in-memory sim; /api/logs and /api/dashboard_pulse were fetched via plain GET with bulk_move_active/stage overwritten, plus the watchdog's WARNING line injected. No real session was armed.

**Fix direction.** None for bulk move itself. Re-describe buglist finding 1 as the chained-confirm drop (I4-1) plus the focus-guard first-click (I4-4). The 'after the timeout' association is temporal: the testing happened during an XL print, and dev's LR-MDB-1/2 slot cards are ejecting spools deployed to that printing XL.

**Regression test.** No new test required for bulk move. Optionally add a Playwright test with page.route-simulated /api/bulk_move_session and pulse flags: arm, Hide, flip to inactive, wait for state.bulkMoveActive === false, then assert no [data-overlay-mount] exists, the pill is display:none, and an ejectSpool click shows #confirmModal with its YES as the elementFromPoint target.

**Verifier.** I did not re-run I4's v0-v4 bulk-move variants. My code read supports the conclusion:
- ejectSpool and doEject (inv_loc_mgr.js:1481-1565) read no bulk-move state.
- The routes_scan.py:294-312 remove branch has no bulk reference.
- mountOverlay cleanup runs every disposer and removes the root (overlay_mount.js:195-204).
- In the bulk-panel range of inv_cmd.js, the only listeners are the DOMContentLoaded shortcut registration (:586) and a per-element 'toggle' (:921).
- The idle onEnter closes the panel (inv_cmd.js:288).

The race I proved independently needs no bulk-move state at all. That Derek's session happened during the XL print is an inference.

**Corrections.** Say plainly that the replacement explanation covers only the cards whose eject triggers a re-prompt: ghost cards deployed to a printing toolhead, and homeless PM/TST/room residents. A direct LR-MDB-1 resident with no saved source returns to room LR on the first POST (logic.py:1623-1625) with no re-prompt, so the race cannot explain a failed eject on such a card.

#### I4-4 — Returning to the window after a long wait: the first click is absorbed by #focus-guard (by design) — a one-shot confounder

*Severity yellow → **info** after review · verdict **PLAUSIBLE** · proof: browser-run · confidence high*

**Claim.** When the browser window loses focus (for example while waiting out a 30-minute timeout), the full-screen #focus-guard (z-index 30000) shows. On return, the window focus event sets opacity 0 but keeps the guard displayed for 100 ms, so the click that re-focuses the window lands on the guard, which swallows it. The first eject click therefore does nothing and the second works. This can make eject look broken after a long wait, but it fails once, not persistently.

**Evidence.**

- templates/components/scripts.html:225-231 blur shows the guard; :233-246 on focus sets opacity '0' and hides it only after setTimeout 100; :129-133 fg.onclick preventDefault + stopPropagation; static/css/global.css:521 z-index: 30000
- Live experiment D (results_chain.json): guard_while_away 'flex'; after dispatching window focus then an immediate mouse click on the eject center: first_click_confirm_visible False, probe pointerdown/click target 'div#focus-guard'; second click: target div.fcc-card-action-btn -> call:ejectSpool [99,"LR-MDB-1",false] -> shown.bs.modal, second_click_confirm_visible True

**Proof.** repro_chain.py experiment D. In headless Chromium, window blur/focus were dispatched manually to emulate leaving and returning; the click was a real page.mouse.click.

**Fix direction.** Working as designed ('Click anywhere to resume'). Mention it in the buglist so it isn't mistaken for the eject bug. Optionally show a brief 'scanner resumed' toast when the guard eats a click, so the swallowed click is visible.

**Regression test.** Not needed. If the UX changes, dispatch a window blur, then focus plus an immediate click, and assert the guard's documented behaviour (the click target is #focus-guard and a subsequent click reaches the page).

**Verifier.** Code checked: scripts.html:128-133 (the guard swallows clicks), :225-231 (shown on blur), :233-246 (opacity 0 on focus, hidden 100 ms later), and global.css:521 (z-index 30000). I did not reproduce it. Firing blur/focus by hand in headless Chromium cannot show how a real window activation orders focus and mousedown; only the code comment claims focus comes first.

**Corrections.** Lower to info. It is working as designed, and before the click the guard is visibly on screen ('SCANNER PAUSED — Click anywhere to resume'). It swallows exactly one click and needs a window blur, not the bulk-move timeout, so it cannot account for a persistent 'eject broken'.

#### I4-5 — Quick-Swap 'Slot N' card eject posts the BOX as location and refreshes the box's contents while the toolhead view is on screen

*Severity yellow → **yellow** after review · verdict **CONFIRMED** · proof: browser-run · confidence medium*

**Claim.** The Quick-Swap card's eject button passes the source box id, not the viewed toolhead, as `loc`. After a successful eject, doEject calls refreshManageView(box) while manage-loc-id is the toolhead. The Quick-Swap grid itself is only re-rendered by the next 5 s sync-pulse's silent refresh. The eject POST is unaffected, because the backend uses the spool's real location, so this does not cause a no-op. It can make a successful eject look stale for up to one pulse, and it re-renders the manage payload for the wrong location. This is relevant if Derek's 'slot version of the filament cards' meant these cards; it is also adjacent to buglist finding 2.

**Evidence.**

- ui_builder.js:359 quickswap card: `ejectSpool(${item.id}, '${box}', false)`
- Live experiment E (results_chain.json): toolhead XL-1, card {spool 57, box LR-MDB-1, slot 1}, manage_loc_id XL-1, list_view block. The eject POST body has location "LR-MDB-1"; probe shows call:refreshManageView ["LR-MDB-1"] at +7 ms, then about 1.5 s later the pulse runs _renderManagePayload ["XL-1"] and renderQuickSwapSection ["XL-1",{silent:true}]
- inv_loc_mgr.js:845-856 refreshManageView(id) renders whatever id it is given into the single manage modal; inv_quickswap.js:1250-1261 the grid refreshes only on inventory:sync-pulse / buffer-updated

**Proof.** repro_chain.py experiment E, with a synthetic manage_contents success. Because the reply was synthetic, server data did not change, so what the card would look like after a real eject was not observable; only the call sequence and request body are proven.

**Fix direction.** In doEject's success path, refresh the manage view that is actually open (document.getElementById('manage-loc-id').value) rather than `loc`, and call window.renderQuickSwapSection on the current toolhead (or dispatch inventory:sync-pulse) so the Quick-Swap grid updates immediately.

**Regression test.** Playwright with page.route: stub /api/manage_contents with a success reply and serve /api/get_contents for the toolhead with the ejected spool removed. Open a toolhead that has Quick-Swap cards, click a card's eject, then YES. Assert that the next get_contents request is for the toolhead id (not the box) and that the card disappears without waiting for a pulse.

**Verifier.** Independently proven by vf_probe.py quickswap, with a real click on the Quick-Swap card eject `ejectSpool(57, 'LR-MDB-1', false)` and a synthetic success reply:
- The POST body carried location "LR-MDB-1".
- GET /api/get_contents?id=LR-MDB-1 fired immediately after YES.
- 700 ms after YES, #manageTitle read '📍 LR-MDB-1 Dryer Box 4/4 Spools 🔀 Move all →' while #manage-loc-id was still 'XL-1'.
- By 6.7 s it was back to '📍 XL-1 Tool Head 1/1 Spools', restored by the pulse, which keys off manage-loc-id (inv_core.js:1336-1341) and renders at :1423-1424.

Code checked: ui_builder.js:359, and inv_loc_mgr.js:1554-1557 plus 845-857.

**Corrections.** A little worse than described: for about one pulse the toolhead view shows the box's whole grid and title, including LR-MDB-1's '🔀 Move all →' bulk-move entry button, under the XL-1 manage id. It is transient and not a cause of the no-op.

**Ruled out (I4).**

- *(a) Slot-card eject's Bootstrap confirm renders behind a still-mounted mountOverlay panel or backdrop after the bulk move* — Proven live in v1-v4. After the simulated timeout, overlayMounts is [] and the pill is display:none. elementFromPoint at YES returns button.btn.btn-lg.btn-success inside #confirmModal (z 1065 over manageModal z 1055), and clicking it sent the POST. With the panel left open (v3), the panel's own 2 s poll closed it within 0.19 s of the session ending. The only 'confirm behind the panel' case is with the panel still OPEN, and then its backdrop covers the eject button, so that click cannot happen.
- *(b) Stale client bulk-move state after the server-side watchdog reset* — Proven live. Via the pulse, the client synced to bulkMoveActive=false in 1.3-4.3 s (v1, v2). Even a deliberately stale still-armed client (v4: bulkMoveActive true, pill visible) ejects normally, because ejectSpool/doEject never read bulk-move state (inv_loc_mgr.js:1481-1565). The panel installs no document or window listeners that outlive cleanup (overlay_mount.js:195-204; only a per-element 'toggle' listener at inv_cmd.js:921).
- *(c) A stuck in-flight or processing guard (setProcessing, window._pickInFlight, _refreshManageViewInflight)* — Proven live, not stuck. Every snapshot shows processing false and #processing-overlay display none, and the pulse kept calling _renderManagePayload after each eject. _pickInFlight guards only the pickup branch (inv_loc_mgr.js:1483), not eject. A hung refreshManageView (bare fetch, inv_loc_mgr.js:851) could stall the view refresh, but it runs only after the eject POST and the 'Ejected' toast, so it cannot make the click itself a no-op. None of these is touched by the bulk-move timeout.
- *(d) Backend refuses the eject because of the bulk-move session* — Code-trace plus grep. The manage_contents remove branch (routes_scan.py:294-312) and perform_smart_eject (logic.py:1496 onward) contain no BULK/bulk reference, and the watchdog only calls state.reset_bulk_move(), an in-place dict update (routes_state_pulse.py:201-210, state.py:148-165). The backend does return require_confirm for deployed or printing-toolhead spools and room-less spools; the client-side drop of that re-prompt is I4-1.
- *Bootstrap stacking or z-order defect as the cause* — Derek's doubt is borne out. Nothing rendered behind anything in any run. Bootstrap's part is only its documented transition guard (modal.js:89-92 ignores show() while _isTransitioning); the defect is FCC calling show() on the same modal mid-hide (inv_core.js:1226-1228 with inv_loc_mgr.js:1530-1543).

**Checked correct (I4).**

- mountOverlay cleanup removes the keydown capture, focusin guard, occlusion and host listeners, and the root node (overlay_mount.js:195-204); no bulk-move panel residue after a timeout (live v1-v4 snapshots)
- Pulse bulk-move sync works on both heartbeat shapes and closes a hidden session's pill (inv_core.js:1190-1198, :1420; live sync in 1.3-4.3 s)
- Shapeshift idle onEnter closes the panel and clears the Hide latch (inv_cmd.js:288, :1013-1023)
- The panel poll closes an open panel as soon as the session ends (inv_cmd.js:950-955; live v3 0.19 s)
- Grid slot-card eject wiring: direct and ghost cards call ejectSpool(id, locId, false) (ui_builder.js:218, :244); control run sends the correct POST body
- setProcessing and fetchT: the processing overlay is never left stuck in any run (inv_core.js:294-306)
- The scan-gate release after a confirm dismissal works: activeModal returns to null (inv_core.js:1536-1580; B0 snapshots)
- Chained confirm works when the server reply arrives after the hide transition (B600: second prompt shown, retry carries confirm_active_print:true)
- No dev mutation: every non-GET was intercepted (logged); afterwards GET /api/bulk_move_session = {active:false, stage:idle} and LR-MDB-1 contents (57/99/134/196, slots 1/4/3/2) were unchanged

**Open questions (I4).**

- The latency of a real POST /api/manage_contents remove was not measured, because that would be a write. Its component reads were measured with GETs (spool 14-36 ms, printer-state probe 36-238 ms), which puts a typical active-print or true-unassign reply inside the ~130-170 ms drop window. A cold PrusaLink probe (up to its 2 s timeout) would escape the window, so the failure is timing-dependent. That could explain why it 'worked after coming back' in Derek's finding 2 (for example, the print ended so no re-prompt was needed, or the probe was slow).
- Which cards Derek clicked is unknown: the grid's DEPLOYED ghost cards on LR-MDB-1/2 (active-print chain, affected), the direct resident #99 (no chain, unaffected), a TST-/PM- box resident (true-unassign chain, affected), or Quick-Swap 'Slot N' cards on a toolhead view (I4-5). A DevTools Network capture on his next attempt settles it: exactly one manage_contents POST followed by no dialog is the I4-1 signature.
- Finding 2 (two spools on one head, eject did nothing until he came back) fits I4-1 on a printing toolhead. Ejecting the wrong spool off XL-n during a print always takes the active-print re-prompt, so it may be the same mechanism rather than a separate hang. This was not separately reproduced here.
- Proposed fix ordering around the document-level hidden.bs.modal scan-gate release (inv_core.js:1536-1580): the element-level once-listener that re-shows should run before the document listener captures the generation. That is how DOM propagation works, but it should be pinned by the regression test.

### Frontend: Verifier challenges to ruled-out items

- I3 (a) hung _refreshManageViewInflight: I AGREE it cannot make the eject a no-op. doEject never consults the flag (inv_loc_mgr.js:1502-1565), and the pulse re-renders the open manage view straight through _renderManagePayload, bypassing the flag (inv_core.js:1336-1341 includes 'manage'; :1423-1424 renders it). One residual they did not state: while the flag is stuck, the eject's own refreshManageView(loc) after success is skipped silently. The pulse repairs the view within about 5 s, so this still cannot explain 'nothing moved until I came back'.
- I3 'confirm rendering behind another layer' / I4 (a): I AGREE for the button path. In my own runs, real Playwright clicks on #confirmModal's YES passed hit-testing and sent the POST every time the dialog was shown. Narrow residual, code-trace only: a CMD:TRASH:<id> scan is handled client-side (inv_cmd.js:1426) and calls ejectSpool whenever #manageModal is shown. That includes while the bulk-move panel (z 20000) is open, which would put #confirmModal (z 1100) BEHIND it: the deadlock class documented at inv_cmd.js:1437-1446. This is not the card-button path Derek described.
- Both investigators' 'not a Bootstrap defect': I AGREE, with a caveat Derek should hear. Bootstrap's transition guard IS the thing FCC trips over. The live 5.3.0 show() returns while _isTransitioning, and hide() ignores calls during the show fade. So Bootstrap behaves as designed and the defect is FCC's call order. Any fix that ignores Bootstrap's lifecycle (hide.bs.modal/hidden.bs.modal) will not work. Derek is right that Bootstrap is not buggy, but wrong if that means Bootstrap has nothing to do with it.
- Derek's symptom 1 (bulk-move timeout breaks slot-card eject), dismissed as not causal by I4-3 and implicitly by I3: the dismissal is supported by code (no bulk-move state in the eject path) and by I4's un-re-run browser variants. The replacement explanation, ghost cards of XL-deployed spools during the print, is still inference. If the card Derek clicked was a direct LR-MDB resident with no saved source, the backend returns it to room LR on the first POST with no re-prompt (logic.py:1623-1625), and then neither the race nor bulk move explains his failure. Ask which card it was, or capture DevTools Network: exactly one manage_contents POST followed by no dialog is the race signature.
- I3 (c) wrong record under double occupancy: I AGREE the backend acts on spool_id (routes_scan.py:294-298). But 'double occupancy does not matter' should not survive. The homeless resident's second hop is PROVEN dropped (my unassign-hop trial at 0/40 ms), and its refusal has already detached single-slot boxes (I3-4, re-run: 2 passed).

### Frontend: Duplicates

- I3-1 == I4-1: same root cause (#confirmModal re-shown from inside confirmAction's callback while Bootstrap 5.3.0 is still hiding it; drop threshold between about 131 and 161 ms in both investigators' runs and mine)
- I3-2 == I4-2: an orphaned state.pendingConfirm fired by a later CMD:CONFIRM scan (inv_cmd.js:1456), which POSTs confirm_active_print:true
- I3-3 is a facet of I3-1/I4-1 (the second, true-unassign hop; same mechanism, same central fix), and I4-1's claim already names that branch
- I4-5 == I3 open question #4 (the Quick-Swap card eject passes the box as loc, so refreshManageView(box) renders into the toolhead view)
- I3-5 overlaps I4 open question #3 (the 'worked after coming back' explanation)

### Frontend: found by the verifier, missed by every investigator

#### The eject re-prompt drop does not need an active print: every button eject that gets the plain true-unassign prompt is affected

**Claim.** Ejecting a spool that floats directly in a room (a location ID with no dash) or sits in a PM/PJ/TST box with no saved home makes the backend answer REQUIRE_CONFIRM with no PrusaLink probe on the way. The answer arrives fast, so from the card or list EJECT button the 'True Unassign' confirm is silently dropped, just like the active-print one. That is a routine, no-print workflow. Both investigators framed the drop as a mid-print problem. I4-1 named TST/PM residents only in passing as code-trace; spools floating in a room were not mentioned. The regression test must include a non-active-print re-prompt.

**Evidence.** Browser-run, verify-frontend/vf_roomfloat.py, real clicks with every non-GET intercepted:
- LR view `ejectSpool(24, 'LR', false)`, delay 20 ms: gap 28.0 ms, isShown_after_rearm False, unassign_visible False, activeModal None, pending function, only one POST.
- Same at 400 ms: visible, and YES posted `{"confirmed":true,...}` with toast ['Ejected'].
- PM-DB-2 view `ejectSpool(18, 'PM-DB-2', false)`, 20 ms: gap 25.6 ms, dropped.

The real backend really does answer this way on dev data (code-trace plus GETs): GET /api/spools/24 gives location LR, physical_source ""; GET /api/spools/18 gives location PM-DB-2, no physical_source; /api/locations shows PM-DB-2 with parent PM. logic.py:1476-1477 returns '' for a dash-less ID, logic.py:1491 excludes locations_db.PSEUDO_ROOM_PREFIXES (locations_db.py:600), and logic.py:1636 returns REQUIRE_CONFIRM before any write. The probe returns early for locations not in printer_map (logic.py:29-31). Backend latency is inference: get_spool GET median 15.5 ms (I3), 14-84 ms in my samples.

#### The orphaned pendingConfirm hazard exists WITHOUT the race: a backdrop-dismissed confirm stays armed and a later CMD:CONFIRM scan fires it

**Claim.** Dismissing a VISIBLE confirm without its buttons, by backdrop click (or the Escape ladder's inst.hide()), leaves state.pendingConfirm armed, because the hidden.bs.modal release deliberately clears only activeModal. Any later CMD:CONFIRM scan then runs the dismissed action. If the dismissed dialog was the active-print warning, it POSTs confirm_active_print:true, the exact thing the user just declined. Fixing the show() race (I3-1/I4-1) therefore does not close I3-2/I4-2. A guard is required: inv_cmd.js:1456 should fire only when a gating dialog is actually visible, or pendingConfirm should be nulled on a non-button dismissal when the generation is unchanged.

**Evidence.** Browser-run, verify-frontend/vf_probe.py orphan, real mouse click at (15,650) on the #confirmModal backdrop.
- on_first_confirm: pre_shown=True 'Eject spool #57?'; after dismissal shown=False, activeModal=None, pending=function. processScan('CMD:CONFIRM') sent identify_scan, then manage_contents `{..."spool_id":57,"confirmed":false,"confirm_active_print":false}`.
- on_active_print_confirm: msg 'XL is PRINTING - ejecting from this toolhead will disrupt the print.' was dismissed, and the scan sent manage_contents `{..."confirm_active_print":true}`.

Code: inv_core.js:1567-1581 (only activeModal released) and inv_cmd.js:1456. tests/test_scan_path_integrity.py:468 even pins that pendingConfirm survives a non-button dismissal, so this is a known state with no guard against it firing later.

#### A stale session-scoped confirm QR (CMD:CONFIRM:<sid>) falls through to the generic confirm and fires an orphaned callback

**Claim.** routeConfirmScan returns false for an unknown or expired sid. processScan then continues to /api/identify_scan, whose substring match maps 'CMD:CONFIRM:<sid>' to {cmd:'confirm'}, and inv_cmd.js:1456 runs confirmAction(true) on whatever pendingConfirm is orphaned. That contradicts the design comment that a stale QR 'can't accidentally fire'. Inline confirm overlays show these QRs (inv_quickswap.js:488, inv_loc_mgr.js:1379, inv_cmd.js:1821), so a scanner double-read of a YES QR after its overlay has closed is a realistic trigger for the I3-2/I4-2 hazard.

**Evidence.** Browser-run, verify-frontend/vf_stale_sid.py: after a delay-0 dropped re-confirm, window.routeConfirmScan('CMD:CONFIRM:zzstale123') returned false. processScan('CMD:CONFIRM:zzstale123','barcode') then sent POST /api/identify_scan `{"text":"CMD:CONFIRM:zzstale123","source":"barcode"}` followed by POST /api/manage_contents `{"action":"remove","location":"XL-1","spool_id":57,"confirmed":false,"confirm_active_print":true}`. The identify_scan reply was synthetic; the real mapping is from reading logic.py:175-179 (`if "CMD:CONFIRM" in upper_text`). Also read: inv_core.js:454 routeConfirmScan; :468 `if (!entry) return false;`; inv_cmd.js:1408 falls through when it returns false.

#### Eject-mode scan is immune to the first (active-print) hop, which matters for regression-test design and for 'it worked when I came back'

**Claim.** An eject triggered by a spool scan in eject mode calls ejectSpool(id,'Scan'). That skips the 'Eject spool #N?' confirm, so no hide is in progress when the active-print prompt arrives, and the prompt shows reliably even with a 0 ms backend. A regression test that drives doEject/ejectSpool with loc 'Scan' would pass on unfixed code; it must use a card or list button, or a non-'Scan' loc. It is also a third candidate for Derek's later success: if the retry went through a scan, it would work mid-print. A following true-unassign hop would still race (same mechanism as the proven unassign-hop trial; not separately run on the scan path).

**Evidence.** Browser-run, verify-frontend/vf_scaneject.py: page.evaluate ejectSpool(57,'Scan',false) with the first reply active_print at 0 ms gave first_prompt_visible=true. YES sent POST `{"location":"Scan",...,"confirm_active_print":true}` with toast ['Ejected']. Code: inv_loc_mgr.js:1500 `if (loc !== "Scan") requestConfirmation(...) else doEject(sid, loc);` and inv_cmd.js:1668 `if (state.ejectMode) { ejectSpool(res.id, "Scan", false); return; }`.


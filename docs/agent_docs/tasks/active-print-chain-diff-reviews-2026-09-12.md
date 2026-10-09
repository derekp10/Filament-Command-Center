# Active-print move pipeline — adversarial diff reviews (2026-09-12)

Review record for fix/active-print-chain-confirm. Two workflows reviewed the branch's uncommitted diff after it was built from the verified investigation (active-print-chain-investigation-2026-09-12.md): a 4-agent backend review (R1 engine correctness, R2 response contracts and consumers, R3 tests and conventions via mutation testing and pre-fix HEAD runs, plus one batched adversarial verifier) and a 2-agent review of the frontend confirm-modal re-show fix (FE, plus a verifier). Line numbers refer to the working tree at review time. Findings marked fixed in Feature-Buglist.md were applied on the branch the same day; the rest are filed there as follow-ups. Scratch tests and browser probes they cite were session-temporary and are not kept; claims, outputs and verdicts are copied verbatim from the agents' structured results.

## Verdict summary

| id | verdict | severity after review | finding |
|---|---|---|---|
| R1-01 | CONFIRMED | orange | Undo of a Smart Load writes the resident back onto a toolhead that still holds the incoming spool |
| R1-02 | CONFIRMED | info | An unreadable ghost or prefix match refuses a load onto an empty head; one extra Spoolman read per match |
| R1-03 | CONFIRMED | yellow | The resident list read is still fail-open, so a Spoolman blip stacks a second spool on an occupied head (existed before) |
| R1-04 | CONFIRMED | info | A legacy toolhead-valued ghost trail survives a re-scan onto the same head, so the spool is still charged for the other head |
| R1-05 | CONFIRMED | yellow | Head-to-head moves now trigger the 13.6 reverse-binding, which stacks a ghost on an occupied bound slot; Return then unseats the staged spool |
| R1-06 | PLAUSIBLE | info | The undo fold finds the chained record by origin and stack depth, not identity |
| R1-07 | CONFIRMED | info | Return reports a get_spool blip as an empty toolhead ('nothing to return', 404) |
| R2-01 | CONFIRMED | orange | Deposit confirmed with Enter still sends confirm_active_print:false, so a keyboard deposit during a print loops on "Deposit again to confirm" forever |
| R2-05 | CONFIRMED | yellow | Force Location Override is the one manage_contents 'add' consumer left keying on status==='success': a rejected write still toasts "Location updated via override" |
| R2-06 | PLAUSIBLE | info | Quick-Swap and Return still hard-code confirm_active_print=True; with fix B that now authorizes unloading a printing head's spool even when no warning was shown |
| R2-02 | CONFIRMED | yellow | return_failed breaks the 29.B3 contract: `toolhead` is the re-tagged ACTIVE head, with no active_toolhead/requested keys |
| R2-03 | CONFIRMED | info | Return overlay still counts ghosts when resolving the head, so it offers a Return the backend now refuses as 'empty'; a doubled head is only discovered after confirming |
| R2-04 | CONFIRMED | info | Return reports a toolhead as empty when its resident merely could not be read from Spoolman |
| R2-07 | PLAUSIBLE | info | Failure status codes are inconsistent (502 / 409 / 200), and a 502 is fragile behind a proxy |
| R2-08 | PLAUSIBLE | info | Deposit's confirm is an unscoped boolean; a stale grid can carry the confirm to a different printing head |
| R3-01 | CONFIRMED | yellow | Fix D (pop -> "") is pinned by no test; reverting it passes the whole relevant suite |
| R3-02 | CONFIRMED | yellow | Smart Load's exact-location resident filter is pinned only for ghosts, not for the Printer-row prefix case |
| R3-03 | CONFIRMED | yellow | Two Smart Load refusal branches are unpinned: an unreadable resident, and the undo record after a partial unload |
| R3-04 | CONFIRMED | yellow | Fix C's Type-row branch of _is_single_occupancy is unpinned; only printer_map heads are tested |
| R3-05 | CONFIRMED | info | The chain's one-slot-feeds-one-head rule (only the last placed spool deploys) is unpinned |
| R3-06 | CONFIRMED | info | Fix E split the Group 20.2 detach into two call sites, but only the return-home one is tested |
| R3-07 | CONFIRMED | info | Two tests use an idle-then-PRINTING trigger that the real per-move probe cache makes impossible |
| R3-08 | CONFIRMED | yellow | Frontend fix G has no offline test coverage at all |
| R3-09 | CONFIRMED | info | CLAUDE.md write-surfaces table not updated for the changed and new write paths |
| R3-10 | CONFIRMED | info | Three smaller branches of the diff survive every test |
| R3-11 | CONFIRMED | info | test_quickswap_return_ignores_a_ghost_resident fails on HEAD for a different reason than its docstring |
| FE-1 | CONFIRMED | orange | Double-clicking YES confirms the re-prompt (active-print override / true unassign) without it ever showing |
| FE-2 | CONFIRMED | yellow | New 7 s 'Confirm scan ignored' warning fires after a successful confirm and in other harmless cases |
| FE-3 | CONFIRMED | yellow | isGatingModalOnScreen is lifecycle-only: a confirm hidden behind a mountOverlay still accepts a CONFIRM scan |
| FE-4 | CONFIRMED | yellow | E2E pins only #confirmModal; the new safety/action deferral and promptAction generation bump have no regression test |
| FE-5 | CONFIRMED | info | Known open item: a stale CMD:CONFIRM:<sid> still confirms a different, fully shown Bootstrap dialog |
| FE-6 | PLAUSIBLE | info | Minor flake surface in the eject-refresh E2E |

## Diff review

### R1 — 

I reviewed the engine changes in logic.py (Smart Load, the auto-deploy chain, the ghost-trail helpers, perform_smart_eject, perform_undo) against every caller of perform_smart_move and perform_smart_eject. Nothing in the repo was edited, and no dev data was touched.

Test runs:
- Scratch tests: 17 hermetic tests, run against both the working tree (WT) and a HEAD extract. The real spoolman_api location matcher ran; Spoolman, PrusaLink and the locations.json readers and writers were faked. The write tripwire recorded 0 repo writes on both runs.
- Repo offline suite on the WT: 1691 passed, 1 failed, 798 skipped. The single failure is the known blank-LocationID row in data/locations.json, so the diff broke no existing test.
- Python 3.9 grammar check passes for logic.py, routes_bindings.py and routes_scan.py.

Results: 7 findings, all backed by failing scratch tests. 1 orange, 4 yellow, 2 info. Five are new in the diff: they pass on HEAD and fail on the WT. Two already existed and the diff leaves them open.
- **R1-01 (orange, new).** perform_undo now really writes an ejected resident back onto its toolhead, without checking that the incoming spool left. If the incoming spool's restore write fails (one Spoolman read blip makes update_spool refuse), the head ends up holding two spools and undo still returns success.
- **R1-02 (yellow, new).** Smart Load reads every matched spool with get_spool before deciding whether it is a real resident. A single unreadable ghost from another head refuses a load onto an EMPTY head, although the detailed matcher already carries is_ghost and location.
- **R1-03 (yellow, existed before).** The resident LIST read is still fail-open. A get_all_spools blip makes an occupied head look empty, and the load stacks a second spool with status success. That breaks the invariant the fix claims, and it is inconsistent with R1-02 failing closed.
- **R1-04 (yellow, existed before).** A legacy toolhead-valued ghost trail survives a re-scan onto the same head, because the is_already_here branch bypasses _ghost_trail_from. The spool keeps getting charged for the other head's prints.
- **R1-05 (yellow, new).** Head-to-head moves now go through the 13.6 reverse-binding, which never checks whether the bound slot is occupied. A spool staged in that slot gets a ghost stacked on it, and a later Return silently unseats it. The chain skips this diff added make that staged state more common.
- **R1-06 (info, new).** The undo fold finds the chained record by origin and stack depth, not by identity. A simulated concurrent chain record with the same origin was popped and merged.
- **R1-07 (info, new).** Return now reports a get_spool blip as "XL-3 is empty — nothing to return" with a 404. HEAD reported a false return_done instead, so this is safer but still misleading.

On the open questions:
- Refusing the move because a REAL resident cannot be read or moved matches Derek's decision and is reasonable. Refusing for ghosts and prefix matches is not needed (R1-02), and the more likely blip point, the list read, still fails open (R1-03).
- "A toolhead is never a home" breaks no intended flow I could find. The DRYER and GENERIC branches always meant to clear the trail, and eject and force-unassign write "". The one behaviour change: a spool whose saved source is the virtual Printer row XL (Max 0) now asks for an unassign confirm instead of returning to XL. That matches plan_bulk_move's single-occupancy types.
- Latency is roughly neutral or better. get_spool calls per Smart Load, WT vs HEAD: 4 vs 3 with one resident, 6 vs 7 with a resident plus two ghosts, 4 vs 7 when the target is the XL Printer row.

#### R1-01 — Undo of a Smart Load writes the resident back onto a toolhead that still holds the incoming spool

*Severity orange → **orange** after review · verdict **CONFIRMED** · proof: test-run · `inventory-hub/logic.py:2066`*

**Claim.** perform_undo restores 'moves' first and 'ejections' second, and the ejection restore always runs. Before this diff the ejection record held the resident's post-eject location, so that write was a no-op. It now writes the resident's pre-eject toolhead plus its extras. Nothing checks that the incoming spool's restore landed, or that nothing else was loaded since. If the incoming spool's restore write is refused, the resident is put on top of it. update_spool refuses on a single _get_raw_extras read blip (Group 36), and the undo payload always carries 'extra'. perform_undo still returns {'success': True}.

**Failure scenario.** XL-1 holds #99, whose home is LR-MDB-2:2. Load #42 from CR onto XL-1: #99 goes home and #42 is on XL-1. Press CMD:UNDO while Spoolman refuses #42's restore write. #42 stays on XL-1, #99 is written back onto XL-1, and undo says success. XL-1 now holds two spools, which then silently blocks the deduct for that position (I5-13). A non-recording writer that loads the head between the move and the undo (wizard location edit, auto-unarchive) hits the same unguarded write.

**Evidence.**

- logic.py:2043-2058: the moves restore only logs on failure and carries on
- logic.py:2066-2083: the ejection restore writes {location: target, extra: snapshot} with no occupancy check and no check of the moves' outcome
- logic.py:631-634: the Smart Load record now holds ejections[rid] = target plus ejection_extras
- WT scratch run: test_undo_partial_failure_restores_resident_onto_still_occupied_head FAILED with "undo left XL-1 holding [42, 99]; undo returned {'success': True}; logs=[('WARNING','↩️ Undid: moved #42 from CR -> XL-1'), ('ERROR','❌ Undo: failed to restore Spool #42 → CR: 400: rejected by test'), ...]"
- HEAD run of the same test: PASSED, XL-1 == [42]; the old no-op ejection restore could not double-occupy (results.json HEAD::undo_partial_failure)

**Fix direction.** In perform_undo, record which move restores failed. Before restoring an ejected resident onto a single-occupancy location, skip it if any spool whose recorded move targeted that location failed to restore. Also re-read the location with get_spools_at_location_detailed_strict and skip if any other direct spool is there. On a skip, log an ERROR naming the resident and return success False, or add a partial flag. Pin this with the scratch test.

**Verifier.** Re-read logic.py perform_undo: moves are restored first and only log on failure; the ejection restore that follows writes {location: pre-eject toolhead, extra: SYSTEM_MANAGED snapshot} with no occupancy check (logic.py ~2059-2083, fed by the Smart Load record at ~631-634). update_spool refuses when _get_raw_extras fails (spoolman_api.py ~350-365), and the undo payload always carries 'extra'. I re-ran R1's test from my scratch copy: WT fails with XL-1 [42, 99] and {'success': True}; HEAD passes.

The defect is also reachable with NO Spoolman failure. My verify-review/r1/test_verify.py::test_r101_undo_after_unrecorded_eject_and_load_double_occupies FAILED on WT with 'XL-1 holds [50, 99] after undo {success: True}' and PASSED on HEAD (XL-1 [50]). The sequence:
- Smart Load #42 onto XL-1.
- Eject #42. perform_smart_eject never pushes an undo record; UNDO_STACK is appended only at logic.py:647 and 820.
- A non-recording writer puts #50 on XL-1 (routes_inventory.py:700-723, /api/spool/update, calls update_spool with the caller's fields).
- Undo.

The diff introduced this: HEAD's ejection replay was a no-op.

**Recommended fix.** In perform_undo, before restoring an ejected resident onto a single-occupancy location (use _is_single_occupancy), re-read direct residents with spoolman_api.get_spools_at_location_detailed_strict and skip the restore if any other direct spool is there or the read raises. On a skip, log an ERROR naming the resident and the occupant, and return success False (or a partial flag the frontend toasts at 7 s). Pin both variants: the rejected incoming restore, and eject then unrecorded load then undo.

#### R1-02 — An unreadable ghost or prefix match refuses a load onto an empty head; one extra Spoolman read per match

*Severity yellow → **info** after review · verdict **CONFIRMED** · proof: test-run · `inventory-hub/logic.py:614`*

**Claim.** Smart Load calls get_spool for every id the matcher returns before it checks whether that spool really sits on the target. A None, which get_spool returns for any exception including its 3 s timeout, is recorded as 'stuck' and refuses the whole move. That id may be only a ghost (a stale physical_source naming this head), or for a Printer-row target a prefix match on another head. get_spools_at_location_detailed already returns is_ghost and the direct location for each match, so eligibility needs no read. Only a real resident's extras snapshot does. The 'landed' read at :635 exists only for the log line.

**Failure scenario.** #7 is loaded on XL-3 with a legacy physical_source 'XL-1'. XL-1 is empty. Load #42 onto XL-1 during a moment when GET /spool/7 times out. The result is status error, 'Not loaded: XL-1 still holds #7 (it could not be read from Spoolman).', and the frontend shows a 7 s error for an empty head. HEAD loaded #42 fine. With the XL Printer row as target, any blip on any XL-n spool refuses.

**Evidence.**

- logic.py:611-619: get_spool(rid) and the 'could not be read' stuck entry come before the location != target skip
- spoolman_api.py:1489-1498: the detailed item carries is_ghost, location (sloc for direct matches) and deployed_to
- spoolman_api.py:85-89: get_spool uses a bare except returning None, timeout=3
- WT: test_unreadable_ghost_refuses_load_onto_empty_head FAILED with "XL-1 was EMPTY ... but the load was refused: result={'status': 'error', 'msg': 'Not loaded: XL-1 still holds #7 (it could not be read from Spoolman).', 'failures': {'42': 'XL-1 still holds #7 (it could not be read from Spoolman)'}}"
- HEAD: same test PASSED (XL-1 [42], XL-3 [7])
- Latency, get_spool ids per Smart Load. One homed resident: WT [99,99,99,42] (4) vs HEAD [99,99,42] (3). Resident plus 2 ghosts: WT 6 vs HEAD 7. Printer row XL with 3 toolhead spools: WT 4 vs HEAD 7.

**Fix direction.** Iterate get_spools_at_location_detailed(target), or the _strict variant (see R1-03). Skip items where is_ghost is set or where str(location).upper() != target. Call get_spool only for the real residents, and refuse only when a REAL resident cannot be read. Drop the log-only 'landed' read, or have perform_smart_eject report its destination.

**Verifier.** Reproduced: WT refuses the load onto the empty XL-1 ('Not loaded: XL-1 still holds #7 (it could not be read from Spoolman)'); HEAD loads it. The get_spool call and the stuck entry come before the location != target filter (logic.py ~611-619), and the detailed matcher already returns is_ghost and location (spoolman_api.py _build_location_match).

Impact is low:
- It fails closed, nothing moves, and a retry succeeds.
- It needs a read failure on a ghost or prefix match. Ghosts that name a toolhead come only from legacy head->head trails, and a read-only dev snapshot (237 spools) has 0 of them.
- The prefix case needs a Printer-row target such as 'XL' (Max 0), which is a rare load target.

**Recommended fix.** Iterate get_spools_at_location_detailed(target) (or the strict variant, see R1-03). Skip items with is_ghost set or with location.upper() != target, and call get_spool only for real residents, so an unreadable REAL resident still refuses. Drop the log-only 'landed' re-read.

#### R1-03 — The resident list read is still fail-open, so a Spoolman blip stacks a second spool on an occupied head (existed before)

*Severity yellow → **yellow** after review · verdict **CONFIRMED** · proof: test-run · `inventory-hub/logic.py:611`*

**Claim.** The fix's stated invariant is 'the head must really be empty before the incoming spool is written'. But residents come from get_spools_at_location, which goes through get_all_spools, and that swallows every error and returns []. The move then treats an occupied head as empty and writes the incoming spool. The status is success with empty failures. The per-resident read fails closed (R1-02) while this more likely blip point fails open.

**Failure scenario.** XL-1 holds #99. GET /api/v1/spool fails once (a NAS Spoolman timeout), and the user Quick-Swaps or assigns #42 onto XL-1. XL-1 ends with [42, 99], the move answers status success, and the UI toasts success. Deducts for XL-1 are then skipped as ambiguous.

**Evidence.**

- logic.py:611 uses the fail-open spoolman_api.get_spools_at_location
- spoolman_api.py:92-105 get_all_spools returns [] on any exception; spoolman_api.py:1507-1523
- spoolman_api.py:1633-1657 get_spools_at_location_detailed_strict already exists and raises
- WT: test_smart_load_list_read_blip_stacks_on_occupied_head FAILED with "list-read blip: XL-1 holds [42, 99]; result={'status': 'success', 'failures': {}}"
- HEAD: same failure (results.json HEAD::list_blip), so it existed before, but it is inside the invariant the diff claims to enforce

**Fix direction.** Resolve single-occupancy residents with get_spools_at_location_detailed_strict. On an exception, refuse every incoming spool: failures[sid] = 'could not read <target> from Spoolman', log an ERROR, return status 'error'. This matches plan_bulk_move's fail-closed source resolve.

**Verifier.** This existed before the diff but sits inside the invariant the diff claims. R1's test fails on BOTH WT and HEAD: XL-1 [42, 99] with status success and failures {}.

Why it happens: get_spools_at_location -> get_spools_at_location_detailed -> get_all_spools, which returns [] on any exception (spoolman_api.py:92-105). The full-list GET (5 s timeout) is a separate request from the per-spool reads, so it can blip on its own while the incoming spool's get_spool succeeds.

The diff made the per-resident read fail closed but left this more likely blip point fail-open. get_spools_at_location_detailed_strict already exists (spoolman_api.py:1633).

**Recommended fix.** In Smart Load, resolve residents with get_spools_at_location_detailed_strict. On an exception, set failures[sid] = 'could not read <target> from Spoolman' for every incoming spool, log an ERROR, and return status 'error' before any eject or write, matching plan_bulk_move's fail-closed source resolve. Add a test where the list read raises.

#### R1-04 — A legacy toolhead-valued ghost trail survives a re-scan onto the same head, so the spool is still charged for the other head

*Severity yellow → **info** after review · verdict **CONFIRMED** · proof: test-run · `inventory-hub/logic.py:723`*

**Claim.** C only stops NEW toolhead trails. When a spool already on the target is moved there again (re-scan, Location Manager re-assign), is_already_here keeps existing_source verbatim, even when that source is a toolhead (every head-to-head move before this fix left one). The spool stays a ghost of the other head. select_deduct_targets' ghost-only fallback charges it for that head's print usage, and the status bar shows it there (I5-14).

**Failure scenario.** #77 is on XL-1 with physical_source 'XL-3' from an old head-to-head move. XL-3 is empty. Re-scan #77 onto XL-1: the trail stays 'XL-3'. A print using XL-3 deducts grams from #77.

**Evidence.**

- logic.py:721-725: is_already_here copies existing_source and never calls _ghost_trail_from
- spoolman_api.py:1561: chosen = direct if direct else ghost
- WT: test_legacy_toolhead_trail_survives_rescan_onto_same_head FAILED with "re-scan kept the toolhead trail 'XL-3'; select_deduct_targets('XL-3') -> ([77], False)"
- HEAD: same failure, so it existed before; the diff's 'ghost trails never name a toolhead' guarantee is incomplete for existing data

**Fix direction.** In the PRINTER MOVE branch, apply is_already_here only when existing_source is not single-occupancy (_is_single_occupancy(existing_source, printer_map, loc_info_map) is False). Otherwise fall through to _ghost_trail_from and the 13.6 reverse-binding. Separately, a read-only count of spools whose physical_source is a printer_map key would size the legacy drift.

**Verifier.** Reproduced on WT and HEAD (existed before the diff): is_already_here keeps a toolhead-valued existing_source verbatim (logic.py ~721-725), and select_deduct_targets('XL-3') returns ([77], False).

The re-scan framing overstates it, because the legacy trail and its ghost-only deduct fallback exist whether or not anyone re-scans. The re-scan is only a missed cleanup chance. The deduct harm also needs the named head to have no direct spool.

The read-only dev Spoolman snapshot has 0 toolhead-valued physical_source trails, so this depends on legacy data in prod, which I did not check.

**Recommended fix.** In the PRINTER MOVE branch, honour is_already_here only when existing_source is not _is_single_occupancy; otherwise fall through to _ghost_trail_from. Separately, run a read-only count on prod of spools whose physical_source names a toolhead. If any exist, add an idempotent startup cleanup (snapshot, then write "") rather than relying on re-scans.

#### R1-05 — Head-to-head moves now trigger the 13.6 reverse-binding, which stacks a ghost on an occupied bound slot; Return then unseats the staged spool

*Severity yellow → **yellow** after review · verdict **CONFIRMED** · proof: test-run · `inventory-hub/logic.py:741`*

**Claim.** _ghost_trail_from gives a head-to-head move an empty trail, so the 13.6 reverse-binding fires and writes the new head's bound box slot as physical_source. It never checks whether that slot already holds a spool. The diff's own chain skips make that more common: a spool left in a bound slot because the head was printing. The slot ends up claimed twice. Return of the moved spool then targets that slot, and the slot-assignment unseat clears the staged spool's container_slot. That unseat is not in the undo record and gets only a logger.info line.

**Failure scenario.** LR-MDB-1 slot 3 (bound to XL-3) holds #240, staged but not deployed. Move #77 from XL-1 to XL-3: #77 gets physical_source LR-MDB-1:3, and slot 3 is claimed by [(77 ghost), (240 direct)]. Quick-Swap Return on XL-3 puts #77 into slot 3 and silently unseats #240, which is left unslotted in the box.

**Evidence.**

- logic.py:727-728: head-to-head now returns an empty trail; logic.py:738-749: the reverse-binding runs with no occupancy check
- logic.py:687-705: the slot-assignment unseat (logger.info only; not recorded for undo)
- WT: test_head_to_head_reverse_binding_double_books_an_occupied_bound_slot FAILED with "slot LR-MDB-1:3 claimed by [(77, True), (240, False)] after XL-1 -> XL-3; after Return #240 is {'location': 'LR-MDB-1', 'extra': {'container_slot': ''}}"
- HEAD: the same test PASSED (slot 3 claims [(240, False)]), though HEAD instead wrote the toolhead trail XL-1 (the defect C fixed). This is a widening of the 13.6 behaviour, which already existed for spools arriving from Unassigned.

**Fix direction.** In the 13.6 reverse-binding, read get_spools_at_location_detailed(bound_box). Skip the synthesis, leaving the trail empty, when another spool id already claims bound_slot, whether direct or ghost. Optionally log that the bound slot is occupied.

**Verifier.** Reproduced the double claim: slot LR-MDB-1:3 is claimed by [(77 ghost), (240 direct)] after XL-1 -> XL-3 on WT, and not on HEAD.

The Return unseat is NOT new. My test_verify.py::test_r105_return_after_head_to_head_unseats_staged_slot_spool fails on BOTH trees:
- On HEAD the toolhead trail made Return fall back to first_binding LR-MDB-1:3 and unseat #240 (container_slot ''), then the chain round-tripped #77 back onto XL-3.
- On WT Return uses physical_source LR-MDB-1:3 and unseats #240 the same way.

What the diff adds is the ghost double claim between the move and the Return. More importantly, Return's auto_deploy=False now parks every returned spool DIRECTLY in its bound slot. That makes the 'staged in the bound slot' state routine. The pre-existing 13.6 reverse-binding (which has no occupancy check) and Return's slot unseat (logic.py ~687-705, logger.info only, not in the undo record) will then collide far more often. This happens for loads from Unassigned as well as head->head: Return spool A, load B onto the head from Unassigned, Return B, and A silently loses its slot. The dev snapshot currently has 0 staged bound slots.

**Recommended fix.** (1) In the 13.6 reverse-binding, call get_spools_at_location_detailed(bound_box) and skip the synthesis when bound_slot is already claimed by another spool, direct or ghost.
(2) Give Return the same 13.2 slot-collision guard perform_smart_eject has: if the destination slot holds another spool, land unslotted (or refuse with return_slot_taken) instead of letting perform_smart_move unseat it.
Pin both with the scratch tests.

#### R1-06 — The undo fold finds the chained record by origin and stack depth, not identity

*Severity info → **info** after review · verdict **PLAUSIBLE** · proof: test-run · `inventory-hub/logic.py:877`*

**Claim.** The parent folds whatever record sits on top of UNDO_STACK when the length is depth+1 and its origin equals 'auto_deploy_from_<origin>'. Flask serves requests on threads, and UNDO_STACK is a plain shared list. Suppose another request with the same origin pushes its chain record during this chain's window (Spoolman and PrusaLink I/O take seconds), while this chain pushes nothing, for example because it was refused. The parent then pops the other request's record, merges its ejections into its own, and drops that record's moves. The race window is small, so this is informational.

**Failure scenario.** Two slot-QR scans ('slot_qr_scan') run at once. The first scan's chain gets requires_confirm and pushes nothing, just as the second scan's chain pushes its record. The first scan pops that record. Its moves are lost from undo, and its ejections are credited to the first scan's record.

**Evidence.**

- logic.py:860-881 (len and origin check, then UNDO_STACK.pop())
- state.py:7: UNDO_STACK = [] with no lock
- WT (simulated interleaving: a probe side effect appends a foreign 'auto_deploy_from_slot_qr_scan' record and returns PRINTING): test_fold_pops_a_concurrent_requests_chain_record FAILED. The stack afterwards held a single record whose ejections were {556: 'XL-2'}; the foreign record, with moves {555: 'LR-MDB-1'}, was gone.
- HEAD: PASSED (no fold; the foreign record stays)

**Fix direction.** Fold by identity. Give the chained call a private way to hand back its record, for example a thread-local undo sink set around the chained perform_smart_move, or a unique token stored in the record and passed down. Pop only that exact object (the check can use `is` before popping).

**Verifier.** The fold logic is as described. It pops whatever sits on top when len == undo_depth + 1 and the origin matches (logic.py ~861-881), and UNDO_STACK is a plain unlocked list (state.py:7). R1's test reproduces the wrong pop, but only through a SIMULATED interleaving (a probe side effect appends a foreign record). A real trigger needs two same-origin chains overlapping inside one move's I/O window, with this chain pushing nothing. The UNDO_STACK race class already existed (perform_undo pops, and moves append without a lock).

**Recommended fix.** Fold by identity. Pass a per-call sink or token down to the chained perform_smart_move (for example a thread-local list the impl appends its record to), and pop only when state.UNDO_STACK[-1] is that exact object. Optionally guard UNDO_STACK with a lock.

#### R1-07 — Return reports a get_spool blip as an empty toolhead ('nothing to return', 404)

*Severity info → **info** after review · verdict **CONFIRMED** · proof: test-run · `inventory-hub/routes_bindings.py:574`*

**Claim.** The new direct-resident filter does `get_spool(rid) or {}` and keeps a spool only when its location equals the head. A failed read of the real loaded spool therefore produces return_no_spool, plus a WARNING 'XL-3 is empty — nothing to return'. HEAD answered a false return_done in the same case, so the new behaviour is safer, but it still misreports a read failure as an empty head.

**Failure scenario.** XL-3 holds #240. GET /spool/240 times out during Return. The user is told the head is empty; they try again or eject by hand.

**Evidence.**

- routes_bindings.py:573-576 and :592-602
- WT: test_return_get_spool_blip_reports_empty_head FAILED with "a read failure was reported as an empty head: 404 {'action': 'return_no_spool', 'candidates': ['XL-3'], 'toolhead': 'XL-3'} logs=[('WARNING', '... ⚠️ Return: XL-3 is empty — nothing to return')]"
- HEAD: 200 return_done with smart_move.failures {'240': 'could not read the spool from Spoolman'} and SUCCESS logs (results.json HEAD::return_blip)

**Fix direction.** Classify candidates with get_spools_at_location_detailed (is_ghost / location) instead of reading each one. If a direct match's get_spool then returns None, answer 502 return_failed with 'could not read #N from Spoolman' rather than return_no_spool.

**Verifier.** Reproduced on WT: 404 return_no_spool plus the WARNING 'XL-3 is empty — nothing to return' while XL-3 holds #240 (the get_spool(rid) or {} filter at routes_bindings.py ~572-576). HEAD answered a false return_done carrying a failures map, so the WT behaviour is strictly safer and nothing moves. Only the message is wrong.

**Recommended fix.** Collect ids whose get_spool returned None. If a head has no readable direct resident but has unreadable matches, answer 502 (or 409) return_failed with toolhead=<requested>, active_toolhead=th and error 'could not read #N from Spoolman', plus an ERROR log, instead of return_no_spool.

**Checked correct (R1).**

- Python 3.9: ast.parse(feature_version=(3,9)) passes for logic.py, routes_bindings.py and routes_scan.py; no 3.10+ syntax.
- Repo offline suite on the working tree (`pytest tests/ -p no:cacheprovider -q --offline`): 1691 passed, 1 failed, 798 skipped. The single red is test_locations_json_integrity, caused by the known blank-LocationID TestCart row in data/locations.json. No regression from the diff; the new test_active_print_chain_confirm.py and the 4 edited tests pass.
- Dual-role CORE1 (Type Printer, Max 1, printer_map key), dev topology: an assign into CR-MDB-1 slot 1 chains to CORE1, the homeless resident #301 lands in Room CR, auto_deployed_to is CORE1, and exactly one undo record remains. HEAD left both spools on CORE1.
- Virtual Printer row XL (Max 0) as the target: only a spool whose location is exactly 'XL' is unloaded (to Room LR); the spool on XL-1 is untouched. HEAD skipped both.
- PRINTER:XL sentinel slot (LR-MDB-1:4): no chain, no auto_deployed_to, no auto_deploy_skipped.
- A JSON-quoted legacy toolhead trail ('"XL-1"') is not used as an eject home: #7 is unassigned and XL-1 still holds only #99.
- Quick-Swap of a slot whose spool is ghost-deployed on another head (#60 on XL-2, trail LR-MDB-1:1, moved to XL-1): XL-1's resident goes home, and #60 gets the new head's bound-box trail LR-MDB-1:1. HEAD wrote the toolhead trail XL-2.
- Multi-spool move into one bound slot: only the last placed spool deploys; the other is reported in auto_deploy_skipped. HEAD deployed both onto XL-3.
- Probe cache vs the chain's confirm (code trace, prusalink_api.py:421-437): the memo is per thread and per outermost move, keyed by printer name. With an explicit slot and confirm False, the chain reuses the pre-flight's idle result. With an auto-picked slot, the chain's probe is the first one, so a PRINTING head is refused and reported rather than covered by the caller's confirm.
- Bulk move (execute_bulk_move): auto_deploy=False and plan_bulk_move blocks single-occupancy destinations, so neither Smart Load nor the chain is reachable. The new status 'error' passthrough is dead code there. The DRYER/GENERIC "" writes only clear stale trails on moved direct spools.
- clear_location, manage_contents remove and force_unassign callers: homeless_destination defaults to None, so the interactive REQUIRE_CONFIRM behaviour is unchanged. The single-slot box detach now runs only after a successful write.
- 'A toolhead is never a home' (code trace): no intended flow stores a toolhead as a home. The DRYER/GENERIC branches always meant to clear the trail (they used pop), and eject and force_unassign already wrote "". One behaviour change: a saved source of the virtual Printer row 'XL' now yields REQUIRE_CONFIRM instead of returning the spool to XL. That matches plan_bulk_move's single-occupancy types.
- MMU / 0-based slots (code trace): the slot-QR scan rejects slot < 1 when Max Spools > 0, auto-slot starts at 1, and a target_slot of '0' on a non-box target never chains, so the explicit_slot truthiness is safe. Dev data has no MMU Slot rows.
- Latency (get_spool calls per Smart Load, WT vs HEAD): 4 vs 3 with one homed resident, 6 vs 7 with a resident plus two ghosts, 4 vs 7 with the Printer row XL as target. Roughly one extra ~150 ms read per real resident, and fewer than HEAD when ghosts or prefix matches are involved.
- Hermeticity: the audit-hook tripwire recorded 0 write-mode opens under the repo in both scratch runs; locations_db.save_locations_list was patched to raise and never fired; git status shows no change from this agent.

### R2 — 

I reviewed the response contracts and their consumers. All proofs were hermetic (scratch pytest with a repo-write tripwire, which recorded 0 writes), plus a Node vm harness that loads the real inv_quickswap.js.

Most of the diff holds:
- **smart_move_failure:** its semantics are sound (10 characterization cases pass).
- **Toasts:** showToast uses innerText, so the new toasts that interpolate backend messages or Spoolman error bodies cannot inject HTML.
- **Deposit flag:** `confirm_active_print: !!stateInfo` is correct for click and QR. The probe only returns non-null when the printer is known and active, which is exactly when the banner shows.
- **Error-body handling:** every consumer reads the body regardless of HTTP ok, so the 409 and 502 answers are handled.
- **Python 3.9 and tests:** the three backend files parse with the 3.9 grammar. 298 existing hermetic tests pass across the 19 affected files, and another 51 pass across the source-text/E2E-offline files.

**Defects found:**
- **R2-01 (orange, proven in Node):** the deposit fix is incomplete. The Enter-key path, with Yes focused by default, still calls `opts.onConfirm()` without stateInfo. A keyboard deposit during a print sends `false`, is told "Deposit again to confirm", and loops forever.
- **R2-02 (yellow):** return_failed breaks the 29.B3 convention. For a request of "XL" it reports `toolhead: "XL-3"`, with no `active_toolhead` or `requested` key.
- **R2-03 (yellow):** the Return overlay still counts ghosts when it resolves a head. It offers a confirm that the backend then refuses with "XL-1 is empty — nothing to return" while XL-3 holds the spool. A head holding two spools also previews one spool and destination, then fails with 409.
- **R2-04 (yellow):** a resident that Spoolman cannot read is reported as an empty toolhead.
- **R2-05 (orange, residual of I2-08):** the Force Location Override consumer in inv_details.js was not updated. It still toasts "Location updated via override" for a rejected write.
- **R2-06 (yellow):** /api/quickswap and Return still hard-code `confirm_active_print=True`. With fix B that confirm now also authorizes unloading the resident, so a swap after a failed or timed-out probe unloads a printing head without any warning shown. The deposit's `!!stateInfo` pattern was not applied to them.

Two info items: the failure status codes are inconsistent (502 / 409 / 200) and a 502 is fragile behind a proxy; and the deposit's confirm flag is an unscoped boolean.

#### R2-01 — Deposit confirmed with Enter still sends confirm_active_print:false, so a keyboard deposit during a print loops on "Deposit again to confirm" forever

*Severity orange → **orange** after review · verdict **CONFIRMED** · proof: test-run · `inventory-hub/static/js/modules/inv_quickswap.js:440`*

**Claim.** The diff passes stateInfo to onConfirm only in yes.onclick (:498) and the QR onConfirm (:490). The capture-phase keyHandler's Enter branch (:440) still calls `opts.onConfirm && opts.onConfirm()` with no argument. mountOverlay focuses #fcc-quickswap-yes (:473) and the focus guard keeps it there, and Enter is the project's keyboard-confirm idiom. So the deposit's `confirm_active_print: !!stateInfo` (:634) is `!!undefined === false` even though the PRINTING banner was on screen. The backend answers assignment_requires_confirm, and the new branch (:662) toasts "... Deposit again to confirm." The next deposit via Enter does the same again, so a keyboard user can never deposit during a print. That outcome also writes no Activity Log entry: the backend requires_confirm branch at routes_scan.py:1133-1142 does not log, and the frontend does not log either, which breaks the CLAUDE.md rule of a log entry plus a toast for every outcome.

**Failure scenario.** XL is PRINTING. The Quick-Swap grid for XL-3 is open, with a buffered spool and an empty slot LR-MDB-1:3 bound to XL-3. The user clicks "Deposit from buffer"; the overlay shows "XL is PRINTING"; the user presses Enter. The POST body is {text:'LOC:LR-MDB-1:SLOT:3', source:'quickswap_deposit', confirm_active_print:false}. The response is assignment_requires_confirm, the toast says "Deposit again to confirm", and repeating it gives the identical result every time. A mouse click or a QR scan on the same overlay works.

**Evidence.**

- inv_quickswap.js:436-442 Enter branch: `if (active === yes) { e.preventDefault(); e.stopPropagation(); opts.onConfirm && opts.onConfirm(); close(); }` (preventDefault also suppresses the native click, so yes.onclick never runs)
- inv_quickswap.js:490 and :498 pass stateInfo; :473 initialFocus '#fcc-quickswap-yes'; :634 confirm_active_print: !!stateInfo; :662 'Deposit again to confirm' toast
- Node vm harness loading the real inv_quickswap.js with the probe stubbed to PRINTING. Output: {"how":"enter","bannerShown":true,"posted_confirm_active_print":[false],...} / {"how":"click","bannerShown":true,"posted_confirm_active_print":[true]} / {"how":"qr","bannerShown":true,"posted_confirm_active_print":[true]}
- Backend half (requires_confirm when the flag is absent while printing) was already proven by I2-14 / I1-09

**Fix direction.** At inv_quickswap.js:440 call `opts.onConfirm && opts.onConfirm(stateInfo);`, so all three confirm paths share one call (for example a local `const confirm = () => { opts.onConfirm && opts.onConfirm(stateInfo); close(); }`). Better still, handle assignment_requires_confirm in the deposit by opening the re-confirm overlay and replaying with confirm_active_print:true, as inv_cmd.js does via _confirmActivePrintScan, instead of the dead-end toast. Also log a WARNING (logClientEvent or backend) for that outcome.

**Verifier.** Code: inv_quickswap.js:436-442, the Enter branch of the capture keyHandler, calls `opts.onConfirm && opts.onConfirm();` with no stateInfo. Its e.preventDefault() suppresses the native button activation, so yes.onclick never runs. mountOverlay sets initialFocus '#fcc-quickswap-yes', and the code comment documents 'Enter activates whichever button is focused... Yes is focused by default.'

Re-ran R2's Node vm harness on the real file: enter posted [false], click [true], QR [true], with the banner shown in all three cases.

The backend answers assignment_requires_confirm and the diff's new branch toasts 'Deposit again to confirm'. Repeating via Enter gives the same answer, so a keyboard deposit during a print can never succeed. The routes_scan requires_confirm branch writes no Activity Log entry. This is a deterministic hole in the diff's own fix G.

**Recommended fix.** In showConfirmOverlay, define one `const doConfirm = () => { opts.onConfirm && opts.onConfirm(stateInfo); close(); }` and use it for Enter, yes.onclick and the QR onConfirm. In the deposit handler, treat assignment_requires_confirm like inv_cmd.js does: open the confirm overlay (_confirmActivePrintScan or mountOverlay) and replay with confirm_active_print:true instead of the dead-end toast. Log a WARNING for that outcome.

#### R2-05 — Force Location Override is the one manage_contents 'add' consumer left keying on status==='success': a rejected write still toasts "Location updated via override"

*Severity orange → **yellow** after review · verdict **CONFIRMED** · proof: test-run · `inventory-hub/static/js/modules/inv_details.js:1226`*

**Claim.** The diff taught performContextAssign and _doAssignFinalize to read res.failures, but not the third status-based consumer named in I2-08. After the diff, manage_contents add with a Spoolman-rejected write still answers HTTP 200 {status:'success', failures:{'42': '...'}}. inv_details.js:1226 `if(res.status === 'success' || res.success)` therefore shows a success toast and re-opens the details as if the spool had moved. The new Smart Load refusal ({status:'error', msg:'Not loaded: XL-1 still holds ...'}) now lands in the else branch, but at showToast's default 2000 ms, below the ≥7 s error-toast convention. An auto_deploy_skipped reason is never surfaced either.

**Failure scenario.** Spool details → Force Location → pick LR-MDB-2 → Spoolman rejects the PATCH (for example a schema or validation error). The toast says 'Location updated via override', the spool is still in CR, and the only trace of the failure is the ERROR line in the Activity Log.

**Evidence.**

- inv_details.js:1226-1231: `if(res.status === 'success' || res.success) { showToast('Location updated via override', 'success'); ... } else { showToast(res.msg || 'Override failed', 'error'); }`
- Scratch test test_manage_contents_add_rejected_write_still_answers_status_success FAILED: `MANAGE_CONTENTS ADD (rejected): 200 {'failures': {'42': '400: rejected by test'}, 'status': 'success'}`, spool still at 'CR'
- routes_scan.py:328-334 returns perform_smart_move's dict verbatim

**Fix direction.** Mirror _doAssignFinalize: `const failedWhy = res.status === 'success' ? (res.failures || {})[String(spoolId)] : null;`. Show success only when there is no failure, toast failedWhy or res.msg at 7000 ms, and warn on res.auto_deploy_skipped. Then add inv_details.js to the diff's consumer list (G).

**Verifier.** Reproduced the backend shape on WT and HEAD: manage_contents add with a rejected write returns HTTP 200 {status:'success', failures:{'42': ...}} and the spool stays in CR. inv_details.js is untouched by the diff (git diff --stat is empty). Lines 1226-1231 still show 'Location updated via override' on status==='success', and the error toast uses the default duration.

The investigation's I2-08 (results.txt:511-521) names this consumer as one of the sites, and the diff claims to fix I2-08 in G, so the fix is incomplete.

This is not orange: the backend writes an ERROR Activity Log line, and openSpoolDetails(spoolId, true) re-opens the details showing the unchanged location.

**Recommended fix.** Mirror _doAssignFinalize in inv_details.js: `const failedWhy = res.status === 'success' ? (res.failures || {})[String(spoolId)] : null;`. Show success only when !failedWhy. Otherwise showToast(failedWhy or res.msg, 'error', 7000) and warn on res.auto_deploy_skipped. Add inv_details.js to the G consumer list.

#### R2-06 — Quick-Swap and Return still hard-code confirm_active_print=True; with fix B that now authorizes unloading a printing head's spool even when no warning was shown

*Severity yellow → **info** after review · verdict **PLAUSIBLE** · proof: test-run · `inventory-hub/routes_bindings.py:782`*

**Claim.** /api/quickswap (:780-783) and /api/quickswap/return (:678-681) pass confirm_active_print=True unconditionally, 'because the user already saw the warning'. The overlay probe fails open: _probeWithTimeout resolves null on its 3 s timeout, and fetchPrinterStateForToolhead returns null on known:false or any error (inv_quickswap.js:340-349, inv_loc_mgr.js:416-434). In that case no banner is shown and the confirm is still sent. Before the diff, the resident eject ignored this confirm, which gave double occupancy (I5-2). Fix B forwards confirm_active_print into perform_smart_eject, so the same hard-coded True now really unloads the resident off a PRINTING head, with no requires_confirm path at all. The deposit was fixed to send `!!stateInfo`; performSwap and performReturn ignore stateInfo, and their request bodies have no confirm field.

**Failure scenario.** XL is PRINTING, but /api/printer_state/XL-3 takes more than 3 s (the status call hits its 2 s timeout and the /api/printer fallback takes another ~1.5 s) or returns prusalink_unreachable on a blip. The Quick-Swap overlay opens without a banner; the user taps Yes. The backend probe is never consulted (confirm=True), #99 is unloaded to LR-MDB-2, #240 is written onto XL-3, and the answer is quickswap_done.

**Evidence.**

- routes_bindings.py:780-783 `perform_smart_move(toolhead, [spool_id], ..., confirm_active_print=True)`; :680 `auto_deploy=False, confirm_active_print=True`
- inv_quickswap.js:703 `onConfirm: () => performSwap(opts)` (stateInfo discarded); :845 `performReturn({ toolhead: th })`
- Scratch test test_quickswap_onto_printing_head_never_asks_and_unloads_resident FAILED: `QUICKSWAP (printing): 200 {'action': 'quickswap_done', ... 'toolhead': 'XL-3'} | XL-3 now: [240] | #99 now: LR-MDB-2`, with a request body of {toolhead, box, slot} only
- Pre-fix behaviour on the same path: results.txt I5-2 (double occupancy)

**Fix direction.** Apply the deposit pattern. performSwap/performReturn send `confirm_active_print: !!stateInfo`; both routes read it from the request, with a default of False, and answer a requires_confirm action when the pre-flight fires; inv_quickswap.js handles that action with the re-confirm overlay. Return's source-side guard would need _active_print_info_for_location(active_toolhead) in the route, because the destination is a box. This is a decision for Derek, since it changes the 'backend trusts the overlay' contract.

**Verifier.** The observation is accurate: WT /api/quickswap onto a PRINTING XL-3 with no confirm field unloads #99 and loads #240 (quickswap_done). It is not a regression of this diff, though. The same run on HEAD also wrote #240 onto the printing head without asking and left XL-3 [99, 240].

The unwarned mid-print load comes from the pre-existing deliberate contract: the overlay probe fails open (inv_loc_mgr.js:416-434, inv_quickswap.js:340-349), and the backend passes confirm_active_print=True (routes_bindings.py ~780 and ~680). Fix B only turns that double occupancy into a clean swap. Whether the backend should stop trusting the overlay is a design decision for Derek.

**Recommended fix.** Optional, for Derek to decide: apply the deposit pattern. performSwap and performReturn send confirm_active_print: !!stateInfo, the routes read it (default False) and answer a requires_confirm action, and inv_quickswap.js re-confirms through mountOverlay. Return would need a source-side _active_print_info_for_location(active_toolhead) check in the route.

#### R2-02 — return_failed breaks the 29.B3 contract: `toolhead` is the re-tagged ACTIVE head, with no active_toolhead/requested keys

*Severity yellow → **yellow** after review · verdict **CONFIRMED** · proof: test-run · `inventory-hub/routes_bindings.py:689`*

**Claim.** 29.B3 made `toolhead` mean the REQUESTED value in every Return error branch. The resolved head goes in `active_toolhead`, with `requested` kept as an alias (return_no_binding, :644-653, pinned by test_l316_charact_bindings_errors). The new return_ambiguous honours it. The new return_failed is built after `toolhead = active_toolhead` (:665), so for a virtual-printer request it reports the concrete head as `toolhead` and has neither `active_toolhead` nor `requested`. return_ambiguous also omits the `requested` alias that return_no_binding carries.

**Failure scenario.** POST /api/quickswap/return {toolhead:'XL'}. XL-3 holds #240 and Spoolman rejects the box write. The response is 502 {action:'return_failed', toolhead:'XL-3', ...}. A consumer that treats `toolhead` as the request, as the 29.B3 characterization tests do for every other error branch, sees the wrong value.

**Evidence.**

- routes_bindings.py:665 `toolhead = active_toolhead` precedes :689-697 return_failed body
- Scratch test test_return_failed_reports_the_requested_toolhead_per_29_b3 FAILED: `RETURN_FAILED BODY: {'action': 'return_failed', 'box': 'LR-MDB-1', 'error': '400: rejected by test', 'slot': '3', 'spool': 240, 'toolhead': 'XL-3'}` -> `AssertionError: 29.B3 ... got 'XL-3'`
- Contrast (passes): `RETURN_AMBIGUOUS BODY: {'action': 'return_ambiguous', 'active_toolhead': 'XL-1', ..., 'toolhead': 'XL'}`

**Fix direction.** Keep the requested value, e.g. `requested = toolhead` before the re-tag, and emit `"toolhead": requested, "active_toolhead": active_toolhead, "requested": requested` in return_failed. Add `"requested": toolhead` to return_ambiguous. Pin both next to the existing 29.B3 tests.

**Verifier.** Reproduced: POST {toolhead:'XL'} with a rejected box write returns 502 {action:'return_failed', toolhead:'XL-3'} with no active_toolhead or requested key. The cause is the `toolhead = active_toolhead` re-tag in routes_bindings.py, which runs before the new return_failed body. return_ambiguous correctly reports toolhead 'XL'. No current consumer breaks, because performReturn's error branch uses opts.toolhead and body.error. It does violate Derek's Group 29.B3 decision (toolhead = requested in every error branch, with active_toolhead separate) inside newly added code.

**Recommended fix.** Capture `requested = toolhead` before the re-tag. Emit `toolhead: requested, active_toolhead: active_toolhead, requested: requested` in return_failed, and add `requested` to return_ambiguous. Pin both next to the existing 29.B3 characterization tests.

#### R2-03 — Return overlay still counts ghosts when resolving the head, so it offers a Return the backend now refuses as 'empty'; a doubled head is only discovered after confirming

*Severity yellow → **info** after review · verdict **CONFIRMED** · proof: code-trace-only · `inventory-hub/static/js/modules/inv_quickswap.js:745`*

**Claim.** The backend now acts only on DIRECT residents: a ghost-only head answers 404 return_no_spool, and 2+ direct residents answer 409 return_ambiguous. The frontend was only half aligned. _resolveReturnTarget (:745) still picks the first candidate whose get_contents is non-empty, ghosts included. For a ghost-only head, _resolveReturnDestination (:764) finds no non-ghost resident and falls back to the head's first bound slot. That builds a non-null `dest`, so the overlay shows 'Sending back to: <box> slot N (first bound slot…)' with an armed confirm. The concrete POST then gets 404 and the toast '⚠️ XL-1 is empty — nothing to return', although the printer's other head holds the spool; the virtual request would have succeeded. For a head with two direct spools, the overlay previews one spool and one destination, and the refusal arrives only after Yes, as an error toast titled 'Return failed' while the backend logs a WARNING.

**Failure scenario.** Legacy data: #7 is loaded on XL-3 with a stale physical_source 'XL-1'. The user opens printer XL and clicks Return. The UI resolves XL-1 (a ghost-only entry) and previews a first-bound-slot destination with no spool line. The user confirms, the POST {toolhead:'XL-1'} gets 404, and the toast says 'XL-1 is empty — nothing to return'. The spool on XL-3 is never offered.

**Evidence.**

- inv_quickswap.js:745 `.then(items => (items && items.length) ? candidates[i] : check(i + 1))` counts ghost entries; :764 `.find(i => !i.is_ghost)`; :845 `onConfirm: dest ? (() => performReturn({ toolhead: th })) : ...`
- Scratch test test_ghost_only_head_resolved_by_ui_is_refused_while_sibling_is_loaded FAILED: `GET_CONTENTS XL-1: [{'id': 7, 'is_ghost': True, 'location': 'XL-1', 'slot': '', 'deployed_to': 'XL-3'}]` / `RETURN XL-1: 404 {'action': 'return_no_spool', 'candidates': ['XL-1'], 'toolhead': 'XL-1'}` / `RETURN XL  : 200 {'action': 'return_done', ..., 'moved': 7, ..., 'toolhead': 'XL-3'}`
- routes_bindings.py:570-591 direct-only filter + 409; inv_quickswap.js:584 generic 'Return failed' error toast for 409
- Frontend resolution/preview behaviour is code-trace only (no browser run)

**Fix direction.** In _resolveReturnTarget count only `items.filter(i => !i.is_ghost).length`. In _resolveReturnDestination, when there are 0 direct residents render the existing 'nothing to return' body with a no-op confirm, and when there are more than 1, render '<th> holds N spools — eject the wrong one first' with a no-op confirm. That way the overlay never offers an action the backend will refuse. Optionally show return_ambiguous as a 7 s warning rather than 'Return failed'.

**Verifier.** Backend half reproduced: ghost-only XL-1 answers 404 return_no_spool while {toolhead:'XL'} answers 200 return_done. Frontend verified by reading: _resolveReturnTarget uses `(items && items.length)`, which counts ghost entries, and performReturn posts the resolved concrete head.

Reach is narrow:
- The ghost-only-head case needs a legacy toolhead-valued trail, and the dev snapshot has 0.
- For the doubled-head case, the user still gets a 7 s error toast carrying the backend's precise reason ('XL-1 holds 2 spools ... eject the wrong one first'), which is acceptable. It is still an overlay offering an action the backend will refuse.

**Recommended fix.** In _resolveReturnTarget, count `items.filter(i => !i.is_ghost).length`. In returnToolheadToSlot, when the resolved head has 0 direct residents, render the existing 'nothing to return' no-op overlay; when it has 2 or more, render '<th> holds N spools — eject one first' with a no-op confirm.

#### R2-04 — Return reports a toolhead as empty when its resident merely could not be read from Spoolman

*Severity yellow → **info** after review · verdict **CONFIRMED** · proof: test-run · `inventory-hub/routes_bindings.py:574`*

**Claim.** The direct-resident filter does `rec = spoolman_api.get_spool(rid) or {}`, so a transient read failure yields location '' and the spool is skipped. With no other resident, the route answers 404 return_no_spool, logs '⚠️ Return: XL-3 is empty — nothing to return', and the UI toasts '⚠️ XL-3 is empty'. Smart Load in the same diff treats the identical condition as a refusal ('it could not be read from Spoolman'). Nothing moves, so this is safe, but it is wrong information on a screen the user trusts.

**Failure scenario.** XL-3 holds #240. Spoolman's GET /spool/240 times out once, while the list read that feeds get_spools_at_location succeeded. Return on XL-3 gives 404 return_no_spool and 'XL-3 is empty — nothing to return' (4 s warning), and the user concludes the head is unloaded.

**Evidence.**

- routes_bindings.py:572-576: `for rid in spoolman_api.get_spools_at_location(th): rec = spoolman_api.get_spool(rid) or {}; if str(rec.get('location') or '').strip().upper() == th: loaded.append(...)`
- Scratch test test_return_with_unreadable_resident_is_not_reported_as_empty FAILED: `UNREADABLE RESIDENT: 404 {'action': 'return_no_spool', 'candidates': ['XL-3'], 'toolhead': 'XL-3'} [... '⚠️ Return: XL-3 is empty — nothing to return' ...]` while sm.direct_at('XL-3') == [240]
- logic.py Smart Load: `if not before: stuck[rid] = "it could not be read from Spoolman"`

**Fix direction.** Collect unreadable ids in the loop. If a head has no readable direct resident but some unreadable ones, answer 502 {action:'return_failed', toolhead:<requested>, active_toolhead:th, error:'could not read #240 from Spoolman'} with an ERROR log, instead of falling through to return_no_spool.

**Verifier.** Duplicate of R1-07. Same route lines (routes_bindings.py ~572-576), same reproduction: 404 return_no_spool plus 'XL-3 is empty' while XL-3 holds #240, and the same comparison with HEAD's false return_done.

**Recommended fix.** See R1-07.

#### R2-07 — Failure status codes are inconsistent (502 / 409 / 200), and a 502 is fragile behind a proxy

*Severity info → **info** after review · verdict **PLAUSIBLE** · proof: code-trace-only · `inventory-hub/routes_bindings.py:697`*

**Claim.** quickswap_failed and return_failed answer 502, return_ambiguous 409, and assignment_failed 200. Every current consumer handles all three, because it reads the body regardless of r.ok. 502 is the status a reverse proxy or tunnel may replace with its own non-JSON page. performSwap/performReturn do `await r.json()` inside the then, so a replaced body throws into .catch and the toast becomes 'Quick-swap — network error', hiding the real Spoolman reason (the Activity Log still has it). 422 or 409, or 200 with the action, as the slot-QR path does, avoids the ambiguity. No proxy was verified.

**Failure scenario.** The prod FCC runs behind a proxy configured to intercept upstream 5xx. A rejected Quick-Swap write returns the proxy's HTML 502, r.json() throws, and the user sees 'network error' instead of the rejection reason.

**Evidence.**

- routes_bindings.py:588 (409), :697 (502), :798 (502); routes_scan.py:1160 (200)
- inv_quickswap.js:541 / :572 `.then(async r => ({ ok: r.ok, body: await r.json() }))` then .catch → 'network error' toast

**Fix direction.** Prefer 409 or 422 for business refusals and failures, or 200 with the action as slot-QR does, and keep the body shape unchanged.

**Verifier.** Code-trace only. The status codes are 409 (routes_bindings.py return_ambiguous), 502 (return_failed, quickswap_failed) and 200 (routes_scan.py assignment_failed). The repo has no reverse-proxy config; grep finds only a stretch-goal note in completed-archive.md. Default nginx (proxy_intercept_errors off) and Cloudflare tunnels pass origin 5xx bodies through. The failure needs a proxy that intercepts errors, which was not shown to exist.

**Recommended fix.** Low priority. Prefer 409 or 422 for these business failures (keeping the body shape) so no intermediary treats them as gateway errors. Optionally make performSwap/performReturn fall back to r.text() when r.json() throws.

#### R2-08 — Deposit's confirm is an unscoped boolean; a stale grid can carry the confirm to a different printing head

*Severity info → **info** after review · verdict **PLAUSIBLE** · proof: code-trace-only · `inventory-hub/static/js/modules/inv_quickswap.js:634`*

**Claim.** The flag tells identify_scan 'the user confirmed', but the backend re-reads the slot's CURRENT binding and never checks that it still feeds the toolhead the overlay probed. /api/quickswap guards this case with quickswap_not_bound; the deposit path has no equivalent. If the slot was rebound elsewhere (another tab or device) while this grid stayed open, a banner about XL confirms a deploy onto the new target. That target could be another PRINTING printer the user was never warned about. This is unlikely, because the grid re-renders on sync-pulse.

**Failure scenario.** The XL-3 grid is open. Another device rebinds LR-MDB-1:3 to CORE1-M0, and both printers are printing. The user deposits with the 'XL is PRINTING' banner and confirms. The chain forwards confirm=True and loads onto CORE1-M0 mid-print, with no CORE1 warning.

**Evidence.**

- inv_quickswap.js:623-635 body {text, source, confirm_active_print} carries no expected toolhead
- routes_scan.py:1126-1129 passes the bare flag; logic.py chain forwards it when explicit_slot
- routes_bindings.py:747-760 quickswap_not_bound check exists only on /api/quickswap

**Fix direction.** Send `expected_toolhead: toolhead` with the deposit. Have the assignment branch treat confirm_active_print as valid only when the slot's current binding equals it, and otherwise answer assignment_requires_confirm or a stale-binding action.

**Verifier.** Code-trace only, and consistent with the code. The deposit body (inv_quickswap.js ~623-635) carries no expected toolhead. routes_scan.py passes the bare flag, and the chain forwards it when explicit_slot. The trigger needs another device to rebind the slot to a different, also-printing head while this grid's overlay is open, and the grid re-renders on sync-pulse. inv_cmd.js's confirmed scan replay has the same unscoped flag, so the class predates the diff.

**Recommended fix.** Send expected_toolhead with the deposit. In the routes_scan assignment branch, honour confirm_active_print only when the slot's current slot_targets value equals expected_toolhead; otherwise answer assignment_requires_confirm (or a stale-binding action).

**Checked correct (R2).**

- showToast renders with el.innerText (inv_core.js:228), so every new toast that interpolates backend msg/error strings, Spoolman error bodies or location ids is inert text, with no injection. The Activity Log renders l.msg via innerHTML (inv_core.js:1150), but the new log lines interpolate the same Spoolman error strings the engine already logs (a pre-existing class, not a new vector).
- _probeWithTimeout -> window.fetchPrinterStateForToolhead returns non-null only when the backend says known && is_active (inv_loc_mgr.js:424-431). It returns null for idle, unknown, errors and the 3 s timeout, and the banner renders iff stateInfo is truthy, so `confirm_active_print: !!stateInfo` via click or QR never claims a warning the user did not see (proven in Node for click and QR; Enter is R2-01).
- logic.smart_move_failure: 10 parametrized characterization cases pass (None/non-dict -> 'the move returned no result'; {} and status 'success' without this spool's failure -> ''; per-spool failure wins; requires_confirm -> its msg; bare 'error' -> 'move error'). Every _perform_smart_move_impl return (logic.py:499, 522, 648, 915) carries a status key, and failures keys are always str(sid). routes_scan handles requires_confirm before calling it, and quickswap/return cannot receive requires_confirm (confirm=True, and Return's target is a box).
- quickswap_failed reports the REQUESTED toolhead (api_quickswap never re-tags); return_ambiguous honours 29.B3 (toolhead='XL', active_toolhead='XL-1').
- Every consumer's handling of HTTP 409/502: performSwap, performReturn and the deposit all build {ok, body} and route by body.action regardless of ok, so quickswap_failed, return_failed and return_ambiguous reach the else branch and show body.error at 7000 ms. The slot-QR assignment_failed is HTTP 200 and is handled by explicit branches in the scan path, the confirmed replay and the deposit.
- Other backend consumers: execute_bulk_move (logic.py:1230-1245) already maps status 'error' to success:false, and single-occupancy destinations are rejected there, so the new Smart Load refusal is unreachable. print_deduct api_smart_move and manage_contents add pass the dict through unchanged (their consumers are covered above and in R2-05). manualAddSpool (inv_loc_mgr.js:1600) does not special-case assignment responses (pre-existing generic toast).
- performContextAssign: failed ids stay in heldSpools (movedSet is built from ids absent from failures), each failure gets a 7 s error toast, a Smart Load refusal (status 'error') takes the else branch with a 7 s toast, and a missing `failures` key (E2E mocks returning {status:'success'}) is tolerated.
- _doAssignFinalize: spoolIdStr (numeric, 'ID:' stripped) matches the engine's str(sid) failure keys. On a failure there is no buffer splice and no swapDisplaced push, the error toast is 7 s, and a skipped deploy gets a 7 s warning.
- Scan-path and deposit assignment_failed / not_deployed: backend ERROR/WARNING Activity Log entries exist (routes_scan.py:1146-1149; logic.py chain skip WARNING) alongside the toasts; all new error toasts are ≥7 s. The only toast-without-log outcome found is the deposit requires_confirm (R2-01).
- Existing hermetic suites still pass: 298 passed / 22 skipped over test_quickswap_api, test_return_and_breadcrumb, test_l316_charact_bindings_errors, test_assignment_logic, test_l316_charact_scan_audit, test_active_print_backend_enforcement, test_active_print_chain_confirm, test_quickswap_printer_pool, test_route_table_pin, test_smart_move_spoolman, test_bulk_move(_session), test_auto_slot_pick, test_logic_undo, test_buglist_group21, test_dryer_bindings, test_deployed_flag_preservation, test_universal_fallback, test_toolhead_resident_eject_21_3. Also 51 passed / 80 skipped (--offline) over the source-text and E2E files that reference the changed JS modules.
- Python 3.9: ast.parse(feature_version=(3,9)) succeeds for logic.py, routes_bindings.py and routes_scan.py.
- E2E files not run (hard rule). By code-trace, none asserts on the changed toast strings or durations. test_quickswap_ui_e2e fulfils the swap POST with {status:'success'} (pre-existing: it already fell to the else branch), and test_return_overlay_and_refresh's Return cleanup now actually parks the spool (auto_deploy=False resolves I1-10).

### R3 — 

Review of the whole diff for test adequacy and CLAUDE.md conventions (label review-tests-conventions). I edited nothing in the repo; all work ran in scratch copies.

1. HEAD run: I extracted HEAD, copied in tests/test_active_print_chain_confirm.py and ran it. All 26 tests fail on HEAD, and each failing assertion matches the fix it names. One test fails on HEAD for a different reason than its docstring gives (R3-11).

2. Mock realism: I re-ran all 26 tests against a realistic Spoolman: the REAL spoolman_api.update_spool (sanitize, read-merge-write, LAST_SPOOLMAN_ERROR) over a fake HTTP layer, plus the REAL _build_location_match (prefix and quote handling). All 26 still pass, so no test relies on the fake replacing extra wholesale or on its exact-only matcher.
   - Because of those same fake semantics, nothing pins fix D (pop -> ""). Mutants M01 and M02 put the pop back, and both survive every repo test (R3-01). My proposed real-merge test catches both, passes on the current code and fails on HEAD. It shows the HEAD PATCH body still carrying physical_source '"LR-MDB-1"'.
   - Separately, two tests use an "idle at pre-flight, PRINTING by the chain" trigger that the real per-move probe cache makes impossible (R3-07).

3. The deliberately changed tests are all justified:
   - Head->head test (5fe1524): its intent, that the trail must not stay at the old box, is still asserted. The old "XL-3" trail never let Return use XL-3 anyway, since Return falls back to the binding. Mutant M16 (old behaviour restored) is caught by this test and by the new one.
   - test_universal_fallback: the loosened kwargs assertion is covered elsewhere. M17 (confirm dropped) and M18 (homeless_destination dropped) are caught by the new file.
   - test_toolhead_resident_eject_21_3: the resident's own record is now required by the fix.
   - test_l316 Return kwargs pin: M14 (auto_deploy back on) is caught by it and by the new Return tests.

4. Coverage gaps, measured with a mutation harness on a scratch copy (376 tests across the 26 most relevant files). These mutants survive every repo test:
   - fix D, both branches;
   - the Printer-row prefix filter;
   - the unreadable-resident refusal;
   - the undo record after a partial unload;
   - the row-type branch of _is_single_occupancy;
   - the multi-spool chain limit;
   - the box detach on the no-home eject branch;
   - the status-only branch of smart_move_failure;
   - chain-crash handling;
   - the `is True` identity check.
   Frontend fix G has no offline coverage at all. Eight gap tests (in scratch test_r3_gaps.py) pass on the current code, fail on HEAD, and catch every one of those mutants except the last three. Control mutants (M08, M10, M13–M16) were all caught by existing tests, which validates the harness.

5. Hermeticity: the new test's `client` fixture imports app.py, which runs startup_migrations against the cwd-relative data/locations.json (the live dev bind-mount file) and resurfaces pending cancel reviews from data/pending_cancel_deducts.json. The migrations are idempotent. Across the full suite, data/locations.json kept the same sha256 and no data file was added. print_tracker_latch.json kept changing with no tests running (21:10:38), so the container writes it. This import behaviour predates the diff, since other tests already import app.

6. Conventions:
   - Module-qualified calls, patch targets and LAST_SPOOLMAN_ERROR adjacency: all OK.
   - Python 3.9: the container's 3.9.25 parses logic.py, routes_bindings.py and routes_scan.py, and the added lines contain no 3.10-only constructs.
   - No routes were added; the route pin, source canaries and test_no_direct_extra_patch all pass.
   - The CLAUDE.md "Spool / Filament write surfaces" table was not updated: perform_undo (now writing extras) has no row, the homeless_destination relocate is not described, and the line numbers were already stale (R3-10).

7. Full hermetic suite (`--offline`, from inventory-hub/): 1 failed, 1691 passed, 798 skipped in 41.23s. The only red is the known test_locations_json_integrity blank-LocationID TestCart row.

#### R3-01 — Fix D (pop -> "") is pinned by no test; reverting it passes the whole relevant suite

*Severity orange → **yellow** after review · verdict **CONFIRMED** · proof: test-run · `inventory-hub/tests/test_active_print_chain_confirm.py:126`*

**Claim.** The DRYER (logic.py:780-782) and GENERIC (logic.py:808-809) branches now write physical_source/physical_source_slot as "" so update_spool's read-merge-write stops keeping the stale trail. No repo test runs the real merge. FakeSpoolman.update_spool replaces extra wholesale (test_active_print_chain_confirm.py:126-127), so an omitted key reads as cleared. The two existing L130 pins accept an absent key: test_deployed_flag_preservation.py:356-359 (`not in extras or ... in (None, "")`) and test_smart_move_spoolman.py:211 (`.get("physical_source", "") == ""`). Nothing stops the pop() from coming back.

**Failure scenario.** Someone restores `new_extra.pop('physical_source', None)` in either branch (the pre-2026-09-12 code). All tests stay green, and in production a spool moved off a toolhead into a room or another box keeps its old physical_source, so it still shows as a ghost in its old box slot (I1-07 / I2-03).

**Evidence.**

- Mutation M01 (dryer branch pop restored): '1 failed, 375 passed, 26 skipped' — the only kill is tests/test_r3_gaps.py::...[dryer-box] (scratch); no repo test fails
- Mutation M02 (generic branch pop restored): only kill is tests/test_r3_gaps.py::...[generic-room]
- Proposed test test_r3_move_off_a_toolhead_clears_the_trail_through_the_real_merge (REAL spoolman_api.update_spool, only requests.get/patch faked): PASSED x2 on the working tree
- Same test on HEAD: FAILED with the wire body {'extra': {'container_slot': '""', 'physical_source': '"LR-MDB-1"', 'physical_source_slot': '"3"', 'sheet_link': '"keep-me"'}, 'location': 'CR'} and, for the dryer case, location 'LR-MDB-2' carrying physical_source '"LR-MDB-1"'
- Realistic re-run of all 26 tests (test_r3_realistic_variant.py): 26 passed — they pass either way, so none of them can see this

**Fix direction.** Add a test that drives perform_smart_move through the real spoolman_api.update_spool with only the HTTP transport faked, as in scratch r3_realistic.RealisticSpoolman plus test_r3_gaps.py::test_r3_move_off_a_toolhead_clears_the_trail_through_the_real_merge (CR and LR-MDB-2 slot 1). Assert that the PATCH body's extra.physical_source and physical_source_slot equal '""' and that a sibling extra survives. Also tighten test_deployed_flag_preservation.py:356-359 and test_smart_move_spoolman.py:211 to require the key to be present and equal "".

**Verifier.** Independently reproduced with my own mutation harness on a scratch copy: 50 relevant repo test files, 449 tests. The harness is validated by a control mutant (the old ghost trail) that 2 tests catch. M01 (dryer pop restored) and M02 (generic pop restored) both give '449 passed' with 0 failures.

Why nothing catches them:
- The new test's FakeSpoolman replaces extra wholesale (test_active_print_chain_confirm.py:126-127).
- Both L130 pins accept an absent key (test_deployed_flag_preservation.py:356-359, test_smart_move_spoolman.py:211).

R3's real-merge gap test PASSES on WT and FAILS on HEAD; the HEAD PATCH body still carries physical_source '"LR-MDB-1"'. So the fix is real and unpinned. Yellow, not orange: this is a test gap, not a behaviour defect.

**Recommended fix.** Promote test_r3_gaps.py::test_r3_move_off_a_toolhead_clears_the_trail_through_the_real_merge (the real spoolman_api.update_spool with only requests.get/patch faked, parametrized over room and dryer box). Tighten the two L130 pins to require the key to be present and equal "" (wire form '""').

#### R3-02 — Smart Load's exact-location resident filter is pinned only for ghosts, not for the Printer-row prefix case

*Severity orange → **yellow** after review · verdict **CONFIRMED** · proof: test-run · `inventory-hub/tests/test_active_print_chain_confirm.py:135`*

**Claim.** The fix skips any matcher hit whose own record is not located exactly at the target (logic.py:618-619). Its comment says this covers ghosts and, for a Printer row, every toolhead's spool matched by prefix. FakeSpoolman's readers (lines 130-143) match only exact locations and exact physical_source, never the real flat-prefix match of _build_location_match (spoolman_api.py:1467,1475). So only the ghost half is tested. A filter that still rejected ghosts but accepted prefix hits would pass every repo test.

**Failure scenario.** The filter is refactored to drop only is_ghost items, or to a prefix/startswith comparison. Loading a spool onto a Printer row such as dev 'XL' (Type Printer, Max 0) then unloads every XL-n toolhead's spool again, the HEAD behaviour in I5-5, with all tests green.

**Evidence.**

- Mutation M11 (filter changed to `startswith(target)`, which still rejects ghosts): no repo test fails; only test_r3_gaps.py::test_r3_loading_a_printer_row_never_unloads_its_toolheads fails
- That gap test, using the real matcher (sm.at_location('XL') == [10, 11]), PASSES on the working tree and FAILS on HEAD: #10 was written to LR-MDB-1 ('[(10, {... 'location': 'LR-MDB-1'}), ... (42, {... 'location': 'XL'})]')

**Fix direction.** Add the Printer-row case using a matcher that mirrors _build_location_match's prefix rule, or the real matcher over the fake store as in scratch r3_realistic._items: spools on XL-1 and XL-3 plus an 'XL' Printer row; perform_smart_move('XL', [42]) must leave both toolhead spools in place.

**Verifier.** My mutation M11 (resident filter changed to startswith(target)) gives 449 passed with 0 failures. The new file's FakeSpoolman readers are exact-match only, so the flat-prefix case of _build_location_match (spoolman_api.py location_prefix) is never exercised. R3's gap test (real matcher, 'XL' Printer row) passes on WT and fails on HEAD (#10 written to LR-MDB-1).

**Recommended fix.** Promote test_r3_gaps.py::test_r3_loading_a_printer_row_never_unloads_its_toolheads, which uses the real matcher over the fake store, into the repo test file.

#### R3-03 — Two Smart Load refusal branches are unpinned: an unreadable resident, and the undo record after a partial unload

*Severity yellow → **yellow** after review · verdict **CONFIRMED** · proof: test-run · `inventory-hub/logic.py:615`*

**Claim.** logic.py:615-617 makes an unreadable resident refuse the whole move, and logic.py:646-647 pushes an undo record when some residents were unloaded before another got stuck. Neither is tested. Deleting either survives every repo test.

**Failure scenario.** (a) `stuck[rid] = ...` is changed to a plain `continue`: a transient get_spool failure for the resident lets the incoming spool land on an occupied head, which is exactly HEAD's behaviour (the resident eject returns False, which is falsy, and the load proceeds). (b) The partial-unload UNDO_STACK.append is removed: on a doubled head where #98 unloads but #99's return is rejected, #98 is moved off the head with no way to undo it.

**Evidence.**

- Mutation M03 (unreadable resident skipped): only test_r3_gaps.py::test_r3_unreadable_resident_refuses_the_load fails; that test fails on HEAD with 42 written to XL-1 ('[(42, {... 'location': 'XL-1'})]')
- Mutation M06 (partial-unload undo record removed): only test_r3_gaps.py::test_r3_refused_load_after_a_partial_unload_is_undoable fails; on HEAD that scenario returned {'failures': {}, 'status': 'success'}
- Side note (code-trace): the partial-unload record has empty 'moves', so perform_undo logs its summary 'Undid: Moved 1 -> XL-1' (logic.py:2115-2119) although it only restored an unloaded resident

**Fix direction.** Promote the two scratch tests (test_r3_gaps.py) into the new test file. Consider giving the partial-unload record a summary that names the restored resident.

**Verifier.** My mutations M03 (unreadable resident skipped) and M06 (partial-unload undo record removed) each give 449 passed with 0 failures. R3's two gap tests pass on WT and fail on HEAD, as I re-ran them. The side note also checks out: a partial-unload record has an empty 'moves', so perform_undo falls back to the summary 'Moved 1 -> XL-1' although it only restored a resident.

**Recommended fix.** Promote test_r3_unreadable_resident_refuses_the_load and test_r3_refused_load_after_a_partial_unload_is_undoable. Give the partial-unload record a summary naming the restored resident(s).

#### R3-04 — Fix C's Type-row branch of _is_single_occupancy is unpinned; only printer_map heads are tested

*Severity yellow → **yellow** after review · verdict **CONFIRMED** · proof: test-run · `inventory-hub/logic.py:356`*

**Claim.** _is_single_occupancy returns True for a printer_map key OR for a row whose Type is a toolhead type or 'Printer'. Both the stale-trail check in perform_smart_eject (logic.py:1779-1784) and _ghost_trail_from depend on it. Every new test uses printer_map toolheads (XL-1/XL-3), so replacing the row-type line with `return False` goes unnoticed. That is the Group 21.3 class: a 'No MMU Direct Load' head that is not a printer_map key.

**Failure scenario.** A spool on XL-3 carries a stale physical_source 'CORE1-M0' (a No MMU Direct Load row outside printer_map) where #99 is loaded. With the row branch broken, ejecting it returns it onto CORE1-M0, leaving two spools on that head, and no test fails.

**Evidence.**

- Mutation M05 (`return row.get('Type') in ...` -> `return False`): only test_r3_gaps.py::test_r3_eject_never_returns_onto_a_toolhead_row_outside_printer_map fails
- That gap test PASSES on the working tree and FAILS on HEAD: '[(7, {... 'location': 'CORE1-M0'})]'

**Fix direction.** Add a case where the stale trail names a toolhead row that is not in printer_map (Type 'No MMU Direct Load'), for the eject and for a head->head move out of such a row.

**Verifier.** My mutation M05 (the row-type branch of _is_single_occupancy returning False) gives 449 passed with 0 failures. The branch is load-bearing beyond the 21.3 non-printer_map heads: the dev 'XL' Printer row is single-occupancy by Type and is not a printer_map key, so both the eject stale-trail check and _ghost_trail_from depend on it. R3's gap test passes on WT and fails on HEAD.

**Recommended fix.** Add cases where the trail names (a) a 'No MMU Direct Load' row outside printer_map and (b) a Type 'Printer' row, for perform_smart_eject and for a move out of such a row.

#### R3-05 — The chain's one-slot-feeds-one-head rule (only the last placed spool deploys) is unpinned

*Severity yellow → **info** after review · verdict **CONFIRMED** · proof: test-run · `inventory-hub/logic.py:856`*

**Claim.** logic.py:856-858 deploys only placed[-1:] and reports the others as skipped. This closes the verifier's MISSED item 4 (a multi-spool move into a bound slot put every spool on one toolhead). No test sends more than one spool through the chain.

**Failure scenario.** The limit is dropped (`to_deploy = placed`). A direct /api/smart_move with two spools and an explicit bound slot puts both on the bound toolhead again, and every test passes.

**Evidence.**

- Mutation M04: only test_r3_gaps.py::test_r3_multi_spool_move_into_a_bound_slot_deploys_only_the_last fails
- That test FAILS on HEAD: both #240 and #241 are written to XL-3 ('(241, {... 'location': 'XL-3'})' after 240's deploy)

**Fix direction.** Add the two-spool explicit-slot case: assert direct_at('XL-3') == [last spool] and that auto_deploy_skipped names the first.

**Verifier.** My mutation M04 (to_deploy = placed) gives 449 passed with 0 failures, and R3's gap test fails on HEAD (both spools written to XL-3).

Reach is low:
- performContextAssign's multi-spool path sends slot null, so auto-slot does not fire for more than one spool and no chain runs.
- Slot-QR and _doAssignFinalize send one spool.
- Bulk move uses auto_deploy=False.
That leaves only a direct /api/smart_move call with several spools and an explicit slot.

**Recommended fix.** Promote test_r3_multi_spool_move_into_a_bound_slot_deploys_only_the_last.

#### R3-06 — Fix E split the Group 20.2 detach into two call sites, but only the return-home one is tested

*Severity yellow → **info** after review · verdict **CONFIRMED** · proof: test-run · `inventory-hub/logic.py:1862`*

**Claim.** The detach now runs after a successful write in both the return-home branch (logic.py:1831) and the no-home/room branch (logic.py:1862). test_successful_eject_detaches_the_box_after_the_spool_write covers only return-home. Deleting the no-home call survives every repo test, test_l271_single_slot_autoattach.py included.

**Failure scenario.** The call at logic.py:1862 is lost in a later edit. Ejecting a spool with no saved home (confirmed unassign, or Smart Load's homeless_destination) from a toolhead then leaves that head's single-slot PolyDryer attached, and no test notices.

**Evidence.**

- Mutation M07 (detach removed from the no-home branch): only test_r3_gaps.py::test_r3_homeless_eject_detaches_the_single_slot_box_after_the_write fails
- Control M08 (detach removed from return-home) IS caught by test_active_print_chain_confirm.py::test_successful_eject_detaches_the_box_after_the_spool_write
- Gap test on HEAD: FAILED with [('XL-1', 'XL-1')] (detached before the write)

**Fix direction.** Parametrize test_successful_eject_detaches_the_box_after_the_spool_write over both branches: a spool with a saved home, and a homeless spool with confirmed_unassign=True or a homeless_destination.

**Verifier.** My mutation M07 (detach removed after the no-home 'Ejected' write) gives 449 passed with 0 failures, while the return-home call site is pinned by test_successful_eject_detaches_the_box_after_the_spool_write. A missed detach leaves a locations.json box attachment, which is visible and recoverable.

**Recommended fix.** Parametrize test_successful_eject_detaches_the_box_after_the_spool_write over a homed spool and a homeless spool (confirmed_unassign=True or homeless_destination='').

#### R3-07 — Two tests use an idle-then-PRINTING trigger that the real per-move probe cache makes impossible

*Severity yellow → **info** after review · verdict **CONFIRMED** · proof: test-run · `inventory-hub/tests/test_active_print_chain_confirm.py:260`*

**Claim.** test_autodeploy_refused_by_the_guard_is_not_reported_as_deployed (lines 258-263) and test_slot_qr_assign_says_why_the_spool_was_not_deployed (lines 684-689) return IDLE on the first probe call and PRINTING afterwards. _run patches prusalink_api.get_printer_state, which is the L3 per-move memo front door (prusalink_api.py:430-437). The real code probes XL once per top-level move and serves the chain from the cache. With the real cache the chain is never refused in that setup. For the slot-QR route, which always names the slot, not_deployed can therefore never come from the guard; its realistic triggers are a rejected toolhead write or a Smart Load refusal, and neither is tested at route level. The logic-level chain refusal is realistically covered by test_confirm_does_not_cover_the_head_of_an_auto_picked_slot.

**Failure scenario.** The route's not_deployed/not_deployed_target contract is proven only through a trigger production cannot produce. A regression in how the route reports a chain that failed because Spoolman rejected the toolhead write (the case users would actually hit) would not be caught.

**Evidence.**

- Scratch test_r3_probe_cache_realism.py (real get_printer_state memo; only _probe_printer_state faked with the same idle-then-PRINTING sequence): 'probe calls: 1 result: {'status': 'success', 'failures': {}, 'auto_deployed_to': 'XL-3'} final: {'location': 'XL-3', ...}' — PASSED
- logic.py:428-462: the perform_smart_move wrapper calls begin_probe_cache/clear_probe_cache around the outermost move

**Fix direction.** Drive both tests with a realistic trigger: reject_locations={'XL-3'} (the toolhead write is rejected), or at logic level an auto-picked slot or confirm=True with XL printing. Or patch prusalink_api._probe_printer_state instead of get_printer_state so the memo stays in the loop.

**Verifier.** _run patches prusalink_api.get_printer_state, which is the per-move memo front door (prusalink_api.py:421-437). R3's realism test, with only _probe_printer_state faked, passes on WT: 1 probe call, the chain deploys, auto_deployed_to XL-3. So within one explicit-slot move the chain can never be refused by the guard, and the two tests at lines 258-263 and 684-689 use a trigger production cannot produce.

The impact is limited to test realism. The route's not_deployed plumbing reads auto_deploy_skipped whatever the cause, and a Spoolman-rejected chain is covered at logic level by test_autodeploy_rejected_by_spoolman_is_not_reported_as_deployed.

**Recommended fix.** Drive both tests with reject_locations={'XL-3'}, or patch prusalink_api._probe_printer_state instead of get_printer_state so the memo stays in the loop.

#### R3-08 — Frontend fix G has no offline test coverage at all

*Severity yellow → **yellow** after review · verdict **CONFIRMED** · proof: code-trace-only · `inventory-hub/static/js/modules/inv_quickswap.js:634`*

**Claim.** None of the new frontend branches is referenced by any test in tests/, and a grep for not_deployed|assignment_failed|return_ambiguous|return_failed|quickswap_failed|stateInfo|auto_deploy_skipped matches only test_active_print_chain_confirm.py. The branches are:
- inv_quickswap.js: deposit sends confirm_active_print: !!stateInfo, and handles assignment_requires_confirm, assignment_failed and not_deployed;
- inv_cmd.js: assignment_failed and not_deployed in the scan handler and its replay; performContextAssign filters by res.failures;
- inv_loc_mgr.js: _doAssignFinalize treats failures[spool] as an error.
The existing quickswap and deposit E2E files are skipped under --offline and assert none of these branches.

**Failure scenario.** A later edit stops sending confirm_active_print on deposit, or goes back to removing every spool from the buffer on status==='success'. This reintroduces I2-06 / I2-08 / I2-14 with no test failing.

**Evidence.**

- grep -rln over inventory-hub/tests for the new action names and stateInfo: only tests/test_active_print_chain_confirm.py (and its .pyc)
- Code-read correctness check: window.fetchPrinterStateForToolhead returns null when the printer is idle or unknown (inv_loc_mgr.js:416-434), so `!!stateInfo` is true only when the active-print banner was shown

**Fix direction.** Add a hermetic canary or an opt-in E2E using page.route stubs: (1) deposit with a mocked active probe posts confirm_active_print:true; (2) an assignment_failed response leaves the spool in heldSpools and raises a 7 s error toast; (3) performContextAssign with res.failures removes only the unfailed ids.

**Verifier.** grep over inventory-hub/tests for not_deployed, assignment_failed, return_ambiguous, return_failed, quickswap_failed and auto_deploy_skipped finds only test_active_print_chain_confirm.py, which is backend-only. The E2E files are skipped under --offline, and by R2's trace they do not assert these branches. R2-01 (a real Enter-path bug in fix G) is concrete proof that the frontend gap let a defect through.

**Recommended fix.** Add E2E tests with page.route stubs:
(1) Deposit with an active probe stub posts confirm_active_print:true via click AND Enter.
(2) assignment_failed keeps the spool in heldSpools and shows a 7 s error toast.
(3) performContextAssign with res.failures removes only the unfailed ids.
(4) _doAssignFinalize with failures[spool] does not splice the buffer.
Run them in the pre-commit full sweep.

#### R3-09 — CLAUDE.md write-surfaces table not updated for the changed and new write paths

*Severity yellow → **info** after review · verdict **CONFIRMED** · proof: code-trace-only · `CLAUDE.md:121`*

**Claim.** The table must be kept current when write surfaces are added or changed. After this diff:
- perform_undo's ejection restore now PATCHes a merged `extra` (logic.py:2068-2083), yet perform_undo (moves at logic.py:2054, ejections at 2079) has no row;
- perform_smart_eject's relocate row does not mention the caller-decided homeless_destination, which skips the protected-unassign prompt (logic.py:1838-1850);
- the smart-move and eject rows still cite logic.py:524/575/603/628/827/853/1007 (stale already at HEAD, which had 564/615/644/670/1617/1643/1797); the current lines are 700/751/784/811/1829/1859/2014.
The Return route's new auto_deploy=False and 502 contract writes nothing directly and needs no row.

**Failure scenario.** The next audit of spool write paths misses the undo and Smart Load writes with extras, the exact class behind the 2026-04-26/27 outages that the table exists to prevent.

**Evidence.**

- CLAUDE.md:121 '| `logic.py:524` | `perform_smart_move` unseat existing |', :125 'logic.py:827 ... return-home', :126 'logic.py:853 ... relocate'; grep of CLAUDE.md for 'perform_undo' in the table: none
- git diff logic.py: ejection restore adds eject_payload['extra'] = merged; perform_smart_eject gains homeless_destination

**Fix direction.** Add a perform_undo row covering the move restore and the ejection restore with system-managed extras. Note homeless_destination on the relocate row. Refresh the logic.py line numbers, or cite function names instead.

**Verifier.** CLAUDE.md:121-127 cites logic.py:524/575/603/628/827/853/1007, which were already stale at HEAD, and grep finds no perform_undo row. perform_undo's moves restore already wrote merged extras at HEAD (L298 Phase 0), so that omission predates the diff. The diff adds the extras-writing ejection restore and the homeless_destination relocate in perform_smart_eject. This is documentation drift only.

**Recommended fix.** Add a perform_undo row (moves plus ejection restore, system-managed extras via read-merge-write, ERROR log on rejection). Note homeless_destination on the eject relocate row. Cite function names instead of line numbers.

#### R3-10 — Three smaller branches of the diff survive every test

*Severity info → **info** after review · verdict **CONFIRMED** · proof: test-run · `inventory-hub/logic.py:351`*

**Claim.** Each of these mutants survived the 376-test selection and my gap tests:
- M09: the status-only branch of smart_move_failure (logic.py:351);
- M12: the chain crash handler that turns an exception into a skip (logic.py:869-871);
- M19: the `ejected is not True` identity check (logic.py:627).
M19 is untestable today rather than merely untested. With confirm_active_print forwarded, homeless_destination always passed and the pre-flight probe cached, perform_smart_eject can no longer return a truthy refusal from Smart Load, so truthiness and `is True` behave the same.

**Failure scenario.** M09: a route calls smart_move_failure on a status 'error' result that has no failures map (e.g. 'No spools found') and reports success. M12: an exception in the chained deploy propagates and the box move is answered as a crash. M19: none reachable today.

**Evidence.**

- M09-smart_move_failure-ignores-status | 376 passed, 26 skipped | []
- M12-chain-crash-propagates | 376 passed, 26 skipped | []
- M19-smart-load-truthiness-instead-of-is-True | 376 passed, 26 skipped | []

**Fix direction.** Optional: unit-test smart_move_failure on {'status':'error','msg':...} with no failures, and a chain whose perform_smart_move raises (assert the box placement stands and auto_deploy_skipped carries the crash message).

**Verifier.** My mutations M09 (status-only branch of smart_move_failure removed), M12 (chain exception re-raised) and M19 (`is not True` changed to truthiness) each give 449 passed with 0 failures. R3's reachability analysis also holds:
- M19 cannot be observed today: Smart Load always forwards the confirm and a non-None homeless_destination, so no truthy refusal can return.
- M09 needs a status 'error' result without a failures map, which the three routes cannot receive (spool ids are ints, and the Smart Load refusal carries failures).

**Recommended fix.** Optional. Add unit tests: smart_move_failure({'status':'error','msg':'x'}, 1) == 'x', and a chain whose perform_smart_move raises leaves the box placement standing with auto_deploy_skipped naming the crash.

#### R3-11 — test_quickswap_return_ignores_a_ghost_resident fails on HEAD for a different reason than its docstring

*Severity info → **info** after review · verdict **CONFIRMED** · proof: test-run · `inventory-hub/tests/test_active_print_chain_confirm.py:610`*

**Claim.** The docstring says HEAD's Return pulls #7 off XL-3. The fixture binds no slot to XL-1 (LOCATIONS only has slot 3 -> XL-3), so on HEAD Return picks the ghost #7 but answers return_no_binding with no write. The ghost selection is still pinned through body['moved'] == 42, but the destructive consequence the test describes is never exercised, and its `direct_at('XL-3') == [7]` assertion would pass on HEAD too.

**Failure scenario.** If the ghost filter regresses in a way that still returns a no-binding answer for this fixture, the test catches it only through the 'moved' field. The spool-yanking path (Return moving #7 into a box and off XL-3) is not demonstrated.

**Evidence.**

- HEAD run: 'AssertionError: {'action': 'return_no_binding', 'active_toolhead': 'XL-1', 'requested': 'XL-1', 'toolhead': 'XL-1'}' at test_active_print_chain_confirm.py:624

**Fix direction.** Bind a slot to XL-1 in this test's locations (e.g. LR-MDB-1 slot 1 -> XL-1), so that on HEAD the ghost really is moved off XL-3 and the location assertions carry weight.

**Verifier.** In my HEAD run of the new test file, test_quickswap_return_ignores_a_ghost_resident fails at test_active_print_chain_confirm.py:624 with {'action': 'return_no_binding', 'active_toolhead': 'XL-1', ...}, not with a spool pulled off XL-3. LOCATIONS binds only slot 3 -> XL-3, so HEAD never reaches the destructive path the docstring describes.

**Recommended fix.** Add a slot bound to XL-1 in this test's locations (for example LR-MDB-1 slot 1 -> XL-1), so that on HEAD the ghost really is moved off XL-3 and the location assertions carry weight.

**Checked correct (R3).**

- HEAD run: all 26 tests in tests/test_active_print_chain_confirm.py FAIL on HEAD (26 failed in 1.79s), each at an assertion tied to its fix (e.g. confirmed box move writes only LR-MDB-1; 'XL-1 holds [42, 99]'; undo leaves #99 at LR-MDB-1; quickswap_done/return_done/assignment_done for rejected writes)
- Mock realism: all 26 tests PASS when re-run through the REAL spoolman_api.update_spool (read-merge-write, sanitize, LAST_SPOOLMAN_ERROR) over a fake HTTP layer and the REAL _build_location_match (26 passed in 1.29s), so none depends on FakeSpoolman's wholesale-replace or exact-only matching
- Deliberate change, test_deployed_flag_preservation head->head: 5fe1524's intent (the trail must not stay at LR-MDB-1, or Return from the new head uses the wrong box) is still asserted. HEAD's 'XL-3' trail never let Return use XL-3 anyway (Return needs a Dryer Box source and falls back to the binding; test_l316_charact_bindings_errors.py:233-240). Mutant M16 (old trail restored) is caught by this test and by test_head_to_head_move_takes_the_new_heads_bound_box
- Deliberate change, test_universal_fallback: loosening assert_called_once_with(9) is justified. The forwarded kwargs are pinned elsewhere: M17 (confirm dropped) is caught by test_confirmed_active_print_smart_load_ejects_the_resident, and M18 (homeless_destination dropped) by both homeless-resident tests
- Deliberate change, test_toolhead_resident_eject_21_3: the resident's own record must now place it on the head; the 21.3 type coverage is intact (full suite green)
- Deliberate change, test_l316_charact_bindings_errors: the Return kwargs pin adding auto_deploy=False is justified; M14 (auto_deploy back on) is caught by it and by test_quickswap_return_parks_the_spool_in_its_box[idle|printing]
- Control mutants caught by repo tests: M08 return-home detach, M10 explicit_slot, M13 eject toolhead-trail check, M14 Return auto_deploy, M15 undo ejection extras, M16 _ghost_trail_from
- Full hermetic suite from inventory-hub/ with --offline: 1 failed, 1691 passed, 798 skipped in 41.23s; the only failure is test_locations_json_integrity::test_every_row_is_a_dict_with_LocationID_and_Type (Derek's blank-LocationID TestCart row)
- Hermeticity: across the full suite, data/locations.json sha256 bf4dae92... is unchanged and no data/ file was added. startup_migrations (run on app import through the client fixture) are idempotent no-ops on the migrated dev file. print_tracker_latch.json mtime changes come from the container (it changed again at 21:10:38 with no test running). The new test mocks Spoolman, the PrusaLink probe, both Group 20.2 locations.json writers and requests; its only unmocked disk access is the app import, which predates this diff
- Python 3.9: container Python 3.9.25 ast.parse of /app/logic.py, /app/routes_bindings.py and /app/routes_scan.py -> 'parsed OK'; grep of the added lines finds no `| None`, match/case, zip(strict), walrus, removeprefix or builtin-generic annotations
- Module-qualified calls: routes use logic.smart_move_failure; logic uses spoolman_api./locations_db.; the diff adds no from-imports
- Patch targets: the new tests patch collaborators on their defining modules (logic.locations_db.*, logic.spoolman_api.*, prusalink_api.get_printer_state); test_universal_fallback patches logic.perform_smart_eject on logic
- LAST_SPOOLMAN_ERROR: still read adjacent in every write branch; _eject_refusal_reason deliberately avoids the global and points to the eject's own adjacent ERROR log; return_failed / quickswap_failed / assignment_failed surface the per-spool failure string captured next to the write
- Route table pin (tests/test_route_table_pin.py) and the source_family canaries pass; no routes were added or removed
- tests/test_no_direct_extra_patch.py passes; the diff adds no direct requests.patch with extra
- Frontend: `confirm_active_print: !!stateInfo` is correct because fetchPrinterStateForToolhead returns null for idle or unknown printers (inv_loc_mgr.js:416-434); new error toasts use 7000 ms per CLAUDE.md
- Repo untouched by this review: git status shows only the pre-existing diff plus files from other agents (Feature-Buglist.md, docs/agent_docs/tasks/active-print-chain-investigation-2026-09-12.md, test_confirm_chain_reshow_e2e.py)

### Diff review: Duplicates

- R2-04 is a duplicate of R1-07 (Return reports an unreadable resident as an empty toolhead).

### Diff review: found by the verifier, missed by every investigator

#### Return overlay previews the first bound slot, not where the backend actually sends the spool

**Claim.** The diff edited inv_quickswap.js _resolveReturnDestination to pick `(items || []).find(i => !i.is_ghost)`, 'the one the backend acts on', but the preview is still wrong. /api/get_contents returns get_spools_at_location_detailed(th) (routes_locations.py:676-678). For a DIRECT resident, _build_location_match sets 'location' to the spool's own location, the toolhead itself. So `preferred.box !== th` is always false. The overlay always previews the toolhead's FIRST bound slot, labelled '(first bound slot — the spool has no recorded origin)'. The backend Return (routes_bindings.py) sends the spool to its physical_source box and slot. Whenever those differ (several boxes feeding one head, or a deploy from a non-first slot), the user confirms one destination and the spool goes to another. This existed before the diff, but it sits inside the function the diff rewrote.

**Evidence.** <session scratch> It emulates the JS branch over the real matcher output and FAILED on WT and on HEAD: "GET_CONTENTS XL-3: [(240, False, 'XL-3', '')] | PREVIEW: ('LR-MDB-1', '3') | BACKEND: 200 return_done LR-MDB-2 2 physical_source". The JS frontend half is code-trace only. A read-only dev snapshot (count_preview.py) shows 0 of 5 loaded spools mismatching today, so it is latent. Fix: when the non-ghost resident's location equals th, read the spool's extra.physical_source and physical_source_slot (for example GET /api/spool_details?id=) and preview that when it names a Dryer Box. Fall back to the first binding only otherwise, mirroring the route.

#### Quick-Swap and deposit confirm text still promise the resident returns to its own origin box

**Claim.** Derek's decision implemented in Smart Load sends a resident with no saved home to its printer's Room (_known_room_of) or to Unassigned, via homeless_destination. The confirm overlays the user reads before a swap still say otherwise. The swap body says the resident 'gets auto-returned to its own origin box — never re-routed into a different dryer box'. The deposit body says 'that one returns to its own origin box first'. Neither text was updated, so a homeless resident silently lands in a Room or Unassigned against what the dialog promised. (The backend does log a WARNING 'unloaded #N from X → Room/Unassigned'.)

**Evidence.** Code-trace only. inv_quickswap.js, quickSwapDeposit body: 'If ${toolhead} currently has another spool, that one returns to its own origin box first.' The Quick-Swap card showConfirmOverlay body: 'Any spool currently on the toolhead gets auto-returned to its own origin box — never re-routed into a different dryer box.' logic.py Smart Load passes homeless_destination=_known_room_of(target, loc_list) into perform_smart_eject, whose no-home branch writes target_loc = homeless_destination ('' = Unassigned). Fix: reword both to say the resident returns to its recorded source, else to the printer's room or Unassigned.

## Diff review

### FE — 

The fix does what it claims. The confirm re-prompt no longer gets dropped mid-fade, and the scan guards stop a CONFIRM scan from firing a dialog that was dismissed or is still queued. The same deferral also works for #safetyModal and #actionModal (proven in a browser; neither worked on HEAD). The new E2E file passed 16/16 on the fixed code (42 s). Its unchanged copy, with HEAD's inv_core/inv_cmd/inv_loc_mgr served through page.route, gave 14 failed / 2 passed, matching the report, and the failures seen in the output were at the intended assertions.

The main gap is that the "never confirm a warning nobody has read" rule covers scans but not clicks. A double-click on YES lands on the fading dialog about 120 ms later and sends the active-print override or true-unassign without the re-prompt ever showing: 12 of 12 runs on the fixed code, 12 of 12 on HEAD. So it is not a regression, but it is still open.

The new 7 s "Confirm scan ignored" toast also fires right after a successful confirm when the scanner double-reads (HEAD was silent), and it writes no Activity Log line. "On screen" is lifecycle-based, so a confirm hidden behind a mountOverlay still accepts a CONFIRM scan. Other checks came out clean:
- Every closeModal caller is covered, and non-gating modals are unchanged.
- Nothing cancels hide.bs.modal on the gating modals, and the scan gate cannot latch shut.
- Clearing pendingConfirm before the callback breaks no caller.
- The doEject sync-pulse is read-only and cheap, with no double render.
- The E2E file is hermetic.

Scratch artifacts are in <session scratch> probe.py, probe_fixed.txt, probe_head.txt, and headtest/test_confirm_chain_reshow_headjs.py.

#### FE-1 — Double-clicking YES confirms the re-prompt (active-print override / true unassign) without it ever showing

*Severity orange → **orange** after review · verdict **CONFIRMED** · proof: browser-run · `inventory-hub/static/js/modules/inv_core.js:1326`*

**Claim.** When the backend's answer arrives inside the ~150 ms fade-out, requestConfirmation writes the new message and callback into the dialog that is still fading out. That dialog is still display:block and clickable. The second click of a double-click therefore reaches confirmAction(true) via modals_core.html:27 and runs the re-armed doEject(..., confirm_active_print=true) or doEject(..., confirmed=true). confirmAction's closeModal also cancels the queued show, so the warning never appears at all. The new isGatingModalOnScreen rule guards only the scan routes in inv_cmd.js; the YES/FORCE EXECUTE buttons (modals_core.html:27, :52) and the action-card onclick (inv_core.js:1335) have no equivalent. This already happened on HEAD, but it is exactly the 'confirm a warning nobody has read' case the change says it closes.

**Failure scenario.** A spool is on a printing toolhead. The user double-clicks YES on 'Eject spool #N?'. The first click hides the dialog and POSTs. The backend answers active_print (median 80 ms, p90 147 ms per results.txt) or true-unassign (get_spool median 15.5 ms). The second click at ~120 ms lands on the fading dialog, now showing the 'XL is PRINTING' text at ~20% opacity, and POSTs confirm_active_print:true. The print is disrupted with an 'Ejected' toast and no readable warning.

**Evidence.**

- probe.py dblclick_real, unwidened Bootstrap timing, second click hit-tested via elementFromPoint: [fixed] 12/12 runs e.g. {"tArm": 20, "t2": 131, "hit2InConfirmContent": true, "opacity": "0.111167", "display": "block", "shownSoFar": 1, "ejects": [[false, false], [false, true]], "shown_total": 1}
- [fixed] unassign backend: {"tArm": 23, "t2": 122, "hit2InConfirmContent": true, "opacity": "0.222027", "ejects": [[false, false], [true, false]], "shown_total": 1}
- probe.py dblclick_widened, real page.mouse.click twice: [fixed] at_second_click {"hitInConfirm": true, "hitText": "YES", "hasShow": false, "display": "block", "opacity": "0.316703", "msg": "XL is PRINTING - ejecting from", "onScreen": false, "shownSoFar": 1} -> result {"ejects": [[false, false], [false, true]], "confirm_shown_total": 1, "toasts": ["Ejected"]}
- [head] identical: dblclick_real 12/12 ejects [[false,false],[false,true]] / [[false,false],[true,false]] with shown_total 1, so this predates the change
- modals_core.html:27 onclick="confirmAction(true)"; inv_core.js:1323 requestConfirmation writes confirm-msg and pendingConfirm before _showGatingModal queues the show

**Fix direction.** Treat a click on a gating dialog that is already hiding as stale. CSS is enough: '#confirmModal:not(.show) .modal-content, #safetyModal:not(.show) .modal-content, #actionModal:not(.show) .modal-content { pointer-events: none; }'. Bootstrap removes .show synchronously in hide() and re-adds it right after display:block in _showElement, so fade-in clicks still work. The JS equivalent is `if (_gatingPhase[id] === 'hiding') return;` at the top of confirmAction, confirmSafety and the action-card handler. Optionally also hold the new message until the queued show fires, so the fading dialog never displays the next prompt's text. Add an E2E: widened fade, click YES, wait for the re-arm, click YES again, then assert exactly one manage_contents POST and that the re-prompt reaches shown.

**Verifier.** I reproduced this independently with real CDP mouse input (page.mouse.click, true browser hit-testing), not element.click(). Script: verify-confirm-race/vprobe.py, scenario dblclick_cdp, unwidened Bootstrap timing, active_print backend, second click fired as soon as the re-prompt text was armed. Result: 5 of 5 runs. Examples:
- run 0: {"gap_ms": 34, "click2": {"tag": "BUTTON", "text": "YES", "inContent": true, "modalHasShow": false, "opacity": "0.777373", "msg": "XL is PRINTING - ejecting from this toolhead will disrupt the print."}, "ejects": [[false, false], [false, true]], "confirm_shown_total": 1, "reprompt_on_screen": false, "toasts": ["Ejected"]}
- runs 1-4 matched, with gaps of 25-45 ms and the fading dialog at opacity 0.78-0.89, so the new warning text is quite readable-looking but not yet confirmable by anyone who read it.

Code trace on the current tree agrees. modals_core.html:27 has onclick="confirmAction(true)" with no phase check. The second click reaches inv_core.js:1326 confirmAction: it takes the re-armed callback and nulls pendingConfirm. closeModal (inv_core.js ~1300) then sets _deferredShow[id]=null, which cancels the queued re-prompt, and calls inst.hide(), a no-op mid-transition. The callback then runs doEject(..., confirm_active_print=true). The action-card onclick at inv_core.js:1335 and FORCE EXECUTE at modals_core.html:52 are equally unguarded.

This predates the change (the reviewer's HEAD A/B shows identical output), so it is not a regression. It is still the exact 'confirm a warning nobody has read' outcome the change says it closes, and the consequence is a disrupted live print.

**Recommended fix.** Use the CSS variant. I validated it in the browser (vprobe.py dblclick_cssfix, 3 of 3) by injecting '#confirmModal:not(.show) .modal-content, #safetyModal:not(.show) .modal-content, #actionModal:not(.show) .modal-content { pointer-events: none; }'.
- The second click fell through to the .modal element: {"click2": {"tag": "DIV", "cls": "modal fade", "inContent": false}}.
- Only one eject went out: "ejects": [[false, false]].
- The re-prompt reached shown: "confirm_shown_total": 2, "reprompt_on_screen": true.
- A deliberate click on the fully shown re-prompt still worked: "after_deliberate_click_ejects": [[false, false], [false, true]].

Do NOT use the JS alternative as the review words it (`if (_gatingPhase[id] === 'hiding') return;` at the top of confirmAction). A CMD:CANCEL scan during the fade-out also goes through confirmAction(false) (inv_cmd.js:1439). With that early return, the queued re-prompt would reappear, breaking the cancel contract pinned by test_cancel_scan_while_a_reprompt_is_queued_cancels_it. If a JS guard is preferred, guard only the confirming direction: `if (y && _gatingPhase.confirmModal === 'hiding') return;`, the same for confirmSafety, and a phase check in the action-card onclick.

Add an E2E: widen the fade, click YES, wait for the re-prompt text to arm, click YES again, then assert exactly one manage_contents POST and that the re-prompt reaches shown.

#### FE-2 — New 7 s 'Confirm scan ignored' warning fires after a successful confirm and in other harmless cases

*Severity yellow → **yellow** after review · verdict **CONFIRMED** · proof: browser-run · `inventory-hub/static/js/modules/inv_cmd.js:1470`*

**Claim.** The res.cmd === 'confirm' route used to be a silent no-op when nothing was armed. It now always raises a 7 s warning, 'Confirm scan ignored — no confirmation dialog is on screen'. The same happens:
- on the second read of a scanner double-read, right after the first read confirmed successfully (the change's own comment names double-reads as a motivating case);
- on any stray CMD:CONFIRM;
- when a mountOverlay confirm, which only accepts CMD:CONFIRM:<sid>, is on screen and a printed plain CMD:CONFIRM is scanned, so the message is false;
- on any CONFIRM scan in the 483 ms fade-in.
It also writes no Activity Log entry, though CLAUDE.md requires one for every scan outcome (showToast at inv_core.js:223-248 does no logging).

**Failure scenario.** A blind scanner reads the YES QR twice 80 ms apart. The confirm takes effect, but an amber 7 s toast says the confirm was ignored. The user rescans. If a chained re-prompt is by then on screen, that rescan confirms it: the unread-warning outcome the guard exists to prevent, prompted by the guard's own wording.

**Evidence.**

- probe.py double_read: [fixed] {"ran": ["cb"], "identify_posts": ["CMD:CONFIRM"], "toasts": ["Confirm scan ignored — no confirmation dialog is on screen"]}
- [head] same scenario: {"ran": ["cb"], "identify_posts": ["CMD:CONFIRM"], "toasts": []}
- probe.py fadein_window: [fixed] {"showToShownMs": 483, "ranAt250": [], "toasts": ["Confirm scan ignored — no confirmation dialog is on screen"], "activeModal": "confirm"}
- HEAD inv_cmd.js:1456 was `else if (res.cmd === 'confirm' && state.pendingConfirm) confirmAction(true);` (silent otherwise); inv_cmd.js:1436 ignoredConfirm = showToast(..., 'warning', 7000) only

**Fix direction.** Keep the 7 s warning for the dangerous case only: a callback armed while its dialog is queued, fading in, or dismissed (`state.pendingConfirm && !onScreen`, or activeModal set but not on screen). When nothing is armed and no gating modal is pending, stay silent or use a short info toast. Reword so the text says why, e.g. 'the dialog isn't ready yet' or 'that dialog was dismissed'. Write the Activity Log line too, per the scan-outcome convention.

**Verifier.** I confirmed this through the REAL keyboard scan listener (scripts.html keydown -> processScan), not just direct processScan calls. There is no de-dup of identical scans anywhere in that listener.
- vprobe.py double_read_kb_plain, plain callback: {"ran": ["cb"], "identify_posts": ["CMD:CONFIRM"], "toasts": ["Confirm scan ignored — no confirmation dialog is on screen"]}. The first read confirms and closeModal nulls activeModal. The second read goes to identify_scan and then the new unconditional ignoredConfirm at inv_cmd.js:1470.
- double_read_kb_eject_ok, eject that succeeds: {"ejects": 1, "toasts": ["Ejected", "Confirm scan ignored — no confirmation dialog is on screen"]}. This is a false alarm right after a successful eject.
- double_read_kb_eject_active: the second read is queued behind state.processing (scripts.html isFrozen/setInterval 250 ms) and lands while the active-print re-prompt is queued. The guard correctly refused it: {"ejects": [[false, false]], "confirm_shown_total": 2, "on_screen_now": true, "toasts": ["Confirm scan ignored — no confirmation dialog is on screen"]}. But the toast says 'no confirmation dialog is on screen' about half a second before that dialog appears, which is the misleading-wording half of the claim.

HEAD's line was `else if (res.cmd === 'confirm' && state.pendingConfirm) confirmAction(true);`, silent otherwise. showToast (inv_core.js:223-248) writes no Activity Log.

The failure scenario's follow-on ('the rescan confirms the now-visible re-prompt') is inference, not reproduced. The false alarm and the wrong wording are proven.

**Recommended fix.** Split the message by cause.
- `state.pendingConfirm` armed (or activeModal set) and the dialog queued, fading in, or fading out: keep the 7 s warning, reworded to 'Confirm scan ignored: the dialog isn't ready yet, scan again once it is visible'.
- Armed but the dialog was dismissed: 'that confirmation was dismissed'.
- Nothing armed and no gating modal pending, which covers a double-read after success and a stray CMD:CONFIRM: stay silent, or use a short info toast.
- Write the Activity Log line for the warning cases per the scan-outcome convention.

#### FE-3 — isGatingModalOnScreen is lifecycle-only: a confirm hidden behind a mountOverlay still accepts a CONFIRM scan

*Severity yellow → **yellow** after review · verdict **CONFIRMED** · proof: browser-run · `inventory-hub/static/js/modules/inv_core.js:1264`*

**Claim.** isGatingModalOnScreen returns true for any fully shown gating modal, including one rendered at z-index 1055 underneath a mountOverlay panel (z 20000), so a CONFIRM scan fires a callback whose dialog nobody can see. One reachable path: the client-side CMD:CLEAR route (inv_cmd.js:1422) runs before identify_scan. With a bulk move armed and a non-empty buffer, it opens 'Clear entire Buffer?' (requestClearBuffer, inv_cmd.js:99) behind the Bulk Move panel (mountOverlay backdrop:true, inv_cmd.js:993-1001). The deadlock guard at ~1452-1462 only covers the backend's cmd:'clear' answer. This is not a regression; the new guard just doesn't cover it.

**Failure scenario.** During a bulk move with spools in the buffer, the user scans a printed CMD:CLEAR label, and the confirm opens invisibly behind the panel. activeModal='confirm' now swallows the destination scan. A CONFIRM scan then clears the buffer without the dialog ever being visible.

**Evidence.**

- probe.py occluded (generic mountOverlay + requestConfirmation): [fixed] {"hitIsOverlay": true, "hitText": "PROBE OVERLAY PANEL", "confirmZ": "1055", "onScreen": true, "ran": ["occluded-cb"]}
- inv_cmd.js:1422 `if (upper === 'CMD:CLEAR') { requestClearBuffer(); return; }` precedes the identify_scan fetch; inv_cmd.js:993-1001 bulk panel mountOverlay({ tier:'standard', backdrop:true })
- The bulk-move path itself is code-trace; the occlusion mechanism is browser-run

**Fix direction.** Have isGatingModalOnScreen return false while any [data-overlay-mount="1"] overlay is mounted, or hit-test the dialog centre with elementFromPoint. Separately, give requestClearBuffer / the client CMD:CLEAR route the same bulkMoveActive bail the backend 'clear' path already has.

**Verifier.** Browser-run on the specific client CMD:CLEAR path, with a mountOverlay shaped like the bulk panel (tier standard, backdrop true, backdropDismiss false, mirroring inv_cmd.js:993-1001). The run used a non-empty fake buffer and processScan('CMD:CLEAR'), which is intercepted client-side at inv_cmd.js:1422 before any bulkMoveActive check.

vprobe.py occluded_clear: {"msg": "Clear entire Buffer?", "activeModal": "confirm", "hitIsOverlay": true, "confirmZ": "1055", "onScreen": true, "loc_scan_reached_backend": false, "heldSpools_after_confirm": 0, "buffer_posts": [{"buffer": []}], "toasts": ["Buffer Cleared"]}. The buffer POST was fulfilled synthetically.

This shows three things:
- The confirm is invisible behind the panel.
- A LOC destination scan is silently swallowed by the activeModal route and never reaches identify_scan.
- A CONFIRM scan clears the buffer because isGatingModalOnScreen (inv_core.js:1264) is lifecycle-only.

The real bulk panel was not opened (that needs backend session writes), so 'bulk move armed' is simulated by an equivalent overlay. This is not a regression.

**Recommended fix.** In isGatingModalOnScreen, hit-test the dialog: take the centre of `#<id> .modal-content` via getBoundingClientRect, call elementFromPoint, and require the hit to be inside that modal. I'd pick that over 'false while any [data-overlay-mount="1"] exists', because mountOverlay supports backdrop:false and small non-occluding overlays. Also add the bulkMoveActive bail to the client CMD:CLEAR route or to requestClearBuffer (inv_cmd.js:99/:1422), matching the backend cmd:'clear' deadlock guard at ~1452-1462.

#### FE-4 — E2E pins only #confirmModal; the new safety/action deferral and promptAction generation bump have no regression test

*Severity yellow → **yellow** after review · verdict **CONFIRMED** · proof: browser-run · `inventory-hub/tests/test_confirm_chain_reshow_e2e.py:53`*

**Claim.** WIDE_FADE_CSS and every chain test target #confirmModal. The same _showGatingModal/closeModal code path now carries promptSafety and promptAction chains, plus the new _confirmGeneration++ in promptAction. These are new behaviours (both chains were dropped on HEAD), but no test would catch a regression. Also unpinned: the stale-hidden guard in the phase tracker (inv_core.js:1243-1261) and the FE-1 click path.

**Failure scenario.** A later edit special-cases confirmModal in _showGatingModal, or drops the generation bump from promptAction. A safety re-prompt from a safety callback, or a 'Slot Occupied' action chain, silently stops appearing again, and all 16 tests stay green.

**Evidence.**

- probe.py safety_chain: [fixed] {"second_shown": true, "snap": {"msg": "second safety", "show": true, "activeModal": "safety", "activeModalAfter600": "safety"}, "ran": ["s2"]}; [head] {"second_shown": false, "snap": {"msg": "second safety", "show": false, "activeModal": null}, "ran": []}
- probe.py action_chain: [fixed] {"second_shown": true, "snap": {"title": "B title", "activeModalAfter600": "action"}, "ran": ["b"]}; [head] {"second_shown": false, "activeModal": null, "ran": []}
- grep of the test file: WIDE_FADE_CSS = "#confirmModal.fade {...}"; only test_scan_into_a_dismissed_safety_or_action_dialog_fires_nothing touches safety/action, and only the scan guard

**Fix direction.** Parametrize test_prompts_queued_behind_a_fade_out_show_once_with_the_newest_text and the synchronous re-prompt test over confirm/safety/action. Widen the fade on #safetyModal and #actionModal too, open with promptSafety/promptAction, and click '#safetyModal .btn-danger' / '#action-buttons .modal-action-card'. Assert the second dialog reaches shown, activeModal survives the 400 ms release, and only the newest callback runs.

**Verifier.** Verified by reading the current test file.
- Line 53: WIDE_FADE_CSS = "#confirmModal.fade { ... }" only.
- The chain and queue tests (test_active_print_reprompt..., test_prompts_queued_behind_a_fade_out..., test_a_callback_that_reprompts_synchronously..., test_closing_a_confirm_during_its_fade_in..., test_a_reprompt_raised_during_a_fade_in_close...) all drive requestConfirmation/#confirmModal.
- Only test_scan_into_a_dismissed_safety_or_action_dialog_fires_nothing touches safety/action, and only the scan guard.

Nothing pins the safety/action deferral through _showGatingModal, the promptAction _confirmGeneration++ (inv_core.js:1338), or the stale-hidden early return in the phase tracker. The behaviour difference is real: the reviewer's probe shows HEAD dropping both chains (second_shown false) and the fixed code showing them.

**Recommended fix.** Parametrize the queued-show, synchronous re-prompt and fade-in-close tests over confirm, safety and action.
- Widen .fade on #safetyModal and #actionModal as well.
- Open with promptSafety/promptAction and click '#safetyModal .btn-danger' or '#action-buttons .modal-action-card'.
- Assert the second dialog reaches shown, activeModal is still set 600 ms later, and only the newest callback runs.

If FE-1's CSS fix lands, add a double-click case too.

#### FE-5 — Known open item: a stale CMD:CONFIRM:<sid> still confirms a different, fully shown Bootstrap dialog

*Severity info → **info** after review · verdict **CONFIRMED** · proof: code-trace-only · `inventory-hub/static/js/modules/inv_cmd.js:1439`*

**Claim.** routeConfirmScan (inv_cmd.js:1408) misses an unknown sid and falls through. With activeModal==='confirm' and #confirmModal shown, `upper.includes('CONFIRM')` then confirms that unrelated dialog. The implementation agent flagged this as left open. It is cheap to close because a sid-scoped payload that routeConfirmScan rejected is by definition stale.

**Failure scenario.** A Quick-Swap confirm overlay closes, and its printed/on-screen QR is scanned late while an 'Eject spool #N?' Bootstrap confirm is up. The eject runs.

**Evidence.**

- inv_cmd.js:1408 `if (window.routeConfirmScan && window.routeConfirmScan(text)) return;` then :1439 `upper.includes('CONFIRM') ? (onScreen('confirmModal') ? confirmAction(true) : ...)`
- inv_core.js:454-470 routeConfirmScan returns false for an unknown sid; logic.py:179 substring-matches CMD:CONFIRM for the identify_scan route

**Fix direction.** In the activeModal routes and before identify_scan, treat text matching /^CMD:(CONFIRM|CANCEL):.+/i that routeConfirmScan rejected as stale: toast 'That confirm QR belongs to a closed dialog' and return, instead of substring-matching.

**Verifier.** Now browser-run, where the review was code-trace only. vprobe.py stale_sid_shown: {"routeConfirmScan": false, "ran": ["eject-cb"], "identify_posts": []}.

With 'Eject spool #990031?' fully shown, processScan('CMD:CONFIRM:zzStale999') misses routeConfirmScan (inv_core.js:454-470 returns false for an unknown sid). It then hits the activeModal==='confirm' route at inv_cmd.js:1439, where upper.includes('CONFIRM') runs the unrelated eject callback without any backend call.

It stays info because sid-scoped QRs exist only on screen inside live mountOverlay confirms and are never printed, so a genuinely stale one needs a delayed scanner or a screenshot. The implementation agent already flagged it as open.

**Recommended fix.** Right after `if (window.routeConfirmScan && window.routeConfirmScan(text)) return;`, add: `if (/^CMD:(CONFIRM|CANCEL):.+/i.test(text)) { showToast('That confirm QR belongs to a closed dialog', 'warning', 7000); return; }`. That treats any sid-scoped payload routeConfirmScan rejected as stale, before the substring-matching activeModal routes and identify_scan. Arguably let CANCEL:<sid> fall through, since cancelling is safe.

#### FE-6 — Minor flake surface in the eject-refresh E2E

*Severity info → **info** after review · verdict **PLAUSIBLE** · proof: code-trace-only · `inventory-hub/tests/test_confirm_chain_reshow_e2e.py:587`*

**Claim.** _until returns on the first recorded get_contents of any id. The refresh can also silently not happen, for two reasons:
- refreshManageView (inv_loc_mgr.js:845-857) returns false if a heartbeat or locations-changed fetchLocations replaces state.allLocations between the fake-row push (line 579) and the YES click;
- it returns without fetching while _refreshManageViewInflight is set.
Either way the test fails with the misleading 'no manage-view refresh'. It passed in both of my runs (fixed and HEAD-JS), so the risk is low.

**Failure scenario.** On a loaded host, a pulse-triggered fetchLocations lands during the ~50 ms between the push and the click. refreshManageView('FCC-TEST-TH') finds no row, the test reports 'no manage-view refresh after a successful eject', and the product is fine.

**Evidence.**

- test lines 579-587: push fake rows, click YES, `_until(page, lambda: be.get_contents_ids, ...)`
- inv_loc_mgr.js:846-848 `const loc = state.allLocations.find(...); if (!loc) return false; if (_refreshManageViewInflight) return true;`

**Fix direction.** Stub GET /api/locations in FakeBackend to append the two FCC-TEST rows, or re-push them immediately before the click inside the same evaluate. Wait specifically for 'FCC-TEST-TH' in get_contents_ids rather than for any entry.

**Verifier.** Code-trace only.
- inv_loc_mgr.js:845-857: refreshManageView returns false when the id is not in state.allLocations, and returns without fetching while _refreshManageViewInflight is set.
- inv_core.js:804 `state.allLocations = rowOnly` in fetchLocations replaces the array wholesale, so a pulse- or locations-changed-triggered fetchLocations that lands between the push (test lines 579-581) and doEject's success removes the fake rows.
- doEject's own locations-changed dispatch comes before refreshManageView, but fetchLocations is async, so that self-race cannot happen. The exposure window is only click + route round-trip.
- `_until(page, lambda: be.get_contents_ids, ...)` (line 587) returns on any recorded id.

The test passed in my run ('16 passed in 43.41s') and in both of the reviewer's, so the risk is low but real.

**Recommended fix.** Make FakeBackend fulfil GET /api/locations by appending the FCC-TEST-TH/FCC-TEST-BOX rows to the passthrough response. Otherwise, re-push the rows and click YES inside one page.evaluate. Wait for 'FCC-TEST-TH' in get_contents_ids specifically, not for any entry.

**Checked correct (FE).**

- New E2E on the fixed code: '16 passed in 42.42s' (run 1). An unchanged copy with HEAD's three modules served through page.route: '14 failed, 2 passed in 62.99s' (run 2). Failures seen were at the intended assertions, e.g. 'a synchronous re-prompt was dropped', 'a CMD:CONFIRM scan fired the DISMISSED eject', "refreshed the card's box instead of the open toolhead view: ['FCC-TEST-BOX']", 'a CMD:MODAL:0 scan fired the callback of a DISMISSED action dialog'.
- E2E hermeticity: context.route is installed before goto on pytest-playwright's function-scoped context. Every non-GET is fulfilled synthetically, and only GETs pass through. Fake ids are used, get_contents for FCC-TEST-* is stubbed, and buffer POSTs from renderBuffer or the heartbeat are fulfilled, not persisted.
- The widened 1 s fade on #confirmModal makes the queued-show tests deterministic regardless of Bootstrap's default duration. The fade-in test only needs fade-in > 50 ms (measured 483 ms).
- closeModal callers (grep of static/js + templates): only actionModal, confirmModal and safetyModal. Non-gating modals (manageModal, locMgrModal, spoolModal, ...) call modals.X.hide() directly and are unaffected. An id with no tracked phase falls through to plain inst.hide(), as before.
- No show.bs.modal or hide.bs.modal listener calls preventDefault on a gating modal (the only hide.bs.modal preventer is inv_wizard.js:88 on wizardModal). The microtask restore is therefore unreachable today, but correct.
- Scan gate cannot latch shut. Phases always progress through Bootstrap's own events, _deferredShow is cleared on hidden or by closeModal, nothing strips .show from gating modals by hand, and the inv_loc_mgr Escape ladder's inst.hide() is tracked through the public events.
- pendingConfirm/pendingSafety cleared before the callback: no callback reads state.pendingConfirm (grep), and no async path relied on the trailing null. The de390a0 invariant still holds: the hidden.bs.modal release still never clears pendingConfirm. A throwing callback no longer leaves a stale armed callback.
- Page load: modals are built inside DOMContentLoaded (scripts.html:83, :114-118), and every requestConfirmation/promptSafety/promptAction caller is user-driven. _showGatingModal's silent return when the instance is missing is not reachable in practice.
- Safety and action re-prompt chains work on the fixed code and were dropped on HEAD (probe safety_chain/action_chain). promptAction's generation bump keeps activeModal='action' past the 400 ms release.
- Scan guards leave legitimate flows intact. routeConfirmScan still runs first for sid-scoped overlay confirms. Bulk-move scans answer cmd:'clear' and never reach the confirm route. A CONFIRM scan on a fully shown dialog confirms, as shown by test_confirm_scan_while_a_reprompt_is_still_queued_is_ignored's second half. CANCEL is unguarded and cancels a queued prompt.
- doEject inventory:sync-pulse listeners are all read-only:
- inv_cmd.js:2119 liveRefreshBuffer, in-flight guarded at :2098 and already triggered by locations-changed;
- inv_quickswap.js:1278, a silent render with a content-hash skip;
- inv_details.js:644, only if details modals are open;
- inv_backlog.js:216, one count GET;
- cancel_review.js:470, one badge GET;
- inv_printer_status.js:517, debounced;
- inv_search.js:136, only if the panel is open and a query is set.
There is no double Quick-Swap render (_renderManagePayload does not call renderQuickSwapSection), and lastLocRenderHash is nulled once before a single refreshManageView.
- openLocId = manage-loc-id value || loc is correct: the manage modal's hidden handler and closeManage both clear manage-loc-id, so a closed view falls back to loc.

### Diff review: found by the verifier, missed by every investigator

#### The FE-1 JS-guard alternative would break the cancel-a-queued-prompt contract

**Claim.** The review offers `if (_gatingPhase[id] === 'hiding') return;` at the top of confirmAction/confirmSafety as equivalent to its CSS fix. It is not. A CMD:CANCEL scan during the fade-out calls confirmAction(false) through the activeModal route. With that early return, closeModal never cancels _deferredShow, so the re-prompt the user just cancelled appears anyway, and so does a safety re-prompt through confirmSafety(false). Only the confirming direction (y === true) or the click surface should be guarded. The CSS variant avoids the issue because it only affects pointer input.

**Evidence.** Code trace:
- inv_cmd.js:1439 routes CANCEL to `confirmAction(false)`, unguarded by design.
- inv_core.js closeModal (~1300) is the only place that clears `_deferredShow[id]`.
- tests/test_confirm_chain_reshow_e2e.py:399-419 (test_cancel_scan_while_a_reprompt_is_queued_cancels_it) scans CMD:CANCEL during the hide and asserts `_count(page, 'show') == 1`.

Browser-run for the CSS variant: vprobe.py dblclick_cssfix 3/3, "ejects": [[false, false]], "confirm_shown_total": 2, then a deliberate click gives [[false, false], [false, true]].

#### The 'Confirm scan ignored' toast contradicts the screen in the one case the guard exists for

**Claim.** When a scanner double-reads YES on an eject whose backend answers active_print, the second read is held by the keyboard listener's state.processing queue (scripts.html, 250 ms poll). It lands while the re-prompt is queued behind the fade-out. The guard correctly refuses it, but the 7 s toast says 'no confirmation dialog is on screen', and the active-print dialog then appears. A blind scanner told the confirm was ignored is invited to rescan YES straight into the warning. This strengthens FE-2's rewording recommendation, and is distinct from FE-2's double-read-after-success case.

**Evidence.** Browser-run through the real keyboard listener, vprobe.py double_read_kb_eject_active: {"ejects": [[false, false]], "confirm_shown_total": 2, "on_screen_now": true, "msg": "XL is PRINTING - ejecting from this toolhead will disrupt the print.", "toasts": ["Confirm scan ignored \u2014 no confirmation dialog is on screen"]}. Scripts: <session scratch> outputs vprobe_out_dblclick.txt and vprobe_out2.txt in the same folder.


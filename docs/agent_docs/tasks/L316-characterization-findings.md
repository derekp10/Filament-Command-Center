# L316 characterization findings — 50 suspected bugs (2026-07-01)

Pinned by the test layer; triage with Derek. **✅ The 10 🔴 Priority reds (findings 18/21/22/25/27/34/40/41/46/49) were FIXED by Group 27 (2026-07-05)** — each pin was flipped to assert the corrected behavior (some renamed; see the per-finding `✅ FIXED` notes below for the current pin name). **✅ The 25 🟠 oranges (findings 1–7, 9–17, 19, 20, 23, 24, 30–33, 35) were FIXED by Group 28 (2026-07-05, `feature/group-28-l316-charact-oranges` → `dev`+`main`)** — each pin was likewise flipped to assert the fix (many renamed to the corrected contract; the current names are in the six `test_l316_charact_{label_helpers,label_endpoints,record_deletes,wizard_error_paths,scan_audit,queue_flags}.py` files, and the per-cluster fix list + Derek's four behavior forks are in `completed-archive.md`). The remaining 🟡 findings (36–39, 42–45, 47, 48, 50, plus doc-notes 28/29) stay pinned as-is (Group 29).


## label-helpers (inventory-hub/tests/test_l316_charact_label_helpers.py)

1. hex_to_rgb: the len()<6 guard runs on the RAW string BEFORE lstrip('#'), so a '#'-prefixed 5-digit hex passes the guard and the blue channel is silently parsed from a single digit: hex_to_rgb('#AABBC') == (170, 187, 12) instead of the ('','','') rejection. (Pinned in test_hex_to_rgb_length_guard_runs_before_hash_strip.)

2. get_smart_type: when filament_attributes exist but material is None/empty, the f-string emits a TRAILING SPACE ('Matte ') which lands verbatim in the label CSV Type column. (Pinned in test_get_smart_type_attrs_without_material_has_trailing_space.)

3. get_color_name: the name FALLBACK is returned verbatim, NOT clean_string'd — asymmetric with the original_color path, so a JSON-quoted filament name ('"Quoted"') prints with literal quotes on the label. (Pinned in test_get_color_name_name_fallback_not_quote_stripped.)

4. get_best_hex: an empty FIRST comma-segment (',445566') abandons multi_color_hexes entirely and falls back to color_hex — the valid second segment is never considered. (Pinned in test_get_best_hex_empty_first_segment_falls_to_color_hex.)

5. sanitize_label_text: the emoji map is inconsistent about VS16 (U+FE0F) — the Warn key INCLUDES it so a bare U+26A0 warning sign passes through untranslated to the P-touch CSV, while the Bolt key OMITS it so an emoji-presentation bolt (U+26A1 U+FE0F) is replaced but leaves a stray invisible VS16 in the output ('Bolt️'). Both directions pinned.

6. flatten_json: a bare scalar input yields {'': value} — an EMPTY-STRING key that would become a blank CSV column header. (Pinned in test_flatten_json_scalar_input_yields_empty_key.)

7. flatten_json: mangled-key collisions are silent — a literal 'a_b' key and a nested {'a': {'b': ...}} both produce output key 'a_b' and dict insertion order decides which value survives (last one wins). Also empty dict/list values vanish entirely (no column emitted). (Pinned in test_flatten_json_mangled_key_collision_last_wins / test_flatten_json_empty_containers_yield_empty_dict.)


## label-endpoints (inventory-hub/tests/test_l316_charact_label_endpoints.py)

8. api_print_location_label failure path is SILENT: a locked/failed write returns bare {'success': False, 'msg': str(e)} with NO 'locked' flag and NO Activity Log entry — inconsistent with /api/print_batch_csv's 2026-06-18 loud-lock contract (matches the known-open 'single-label endpoint' buglist item). It also bypasses _write_label_csv entirely (raw open('a'): no atomic write, no fcc_locked_name tagging). Pinned in test_location_label_write_failure_is_quiet_no_activity_log_no_locked_flag.

9. api_print_batch_csv mode='location' builds loc_lookup via EXACT row['LocationID'] key access (app.py:1477): a single locations row stored with a differently-cased key (e.g. 'locationid') raises KeyError and fails the WHOLE batch with msg "'LocationID'" — inconsistent with the case-insensitive 'Max Spools' matching later in the same handler and with api_print_location_label's tolerant lookup. Pinned in test_batch_location_row_missing_exact_locationid_key_fails_whole_export.

10. Filament/swatch mode does NOT run sanitize_label_text on Brand/Color/Type (spool and location modes do), so emoji reach the P-touch swatch CSV unsanitized. Pinned (raccoon emoji survives into Brand).

11. A literal 0 for settings_bed_temp/settings_extruder_temp renders as '' (falsy check), not '0°C' — a deliberate 0° temp prints blank on the swatch label. Pinned.

12. api_print_location_label writes LocationID and the LOC: QR using the UPPERCASED scanned id (target_id), not the row's stored casing (visible in the UNASSIGNED test: row says 'Unassigned', CSV gets 'UNASSIGNED') — if any scan-resolution consumer is case-sensitive, labels printed from a lowercase-stored LocationID won't round-trip.

13. Cosmetic: batch msg grammar is always plural — 'Overwritten 1 items.' Pinned as-is.


## record-deletes (inventory-hub/tests/test_l316_charact_record_deletes.py)

14. DELETE /api/locations with a blank/missing id returns HTTP 200 {"success": false} with no error/msg key — not a 4xx (the task brief said "blank id -> 400", but the shipped code at app.py:2036 returns a bare jsonify with default 200; the audit_extract agrees). Pinned as-is in test_delete_location_blank_id_returns_200_success_false_no_save.

15. api_delete_filament's "abort semantics" only abort the FILAMENT delete: after a child-spool delete failure the loop CONTINUES deleting the remaining children (children [1,2,3] with #2 failing yields deleted_spool_ids [1,3]). The docstring frames this as recoverable partial state so it may be intended best-effort, but callers reading "abort" might expect stop-on-first-failure. Pinned in test_delete_filament_child_failure_aborts_filament_delete.

16. api_delete_spool has no existence guard: deleting a nonexistent spool id returns 502 (Spoolman rejection passthrough) rather than 404 — get_spool returning None only degrades the log label to '#<id>'. Pinned via test_delete_spool_missing_snapshot_falls_back_to_bare_id_label / the rejection tests.


## wizard-vendor-errors (inventory-hub/tests/test_l316_charact_wizard_error_paths.py)

17. api_create_filament (app.py:595): the create_filament->None rejection branch returns the fixed generic msg 'Spoolman rejected the filament create.' WITHOUT surfacing spoolman_api.LAST_SPOOLMAN_ERROR — breaks the CLAUDE.md error-surfacing convention; its sibling api_create_vendor (app.py:629) does surface the body. Pinned as-is in test_create_filament_rejection_returns_500_generic_msg.

18. **✅ FIXED (Group 27, 2026-07-05).** api_edit_spool_wizard (now `routes_inventory.py`): a get_spool→None pre-fetch blip skipped BOTH the dirty-diff and the SYSTEM_MANAGED_EXTRAS strip and forwarded the raw payload (incl. container_slot / physical_source) verbatim, reopening the Item-4 slot-clobber window. FIX: fail closed — surface LAST_SPOOLMAN_ERROR, no raw-payload PATCH. Pin now: test_wizard_get_spool_none_fails_closed_no_raw_forward.

19. api_edit_spool_wizard ordering: the spool write commits (and emits the 24.F weight log) BEFORE the filament update; a filament rejection then returns success:False with no indication the spool half already persisted (partial write reported as total failure; retry is mostly benign because the second diff comes up empty). Pinned in test_wizard_spool_committed_before_filament_rejection.

20. api_external_fields_add_choice (app.py:936): missing-required-field validation returns HTTP 200 with {success:false,msg:'Missing required fields.'} instead of a 400 — contract quirk, pinned in test_add_choice_missing_field_returns_200_success_false.


## scan-audit (inventory-hub/tests/test_l316_charact_scan_audit.py)

21. **✅ FIXED (Group 27, 2026-07-05).** identify_scan spool (and filament) branch (now `routes_scan.py`): a get_spool/get_filament→None (deleted/unknown id) fell through to the terminal `return jsonify(res)` and echoed the bare resolver dict {'type':'spool','id':N} with no failure signal. FIX: return {'type':'error','msg':'… not found'} (frontend toasts res.type=='error') + a WARNING Activity-Log line, for BOTH branches. Pins now: test_spool_scan_unknown_spool_returns_error_payload + test_filament_scan_unknown_filament_returns_error_payload.

22. **✅ FIXED (Group 27, 2026-07-05).** manage_contents clear_location (now `routes_scan.py`) SKIPPED any slotted spool yet returned bare {'success': true} with no warning about the survivors. FIX (Derek's call — keep slotted, warn+report; a slotted spool is loaded into a toolhead/MMU): still ejects unslotted, but surfaces the survivors in the response (ejected[]/skipped_slotted[]/msg) + a WARNING Activity-Log line; the "Nuke all unslotted" button toasts the honest result. Pin now: test_clear_location_ejects_unslotted_and_surfaces_slotted_survivors.

23. app.py 2438/2481: an unrecognized manage_contents action returns {'success': false, 'msg': 'Spool not found'} (misleading message — nothing was looked up), and the terminal `return jsonify({"success": False})` at app.py:2481 is unreachable in practice. Pinned in test_unknown_action_returns_spool_not_found.

24. app.py 2839-2846: while an audit session is active, process_audit_scan's return value is discarded — the route answers {'type':'command','cmd':'clear'} even when the handler reports {'status':'error'} (e.g. a disallowed command), so the scanner UI gets no route-level failure signal (Activity Log only). Pinned in test_active_audit_hijacks_spool_scan_and_refreshes_watchdog.

25. **✅ FIXED (Group 27, 2026-07-05).** CMD:AUDIT scanned DURING an active audit session (now `routes_scan.py`) silently reset_audit()'d and restarted — wiping in-progress scanned/expected/rogue state. FIX (Derek's call — no-op + info line): the active-session check now sits ABOVE the reset; re-scanning CMD:AUDIT mid-audit preserves state, refreshes the idle watchdog, logs "Audit already in progress …", and the user ends via CMD:CANCEL/CMD:DONE. Pin now: test_cmd_audit_during_active_session_is_noop_preserves_state.


## filament-edit-log (d:/My Documents/Documents/3D Printing/Filament Command Center/inventory-hub/tests/test_l316_charact_filament_edit_log.py)

26. api_update_filament generic-Exception branch returns HTTP 200 with {success:false, msg:str(e)} — NOT a 500 (the audit/assignment said '500 shape'; the code jsonify()s at default 200). Pinned as-is in test_update_filament_generic_exception_returns_200_with_str.

27. **✅ FIXED (Group 27, 2026-07-05).** api_update_filament (now `routes_scan.py`): the activity-log formatting ran INSIDE the try AFTER a successful update_filament, so a formatter/logger crash returned success:false for an already-COMMITTED write → user retries + double-writes. FIX: format+log moved to its own guarded block AFTER the success-determining try; a log crash is logged but the response still reports success:true. Pin now: test_update_filament_committed_write_survives_raising_logger.

28. Doc staleness, not code: CLAUDE.md's Group 23.4 section says the delete-sentinel behavior is pinned by tests/test_delete_sentinel.py, but that file only covers the spoolman_api merge helpers — the '(cleared)' render in _format_filament_edit_log had zero coverage until this file.

29. Observation (borderline, not pinned as a failure): the 23.6 product_url 'idempotent' upgrade compares via _pm_norm, which strips quotes/whitespace but NOT a trailing slash — a stored path-form URL with trailing slash (the exact shape the physical QR encodes, e.g. https://prusament.com/spool/17705/5b1a183b26/) differs from the computed canonical (no slash), so the first scan of such a spool always fires one upgrade write. Self-healing after that write, so churn is bounded to one PATCH per spool; flagging in case the carve team assumes stored-QR-form URLs are no-ops.


## queue-flags (d:\My Documents\Documents\3D Printing\Filament Command Center\inventory-hub\tests\test_l316_charact_queue_flags.py)

30. set_flag has NO missing-id validation: a payload without 'id' forwards None straight to spoolman_api.get_spool (a live Spoolman lookup with id=None in prod) and returns HTTP 200 bare {'success': false} — asymmetric with mark_printed's 'Missing ID or Type' guard. Pinned in test_set_flag_missing_id_is_forwarded_as_none_not_4xx.

31. set_flag does NOT int-coerce the id: 'legacy_foo' is passed verbatim to get_spool, unlike mark_printed which rejects non-numeric legacy IDs with a dedicated msg. Decide before the carve which behavior wins (audit quirk #5). Pinned in test_set_flag_string_id_passed_through_uncoerced.

32. set_flag fall-throughs (unknown type, get_spool->None, missing type) all return HTTP 200 {'success': false} with NO 'msg' key — inv_queue.js can only show its generic 'Failed to flag for label print' toast; no LAST_SPOOLMAN_ERROR context, no 4xx. Pinned in three tests.

33. Both endpoints evaluate strict `request.json` BEFORE their try blocks: malformed JSON -> framework HTML 400, wrong content-type -> 415 (Flask 3.1 UnsupportedMediaType), bypassing the endpoints' JSON {'success': false, msg} error contract entirely — unlike api_quickswap's request.get_json(silent=True) idiom. A carve that 'harmonizes' this flips the status codes. Pinned in the 400/415 tests.

34. **✅ FIXED (Group 27, 2026-07-05).** mark_printed's legacy-ID gate (now `routes_print_queue.py`) caught ONLY ValueError from int(item_id); a JSON-array id raised TypeError → unhandled 500 in prod. FIX: broadened to `except (ValueError, TypeError)` so a non-scalar id returns the JSON error contract at HTTP 200. Pin now: test_mark_printed_non_intable_id_type_returns_json_error.

35. mark_printed treats id=0 as missing (`if not item_id` truthiness) and returns 'Missing ID or Type' — harmless today (Spoolman ids start at 1) but pinned in the parametrized missing-field test.


## filament-attributes (inventory-hub/tests/test_l316_charact_filament_attributes_unit.py)

36. report counts can gain keys OUTSIDE the schema choice list: `counts[a] = counts.get(a, 0) + 1` adds any rogue attribute a filament carries; the live test (test_filament_attributes_bulk_api.py::test_report_shape) asserts counts keys are a subset of choices, so it would go red against such data. Pinned in test_report_counts_can_gain_keys_outside_choices.

37. remove_choice docstring vs implementation ordering mismatch (also flagged by the audit): the docstring claims the choice is stripped from filaments BEFORE deleting from the schema ('so a mid-operation crash doesn't leave the field referencing a value still attached to records'), but the code actually does snapshot -> schema DELETE -> POST recreate -> strip-during-restore. The documented crash invariant is not what ships. Actual order pinned in test_remove_choice_happy_path_order_and_payloads.

38. bulk_set returns top-level success:true even when EVERY id errored (errors only surface in errors[]); a caller checking only `success` treats a total failure as success. Pinned in test_bulk_set_per_id_error_surface_and_warning_log.

39. remove_choice/sweep_unused restore loops only catch requests.RequestException; any other exception mid-restore (AFTER the schema was already deleted+recreated) escapes as an HTTP 500 with some filaments unrestored and no restore_failures report. Observed by reading, not pinned (no clean current-behavior assertion beyond a raw 500).


## monitor-boot (inventory-hub/tests/test_l316_charact_monitor_boot.py)

40. **✅ FIXED (Group 27, 2026-07-05).** _seed_printer_credentials_from_filabridge (now `print_monitor.py`): the inner locations_db.seed_printer_credentials call AND the `__main__` call site were both unwrapped — a raising seed would kill the serving-process launch before _start_cancel_monitor. FIX: wrapped the seed call (try/except→WARNING, return) + a belt-and-suspenders wrap at the `__main__` site; boot survives + the monitor still starts. Pin now: test_seed_inner_seed_exception_is_swallowed.

41. **✅ FIXED (Group 27, 2026-07-05).** _fcc_owns_completion_deduct (now `print_monitor.py`) bool()-coerced the raw config value — the JSON string "false" read as True and ENABLED the completion deduct (a dangerous safety-flag inversion). FIX: real parser (bools + numerics + "true"/"false"/"1"/"0"/"yes"/"no"/"on"/"off"; default safe False). Pin now: test_completion_flag_parses_bool_string_and_numeric_forms.


## bindings-errors (inventory-hub/tests/test_l316_charact_bindings_errors.py)

42. api_quickswap_return (app.py:3609): virtual-printer fan-out candidates are sorted LEXICOGRAPHICALLY, so XL-10 orders (and is probed) before XL-2 — on a 10+ toolhead printer (indxx forward-compat) the 'first loaded toolhead' the return acts on and the candidates[] order in the return_no_spool 404 body are numerically surprising. Pinned as-is in test_return_all_toolheads_empty_is_404_no_spool_with_sorted_candidates.

43. api_put_printer_creds (app.py:3335): the 'Printer connection updated for <name>' INFO activity-log fires even when changed=False (a no-op PUT with identical creds) — misleading log noise. Pinned as-is in test_put_printer_creds_unchanged_skips_save_and_returns_200.

44. Response-shape inconsistency across the return taxonomy: return_no_spool's 'toolhead' field is the REQUESTED prefix while return_no_binding's 'toolhead' is the ACTIVE toolhead (with the request demoted to 'requested') — a frontend consumer reading 'toolhead' uniformly gets different semantics per branch. Pinned in both tests; a carve must preserve the asymmetry.

45. api_quickswap_return (app.py:3597): cfg = config_loader.load_config() is dead — the value is never used (printer_map comes from locations_db.get_active_printer_map()). Vestigial, but a pure-move should carry it (or its removal should be a deliberate, separate commit) since it has a config-file read side effect.


## deduct-misc (inventory-hub/tests/test_l316_charact_deduct_misc.py)

46. **✅ FIXED (Group 27, 2026-07-05).** api_get_multi_spool_filaments (now `print_deduct.py`): one malformed spool entry (missing 'id', or 'vendor': None) tripped the blanket except and poisoned the whole response to [] (HTTP 200), hiding every valid candidate. FIX: per-spool try/except (skip+log the bad record) + null-safe filament/vendor reads; valid candidates still return. Pin now: test_multi_spool_malformed_spool_is_skipped_valid_candidates_survive.

47. api_get_multi_spool_filaments display string: f'{vendor} - {name}'.strip(' -') strips ALL leading/trailing spaces AND hyphens, so a legitimate vendor/name that starts or ends with '-' (e.g. name '-EOL-') gets its dashes eaten in the picker display. Cosmetic; fallback behavior pinned in test_multi_spool_display_fallbacks (not the dash-eating edge itself).

48. api_backfill_spool_weights (app.py:4207-4217): a spool list entry without an 'id' key yields sp.get('id') == None and the loop calls update_spool(None, {...}) — a PATCH aimed at /spool/None. Only reachable with malformed Spoolman data; not pinned (would require asserting on a nonsense write).


## pulse-state (inventory-hub/tests/test_l316_charact_pulse_state.py)

49. **✅ FIXED (Group 27, 2026-07-05).** /api/dashboard_pulse (now `routes_state_pulse.py`): when the shared _pulse_section_logs helper raised, the derived 'status' section was silently OMITTED (include=status alone returned {}), contradicting the docstring's per-section-isolation promise; the nav-bar dot got no signal. FIX: on a logs-helper error, the 'status' slot carries {'error': str(e)}. Pin now: test_pulse_status_section_carries_error_when_logs_helper_raises.

50. /api/state/buffer and /api/state/queue (app.py 6100/6107): POST stores ANY JSON type verbatim into state.GLOBAL_BUFFER/GLOBAL_QUEUE — no list validation (unlike /api/spools/refresh, which 400s on a non-list). One malformed client write poisons the persisted buffer/queue served to every dashboard until the next good write. Pinned by test_state_buffer_post_non_list_value_stored_verbatim.


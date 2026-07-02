"""Route-table pin for the app.py modularization (L316).

Pins every (rule, methods, handler-name) triple registered on the Flask app.
The modularization carve must keep this table intact: a missing row means a
route was lost in a move; a changed row means a handler was renamed or its
methods changed. If the carve ever introduces blueprints, their endpoint
prefixes are tolerated — comparison uses only the endpoint's basename.

Snapshot captured 2026-07-01 on feature/l316-app-modularization (pre-carve,
77 rules). Regenerate ONLY when a route is intentionally added or removed —
never to make a refactor pass:

    python -c "import app, json; print(json.dumps(sorted((str(r.rule), ','.join(sorted(m for m in r.methods if m not in ('HEAD','OPTIONS'))), r.endpoint.split('.')[-1]) for r in app.app.url_map.iter_rules())))"
"""
import app as app_module


EXPECTED_ROUTES = [
    ("/", "GET", "dashboard"),
    ("/api/audit_session", "GET", "api_audit_session"),
    ("/api/backfill_spool_weights/<int:fid>", "POST", "api_backfill_spool_weights"),
    ("/api/buffer/clear", "POST", "api_buffer_clear"),
    ("/api/cancel_deduct/confirm", "POST", "api_cancel_deduct_confirm"),
    ("/api/cancel_deduct/dismiss", "POST", "api_cancel_deduct_dismiss"),
    ("/api/cancel_deduct/pending", "GET", "api_cancel_deduct_pending"),
    ("/api/config", "GET", "api_get_config"),
    ("/api/config", "PUT", "api_put_config"),
    ("/api/config/export", "GET", "api_config_export"),
    ("/api/config/import", "POST", "api_config_import"),
    ("/api/create_filament", "POST", "api_create_filament"),
    ("/api/create_inventory_wizard", "POST", "api_create_inventory_wizard"),
    ("/api/dashboard_pulse", "GET,POST", "api_dashboard_pulse"),
    ("/api/dryer_box/<loc_id>/bindings", "GET", "api_dryer_box_bindings_get"),
    ("/api/dryer_box/<loc_id>/bindings", "PUT", "api_dryer_box_bindings_put"),
    ("/api/dryer_box/<loc_id>/bindings/<slot>", "PUT", "api_single_slot_binding_put"),
    ("/api/dryer_box/<loc_id>/slot_order", "GET", "api_dryer_box_slot_order_get"),
    ("/api/dryer_box/<loc_id>/slot_order", "PUT", "api_dryer_box_slot_order_put"),
    ("/api/dryer_boxes/slots", "GET", "api_all_dryer_box_slots"),
    ("/api/edit_spool_wizard", "POST", "api_edit_spool_wizard"),
    ("/api/external/fields", "GET", "api_external_fields"),
    ("/api/external/fields/add_choice", "POST", "api_external_fields_add_choice"),
    ("/api/external/search", "GET", "api_external_search"),
    ("/api/external/vendors", "GET", "api_external_vendors"),
    ("/api/filament/<fid>/flag_spool_labels", "POST", "api_flag_spool_labels"),
    ("/api/filament/<int:fid>", "DELETE", "api_delete_filament"),
    ("/api/filament/<int:src_fid>/merge_into/<int:dst_fid>", "POST", "api_merge_filament"),
    ("/api/filament_attributes/add_choice", "POST", "api_filament_attributes_add_choice"),
    ("/api/filament_attributes/bulk_set", "POST", "api_filament_attributes_bulk_set"),
    ("/api/filament_attributes/remove_choice", "POST", "api_filament_attributes_remove_choice"),
    ("/api/filament_attributes/report", "GET", "api_filament_attributes_report"),
    ("/api/filament_attributes/sweep_unused", "POST", "api_filament_attributes_sweep_unused"),
    ("/api/filament_details", "GET", "api_filament_details"),
    ("/api/filaments", "GET", "api_filaments"),
    ("/api/filaments/<int:filament_id>", "GET", "api_get_filament"),
    ("/api/get_contents", "GET", "api_get_contents_route"),
    ("/api/get_multi_spool_filaments", "GET", "api_get_multi_spool_filaments"),
    ("/api/identify_scan", "POST", "api_identify_scan"),
    ("/api/locations", "DELETE", "api_delete_location"),
    ("/api/locations", "GET", "api_get_locations"),
    ("/api/locations", "POST", "api_save_location"),
    ("/api/log_event", "POST", "api_log_event"),
    ("/api/logs", "GET", "api_get_logs_route"),
    ("/api/machine/<path:printer_name>/toolhead_slots", "GET", "api_machine_toolhead_slots"),
    ("/api/manage_contents", "POST", "api_manage_contents"),
    ("/api/materials", "GET", "api_materials"),
    ("/api/print_batch_csv", "POST", "api_print_batch_csv"),
    ("/api/print_label", "POST", "api_print_label"),
    ("/api/print_location_label", "POST", "api_print_location_label"),
    ("/api/print_queue/mark_printed", "POST", "api_print_queue_mark_printed"),
    ("/api/print_queue/pending", "GET", "api_print_queue_pending"),
    ("/api/print_queue/set_flag", "POST", "api_print_queue_set_flag"),
    ("/api/printer_creds", "PUT", "api_put_printer_creds"),
    ("/api/printer_map", "GET", "api_printer_map"),
    ("/api/printer_map", "PUT", "api_put_printer_map"),
    ("/api/printer_state/<path:toolhead_id>", "GET", "api_printer_state"),
    ("/api/quickswap", "POST", "api_quickswap"),
    ("/api/quickswap/return", "POST", "api_quickswap_return"),
    ("/api/search", "GET", "api_search_inventory"),
    ("/api/smart_move", "POST", "api_smart_move"),
    ("/api/spool/<int:sid>", "DELETE", "api_delete_spool"),
    ("/api/spool/prusament_apply_weights", "POST", "api_prusament_apply_weights"),
    ("/api/spool/update", "POST", "api_spool_update"),
    ("/api/spool_details", "GET", "api_spool_details"),
    ("/api/spoolman/restore_field_order", "POST", "api_spoolman_restore_field_order"),
    ("/api/spools/<int:spool_id>", "GET", "api_get_spool"),
    ("/api/spools/refresh", "POST", "api_spools_refresh"),
    ("/api/spools_by_filament", "GET", "api_get_spools_by_filament"),
    ("/api/state/buffer", "GET,POST", "api_state_buffer"),
    ("/api/state/queue", "GET,POST", "api_state_queue"),
    ("/api/undo", "POST", "api_undo"),
    ("/api/update_filament", "POST", "api_update_filament"),
    ("/api/vendors", "GET", "api_vendors"),
    ("/api/vendors", "POST", "api_create_vendor"),
    ("/api/vendors/<int:vid>", "PATCH", "api_update_vendor"),
    ("/static/<path:filename>", "GET", "static"),
]


def _current_route_table():
    return sorted(
        (
            str(rule.rule),
            ",".join(sorted(m for m in rule.methods if m not in ("HEAD", "OPTIONS"))),
            rule.endpoint.split(".")[-1],
        )
        for rule in app_module.app.url_map.iter_rules()
    )


def test_route_table_matches_pinned_snapshot():
    actual = _current_route_table()
    expected = sorted(EXPECTED_ROUTES)
    missing = [r for r in expected if r not in actual]
    added = [r for r in actual if r not in expected]
    assert actual == expected, (
        f"Route table drifted from the pinned snapshot.\n"
        f"MISSING (dropped by a move?): {missing}\n"
        f"ADDED (update the pin if intentional): {added}"
    )


def test_every_handler_reachable_via_app_module():
    """Every route's handler must stay importable as app.<name>.

    This is the compatibility-shim contract for the L316 carve: tests and
    callers monkeypatch/call handlers through the `app` module namespace,
    so every moved symbol must be re-exported. `static` is Flask-internal.
    """
    for rule in app_module.app.url_map.iter_rules():
        name = rule.endpoint.split(".")[-1]
        if name == "static":
            continue
        assert hasattr(app_module, name), (
            f"app.{name} not reachable — moved without a compatibility re-export?"
        )
        view = app_module.app.view_functions[rule.endpoint]
        assert getattr(app_module, name) is view, (
            f"app.{name} is not the registered view function — a re-export "
            f"points at the wrong callable (stale copy / wrapper / shadowed name)"
        )

"""Locations + record-lifecycle routes (L316 step 4).

Moved verbatim from app.py: the /api/locations GET synthesizer (virtual
rooms, transitive occupancy rollup, nested tree payload), location save and
delete (incl. the toolhead-delete cascade route layer), the destructive
spool/filament deletes, filament merge, undo, get_contents, and the
spool/filament details reads. Route contracts pinned by
tests/test_l316_charact_record_deletes.py.

Preserved quirks (do not 'fix' in a move — see the carve plan):
- api_get_locations' bare except-pass around the Spoolman occupancy probe
  (Spoolman down -> counts read zero, page still renders).
- api_delete_location relies on logic.perform_toolhead_delete_cascade
  MUTATING the passed-in list in place before the single save.
- api_get_locations / api_merge_filament call Spoolman via the module-level
  requests import directly (tests patch 'app.requests.get', which mutates
  the shared requests module — keep the bare-module call style).

Python 3.9 runtime (the container image) — keep syntax 3.9-safe.
"""
from flask import request, jsonify  # type: ignore
import requests  # type: ignore

import state  # type: ignore
import config_loader  # type: ignore
import locations_db  # type: ignore
import spoolman_api  # type: ignore
import logic  # type: ignore

from app_core import app

# --- EXISTING ROUTES ---

@app.route('/api/locations', methods=['GET'])
def api_get_locations():
    try:
        local_rows = locations_db.load_locations_list()
    except locations_db.LocationsCorruptError as e:
        # Surface the corruption directly instead of falling back to an
        # empty list — silent fallback masks the failure as a UI-wide
        # "Names/Types/Grouping all gone" symptom.
        return jsonify({
            "error": "locations_corrupt",
            "path": str(e.path),
            "line": e.decode_error.lineno,
            "col": e.decode_error.colno,
            "msg": e.decode_error.msg,
        }), 500
    local_map = {str(row['LocationID']).upper(): row for row in local_rows}
    
    # 1. Fetch native Spoolman Locations
    sm_locations = spoolman_api.get_all_locations()
    for sm_loc in sm_locations:
        if not sm_loc or not isinstance(sm_loc, str): continue
        loc_name = sm_loc.strip()
        loc_id_upper = loc_name.upper()
        if loc_id_upper == "UNASSIGNED": continue # Prevent duplicate from legacy strings
        if loc_id_upper and loc_id_upper not in local_map:
            # Create a virtual entry for Spoolman native locations
            local_map[loc_id_upper] = {
                "LocationID": loc_name,
                "Name": loc_name,
                "Type": "Spoolman Native",
                "Max Spools": 0,
                # L271 Phase 2.5: carry parent_id like every other row so the
                # frontend tree reads it uniformly. Derived from the prefix
                # (uppercased); None for a dash-free native name. A Spoolman
                # name can be mixed-case, so the tree grouping in inv_core.js
                # compares parent_id vs LocationID case-insensitively.
                "parent_id": locations_db.derive_parent_id_from_prefix(loc_name),
            }
            
    csv_rows = list(local_map.values())
    occupancy_map: dict[str, int] = {}
    # L271 Phase 3.5 (review fix #2): per-spool (id, loc, ghost) so the ancestor
    # rollup can count DISTINCT physical spools — a deployed spool sits in
    # occupancy_map twice (toolhead loc + ghost home-box) and, now that a printer
    # nests under its home box's room, both rolled into the same room and
    # double-counted its Total. Dedup by spool id fixes that.
    spool_entries: list = []  # (sid, loc_or_'', ghost_or_'')
    unassigned_count: int = 0
    unknown_count: int = 0  # 18.1 — spools sitting at the virtual UNKNOWN bucket

    sm_url, _ = config_loader.get_api_urls()
    try:
        resp = requests.get(f"{sm_url}/api/v1/spool", timeout=5)
        if resp.ok:
            for s in resp.json():
                if not isinstance(s, dict): continue
                loc = str(s.get('location', '')).upper().strip()
                if loc == 'UNASSIGNED': loc = "" # Coerce to true blank
                extra = s.get('extra')
                if not isinstance(extra, dict): extra = {}

                if loc == 'UNKNOWN':
                    unknown_count += 1
                    # Don't add UNKNOWN to occupancy_map — it's a virtual
                    # bucket with no on-disk row to attach to.
                elif loc:
                    if loc not in occupancy_map:
                        occupancy_map[loc] = 1
                    else:
                        occupancy_map[loc] += 1
                else:
                    unassigned_count += 1 # type: ignore # pyre-ignore
                
                # [ALEX FIX] Ghost Occupancy Count
                # Ensure deployed items still count towards their home box's total
                p_source = str(extra.get('physical_source', '')).upper().strip().replace('"', '')
                if p_source and p_source != loc:
                    occupancy_map[p_source] = occupancy_map.get(p_source, 0) + 1

                # L271 Phase 3.5 (review fix #2): record this spool for the
                # distinct-count ancestor rollup. loc is '' for unassigned and
                # 'UNKNOWN' for the lost bucket — neither rolls into a room.
                spool_entries.append((
                    s.get('id'),
                    loc if (loc and loc != 'UNKNOWN') else '',
                    p_source,
                ))

    except: pass

    # [ALEX FIX] Support Room logic correctly by adding grouped floating data
    csv_rows = list(local_map.values())

    # 1. First Pass: TRANSITIVE subtree occupancy (L271 Phase 3.5).
    # parent_id now stores each row's IMMEDIATE parent, so a single-level rollup
    # would drop a spool sitting in a cart-ROW from its room's total (the row
    # rolls into the cart, not the room). For each spool, add its id to every
    # ancestor of BOTH its location and its ghost home-box, then a parent's
    # Total is the count of DISTINCT spool ids in its subtree. Deduping by id is
    # essential: a deployed spool appears at its toolhead loc AND its ghost
    # home-box, which (with the printer nested under the home-box's room) both
    # resolve into the same room — summing would double-count it (review fix #2).
    # `ancestors_of` stops at the PM/PJ/TST pseudo-prefixes so they never
    # aggregate into a room. Leaf display + the "floating" figure still use
    # occupancy_map (loc + ghost at the exact row) so a box keeps showing its
    # deployed ghosts.
    parent_map = locations_db.build_parent_map(csv_rows)

    # Immediate-child counts so a row can be classified parent-vs-leaf for the
    # occupancy display (a real parent shows a subtree Total; a leaf shows
    # curr/max). Pseudo-prefix parents never count as real parents.
    children_count: dict[str, int] = {}
    for _lid, _p in parent_map.items():
        if _p and _p not in locations_db.PSEUDO_ROOM_PREFIXES:
            children_count[_p] = children_count.get(_p, 0) + 1

    subtree_ids: dict[str, set] = {}   # ancestor -> set of distinct spool ids
    ancestor_hit: set[str] = set()     # non-row prefixes that need a Virtual Room
    for sid, loc, ghost in spool_entries:
        touched: set[str] = set()
        for base in (loc, ghost):
            if not base:
                continue
            ancs = list(locations_db.ancestors_of(base, parent_map))
            touched.add(base)
            touched.update(ancs)
            for anc in ancs:
                ancestor_hit.add(anc)
            if not ancs:
                # Top-level / unparented occupancy — its own "room" candidate
                # (mirrors the pre-3.5 seed of a virtual room for a dash-free
                # orphan). A pseudo-prefixed base (PM/PJ/TST box) yields no
                # ancestors and is itself a real row, so synthesis skips it.
                ancestor_hit.add(base)
        for t in touched:
            subtree_ids.setdefault(t, set()).add(sid)
    # subtree_occ = distinct spool count per row; direct/floating stays the
    # loc+ghost count at the exact row (occupancy_map).
    subtree_occ = {k: len(v) for k, v in subtree_ids.items()}
    direct_occ = occupancy_map

    # 2. Inject Virtual Rooms for occupancy-only prefixes.
    #
    # L271 Phase 3: printers are now first-class on-disk Type:"Printer" rows
    # (written by locations_db.migrate_printers_to_rows_if_needed at startup),
    # so this no longer synthesizes them — the printer-prefix seed and the
    # is_printer / printer_name detection were RETIRED. It now only conjures a
    # Virtual Room for a prefix that has spool occupancy today but no on-disk
    # parent row of its own. Any parent that already has a real on-disk row —
    # the first-class Printer rows included — is skipped by the existing-row
    # check below, so they flow through from disk untouched. `ancestor_hit` is
    # the set of prefixes that received rollup (plus dash-free orphan spool
    # locations) — the Phase 3.5 transitive equivalent of the old
    # room_occupancy.keys() candidate set.
    for parent in set(ancestor_hit):
        # Skip a parent that already has a real on-disk row. A blank-Type
        # placeholder (legacy/manual state that would otherwise strand the row
        # in "Unassigned" rendering) is promoted in place instead.
        existing = local_map.get(parent)
        existing_type_blank = bool(existing) and not str(existing.get('Type', '')).strip()
        if existing and not existing_type_blank:
            continue

        synthetic_row = {
            "LocationID": parent,
            "Name": f"{parent} (Room)",
            "Type": "Virtual Room",
            "Max Spools": 0,
            "OccupancyRaw": 0,
            # L271 Phase 2.5: expose parent_id so the frontend tree reads it
            # uniformly. `parent` is a dash-free top-level prefix → null.
            "parent_id": None,
        }

        if existing_type_blank:
            # Replace the broken blank-Type row in-place rather than appending
            # a duplicate (would trip duplicate-LocationID guards downstream).
            for i, r in enumerate(csv_rows):
                if str(r.get('LocationID', '')).upper() == parent:
                    csv_rows[i] = {**r, **synthetic_row}
                    break
        else:
            csv_rows.append(synthetic_row)

    final_list = []
    # [ALEX FIX] Inject Virtual Unassigned Row
    final_list.append({
        "LocationID": "Unassigned",
        "Name": "Workbench / Unsorted",
        "Type": "Virtual",
        "Occupancy": f"{unassigned_count} items",
        "Max Spools": 0,
        "parent_id": None,  # L271 Phase 2.5 — virtual top-level row
    })

    for row in csv_rows:
        lid = str(row.get('LocationID', '')).upper()
        if lid == "UNASSIGNED": continue # Skip if somehow in CSV
        # 18.1 — Skip any on-disk UNKNOWN row too. Derek experimented with
        # creating one manually before this feature landed; an on-disk
        # row with "Spoolman Native" Type would shadow the virtual yellow-
        # band row injected at the bottom. The virtual injection is the
        # single source of truth now. Stale on-disk rows can be deleted
        # via the Location Manager UI without breaking anything.
        if lid == "UNKNOWN": continue
        
        max_s = row.get('Max Spools', '')
        try:
            max_val = int(max_s) if max_s else 0
        except (ValueError, TypeError):
            max_val = 0
            
        direct_cnt = direct_occ.get(lid, 0)
        sub = subtree_occ.get(lid, direct_cnt)

        # L271 Phase 3.5: a row that is a PARENT in the tree (has child rows, or
        # is a synthesized Virtual Room) shows its TRANSITIVE subtree total +
        # the count floating directly at it; a leaf shows curr/max. This
        # replaces the old `"-" not in lid` dash-free gate, so nested parents
        # (carts, printers) now show a real subtree total instead of looking
        # empty when collapsed, and a room's total includes everything beneath
        # it (incl. a nested printer's toolhead spools).
        is_parent = bool(children_count.get(lid)) or str(row.get('Type', '')).strip() == 'Virtual Room'
        if is_parent:
            row['OccupancyRaw'] = sub
            if direct_cnt > 0:
                row['Occupancy'] = f"{sub} Total ({direct_cnt} floating)"
            else:
                row['Occupancy'] = f"{sub} Total"
        else:
            row['OccupancyRaw'] = direct_cnt
            if max_val > 0: row['Occupancy'] = f"{direct_cnt}/{max_val}"
            else: row['Occupancy'] = f"{direct_cnt} items"

        final_list.append(row)

    # 18.1 — virtual UNKNOWN bucket, pinned to the BOTTOM of the list
    # (Derek's pick: bottom over top because spools land here when they're
    # physically misplaced; finding them is the goal, so they shouldn't
    # crowd the top of the manager). Distinct from Unassigned (which is
    # "deliberately on the workbench, awaiting a destination"); Unknown
    # is "we don't know where it actually is — it's not at the location
    # its tag claims." Riff on Unassigned visual treatment but yellow
    # to flag as a caution state. The frontend renders the badge.
    final_list.append({
        "LocationID": "UNKNOWN",
        "Name": "❓ Unknown (Physically Lost)",
        "Type": "Unknown",
        "Occupancy": f"{unknown_count} items",
        "Max Spools": 0,
        "parent_id": None,  # L271 Phase 2.5 — virtual top-level row
    })
    # FilaBridge Phase-2: per-printer credentials (ip + api_key) live on the
    # Printer rows but must NEVER reach the browser — locations.json has no
    # secret-sentinel machinery the way config.json does. Strip them from this
    # GET. The printer-map Settings editor reads creds through its own masked
    # endpoint instead.
    for _row in final_list:
        if isinstance(_row, dict):
            _row.pop(locations_db.PRINTER_CREDS_KEY, None)
    return jsonify(final_list)

@app.route('/api/locations', methods=['POST'])
def api_save_location():
    data = request.json
    old_id = data.get('old_id')
    new_entry = data.get('new_data')
    current_list = locations_db.load_locations_list()
    old_row = None
    if old_id:
        old_row = next((r for r in current_list if r.get('LocationID') == old_id), None)
        current_list = [row for row in current_list if row['LocationID'] != old_id]

    # L271 Phase 5 (review #7): reject a create/rename onto an id that already
    # exists — current_list has the row's own (old) id removed, so any remaining
    # match is a genuine duplicate (the hard invariant test_no_duplicate_LocationIDs
    # guards). Editable #edit-id + the new Parent selector make rename reachable.
    if isinstance(new_entry, dict):
        _new_lid_dup = str(new_entry.get('LocationID', '')).strip().upper()
        if _new_lid_dup and any(str(r.get('LocationID', '')).strip().upper() == _new_lid_dup
                                for r in current_list if isinstance(r, dict)):
            return jsonify({"success": False,
                            "error": f"LocationID '{new_entry.get('LocationID')}' already exists."}), 400

    # L271 Phase 5: when the Edit modal sends an EXPLICIT parent_id (the new
    # Parent selector), validate it before persisting — it must reference an
    # existing row and must not create a cycle (self, or a descendant of this
    # row). An empty/None explicit value means "top level" and is allowed. The
    # auto-derive path (parent_id absent) is already safe and is untouched.
    # current_list already has the row's own (old) id filtered out above.
    if isinstance(new_entry, dict) and 'parent_id' in new_entry:
        _pid = new_entry.get('parent_id')
        _pid_norm = None if _pid in (None, '') else str(_pid).strip().upper()
        if _pid_norm is not None:
            _new_lid = str(new_entry.get('LocationID', '')).strip().upper()
            _existing = {str(r.get('LocationID', '')).strip().upper()
                         for r in current_list if isinstance(r, dict)}
            if _pid_norm == _new_lid:
                return jsonify({"success": False, "error": "A location can't be its own parent."}), 400
            # A valid parent is an on-disk row OR a known pseudo-room prefix
            # (PM/PJ/TST → virtual rooms with no real row), matching the
            # dangling-FK contract in test_locations_json_integrity.
            if _pid_norm not in _existing and _pid_norm not in locations_db.PSEUDO_ROOM_PREFIXES:
                return jsonify({"success": False, "error": f"Parent '{_pid}' is not an existing location."}), 400
            # strict=True so a DANGLING dashed parent_id elsewhere can't prefix-
            # derive a phantom ancestor and spuriously reject a valid move (review #5).
            _pmap = locations_db.build_parent_map(current_list + [new_entry])
            if locations_db.is_descendant(_pid_norm, _new_lid, parent_map=_pmap, strict=True):
                return jsonify({"success": False,
                                "error": "Can't parent a location under its own descendant (would create a cycle)."}), 400
        # Canonicalize the stored value (review #6): None for top-level, else the
        # upper-cased id — consistent with how every other write path stores it.
        new_entry['parent_id'] = _pid_norm

    if old_id:
        state.add_log_entry(f"📝 Updated: {new_entry['LocationID']}")
    else:
        state.add_log_entry(f"✨ Created: {new_entry['LocationID']}")
    # L271 Phase 3.5 (review fix #4): stamp parent_id at write time, but PRESERVE
    # the existing parent_id on an IN-PLACE edit (same LocationID). The edit
    # modal only sends LocationID/Name/Type/Max Spools — never parent_id — so a
    # naive recompute would un-nest a Printer (immediate_parent_for('XL') → None,
    # there's no dashed ancestor) and silently revert an operator-set parent_id
    # on every field edit. Only CREATE or RENAME (re)derives the immediate parent
    # from the new LocationID; a Printer's room is then (re)resolved by the
    # startup migration. Respect an explicitly-supplied parent_id.
    if isinstance(new_entry, dict) and 'parent_id' not in new_entry:
        same_id = (old_row is not None
                   and str(old_row.get('LocationID', '')) == str(new_entry.get('LocationID', ''))
                   and 'parent_id' in old_row)
        if same_id:
            new_entry['parent_id'] = old_row.get('parent_id')
        else:
            new_entry['parent_id'] = locations_db.immediate_parent_for(
                new_entry.get('LocationID'), current_list)
    # FilaBridge Phase-2: printer_creds (ip/api_key) live on the Printer row but
    # are REDACTED out of GET /api/locations, so the Location-Manager edit modal
    # never receives them and would silently DROP them on a Name/Type edit (this
    # POST replaces the whole row). Carry them forward from the old row (same
    # printer, possibly renamed) unless the caller explicitly sent a creds object.
    # Mirrors the parent_id-preserve above; the printer-map editor is the only
    # surface that writes creds intentionally.
    if (isinstance(new_entry, dict) and old_row is not None
            and locations_db.PRINTER_CREDS_KEY not in new_entry):
        _carry_creds = old_row.get(locations_db.PRINTER_CREDS_KEY)
        if _carry_creds:
            new_entry[locations_db.PRINTER_CREDS_KEY] = _carry_creds
    current_list.append(new_entry)
    current_list.sort(key=lambda x: str(x.get('LocationID', '')))
    locations_db.save_locations_list(current_list)
    return jsonify({"success": True})

@app.route('/api/locations', methods=['DELETE'])
def api_delete_location():
    target = request.args.get('id', '').strip()
    if not target: return jsonify({"success": False})
    confirm_active = request.args.get('confirm_active_print', '').strip().lower() in ('1', 'true', 'yes')

    current = locations_db.load_locations_list()
    target_row = next((r for r in current if str(r.get('LocationID', '')).strip() == target), None)
    is_toolhead = bool(target_row) and str(target_row.get('Type', '')).strip() in locations_db.TOOLHEAD_TYPES

    if is_toolhead:
        # Group 20.3: a toolhead delete needs the FULL cascade — direct spools →
        # UNASSIGNED, ghost spools un-deployed (NOT yanked from their box),
        # filabridge unmapped, dryer-box slot_targets feeding it dropped, and the
        # toolhead pruned from its Printer row's toolheads[]. The cascade mutates
        # `current` for the locations.json-side cleanup; we then remove the row +
        # save ONCE. An active print on the toolhead blocks with requires_confirm.
        result = logic.perform_toolhead_delete_cascade(target, current, confirm_active_print=confirm_active)
        if isinstance(result, dict) and result.get("status") == "requires_confirm":
            return jsonify({"success": False, **result}), 409
        new_list = [row for row in current if str(row.get('LocationID', '')).strip() != target]
        locations_db.save_locations_list(new_list)
        bits = []
        if result["unassigned"]:
            bits.append(f"{len(result['unassigned'])} spool(s) → UNASSIGNED")
        if result["undeployed"]:
            bits.append(f"{len(result['undeployed'])} un-deployed")
        if result["slot_bindings_cleared"]:
            bits.append(f"{len(result['slot_bindings_cleared'])} slot binding(s) cleared")
        if result["toolhead_pruned_from"]:
            bits.append(f"pruned from {', '.join(str(p) for p in result['toolhead_pruned_from'])}")
        detail = "; ".join(bits) if bits else "nothing referenced it"
        state.add_log_entry(f"🗑️ Deleted toolhead {target} — {detail}", "WARNING")
        if result["errors"]:
            state.add_log_entry(
                f"⚠️ Toolhead-delete cascade for {target} had errors: {'; '.join(result['errors'])}",
                "ERROR", "ff4444")
        return jsonify({"success": True, "cascade": result})

    # Non-toolhead delete (Box / Room / Cart / Shelf): keep the existing best-
    # effort cascade-unassign of direct contents. Box/room semantics differ from
    # toolheads and are out of 20.3 scope.
    try:
        contents = spoolman_api.get_spools_at_location(target)
        for sid in contents:
            # Best-effort cascade unassign on location delete. Don't raise
            # on individual failures — the location is going away regardless,
            # but log so a user can see partial completion.
            if not spoolman_api.update_spool(sid, {"location": ""}):
                err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
                state.logger.warning(
                    f"location delete: failed to unassign Spool #{sid} from {target}: {err}"
                )
    except Exception as e:
        state.logger.warning(f"location delete: cascade unassign failed: {e}")

    new_list = [row for row in current if str(row.get('LocationID', '')).strip() != target]
    locations_db.save_locations_list(new_list)
    state.add_log_entry(f"🗑️ Deleted: {target}", "WARNING")
    return jsonify({"success": True})


@app.route('/api/spool/<int:sid>', methods=['DELETE'])
def api_delete_spool(sid):
    """Hard-delete a spool from Spoolman. Triggered from the buried Delete
    action in the spool details modal (see inv_details.js). The frontend
    is responsible for the double-confirm UX (type-the-id pattern); this
    endpoint trusts the request and just executes the delete."""
    snapshot = spoolman_api.get_spool(sid) or {}
    label = f"#{sid}"
    fil = snapshot.get('filament') or {}
    if fil.get('name'):
        label = f"#{sid} ({fil.get('name')})"
    if not spoolman_api.delete_spool(sid):
        err = spoolman_api.LAST_SPOOLMAN_ERROR or "Spoolman rejected the delete"
        state.add_log_entry(f"❌ Failed to delete Spool {label}: {err}", "ERROR", "ff4444")
        return jsonify({"success": False, "error": err}), 502
    state.add_log_entry(f"🗑️ Deleted Spool {label}", "WARNING", "ff8800")
    return jsonify({"success": True, "deleted_spool_id": sid})


@app.route('/api/filament/<int:fid>', methods=['DELETE'])
def api_delete_filament(fid):
    """Cascade-delete a filament: removes every child spool first, then
    deletes the filament itself. Returns a per-spool error list so the
    frontend can surface partial failures.

    Spoolman refuses to delete a filament that still has child spools, so
    cascade is the only correct path from the UI side. Triggered from the
    buried Delete action in the filament details modal — the frontend
    enforces the double-confirm and the "type CONFIRM" cascade prompt."""
    snapshot = spoolman_api.get_filament(fid) or {}
    fil_label = f"#{fid}"
    if snapshot.get('name'):
        fil_label = f"#{fid} ({snapshot.get('name')})"

    children = spoolman_api.get_spools_for_filament(fid)
    deleted_spool_ids = []
    spool_errors = []
    for s in children:
        sid = s.get('id')
        if sid is None:
            continue
        if spoolman_api.delete_spool(sid):
            deleted_spool_ids.append(sid)
        else:
            err = spoolman_api.LAST_SPOOLMAN_ERROR or "Spoolman rejected the delete"
            state.add_log_entry(f"❌ Cascade delete: failed to delete Spool #{sid} (parent Filament {fil_label}): {err}",
                                "ERROR", "ff4444")
            spool_errors.append({"spool_id": sid, "error": err})

    if spool_errors:
        # Don't try to delete the filament if any child spool failed —
        # Spoolman will reject it anyway, and partial state is recoverable.
        return jsonify({
            "success": False,
            "error": "Some child spools could not be deleted; filament left in place.",
            "deleted_spool_ids": deleted_spool_ids,
            "spool_errors": spool_errors,
        }), 502

    if not spoolman_api.delete_filament(fid):
        err = spoolman_api.LAST_SPOOLMAN_ERROR or "Spoolman rejected the delete"
        state.add_log_entry(f"❌ Failed to delete Filament {fil_label}: {err}", "ERROR", "ff4444")
        return jsonify({
            "success": False,
            "error": err,
            "deleted_spool_ids": deleted_spool_ids,
        }), 502

    if deleted_spool_ids:
        state.add_log_entry(
            f"🗑️ Deleted Filament {fil_label} (cascade: {len(deleted_spool_ids)} child spool(s))",
            "WARNING", "ff8800",
        )
    else:
        state.add_log_entry(f"🗑️ Deleted Filament {fil_label}", "WARNING", "ff8800")
    return jsonify({
        "success": True,
        "deleted_filament_id": fid,
        "deleted_spool_ids": deleted_spool_ids,
    })


@app.route('/api/filament/<int:src_fid>/merge_into/<int:dst_fid>', methods=['POST'])
def api_merge_filament(src_fid, dst_fid):
    """Merge `src_fid` into `dst_fid`: re-parent every spool from source to
    target, then delete the now-orphan source filament. Used by the
    "Merge into another filament…" action on the Filament Details modal
    to clean up duplicates that pre-date the tier-1 product-id matcher
    (Group 11.2). Atomic-ish: if any spool re-parent fails, we abort
    before deleting the source so partial state stays recoverable.
    """
    if src_fid == dst_fid:
        return jsonify({
            "success": False,
            "error": "Source and target filaments must differ.",
        }), 400

    src = spoolman_api.get_filament(src_fid)
    if not src:
        return jsonify({
            "success": False,
            "error": f"Source filament #{src_fid} not found.",
        }), 404
    dst = spoolman_api.get_filament(dst_fid)
    if not dst:
        return jsonify({
            "success": False,
            "error": f"Target filament #{dst_fid} not found.",
        }), 404

    src_label = f"#{src_fid}" + (f" ({src.get('name')})" if src.get('name') else "")
    dst_label = f"#{dst_fid}" + (f" ({dst.get('name')})" if dst.get('name') else "")

    # Include archived — they're owned by the source filament too and have to
    # follow it to the target so we can safely delete the source.
    sm_url, _ = config_loader.get_api_urls()
    try:
        r = requests.get(
            f"{sm_url}/api/v1/spool?filament_id={src_fid}&allow_archived=true",
            timeout=5,
        )
        children = r.json() if r.ok else []
    except Exception as e:
        state.logger.error(f"Merge: failed to enumerate spools for filament {src_fid}: {e}")
        return jsonify({
            "success": False,
            "error": f"Could not list source spools: {e}",
        }), 502

    reparented_spool_ids = []
    spool_errors = []
    for s in children:
        sid = s.get('id')
        if sid is None:
            continue
        try:
            spoolman_api.update_spool_or_raise(sid, {"filament_id": dst_fid})
            reparented_spool_ids.append(sid)
        except spoolman_api.SpoolmanRejection as e:
            err = str(e) or "Spoolman rejected the re-parent"
            state.add_log_entry(
                f"❌ Merge {src_label} → {dst_label}: failed to re-parent Spool #{sid}: {err}",
                "ERROR", "ff4444",
            )
            spool_errors.append({"spool_id": sid, "error": err})

    if spool_errors:
        # Abort — leave source intact so the user can retry / inspect.
        return jsonify({
            "success": False,
            "error": "Some spools could not be re-parented; source filament left in place.",
            "reparented_spool_ids": reparented_spool_ids,
            "spool_errors": spool_errors,
        }), 502

    if not spoolman_api.delete_filament(src_fid):
        err = spoolman_api.LAST_SPOOLMAN_ERROR or "Spoolman rejected the delete"
        state.add_log_entry(
            f"❌ Merge {src_label} → {dst_label}: spools re-parented but source delete failed: {err}",
            "ERROR", "ff4444",
        )
        return jsonify({
            "success": False,
            "error": f"Spools re-parented, but source filament delete failed: {err}",
            "reparented_spool_ids": reparented_spool_ids,
        }), 502

    n = len(reparented_spool_ids)
    state.add_log_entry(
        f"🔗 Merged Filament {src_label} → {dst_label} ({n} spool{'' if n == 1 else 's'} re-parented; source deleted)",
        "INFO", "00ccff",
    )
    return jsonify({
        "success": True,
        "source_filament_id": src_fid,
        "target_filament_id": dst_fid,
        "reparented_spool_ids": reparented_spool_ids,
    })


@app.route('/api/undo', methods=['POST'])
def api_undo(): return jsonify(logic.perform_undo())

@app.route('/api/get_contents', methods=['GET'])
def api_get_contents_route():
    loc = request.args.get('id', '').strip().upper()
    return jsonify(spoolman_api.get_spools_at_location_detailed(loc))

@app.route('/api/spool_details', methods=['GET'])
def api_spool_details():
    sid = request.args.get('id')
    if not sid: return jsonify({})
    return jsonify(spoolman_api.get_spool(sid))

@app.route('/api/filament_details', methods=['GET'])
def api_filament_details():
    fid = request.args.get('id')
    if not fid: return jsonify({})
    return jsonify(spoolman_api.get_filament(fid))


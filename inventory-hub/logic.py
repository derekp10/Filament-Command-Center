import re
import threading
import typing
import urllib.parse
import requests
import state
import config_loader
import spoolman_api
import locations_db


def _active_print_info_for_location(location_str, printer_map=None):
    """If `location_str` is a toolhead whose printer is currently PRINTING/
    PAUSED/BUSY, return {'printer_name', 'state', 'toolhead'} so a warning
    can be surfaced. Returns None otherwise (not a toolhead, printer idle,
    or probe failed — fail open, never block moves).

    Used as a shared backend pre-flight so every spool-move surface
    (manage_contents add/remove, smart_move, identify_scan assignment,
    quickswap) inherits the same protection without each endpoint
    re-implementing the lookup.
    """
    if not location_str:
        return None
    loc_up = str(location_str).strip().strip('"').upper()
    if printer_map is None:
        printer_map = locations_db.get_active_printer_map()  # L271 P4 step 2: Printer-row toolheads[] (dual-read)
    info = printer_map.get(loc_up)
    if not info:
        return None
    printer_name = info.get('printer_name')
    if not printer_name:
        return None
    try:
        # Deferred import: keeps logic.py usable in unit tests that don't
        # have prusalink_api's `requests` import graph fully satisfied.
        import prusalink_api
        _, fb_url = config_loader.get_api_urls()
        state_dict = prusalink_api.get_printer_state(fb_url, printer_name)
    except Exception:
        return None
    if not state_dict or not state_dict.get('is_active'):
        return None
    return {
        'toolhead': loc_up,
        'printer_name': printer_name,
        'state': state_dict.get('state', 'ACTIVE'),
    }


def _toolhead_of(location_str, printer_map=None):
    """Resolve a location string to its (printer_name, toolhead_id) tuple.

    Returns None if the location is empty or not a registered toolhead.
    Used so callers can decide whether a filabridge unmap is needed
    before a move.
    """
    if not location_str:
        return None
    if printer_map is None:
        printer_map = locations_db.get_active_printer_map()  # L271 P4 step 2: Printer-row toolheads[] (dual-read)
    loc = str(location_str).strip().strip('"').upper()
    if loc in printer_map:
        p = printer_map[loc]
        return (p.get('printer_name'), p.get('position'))
    return None


def _find_box_slot_feeding_toolhead(toolhead_id, loc_list=None):
    """Reverse-lookup the dryer-box slot that feeds `toolhead_id` via
    `extra.slot_targets`. Returns (box_loc_id, slot_str) or (None, None).

    Used by `perform_smart_move`'s PRINTER MOVE branch (13.6 Part A) to
    synthesize a ghost binding when a spool is moved directly to a toolhead
    that has a reverse-binding back to a dryer-box slot. Without this, the
    box card never sees the spool and the user has to manually re-assign.

    Multiple boxes pointing the same toolhead is degenerate but tolerated:
    we return the first match in `locations.json` iteration order.
    """
    if not toolhead_id:
        return (None, None)
    if loc_list is None:
        loc_list = locations_db.load_locations_list()
    target_th = str(toolhead_id).strip().upper()
    for row in loc_list:
        if row.get('Type') != 'Dryer Box':
            continue
        slot_targets = (row.get('extra') or {}).get('slot_targets') or {}
        for slot, bound_th in slot_targets.items():
            if not bound_th:
                continue
            if str(bound_th).strip().upper() == target_th:
                return (row.get('LocationID'), str(slot))
    return (None, None)


def _spool_brand_color_suffix(sid):
    """Return a ' — Brand MAT (Color)' suffix for a spool, or '' if unavailable.

    Used by Activity Log entries (e.g. auto-deploy) so the line identifies the
    physical spool, not just its numeric ID. Never raises — a missing spool,
    network hiccup, or malformed payload collapses to an empty suffix.
    """
    try:
        snap = spoolman_api.get_spool(sid) or {}
        info = spoolman_api.format_spool_display(snap) or {}
        short = str(info.get("text_short", "")).strip()
        return f" — {short}" if short else ""
    except Exception:
        return ""


def _resolve_legacy_spool_lookup(legacy_id):
    """Item 3.6 — wrap `find_spools_by_legacy_id` so the scan path can
    surface the ambiguous case to the UI instead of silently picking the
    first candidate.

    Returns one of:
      * `None`                                          — no matching spool
      * `{'type': 'spool', 'id': N}`                    — exactly one match
      * `{'type': 'ambiguous', 'legacy_id': str,
          'candidates': [...]}`                         — 2+ matches; UI prompts

    Each candidate dict carries enough display data for a picker without
    forcing a second round-trip per spool: id, remaining_weight, location,
    archived, filament_id, plus a flat `display` string that mirrors
    `format_spool_display`'s text for selector readability.
    """
    spools = spoolman_api.find_spools_by_legacy_id(legacy_id)
    if not spools:
        return None
    if len(spools) == 1:
        return {'type': 'spool', 'id': spools[0]['id']}
    candidates = []
    for s in spools:
        info = {}
        try:
            info = spoolman_api.format_spool_display(s) or {}
        except Exception:
            info = {}
        fil = s.get('filament') or {}
        candidates.append({
            'id': s.get('id'),
            'remaining_weight': s.get('remaining_weight'),
            'location': s.get('location') or '',
            'archived': bool(s.get('archived')),
            'filament_id': fil.get('id'),
            'filament_name': fil.get('name') or '',
            'material': fil.get('material') or '',
            'vendor_name': (fil.get('vendor') or {}).get('name') or '',
            'color_hex': fil.get('color_hex') or '',
            'display': info.get('text') or info.get('text_short') or f"Spool #{s.get('id')}",
        })
    return {'type': 'ambiguous', 'legacy_id': str(legacy_id), 'candidates': candidates}


def resolve_scan(text):
    text = text.strip().strip('"').strip("'")
    decoded = urllib.parse.unquote(text)
    upper_text = text.upper()

    # 1. [ALEX FIX] PRIORITY: SLOT ASSIGNMENT (LOC:x:SLOT:y)
    # Must be checked FIRST. regex is non-greedy to capture the location ID correctly.
    slot_match = re.search(r'LOC:(.+?):SLOT:(\d+)', upper_text)
    if slot_match:
        return {
            'type': 'assignment', 
            'location': slot_match.group(1).strip(), 
            'slot': slot_match.group(2).strip()
        }

    # 2. COMMAND HANDLING
    if "CMD:" in upper_text:
        if "CMD:UNDO" in upper_text: return {'type': 'command', 'cmd': 'undo'}
        if "CMD:CLEAR" in upper_text: return {'type': 'command', 'cmd': 'clear'}
        if "CMD:EJECT" in upper_text: return {'type': 'command', 'cmd': 'eject'} 
        if "CMD:CONFIRM" in upper_text: return {'type': 'command', 'cmd': 'confirm'}
        if "CMD:EJECTALL" in upper_text: return {'type': 'command', 'cmd': 'ejectall'} 
        
        # NAV
        if "CMD:CYCLE" in upper_text: return {'type': 'command', 'cmd': 'next'}
        if "CMD:NEXT" in upper_text: return {'type': 'command', 'cmd': 'next'}
        if "CMD:PREV" in upper_text: return {'type': 'command', 'cmd': 'prev'}
        if "CMD:DONE" in upper_text: return {'type': 'command', 'cmd': 'done'}
        # 18.2 Part B — CMD:CANCEL is the safe-bail counterpart to CMD:DONE
        # for audit mode. DONE commits + auto-parks missing spools at UNKNOWN;
        # CANCEL closes the session without any moves. Required so the
        # AUDIT deck button toggle can map to CANCEL (no accidental
        # auto-parks) and the visual panel can surface both actions.
        if "CMD:CANCEL" in upper_text: return {'type': 'command', 'cmd': 'cancel'}
        
        # SLOT (Interactive)
        if "CMD:SLOT:" in upper_text:
            try:
                parts = upper_text.split(':')
                val = parts[-1].strip()
                if val.isdigit(): return {'type': 'command', 'cmd': 'slot', 'value': val}
            except: pass
        
        # AUDIT
        if "CMD:AUDIT" in upper_text: return {'type': 'command', 'cmd': 'audit'}
        
        return {'type': 'error', 'msg': 'Malformed Command'}

    # 3. [ALEX FIX] STANDARD LOCATION SCAN (LOC: Prefix)
    # This handles "LOC:BOX-01" or "LOC:PRINTER". 
    # It MUST run after the Slot check (so it doesn't steal slot codes) but BEFORE legacy checks.
    if upper_text.startswith("LOC:"):
        clean_loc = upper_text[4:].strip()
        if clean_loc:
             return {'type': 'location', 'id': clean_loc}
        return {'type': 'error', 'msg': 'Empty Location Code'}

    # 4. EXPLICIT LEGACY ID (Manual Override)
    if upper_text.startswith("LEGACY:") or upper_text.startswith("LEG:") or upper_text.startswith("OLD:"):
        clean_id = upper_text.split(":")[-1].strip()
        result = _resolve_legacy_spool_lookup(clean_id)
        if result is not None:
            return result
        # A legacy id can map to a FILAMENT that currently has no spools (e.g.
        # every spool used up + archived, or never created). Surface the
        # filament instead of dead-ending — mirrors the pure-number branch's
        # Priority-4 fallback (buglist 2026-06-02).
        fid = spoolman_api.find_filament_by_legacy_id(clean_id)
        if fid:
            return {'type': 'filament', 'id': fid}
        return {'type': 'error', 'msg': f'Legacy Spool ID {clean_id} not found'}

    # 5. DIRECT SPOOL ID
    if upper_text.startswith("ID:") or upper_text.startswith("SPL:"):
        prefix_len = 3 if upper_text.startswith("ID:") else 4
        clean_id = text[prefix_len:].strip()
        if clean_id.isdigit(): return {'type': 'spool', 'id': int(clean_id)}
        return {'type': 'error', 'msg': 'Invalid Spool ID Format'}

    # 5. FILAMENT DEFINITION ID
    if upper_text.startswith("FIL:"):
        clean_id = text[4:].strip()
        if clean_id.isdigit(): return {'type': 'filament', 'id': int(clean_id)}
        return {'type': 'error', 'msg': 'Invalid Filament ID Format'}

    # 5.5 — Prusament spool QR. The physical Prusament spool label encodes a
    # https://prusament.com/spool/<id>/<hash>/ URL. Recognize it BEFORE the
    # generic URL branch below (which would otherwise dead-end on "Unknown/
    # Invalid Link") so the scan pipeline can backfill temps onto the matching
    # existing filament or onboard a brand-new spool.
    #
    # The numeric <id> identifies the *product* (shared by every spool of that
    # product); the trailing <hash> identifies the *unique physical spool*.
    # Recognition stays keyed on the product <id> so a malformed or absent hash
    # never breaks the scan. The hash is captured best-effort as an optional,
    # contiguous alphanumeric run — real Prusament hashes are 10 lowercase hex
    # chars (see setup-and-rebuild/seeds), but we stay permissive and
    # case-insensitive so we neither truncate nor mis-recognize. The greedy
    # product-id group stops at the '/', so an all-digit hash isn't swallowed.
    # spool_hash is None when the URL carries no hash segment. Consumers needing
    # spool-level granularity (vs. product-level temp backfill) match on the
    # hash — see _handle_prusament_url_scan in app.py.
    pm = re.search(r'prusament\.com/spool/(\d+)(?:/([0-9a-z]+))?', text, re.IGNORECASE)
    if pm:
        return {
            'type': 'prusament_url',
            'url': text,
            'spool_id': pm.group(1),
            'spool_hash': pm.group(2),
        }

    # 6. LEGACY / URL PARSING
    if any(x in text.lower() for x in ['http', 'www.', '.com', 'google', '/', '\\', '{', '}', '[', ']']):
        m = re.search(r'range=(\d+)', decoded, re.IGNORECASE)
        legacy_candidate = m.group(1) if m else None
        if legacy_candidate:
            result = _resolve_legacy_spool_lookup(legacy_candidate)
            if result is not None:
                return result
        result = _resolve_legacy_spool_lookup(text)
        if result is not None:
            return result
        # Spool lookup came up empty. A legacy id can map to a FILAMENT that
        # currently has no spools (Derek 2026-06-02 — a Google-Sheets `range=`
        # link dead-ended with "unknown error" because the filament had zero
        # active spools). Fall back to surfacing the filament itself rather
        # than erroring out. Mirrors the pure-number branch's Priority 4.
        if legacy_candidate:
            fid = spoolman_api.find_filament_by_legacy_id(legacy_candidate)
            if fid:
                return {'type': 'filament', 'id': fid}
        return {'type': 'error', 'msg': 'Unknown/Invalid Link'}

    # 7. PURE NUMBER SCAN (Priority Stack)
    if text.isdigit():
        # Priority 1: Direct Spool ID
        spool_check = spoolman_api.get_spool(text)
        if spool_check and spool_check.get('id'):
            return {'type': 'spool', 'id': int(text)}

        # Priority 2: Direct Filament ID
        fil_check = spoolman_api.get_filament(text)
        if fil_check and fil_check.get('id'):
            return {'type': 'filament', 'id': int(text)}

        # Priority 3: Legacy Spool
        result = _resolve_legacy_spool_lookup(text)
        if result is not None:
            return result
        
        # Priority 4: Legacy Filament
        fid = spoolman_api.find_filament_by_legacy_id(text)
        if fid: return {'type': 'filament', 'id': fid}
        
        return {'type': 'error', 'msg': 'ID Not Found'}
        
    # 8. LEGACY LOCATION FALLBACK (Len > 2)
    # Only accepts a "random string" if it matches a known location in DB.
    if len(text) > 2:
        loc_list = locations_db.load_locations_list()
        valid_ids = {row['LocationID'].upper() for row in loc_list}
        valid_ids.add("UNASSIGNED") # [ALEX FIX] Allow the virtual Unassigned bucket
        valid_ids.add("UNKNOWN")    # 18.1 — virtual UNKNOWN bucket (physically lost)

        if text.upper() in valid_ids:
            return {'type': 'location', 'id': text.upper()}
        else:
            return {'type': 'error', 'msg': 'Unknown Code (Use LOC: prefix)'}
        
    return {'type': 'error', 'msg': 'Unknown Code'}

# Thread-local re-entry depth for perform_smart_move. The auto-deploy chain
# re-enters the wrapper synchronously on the same thread; depth 0 is the
# outermost move, which owns the per-move printer-state probe cache (L3 fix A).
_smart_move_depth = threading.local()


def perform_smart_move(target, raw_spools, target_slot=None, origin='', auto_deploy=True, confirm_active_print=False):
    """Entry point for the slot-move pipeline.

    Owns the per-move printer-state probe cache (L3 fix A) so the auto-deploy
    recursion probes a given printer ONCE, not twice: a thread-local depth guard
    detects the OUTERMOST call and begins/clears the cache around it, while the
    recursive re-entry (depth > 0) leaves the outer cache untouched. All real
    work lives in _perform_smart_move_impl — this is a behaviour-neutral wrapper.
    """
    depth = getattr(_smart_move_depth, "n", 0)
    owns_move = depth == 0
    _smart_move_depth.n = depth + 1
    _pa = None
    if owns_move:
        # Deferred import keeps logic.py importable in unit tests that don't
        # satisfy prusalink_api's import graph (mirrors _active_print_info_*).
        try:
            import prusalink_api as _pa
            _pa.begin_probe_cache()
        except Exception:
            _pa = None
    try:
        return _perform_smart_move_impl(
            target, raw_spools, target_slot=target_slot, origin=origin,
            auto_deploy=auto_deploy,
            confirm_active_print=confirm_active_print,
        )
    finally:
        _smart_move_depth.n = getattr(_smart_move_depth, "n", 1) - 1
        if owns_move and _pa is not None:
            try:
                _pa.clear_probe_cache()
            except Exception:
                pass


def _perform_smart_move_impl(target, raw_spools, target_slot=None, origin='', auto_deploy=True, confirm_active_print=False):
    """Move spool(s) to `target`, optionally into `target_slot` of that location.

    `auto_deploy` (default True): when the target is a Dryer Box AND the
    target_slot is bound to a toolhead in that box's extra.slot_targets,
    chain a second move that ghost-deploys the spool onto that toolhead.
    This centralizes the behavior so every caller (scan, /api/manage_contents
    action=add, Feeds-editor post-save triggers, future callers) gets it
    consistently — not just the slot-QR scan path.

    Internal recursive calls set auto_deploy=False to prevent infinite
    chains (the toolhead deploy itself would otherwise try to auto-deploy
    onto its own printer binding).

    `origin_toolhead` (optional): location string naming the spool's
    previous toolhead, used only for the filabridge unmap. The
    auto-deploy recursive call passes this because by phase 2 the
    spool's Spoolman location is the dryer box, not the toolhead it
    came from — without this hint, phase 2 can't unmap the origin and
    filabridge rejects the destination map on its one-spool-one-toolhead
    invariant (the 2026-04-22 desync).
    """
    target = target.strip().upper()
    cfg = config_loader.load_config()
    printer_map = locations_db.get_active_printer_map()  # L271 P4 step 2: Printer-row toolheads[] (dual-read)
    loc_list = locations_db.load_locations_list()
    loc_info_map = {row['LocationID'].upper(): row for row in loc_list}

    spools = []
    for item in raw_spools:
        if str(item).isdigit(): spools.append(item)
        else:
            found = spoolman_api.get_spools_at_location(str(item))
            if found: spools.extend(found)

    if not spools: return {"status": "error", "msg": "No spools found"}

    # Active-print safety check: if the destination is a toolhead on a
    # printer that's currently PRINTING/PAUSED/BUSY, bail with a
    # requires_confirm response so the caller can show a dialog and retry
    # with confirm_active_print=True. Fail-open via None inside the helper.
    #
    # Walks slot-targets too: if target is a Dryer Box and target_slot is
    # bound to a toolhead, that toolhead is the eventual destination (via
    # the auto-deploy chain below). Checking it preemptively means the
    # user gets prompted BEFORE any Spoolman writes happen, instead of
    # having the recursive call swallow requires_confirm silently.
    if not confirm_active_print:
        ap = _active_print_info_for_location(target, printer_map)
        if not ap:
            # Check slot-binding's eventual toolhead.
            tgt_row = loc_info_map.get(target)
            if tgt_row and tgt_row.get('Type') == 'Dryer Box' and target_slot:
                bound = (tgt_row.get('extra') or {}).get('slot_targets', {}) or {}
                bound_th = bound.get(str(target_slot)) or bound.get(str(int(target_slot))) if str(target_slot).isdigit() else bound.get(str(target_slot))
                if bound_th:
                    ap = _active_print_info_for_location(bound_th, printer_map)
        if ap:
            return {
                "status": "requires_confirm",
                "confirm_type": "active_print",
                "active_print": ap,
                "msg": f"{ap['printer_name']} is {ap['state']} — moving a spool here will disrupt the print.",
            }

    # Auto-slot-pick: if the caller didn't specify a slot and the target is a
    # slotted container (Max Spools > 1) with at least one free slot, fill the
    # lowest-numbered free slot. Only fires for single-spool moves — in a bulk
    # move, a shared target_slot would make each spool unseat the previous
    # one, so a bulk slotless move stays slotless (rooms/shelves handle that
    # case correctly; slotted bulk moves should be explicit).
    tgt_info_auto = loc_info_map.get(target)
    if not target_slot and tgt_info_auto and len(spools) == 1:
        try:
            max_slots_auto = int(str(tgt_info_auto.get('Max Spools', '0')).strip() or '0')
        except (TypeError, ValueError):
            max_slots_auto = 0
        if max_slots_auto > 1:
            # Collect currently-occupied slot numbers at this target.
            existing_at_target = spoolman_api.get_spools_at_location_detailed(target) or []
            occupied_slots = set()
            for existing in existing_at_target:
                # Skip the spool we're about to move — otherwise its own current slot
                # gets flagged as occupied and we miss the obvious re-slot case.
                if str(existing.get('id')) in [str(s) for s in spools]:
                    continue
                raw = str(existing.get('slot', '') or '').strip().strip('"')
                if raw and raw.isdigit():
                    occupied_slots.add(int(raw))
            # Pick lowest-numbered free slot.
            for i in range(1, max_slots_auto + 1):
                if i not in occupied_slots:
                    target_slot = str(i)
                    state.logger.info(
                        f"🪑 Auto-slot: {target} has free slot {i} — assigning spool there"
                    )
                    break

    # --- SMART LOAD LOGIC (Auto-Eject Resident) ---
    # Determine if this is a single-occupancy target (Printer/Toolhead)
    tgt_info = loc_info_map.get(target)
    is_printer = target in printer_map
    # 21.3 — single-occupancy = the canonical toolhead type set (Tool Head /
    # MMU Slot / No MMU Direct Load) plus the dual-role "Printer" row. The old
    # inline list omitted "No MMU Direct Load" (the Core One direct-load type),
    # so manually assigning a spool to such a head — when it wasn't ALSO present
    # in printer_map to be caught by is_printer — skipped the resident auto-eject
    # and left two spools on one head. Sourced from locations_db.TOOLHEAD_TYPES
    # so this can't drift out of sync with the rest of the codebase again.
    is_toolhead = bool(tgt_info) and tgt_info.get('Type') in (locations_db.TOOLHEAD_TYPES | {'Printer'})

    undo_record: typing.Dict[str, typing.Any] = {"target": target, "moves": {}, "labels": {}, "ejections": {}, "summary": f"Moved {len(spools)} -> {target}", "origin": origin}

    if is_printer or is_toolhead:
        # Check if anyone is already home
        residents = spoolman_api.get_spools_at_location(target)
        for rid in residents:
            # Don't eject the spool we are currently trying to move (if it's already there)
            if str(rid) not in [str(s) for s in spools]:
                state.add_log_entry(f"⚠️ <b>Smart Load:</b> Ejecting #{rid} from {target}...", "WARNING")
                # No suppress_fb_unmap: filabridge must see the target
                # toolhead cleared before we map the incoming spool to
                # it (filabridge invariant: one spool, one toolhead).
                if perform_smart_eject(rid):
                    # Find out where it actually got sent to so we can bring it back!
                    ejected_data = spoolman_api.get_spool(rid)
                    if ejected_data:
                        undo_record['ejections'][rid] = ejected_data.get('location', '')

    for sid in spools:
        spool_data = spoolman_api.get_spool(sid)
        if not spool_data: continue
        current_loc = spool_data.get('location', '').strip().upper()
        undo_record['moves'][sid] = current_loc
        current_extra: dict = dict(spool_data.get('extra') or {})
        info = spoolman_api.format_spool_display(spool_data)
        # Capture the rich display label now (already computed for the forward-
        # move log) so the Undo line can name the spool + source, not just a
        # count — see perform_undo's readable from→to rendering.
        undo_record['labels'][sid] = info['text']
        
        new_extra: typing.Dict[str, typing.Any] = dict(current_extra)
        
# Handle Slot Assignment
        if target_slot:
            existing_items = spoolman_api.get_spools_at_location_detailed(target)
            for existing in existing_items:
                # [ALEX FIX] Improved comparison to catch string vs int mismatches
                if str(existing.get('slot', '')).strip('"') == str(target_slot) and existing['id'] != int(sid):
                    state.logger.info(f"🪑 Unseating Spool {existing['id']} from Slot {target_slot}")
                    # Load the existing spool's full extra and MERGE — Spoolman's
                    # PATCH replaces the entire `extra` object, so passing only
                    # {container_slot: ''} would wipe physical_source, spool_type,
                    # temps, etc. Read → clear just the slot → write whole extra.
                    _existing_full = spoolman_api.get_spool(existing['id']) or {}
                    _merged_extra = dict(_existing_full.get('extra') or {})
                    _merged_extra['container_slot'] = ''
                    if not spoolman_api.update_spool(existing['id'], {'extra': _merged_extra}):
                        err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
                        state.add_log_entry(
                            f"❌ Failed to unseat Spool #{existing['id']} from slot: {err}",
                            "ERROR", "ff4444"
                        )

            new_extra['container_slot'] = str(target_slot)
        else:
            # If moving to a non-slotted location, clear the slot
            new_extra['container_slot'] = ""

        # PRINTER MOVE
        if target in printer_map:
            # Preserve ghost trail when the spool is already deployed to
            # this exact toolhead. Without this guard, re-scanning a spool
            # that's already on the toolhead would set physical_source to
            # the toolhead itself — physical_source == location means "not
            # a ghost," so the deployed indicator disappears and Return-
            # to-Slot loses its home. Only overwrite physical_source when
            # the spool is genuinely arriving from somewhere else.
            existing_source = str(current_extra.get('physical_source', '') or '').strip().strip('"')
            is_already_here = (current_loc == target) and bool(existing_source)
            if is_already_here:
                new_extra['physical_source'] = existing_source
                new_extra['physical_source_slot'] = current_extra.get('physical_source_slot')
            else:
                new_extra['physical_source'] = current_loc
                new_extra['physical_source_slot'] = current_extra.get('container_slot')

            # 13.6 Part A — if the destination toolhead is the value of some
            # dryer-box slot's `extra.slot_targets`, treat the spool as if
            # it came from that slot so the box card lists it as a ghost in
            # the bound slot (mirrors the slot→toolhead auto-deploy chain's
            # forward direction). Only kicks in when there's no genuine
            # source already (UNASSIGNED, buffer, room, etc.) — preserving
            # the existing physical_source when the spool actually came
            # from somewhere meaningful.
            current_source_meaningful = bool(
                str(new_extra.get('physical_source') or '').strip().strip('"')
            )
            if not current_source_meaningful:
                bound_box, bound_slot = _find_box_slot_feeding_toolhead(target, loc_list)
                if bound_box and bound_slot:
                    new_extra['physical_source'] = bound_box
                    new_extra['physical_source_slot'] = bound_slot
                    state.logger.info(
                        f"🔗 Reverse-binding: toolhead {target} is fed by "
                        f"{bound_box} slot {bound_slot} — synthesizing ghost source."
                    )

            if spoolman_api.update_spool(sid, {"location": target, "extra": new_extra}):
                state.add_log_entry(f"🖨️ {info['text']} -> {target}", "INFO", info['color'])
                # Group 20.2: a spool deployed FROM a single-slot dryer box
                # attaches that box to this toolhead so the box follows its
                # spool (Core One "missing box" aid). current_loc is where the
                # spool lived before this move. Best-effort — never fail the move.
                try:
                    _att, _ad = locations_db.attach_single_slot_box_to_toolhead(current_loc, target)
                    if _att and _ad != "already attached":
                        state.add_log_entry(f"🔗 Single-slot box auto-attached → {target} ({_ad})", "INFO")
                except Exception as _ae:
                    state.logger.warning(f"20.2 box auto-attach skipped: {_ae}")
            else:
                # Surface Spoolman rejection so slot-assignment failures are
                # visible. Pre-fix, Spoolman 400s here left the slot stuck
                # with no user-visible signal — a class of bug behind the
                # 2026-04-27 outage (Item 2 in Feature-Buglist).
                err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
                state.add_log_entry(
                    f"❌ Failed to slot Spool #{sid} -> {target}: {err}", "ERROR", "ff4444"
                )

        # DRYER MOVE
        elif target in loc_info_map and loc_info_map[target].get('Type') == 'Dryer Box':
            new_extra.pop('physical_source', None)
            # [ALEX FIX] Clean up the source slot memory too, since we are home now.
            new_extra.pop('physical_source_slot', None)

            if spoolman_api.update_spool(sid, {"location": target, "extra": new_extra}):
                slot_txt = f" [Slot {target_slot}]" if target_slot else ""
                state.add_log_entry(f"📦 {info['text']} -> Dryer {target}{slot_txt}", "INFO", info['color'])
            else:
                err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
                state.add_log_entry(
                    f"❌ Failed to move Spool #{sid} -> Dryer {target}: {err}", "ERROR", "ff4444"
                )

        # GENERIC MOVE
        else:
            # [Universal Fallback Ghost Logic]
            if is_toolhead:
                 new_extra['physical_source'] = current_loc
                 new_extra['physical_source_slot'] = current_extra.get('container_slot')
            else:
                # L130 fix: when forcing a spool to a Room/Cart/Shelf
                # (the typical Force-Location destinations), clear any
                # stale ghost trail so the "deployed" indicator computed
                # from physical_source (spoolman_api.search_inventory)
                # doesn't keep flagging the spool as still on a toolhead.
                # Mirrors the DRYER MOVE branch's pop() above.
                new_extra.pop('physical_source', None)
                new_extra.pop('physical_source_slot', None)

            if spoolman_api.update_spool(sid, {"location": target, "extra": new_extra}):
                state.add_log_entry(f"🚚 {info['text']} -> {target}", "INFO", info['color'])
            else:
                err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
                state.add_log_entry(
                    f"❌ Failed to move Spool #{sid} -> {target}: {err}", "ERROR", "ff4444"
                )

    state.UNDO_STACK.append(undo_record)

    # --- AUTO-DEPLOY CHAIN ---
    # If this move placed spool(s) into a Dryer Box slot that's bound to a
    # toolhead (extra.slot_targets[slot]), chain a second move so the spool
    # ends up ghost-deployed onto the toolhead. Previously this logic
    # lived only in api_identify_scan's assignment branch, so only scans
    # triggered it; callers like /api/manage_contents action='add' (assign
    # from buffer, deposit cards, etc.) silently skipped it. Centralizing
    # here gives every caller the same behavior for free.
    #
    # auto_deploy=False on the chained call prevents infinite recursion
    # (the toolhead move would try to auto-deploy onto its own printer).
    auto_deploy_result = None
    bound_toolhead = None
    if auto_deploy and target_slot and tgt_info and tgt_info.get('Type') == 'Dryer Box':
        bindings = (tgt_info.get('extra') or {}).get('slot_targets') or {}
        bound_toolhead = bindings.get(str(target_slot))
        # PRINTER:<id> sentinels declare "this slot is staged for the named
        # printer's pool" — no toolhead is implied, so auto-deploy is a no-op.
        if bound_toolhead and locations_db.is_printer_sentinel(bound_toolhead):
            bound_toolhead = None
        if bound_toolhead:
            try:
                auto_deploy_result = perform_smart_move(
                    bound_toolhead, list(spools),
                    target_slot=None, origin=f'auto_deploy_from_{origin or "smart_move"}',
                    auto_deploy=False,
                )
                for sid in spools:
                    state.add_log_entry(
                        f"⚡ Auto-deployed Spool #{sid}{_spool_brand_color_suffix(sid)} → <b>{str(bound_toolhead).upper()}</b> "
                        f"(source: {target}:SLOT:{target_slot})",
                        "SUCCESS", "00ff00"
                    )
            except Exception as _ad_err:
                state.logger.error(f"Auto-deploy failed for {target}:SLOT:{target_slot}: {_ad_err}")

    result: typing.Dict[str, typing.Any] = {
        "status": "success",
    }
    if auto_deploy_result is not None and bound_toolhead:
        result["auto_deployed_to"] = str(bound_toolhead).upper()
    return result


def get_room_from_location(loc_id):
    if not loc_id:
        return ""
    loc_id = loc_id.strip().upper()
    if "-" not in loc_id:
        return ""

    # L271 Phase 3.5: walk to the TOP-LEVEL room. `parent_id` now stores each
    # row's IMMEDIATE parent, so resolve_parent (a single hop) no longer reaches
    # the room for a nested row (cart-row -> cart, toolhead -> printer);
    # resolve_room walks the chain to the topmost ancestor. On the pre-3.5 flat
    # tree this is byte-identical to the old single-hop split (a dashed row's
    # only ancestor IS its first-segment room). After the immediate-parent
    # migration, a toolhead's room correctly resolves to the printer's room
    # (XL-1 -> XL -> LR) instead of stopping at the printer.
    room = locations_db.resolve_room(loc_id) or ""

    # Exclude known non-room prefixes we don't want to spawn virtual rooms for
    # PM = Polymaker portable boxes, PJ = Project Carts, TST = System Tests.
    if room in locations_db.PSEUDO_ROOM_PREFIXES:
        return ""

    return room

def perform_smart_eject(spool_id, confirmed_unassign=False, confirm_active_print=False):
    """Remove `spool_id` from its current location.

    Returns:
      - True on successful eject
      - False on any failure (load error, DB write error, etc.)
      - "REQUIRE_CONFIRM" if the spool is in a room and confirmed_unassign=False
      - {"status": "requires_confirm", "confirm_type": "active_print", ...}
        when the spool is currently on an actively-printing toolhead and the
        caller hasn't explicitly opted in via confirm_active_print=True.
    """
    spool_data = spoolman_api.get_spool(spool_id)
    if not spool_data: return False

    current_location = spool_data.get('location', '').strip().upper()
    extra = spool_data.get('extra', {})

    cfg = config_loader.load_config()
    printer_map = locations_db.get_active_printer_map()  # L271 P4 step 2: Printer-row toolheads[] (dual-read)

    # Active-print safety: ejecting a spool from a printing toolhead is
    # destructive. Bail with requires_confirm so the caller can prompt.
    if not confirm_active_print:
        ap = _active_print_info_for_location(current_location, printer_map)
        if ap:
            return {
                "status": "requires_confirm",
                "confirm_type": "active_print",
                "active_print": ap,
                "msg": f"{ap['printer_name']} is {ap['state']} — ejecting from this toolhead will disrupt the print.",
            }

    # Group 20.2: ejecting off a toolhead detaches any single-slot dryer box that
    # was following its spool onto this toolhead (the lifecycle pair of the
    # auto-attach in perform_smart_move). Best-effort — never fail the eject.
    if current_location in printer_map:
        try:
            _detached = locations_db.detach_single_slot_boxes_from_toolhead(current_location)
            if _detached:
                state.add_log_entry(
                    f"🔓 Single-slot box(es) auto-detached from {current_location}: "
                    f"{', '.join(str(d) for d in _detached)}", "INFO")
        except Exception as _de:
            state.logger.warning(f"20.2 box auto-detach skipped: {_de}")

    # Save the original slot before we wipe it for processing
    orig_container_slot = extra.get('container_slot', '')
    
    # [ALEX FIX] Explicitly overwrite the slot with empty string.
    # .pop() just removes the key, which causes PATCH to ignore it (keeping the old value).
    extra['container_slot'] = ""
    
    saved_source = extra.get('physical_source')
    
    # [ALEX FIX] Prevent Infinite Return Loop
    # If the database thinks we "came from" the place we are currently ejecting from,
    # we must clear that memory, otherwise we just 'return' to the same box.
    if saved_source and saved_source.strip().upper() == current_location:
        state.logger.info(f"🛑 Eject Loop Detected: Source is same as Location ({saved_source}). Clearing.")
        saved_source = None
        extra['physical_source'] = "" # Wipe the memory

    # [ALEX FIX] Room hierarchy bypass
    # If we are currently floating in a room, and the saved_source is a CHILD of this room,
    # we NEVER bounce back down to the child box. We break the loop and eject to Unassigned.
    # L271 Phase 3.5: "is saved_source anywhere BENEATH current_location" via
    # is_descendant instead of a single-hop resolve_parent equality. parent_id
    # now stores the immediate parent, so a one-hop check would only catch a
    # DIRECT child — but a saved_source can be a grandchild of the room we're
    # floating in (room -> cart -> cart-row). is_descendant walks the chain so
    # the loop-break fires for the whole subtree. On the pre-3.5 flat tree this
    # reduces to the old single-hop equality (a row's only ancestor is its
    # first-segment room), so it's byte-identical until the data flip.
    if current_location and saved_source:
        if locations_db.is_descendant(saved_source.strip('"'), current_location):
            state.logger.info(f"🛑 Bypassing Saved Source: {saved_source} is inside {current_location}. Ejecting to Unassigned.")
            saved_source = None

    if saved_source:
        if saved_source.startswith('"'): saved_source = saved_source.strip('"')

        # [ALEX FIX] Retain the assignment slot when returning home.
        # Move the saved slot back into container_slot
        saved_slot = extra.get('physical_source_slot', '')
        if saved_slot:
            saved_slot_clean = str(saved_slot).strip('"')
            # 13.2 — Don't recreate a slot binding that's already claimed by
            # another spool (direct OR ghost from a different spool). The
            # auto-deploy chain can leave a ghost in our former slot moments
            # before we return; landing on top of it makes a 2/2-but-only-
            # one-visible collision in the dryer-box grid. When the slot is
            # already claimed by someone else, land unslotted — the user
            # can manually re-slot once the binding cycle settles.
            slot_taken_by_other = False
            try:
                here = spoolman_api.get_spools_at_location_detailed(saved_source) or []
                for other in here:
                    if int(other.get('id', 0)) == int(spool_id):
                        continue
                    if str(other.get('slot', '')).strip('"') == saved_slot_clean:
                        slot_taken_by_other = True
                        state.logger.info(
                            f"🛑 Slot collision: {saved_source} slot {saved_slot_clean} "
                            f"already claimed by Spool #{other.get('id')} "
                            f"({'ghost' if other.get('is_ghost') else 'direct'}); "
                            f"landing #{spool_id} unslotted instead."
                        )
                        break
            except Exception as _slot_check_err:
                state.logger.warning(f"Slot-collision check failed: {_slot_check_err}")
            if slot_taken_by_other:
                extra['container_slot'] = ""
            else:
                extra['container_slot'] = saved_slot_clean
            extra['physical_source_slot'] = ""
        else:
            extra['container_slot'] = ""
            
        # Clear the source memory so we don't bounce back again later
        extra['physical_source'] = "" 
        
        if spoolman_api.update_spool(spool_id, {"location": saved_source, "extra": extra}):
            state.add_log_entry(f"↩️ Returned #{spool_id} -> {saved_source}", "WARNING")
            return True
        err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
        state.add_log_entry(
            f"❌ Failed to return Spool #{spool_id} -> {saved_source}: {err}", "ERROR", "ff4444"
        )
    else:
        # Normal unslotted eject with Room Fallback
        # [Universal Fallback fix] A printer is not a Room. If ejecting from a printer and missing physical_source, default to Unassigned.
        if current_location in printer_map:
            target_loc = ""
        else:
            room_fallback = get_room_from_location(current_location)
            target_loc = room_fallback if room_fallback else ""

        # Protected Unassign
        if target_loc == "" and current_location != "":
            if not confirmed_unassign:
                return "REQUIRE_CONFIRM"

        # Strictly clear source bindings so it doesn't become a ghost in its old container
        extra['physical_source'] = ""
        extra['physical_source_slot'] = ""
        extra['container_slot'] = ""

        if spoolman_api.update_spool(spool_id, {"location": target_loc, "extra": extra}):
            dest_msg = f" to Room {target_loc}" if target_loc else " (Unassigned)"
            state.add_log_entry(f"⏏️ Ejected #{spool_id}{dest_msg}", "WARNING")
            return True
        err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
        state.add_log_entry(
            f"❌ Failed to eject Spool #{spool_id}: {err}", "ERROR", "ff4444"
        )
    return False


def perform_toolhead_delete_cascade(target, loc_list, confirm_active_print=False):
    """Group 20.3 — propagate a TOOLHEAD row deletion to the three drifting
    binding stores so nothing is left pointing at the now-gone toolhead.

    Spool side (Spoolman), per Derek's 20.3 decision = UNASSIGNED + breadcrumb:
      - DIRECT spools (Spoolman ``location`` == target): → UNASSIGNED
        (``location`` = ""), with the ghost-trail cleared so they don't resurrect
        as a ghost in their old box.
      - GHOST spools (physically in a box, only DEPLOYED to the toolhead via
        ``physical_source``): keep their box ``location`` and clear ONLY the
        deployment ghost-trail — deleting the toolhead must NOT yank a spool out
        of the box it actually lives in. (The pre-20.3 cascade blindly set
        ``location`` = "" for everything ``get_spools_at_location`` returned,
        which includes these ghosts.)
    FilaBridge: unmap the toolhead (best-effort) so the printer-side map doesn't
    stay pinned to a spool that's no longer assigned.
    locations.json: drop any dryer-box ``slot_targets`` feeding the toolhead, and
    prune the toolhead from any Printer row's ``toolheads[]`` (L271 Phase-4 store).

    MUTATES ``loc_list`` IN-PLACE for the locations.json cleanup; the caller owns
    removing the toolhead row itself + the single ``save_locations_list``.

    ``confirm_active_print=False`` + an ACTIVE print on this toolhead → returns
    ``{"status": "requires_confirm", ...}`` WITHOUT touching anything (mirrors
    ``perform_force_unassign``). Otherwise returns a summary dict
    ``{"status": "ok", "unassigned": [...], "undeployed": [...],
       "slot_bindings_cleared": [...], "toolhead_pruned_from": [...], "errors": [...]}``.
    """
    target_up = str(target).strip().strip('"').upper()
    printer_map = locations_db.get_active_printer_map(loc_list)  # target still present → resolvable for the active-print check

    # Active-print safety: deleting a toolhead mid-print orphans the running spool.
    if not confirm_active_print:
        ap = _active_print_info_for_location(target_up, printer_map)
        if ap:
            return {
                "status": "requires_confirm",
                "confirm_type": "active_print",
                "active_print": ap,
                "msg": f"{ap['printer_name']} is {ap['state']} on {target_up} — "
                       f"deleting this toolhead will orphan the running spool.",
            }

    summary = {"status": "ok", "unassigned": [], "undeployed": [],
               "slot_bindings_cleared": [], "toolhead_pruned_from": [], "errors": []}

    # --- Spoolman: re-home spools that reference the toolhead ---
    try:
        at_loc = spoolman_api.get_spools_at_location_detailed(target_up)
    except Exception as e:
        at_loc = []
        summary["errors"].append(f"could not list spools at {target_up}: {e}")
    for item in at_loc:
        sid = item.get('id')
        spool = spoolman_api.get_spool(sid)
        if not spool:
            summary["errors"].append(f"could not fetch spool #{sid}")
            continue
        extra = dict(spool.get('extra') or {})
        # Read-merge-write: only touch the system-managed binding keys; preserve
        # every sibling extra (Spoolman PATCH replaces the whole extra dict).
        extra['physical_source'] = ""
        extra['physical_source_slot'] = ""
        if item.get('is_ghost'):
            # Only deployed to the dead toolhead → un-deploy, keep box location.
            if spoolman_api.update_spool(sid, {"extra": extra}):
                summary["undeployed"].append(sid)
            else:
                summary["errors"].append(
                    f"spool #{sid} un-deploy failed: {spoolman_api.LAST_SPOOLMAN_ERROR or 'unknown'}")
        else:
            # Physically ON the toolhead → UNASSIGNED, ghost-trail fully cleared.
            extra['container_slot'] = ""
            if spoolman_api.update_spool(sid, {"location": "", "extra": extra}):
                summary["unassigned"].append(sid)
            else:
                summary["errors"].append(
                    f"spool #{sid} unassign failed: {spoolman_api.LAST_SPOOLMAN_ERROR or 'unknown'}")

    # --- locations.json: drop dryer-box slot_targets feeding the toolhead ---
    for row in loc_list:
        if not isinstance(row, dict) or str(row.get('Type', '')).strip() != locations_db.DRYER_BOX_TYPE:
            continue
        extra_l = row.get('extra') or {}
        targets = extra_l.get('slot_targets')
        if not isinstance(targets, dict):
            continue
        kept, dropped = {}, []
        for slot, bound in targets.items():
            # Leave PRINTER:<prefix> pool sentinels alone — they bind a printer, not this toolhead.
            if bound and not locations_db.is_printer_sentinel(bound) and str(bound).strip().upper() == target_up:
                dropped.append(slot)
            else:
                kept[slot] = bound
        if dropped:
            extra_l['slot_targets'] = kept
            row['extra'] = extra_l
            for slot in dropped:
                summary["slot_bindings_cleared"].append(f"{row.get('LocationID')}:{slot}")

    # --- locations.json: prune the toolhead from any Printer row's toolheads[] ---
    for row in loc_list:
        if not isinstance(row, dict) or str(row.get('Type', '')).strip().lower() != 'printer':
            continue
        ths = row.get('toolheads')
        if not isinstance(ths, list):
            continue
        kept = [t for t in ths
                if not (isinstance(t, dict) and str(t.get('location_id', '')).strip().upper() == target_up)]
        if len(kept) != len(ths):
            row['toolheads'] = kept
            summary["toolhead_pruned_from"].append(row.get('LocationID'))

    return summary


def perform_force_unassign(spool_id, confirm_active_print=False):
    spool_data = spoolman_api.get_spool(spool_id)
    if not spool_data: return False
    extra = spool_data.get('extra', {})
    current_location = spool_data.get('location', '').strip().upper()

    cfg = config_loader.load_config()
    printer_map = locations_db.get_active_printer_map()  # L271 P4 step 2: Printer-row toolheads[] (dual-read)

    # Active-print safety: force-unassign from a printing toolhead disrupts
    # the print. Bail with requires_confirm unless the caller opted in.
    if not confirm_active_print:
        ap = _active_print_info_for_location(current_location, printer_map)
        if ap:
            return {
                "status": "requires_confirm",
                "confirm_type": "active_print",
                "active_print": ap,
                "msg": f"{ap['printer_name']} is {ap['state']} — force-unassigning from this toolhead will disrupt the print.",
            }

    # [ALEX FIX] Explicitly overwrite slots and sources with empty strings
    # to guarantee Spoolman API removes them instead of ignoring dropped keys
    extra['container_slot'] = ""
    extra['physical_source'] = ""
    extra['physical_source_slot'] = ""

    if spoolman_api.update_spool(spool_id, {"location": "", "extra": extra}):
        state.add_log_entry(f"🗑️ Force Unassigned #{spool_id}", "WARNING")
        return True
    err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
    state.add_log_entry(
        f"❌ Failed to force-unassign Spool #{spool_id}: {err}", "ERROR", "ff4444"
    )
    return False

def perform_undo():
    if not state.UNDO_STACK: return {"success": False, "msg": "Nothing to undo (Undo reverts spool moves only)."}
    last = state.UNDO_STACK.pop()
    moves = last['moves']
    target = last.get('target')
    origin = last.get('origin', '')
    sm_url, _ = config_loader.get_api_urls()
    
    # Reassign each moved spool back to its origin location in Spoolman.
    for sid, loc in moves.items():
        requests.patch(f"{sm_url}/api/v1/spool/{sid}", json={"location": loc})
    # [ALEX FIX] Revert Smart Ejections
    ejections = last.get('ejections', {})
    for ejected_sid, original_loc in ejections.items():
        requests.patch(f"{sm_url}/api/v1/spool/{ejected_sid}", json={"location": original_loc})
            
            
    # [ALEX FIX] Restore to Buffer Memory
    state.logger.info(f"UNDO RECORD TRIGGER: {last}")
    if origin == 'buffer':
        for sid in moves.keys():
            spool_data = spoolman_api.get_spool(sid)
            if spool_data:
                info = spoolman_api.format_spool_display(spool_data)
                # Ensure we avoid duplicates
                if not any(s.get('id') == int(sid) for s in getattr(state, 'GLOBAL_BUFFER', [])):
                    if not hasattr(state, 'GLOBAL_BUFFER'): state.GLOBAL_BUFFER = []
                    # Prepend to buffer so it shows up first
                    state.GLOBAL_BUFFER.insert(0, {'id': int(sid), 'display': info['text'], 'color': info['color']})
                    
    # Render a readable from→to line: label + source were captured at move time
    # (logic.py undo_record build). Fall back to bare #sid / UNASSIGNED for legacy
    # records or a spool deleted between the move and the undo.
    labels = last.get('labels', {})

    def _undo_seg(sid, with_target):
        label = labels.get(sid) or labels.get(str(sid)) or f"#{sid}"
        src = moves.get(sid) or moves.get(str(sid)) or "UNASSIGNED"
        # The multi-spool header already states the destination, so the per-spool
        # segments drop the redundant "-> target".
        return f"{label} from {src} -> {target}" if with_target else f"{label} from {src}"

    if len(moves) == 1:
        detail = f"moved {_undo_seg(next(iter(moves)), True)}"
    elif moves:
        detail = f"moved {len(moves)} spools -> {target} (" + "; ".join(_undo_seg(s, False) for s in moves) + ")"
    else:
        # Legacy / no-move record: its summary already reads "Moved N -> target",
        # so don't prepend a second "moved".
        detail = last.get('summary', f"moved -> {target}")
    state.add_log_entry(f"↩️ Undid: {detail}", "WARNING")
    return {"success": True}

def process_audit_scan(scan_result):
    """Handles scans when in Audit Mode."""
    session = state.AUDIT_SESSION
    
    # 1. COMMANDS
    if scan_result['type'] == 'command':
        cmd = scan_result['cmd']
        if cmd == 'done' or cmd == 'cancel':
            # Generate Report
            missing = [sid for sid in session['expected_items'] if sid not in session['scanned_items']]
            expected_loc = session.get('location_id') or ''

            # 18.2 follow-up — bare spool IDs aren't useful in the Activity
            # Log report ("Missing: 101, 102, 103" doesn't tell the user
            # which spools to look for). Resolve each id to a display label
            # via format_spool_display; fall back to "#N" on any lookup
            # miss so a missing record can't break the report.
            def _label(sid):
                try:
                    sd = spoolman_api.get_spool(sid)
                    if sd:
                        info = spoolman_api.format_spool_display(sd) or {}
                        text = info.get('text') or ''
                        if text:
                            return f"#{sid} {text}"
                except Exception:
                    pass
                return f"#{sid}"

            summary = "📝 <b>Audit Report:</b><br>"
            if not missing and not session['rogue_items']:
                summary += "✅ Perfect Match! All items accounted for."
                color = "00ff00" # Green
            else:
                color = "ffaa00" # Orange
                if missing: summary += f"❌ <b>Missing:</b> {', '.join(_label(sid) for sid in missing)}<br>"
                if session['rogue_items']: summary += f"⚠️ <b>Extra:</b> {', '.join(_label(sid) for sid in session['rogue_items'])}"

            state.add_log_entry(summary, "INFO", color)

            # 18.2 Part A — on `done` (not `cancel` — cancel is the user
            # explicitly bailing out, e.g. they realized they were
            # auditing the wrong location), auto-park each missing spool
            # at the virtual UNKNOWN bucket. Plant the audited location
            # on extra.fcc_pre_audit_location so a recovery scan can
            # route the spool home. SYSTEM_MANAGED_EXTRAS protects the
            # key from being clobbered by user-driven edit surfaces.
            if cmd == 'done' and missing and expected_loc:
                for sid in missing:
                    try:
                        existing = spoolman_api.get_spool(sid) or {}
                        cur_extra = dict(existing.get('extra') or {})
                        cur_extra['fcc_pre_audit_location'] = expected_loc
                        ok = spoolman_api.update_spool(
                            sid,
                            {"location": "UNKNOWN", "extra": cur_extra},
                        )
                        # 18.2 follow-up — log with the spool's display label
                        # so the Activity Log line is actually readable
                        # ("moved Spool #102 Hatchbox PLA Black → UNKNOWN"
                        # vs the prior bare "moved Spool #102 → UNKNOWN").
                        display = _label(sid)
                        if ok:
                            state.add_log_entry(
                                f"❓ Audit: moved Spool {display} → UNKNOWN "
                                f"(was expected at {expected_loc}, not scanned)",
                                "WARNING",
                                "ffaa00",
                            )
                        else:
                            err = spoolman_api.LAST_SPOOLMAN_ERROR or "unknown error"
                            state.add_log_entry(
                                f"❌ Audit: failed to park Spool {display} at UNKNOWN: {err}",
                                "ERROR",
                                "ff4444",
                            )
                    except Exception as _e:
                        state.logger.error(f"Audit auto-park failed for #{sid}: {_e}")

            state.reset_audit()
            state.add_log_entry("Audit Mode Ended.", "INFO")
            return {"status": "success", "msg": "Audit Complete"}

        return {"status": "error", "msg": "Command not allowed in Audit"}

    # 2. LOCATION SCAN
    if scan_result['type'] == 'location':
        loc_id = scan_result['id']
        if session['location_id']:
            state.add_log_entry(f"⚠️ Already auditing {session['location_id']}. Finish first!", "WARNING")
            return {"status": "error"}
            
        session['location_id'] = loc_id
        expected = spoolman_api.get_spools_at_location(loc_id)
        session['expected_items'] = expected
        state.add_log_entry(f"🧐 Auditing <b>{loc_id}</b>. expecting {len(expected)} items. Start scanning!", "INFO", "00aaff")
        return {"status": "success"}

    # 3. SPOOL SCAN
    if scan_result['type'] == 'spool':
        if not session['location_id']:
            state.add_log_entry("⚠️ Scan a Location first!", "WARNING")
            return {"status": "error"}
            
        spool_id = scan_result['id']
        if spool_id in session['scanned_items']:
            return {"status": "success", "msg": "Already scanned"}
            
        session['scanned_items'].append(spool_id)
        
        if spool_id in session['expected_items']:
            rem = len(session['expected_items']) - len(session['scanned_items'])
            msg = f"✅ Found #{spool_id}"
            if rem > 0: msg += f" ({rem} left)"
            else: msg += " (All found!)"
            state.add_log_entry(msg, "INFO", "00ff00")
        else:
            session['rogue_items'].append(spool_id)
            data = spoolman_api.get_spool(spool_id)
            curr_loc = data.get('location', 'Unknown')
            state.add_log_entry(f"⚠️ Found #{spool_id}! (DB says: {curr_loc})", "WARNING")
            
        return {"status": "success"}

    return {"status": "error", "msg": "Unknown scan type"}

def get_live_spools_data(spool_ids):
    """
    Rapidly queries Spoolman for a specific list of Spool IDs and returns 
    their formatted display strings and colors.
    Used by the frontend to live-refresh the Dashboard Buffer and Location Manager UI.
    """
    results = {}
    for sid in spool_ids:
        try:
            spool_data = spoolman_api.get_spool(sid)
            if spool_data:
                info = spoolman_api.format_spool_display(spool_data)
                
                sloc = str(spool_data.get('location', '')).strip()
                extra = spool_data.get('extra', {})
                is_ghost = False
                p_source = str(extra.get('physical_source', '')).strip().replace('"', '')
                if p_source and sloc.upper() != p_source.upper():
                    is_ghost = True
                ghost_slot = str(extra.get('physical_source_slot', '')).strip('"')
                
                final_slot = info.get('slot', '')
                if is_ghost and ghost_slot:
                    final_slot = ghost_slot

                results[str(sid)] = {
                    "display": info["text"],
                    "color": info["color"],
                    "color_direction": info.get("color_direction", "longitudinal"),
                    "remaining_weight": spool_data.get("remaining_weight"),
                    "details": info.get("details", {}),
                    "archived": spool_data.get("archived", False),
                    "location": p_source if is_ghost else sloc,
                    "is_ghost": is_ghost,
                    "slot": final_slot,
                    "deployed_to": sloc if is_ghost else None
                }
        except Exception as e:
            state.logger.error(f"Failed to live-refresh spool {sid}: {e}")

    return results


def find_spool_in_slot(box_loc_id, slot):
    """Return the spool id sitting in (box_loc_id, slot), or None.

    Scans items at the location (including ghost items whose
    physical_source points back to this box) and matches the slot
    string loosely (Spoolman stores container_slot with JSON-string
    quoting — see spoolman_api.parse_inbound_data).
    """
    if not box_loc_id or not str(slot).strip():
        return None
    wanted = str(slot).strip().strip('"')
    items = spoolman_api.get_spools_at_location_detailed(box_loc_id)
    for item in items:
        item_slot = str(item.get('slot', '')).strip().strip('"')
        if item_slot == wanted:
            return int(item['id'])
    return None
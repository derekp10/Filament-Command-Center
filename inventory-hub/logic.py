import re
import typing
import urllib.parse
import requests
import state
import config_loader
import spoolman_api
import locations_db


def _toolhead_of(location_str, printer_map=None):
    """Resolve a location string to its (printer_name, toolhead_id) tuple.

    Returns None if the location is empty or not a registered toolhead.
    Used so callers can decide whether a filabridge unmap is needed
    before a move.
    """
    if not location_str:
        return None
    if printer_map is None:
        cfg = config_loader.load_config()
        printer_map = cfg.get("printer_map", {})
    loc = str(location_str).strip().strip('"').upper()
    if loc in printer_map:
        p = printer_map[loc]
        return (p.get('printer_name'), p.get('position'))
    return None


def _fb_spool_location(spool_id, fb_url=None):
    """Return (printer_name, toolhead_id) where filabridge currently has
    `spool_id` mapped, or None.

    This is the AUTHORITATIVE origin for any upcoming map call — Spoolman's
    `location` field can lag behind filabridge (stale desyncs, manual DB
    edits, prior failed moves), and filabridge will reject the map if its
    own view shows the spool on a different toolhead. Querying the status
    endpoint lets us clear the correct toolhead first.
    """
    if fb_url is None:
        _, fb_url = config_loader.get_api_urls()
    try:
        resp = requests.get(f"{fb_url}/status", timeout=3)
        if not getattr(resp, 'ok', False):
            return None
        data = resp.json() or {}
        mappings = data.get('toolhead_mappings', {}) or {}
        target = int(spool_id)
        for _printer_key, toolheads in mappings.items():
            for th_id, entry in (toolheads or {}).items():
                try:
                    if int(entry.get('spool_id') or 0) == target:
                        return (entry.get('printer_name'), int(th_id))
                except (TypeError, ValueError):
                    continue
    except Exception:
        pass
    return None


def _fb_write(printer_name, toolhead_id, spool_id, fb_url=None):
    """POST a toolhead map/unmap to Filabridge. Never raises.

    Returns (ok: bool, detail: str). spool_id=0 means unmap. Caller owns
    the unmap-before-map sequencing and any Activity Log entry on failure.
    This wraps the bare `except: pass` that previously hid every
    filabridge rejection (which is how the 2026-04-22 desync went
    invisible — filabridge was rejecting the "two toolheads" map on its
    invariant, and nobody looked at the response).
    """
    if fb_url is None:
        _, fb_url = config_loader.get_api_urls()
    payload = {"printer_name": printer_name, "toolhead_id": toolhead_id, "spool_id": int(spool_id)}
    try:
        resp = requests.post(f"{fb_url}/map_toolhead", json=payload, timeout=3)
        # Prefer the standard requests.Response `.ok` accessor (True when
        # status_code is 2xx). Falls through to explicit status_code +
        # body inspection for richer detail on failures.
        if getattr(resp, 'ok', False):
            return (True, f"{printer_name}-{toolhead_id} <- #{spool_id}")
        code = getattr(resp, 'status_code', '?')
        body = ""
        try:
            body = (getattr(resp, 'text', '') or "")[:200]
        except Exception:
            pass
        return (False, f"HTTP {code}: {body}".strip())
    except Exception as e:
        return (False, f"transport error: {e}")


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
        rid = spoolman_api.find_spool_by_legacy_id(clean_id, strict_mode=True)
        if rid: return {'type': 'spool', 'id': rid}
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

    # 6. LEGACY / URL PARSING
    if any(x in text.lower() for x in ['http', 'www.', '.com', 'google', '/', '\\', '{', '}', '[', ']']):
        m = re.search(r'range=(\d+)', decoded, re.IGNORECASE)
        if m:
            rid = spoolman_api.find_spool_by_legacy_id(m.group(1), strict_mode=True)
            if rid: return {'type': 'spool', 'id': rid}
        rid = spoolman_api.find_spool_by_legacy_id(text, strict_mode=True)
        if rid: return {'type': 'spool', 'id': rid}
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
        rid = spoolman_api.find_spool_by_legacy_id(text, strict_mode=True)
        if rid: return {'type': 'spool', 'id': rid}
        
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
        
        if text.upper() in valid_ids:
            return {'type': 'location', 'id': text.upper()}
        else:
            return {'type': 'error', 'msg': 'Unknown Code (Use LOC: prefix)'}
        
    return {'type': 'error', 'msg': 'Unknown Code'}

def perform_smart_move(target, raw_spools, target_slot=None, origin='', auto_deploy=True, origin_toolhead=None):
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
    printer_map = cfg.get("printer_map", {})
    loc_list = locations_db.load_locations_list()
    loc_info_map = {row['LocationID'].upper(): row for row in loc_list}
    _, fb_url = config_loader.get_api_urls()

    spools = []
    for item in raw_spools:
        if str(item).isdigit(): spools.append(item)
        else:
            found = spoolman_api.get_spools_at_location(str(item))
            if found: spools.extend(found)

    if not spools: return {"status": "error", "msg": "No spools found"}

    # Snapshot each spool's origin toolhead BEFORE any Spoolman writes.
    # Phase 2 of the auto-deploy chain uses this to unmap filabridge for
    # the pre-phase-1 toolhead (e.g. Core1-M0) before mapping the
    # destination (e.g. XL-3). If the caller passed an explicit
    # origin_toolhead, it overrides the Spoolman snapshot — that's how
    # phase 2 learns about the pre-phase-1 location.
    origin_toolheads_by_spool: typing.Dict[str, typing.Optional[typing.Tuple[str, int]]] = {}
    explicit_origin_th = _toolhead_of(origin_toolhead, printer_map) if origin_toolhead else None
    for sid in spools:
        if explicit_origin_th is not None:
            origin_toolheads_by_spool[str(sid)] = explicit_origin_th
        else:
            snap = spoolman_api.get_spool(sid) or {}
            cur = str(snap.get('location', '')).strip().upper()
            origin_toolheads_by_spool[str(sid)] = _toolhead_of(cur, printer_map)

    # Track filabridge outcomes so the endpoint layer can surface
    # failures (warning toast + Activity Log) instead of swallowing them.
    fb_outcomes: typing.List[typing.Tuple[bool, str]] = []

    # --- SMART LOAD LOGIC (Auto-Eject Resident) ---
    # Determine if this is a single-occupancy target (Printer/Toolhead)
    tgt_info = loc_info_map.get(target)
    is_printer = target in printer_map
    is_toolhead = tgt_info and tgt_info.get('Type') in ['Tool Head', 'MMU Slot', 'Printer']

    undo_record: typing.Dict[str, typing.Any] = {"target": target, "moves": {}, "ejections": {}, "summary": f"Moved {len(spools)} -> {target}", "origin": origin}

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
                    spoolman_api.update_spool(existing['id'], {'extra': _merged_extra})

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

            p = printer_map[target]
            dest_th = (p['printer_name'], p['position'])

            # Determining the spool's ORIGIN toolhead for the pre-map
            # unmap. Filabridge is authoritative here: Spoolman can lag
            # (stale desyncs, manual edits, prior failed moves) and when
            # they disagree filabridge wins because its view is what
            # will accept or reject our map call. Fall back to the
            # Spoolman-derived snapshot only if filabridge is unreachable
            # or reports no mapping for this spool.
            fb_origin = _fb_spool_location(int(sid), fb_url)
            origin_th = fb_origin or origin_toolheads_by_spool.get(str(sid))

            # Unmap the spool's ORIGIN toolhead first so filabridge's
            # one-spool-one-toolhead invariant is satisfied before we
            # map the destination. Skip if origin == destination (the
            # already-here re-scan case) because that unmap would clear
            # the toolhead we're about to remap.
            if origin_th and origin_th != dest_th:
                ok, detail = _fb_write(origin_th[0], origin_th[1], 0, fb_url)
                fb_outcomes.append((ok, detail))
                if not ok:
                    state.add_log_entry(f"⚠️ Filabridge unmap {origin_th[0]}-{origin_th[1]} FAILED: {detail}", "ERROR", "ff4444")
                    # Abort this spool's destination map to avoid layering
                    # bad state on top of a known-bad filabridge response.
                    continue

            if spoolman_api.update_spool(sid, {"location": target, "extra": new_extra}):
                ok, detail = _fb_write(dest_th[0], dest_th[1], int(sid), fb_url)
                fb_outcomes.append((ok, detail))
                if ok:
                    state.add_log_entry(f"🖨️ {info['text']} -> {target}", "INFO", info['color'])
                else:
                    state.add_log_entry(f"⚠️ Filabridge map {target} <- #{sid} FAILED: {detail}", "ERROR", "ff4444")
        
        # DRYER MOVE
        elif target in loc_info_map and loc_info_map[target].get('Type') == 'Dryer Box':
            new_extra.pop('physical_source', None)
            # [ALEX FIX] Clean up the source slot memory too, since we are home now.
            new_extra.pop('physical_source_slot', None)
            
            if spoolman_api.update_spool(sid, {"location": target, "extra": new_extra}):
                slot_txt = f" [Slot {target_slot}]" if target_slot else ""
                state.add_log_entry(f"📦 {info['text']} -> Dryer {target}{slot_txt}", "INFO", info['color'])
            
        # GENERIC MOVE
        else:
            # [Universal Fallback Ghost Logic]
            if is_toolhead:
                 new_extra['physical_source'] = current_loc
                 new_extra['physical_source_slot'] = current_extra.get('container_slot')

            if spoolman_api.update_spool(sid, {"location": target, "extra": new_extra}):
                state.add_log_entry(f"🚚 {info['text']} -> {target}", "INFO", info['color'])

    state.UNDO_STACK.append(undo_record)

    # --- AUTO-DEPLOY CHAIN ---
    # If this move placed spool(s) into a Dryer Box slot that's bound to a
    # toolhead (extra.slot_targets[slot]), chain a second move so the spool
    # ends up ghost-deployed onto the toolhead. Filabridge gets notified
    # via the printer branch of that second call. Previously this logic
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
        if bound_toolhead:
            try:
                # Thread the spool's pre-phase-1 toolhead (snapshotted
                # above, before Spoolman was written) into phase 2 so
                # phase 2 can issue the filabridge unmap of that origin
                # toolhead before it maps the destination. Without this,
                # phase 2 would read the spool's current Spoolman location
                # (the dryer box we just wrote) and find no origin
                # toolhead, skipping the unmap — which was exactly the
                # 2026-04-22 desync. Multi-spool auto-deploy flows don't
                # exist today, so passing the first spool's origin is
                # sufficient; per-spool override would be additive later.
                first_sid = str(spools[0]) if spools else None
                first_origin_th = origin_toolheads_by_spool.get(first_sid) if first_sid else None
                origin_toolhead_loc = None
                if first_origin_th:
                    # Reverse-lookup a printer_map key for this toolhead.
                    for loc_key, p_info in printer_map.items():
                        if (p_info.get('printer_name'), p_info.get('position')) == first_origin_th:
                            origin_toolhead_loc = loc_key
                            break
                auto_deploy_result = perform_smart_move(
                    bound_toolhead, list(spools),
                    target_slot=None, origin=f'auto_deploy_from_{origin or "smart_move"}',
                    auto_deploy=False,
                    origin_toolhead=origin_toolhead_loc,
                )
                for sid in spools:
                    state.add_log_entry(
                        f"⚡ Auto-deployed Spool #{sid} → <b>{str(bound_toolhead).upper()}</b> "
                        f"(source: {target}:SLOT:{target_slot})",
                        "SUCCESS", "00ff00"
                    )
                # Bubble filabridge outcomes from phase 2 up into this
                # call's outcome list so the endpoint sees the full picture.
                if isinstance(auto_deploy_result, dict):
                    fb_outcomes.extend(auto_deploy_result.get('filabridge_outcomes', []))
            except Exception as _ad_err:
                state.logger.error(f"Auto-deploy failed for {target}:SLOT:{target_slot}: {_ad_err}")

    filabridge_ok = all(ok for ok, _ in fb_outcomes) if fb_outcomes else True
    filabridge_detail = "; ".join(d for ok, d in fb_outcomes if not ok) if not filabridge_ok else ""

    result: typing.Dict[str, typing.Any] = {
        "status": "success",
        "filabridge_ok": filabridge_ok,
        "filabridge_detail": filabridge_detail,
        "filabridge_outcomes": fb_outcomes,
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
        
    prefix = loc_id.split("-")[0]
    
    # Exclude known non-room prefixes we don't want to spawn virtual rooms for
    # PM = Polymaker portable boxes, PJ = Project Carts, TST = System Tests
    if prefix in ["TST", "TEST", "PM", "PJ"]:
        return ""
            
    return prefix

def perform_smart_eject(spool_id, confirmed_unassign=False):
    """Remove `spool_id` from its current location.

    If it's on a toolhead, the filabridge unmap ALWAYS fires — there's no
    opt-out (the old `suppress_fb_unmap` flag was a footgun that caused
    filabridge desync). Callers needing "eject without filabridge" were
    wrong to skip the unmap and have been corrected.
    """
    spool_data = spoolman_api.get_spool(spool_id)
    if not spool_data: return False

    current_location = spool_data.get('location', '').strip().upper()
    extra = spool_data.get('extra', {})

    cfg = config_loader.load_config()
    printer_map = cfg.get("printer_map", {})
    sm_url, fb_url = config_loader.get_api_urls()

    # Ensure toolhead is cleared in filabridge BEFORE we rewrite Spoolman,
    # so filabridge's one-spool-one-toolhead invariant is maintained if
    # the caller immediately reuses this toolhead.
    if current_location in printer_map:
        p = printer_map[current_location]
        ok, detail = _fb_write(p['printer_name'], p['position'], 0, fb_url)
        if not ok:
            state.add_log_entry(f"⚠️ Filabridge unmap {p['printer_name']}-{p['position']} FAILED: {detail}", "ERROR", "ff4444")
    
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
    if current_location and saved_source:
        if saved_source.strip('"').upper().startswith(current_location + "-"):
            state.logger.info(f"🛑 Bypassing Saved Source: {saved_source} is a child of {current_location}. Ejecting to Unassigned.")
            saved_source = None

    if saved_source:
        if saved_source.startswith('"'): saved_source = saved_source.strip('"') 
        
        # [ALEX FIX] Retain the assignment slot when returning home. 
        # Move the saved slot back into container_slot
        saved_slot = extra.get('physical_source_slot', '')
        if saved_slot:
            extra['container_slot'] = str(saved_slot).strip('"')
            extra['physical_source_slot'] = ""
        else:
            extra['container_slot'] = ""
            
        # Clear the source memory so we don't bounce back again later
        extra['physical_source'] = "" 
        
        if spoolman_api.update_spool(spool_id, {"location": saved_source, "extra": extra}):
            state.add_log_entry(f"↩️ Returned #{spool_id} -> {saved_source}", "WARNING")
            return True
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
    return False

def perform_force_unassign(spool_id):
    spool_data = spoolman_api.get_spool(spool_id)
    if not spool_data: return False
    extra = spool_data.get('extra', {})
    current_location = spool_data.get('location', '').strip().upper()
    
    cfg = config_loader.load_config()
    printer_map = cfg.get("printer_map", {})
    sm_url, fb_url = config_loader.get_api_urls()
    
    if current_location in printer_map:
        p = printer_map[current_location]
        ok, detail = _fb_write(p['printer_name'], p['position'], 0, fb_url)
        if not ok:
            state.add_log_entry(f"⚠️ Filabridge unmap {p['printer_name']}-{p['position']} FAILED: {detail}", "ERROR", "ff4444")

    # [ALEX FIX] Explicitly overwrite slots and sources with empty strings
    # to guarantee Spoolman API removes them instead of ignoring dropped keys
    extra['container_slot'] = ""
    extra['physical_source'] = ""
    extra['physical_source_slot'] = ""

    if spoolman_api.update_spool(spool_id, {"location": "", "extra": extra}):
        state.add_log_entry(f"🗑️ Force Unassigned #{spool_id}", "WARNING")
        return True
    return False

def perform_undo():
    if not state.UNDO_STACK: return {"success": False, "msg": "History empty."}
    last = state.UNDO_STACK.pop()
    moves = last['moves']
    target = last.get('target')
    origin = last.get('origin', '')
    cfg = config_loader.load_config(); printer_map = cfg.get("printer_map", {})
    sm_url, fb_url = config_loader.get_api_urls()
    
    # UNDO ordering: unmap the target toolhead FIRST so filabridge sees it
    # free, then reassign each moved spool back to its origin (which may
    # itself be a toolhead — remap happens after the Spoolman write).
    if target in printer_map:
        p = printer_map[target]
        ok, detail = _fb_write(p['printer_name'], p['position'], 0, fb_url)
        if not ok:
            state.add_log_entry(f"⚠️ Undo: Filabridge unmap {p['printer_name']}-{p['position']} FAILED: {detail}", "ERROR", "ff4444")

    for sid, loc in moves.items():
        requests.patch(f"{sm_url}/api/v1/spool/{sid}", json={"location": loc})
        if loc in printer_map:
            p = printer_map[loc]
            ok, detail = _fb_write(p['printer_name'], p['position'], int(sid), fb_url)
            if not ok:
                state.add_log_entry(f"⚠️ Undo: Filabridge map {loc} <- #{sid} FAILED: {detail}", "ERROR", "ff4444")
    # [ALEX FIX] Revert Smart Ejections
    ejections = last.get('ejections', {})
    for ejected_sid, original_loc in ejections.items():
        requests.patch(f"{sm_url}/api/v1/spool/{ejected_sid}", json={"location": original_loc})
        if original_loc in printer_map:
            p = printer_map[original_loc]
            ok, detail = _fb_write(p['printer_name'], p['position'], int(ejected_sid), fb_url)
            if not ok:
                state.add_log_entry(f"⚠️ Undo: Filabridge remap {original_loc} <- #{ejected_sid} FAILED: {detail}", "ERROR", "ff4444")
            
            
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
                    
    state.add_log_entry(f"↩️ Undid: {last['summary']}", "WARNING")
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
            
            summary = "📝 <b>Audit Report:</b><br>"
            if not missing and not session['rogue_items']:
                summary += "✅ Perfect Match! All items accounted for."
                color = "00ff00" # Green
            else:
                color = "ffaa00" # Orange
                if missing: summary += f"❌ <b>Missing:</b> {', '.join(map(str, missing))}<br>"
                if session['rogue_items']: summary += f"⚠️ <b>Extra:</b> {', '.join(map(str, session['rogue_items']))}"
            
            state.add_log_entry(summary, "INFO", color)
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
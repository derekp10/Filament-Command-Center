import re
import typing
import urllib.parse
import requests
import state
import config_loader
import spoolman_api
import locations_db

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

    # 4. DIRECT SPOOL ID
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
        # Priority 1: Legacy Spool
        rid = spoolman_api.find_spool_by_legacy_id(text, strict_mode=True)
        if rid: return {'type': 'spool', 'id': rid}
        
        # Priority 2: Legacy Filament
        fid = spoolman_api.find_filament_by_legacy_id(text)
        if fid: return {'type': 'filament', 'id': fid}
        
        # Priority 3: Direct Spool ID
        spool_check = spoolman_api.get_spool(text)
        if spool_check and spool_check.get('id'):
            return {'type': 'spool', 'id': int(text)}

        # Priority 4: Direct Filament ID
        fil_check = spoolman_api.get_filament(text)
        if fil_check and fil_check.get('id'):
            return {'type': 'filament', 'id': int(text)}
        
        return {'type': 'error', 'msg': 'ID Not Found'}
        
    # 8. LEGACY LOCATION FALLBACK (Len > 2)
    # Only accepts a "random string" if it matches a known location in DB.
    if len(text) > 2: 
        loc_list = locations_db.load_locations_list()
        valid_ids = {row['LocationID'].upper() for row in loc_list}
        
        if text.upper() in valid_ids:
            return {'type': 'location', 'id': text.upper()}
        else:
            return {'type': 'error', 'msg': 'Unknown Code (Use LOC: prefix)'}
        
    return {'type': 'error', 'msg': 'Unknown Code'}

def perform_smart_move(target, raw_spools, target_slot=None, origin=''):
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
                    # [ALEX FIX] Explicitly set to empty string to ensure DB update
                    spoolman_api.update_spool(existing['id'], {'extra': {'container_slot': ''}})
            
            new_extra['container_slot'] = str(target_slot)
        else:
            # If moving to a non-slotted location, clear the slot
            new_extra['container_slot'] = ""

        # PRINTER MOVE
        if target in printer_map:
            src_info = loc_info_map.get(current_loc)
            if src_info and src_info.get('Type') == 'Dryer Box':
                new_extra['physical_source'] = current_loc
                # [ALEX FIX] Save the slot! This was missing, causing the "Missing Ghost" bug.
                new_extra['physical_source_slot'] = current_extra.get('container_slot')
            
            if spoolman_api.update_spool(sid, {"location": target, "extra": new_extra}):
                p = printer_map[target]
                try:
                    requests.post(f"{fb_url}/map_toolhead", 
                                  json={"printer_name": p['printer_name'], "toolhead_id": p['position'], "spool_id": int(sid)}, timeout=3)
                except: pass
                state.add_log_entry(f"🖨️ {info['text']} -> {target}", "INFO", info['color'])
        
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
            # [ALEX FIX] Ghost Logic: If moving Dryer -> Tool, leave a breadcrumb (Source + Slot)
            # We only do this if the target is a "Consumer" (Tool/MMU), not just a random cart.
            if loc_info_map.get(current_loc, {}).get('Type') == 'Dryer Box' and is_toolhead:
                 new_extra['physical_source'] = current_loc
                 new_extra['physical_source_slot'] = current_extra.get('container_slot')

            if spoolman_api.update_spool(sid, {"location": target, "extra": new_extra}):
                state.add_log_entry(f"🚚 {info['text']} -> {target}", "INFO", info['color'])

    state.UNDO_STACK.append(undo_record)
    return {"status": "success"}

def perform_smart_eject(spool_id):
    spool_data = spoolman_api.get_spool(spool_id)
    if not spool_data: return False
    
    current_location = spool_data.get('location', '').strip().upper()
    extra = spool_data.get('extra', {})
    
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

    if saved_source:
        if saved_source.startswith('"'): saved_source = saved_source.strip('"') 
        # Clear the source memory so we don't bounce back again later
        extra['physical_source'] = "" 
        
        if spoolman_api.update_spool(spool_id, {"location": saved_source, "extra": extra}):
            state.add_log_entry(f"↩️ Returned #{spool_id} -> {saved_source}", "WARNING")
            return True
    else:
        if spoolman_api.update_spool(spool_id, {"location": "", "extra": extra}):
            state.add_log_entry(f"⏏️ Ejected #{spool_id}", "WARNING")
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
    
    if target in printer_map:
        p = printer_map[target]
        try:
            requests.post(f"{fb_url}/map_toolhead", 
                          json={"printer_name": p['printer_name'], "toolhead_id": p['position'], "spool_id": 0})
        except: pass
        
    for sid, loc in moves.items():
        requests.patch(f"{sm_url}/api/v1/spool/{sid}", json={"location": loc})
        if loc in printer_map:
            p = printer_map[loc]
            try: requests.post(f"{fb_url}/map_toolhead", 
                              json={"printer_name": p['printer_name'], "toolhead_id": p['position'], "spool_id": int(sid)})
            except: pass
    # [ALEX FIX] Revert Smart Ejections
    ejections = last.get('ejections', {})
    for ejected_sid, original_loc in ejections.items():
        requests.patch(f"{sm_url}/api/v1/spool/{ejected_sid}", json={"location": original_loc})
        if original_loc in printer_map:
            p = printer_map[original_loc]
            try: requests.post(f"{fb_url}/map_toolhead", 
                               json={"printer_name": p['printer_name'], "toolhead_id": p['position'], "spool_id": int(ejected_sid)})
            except: pass
            
            
    # [ALEX FIX] Restore to Buffer Memory
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
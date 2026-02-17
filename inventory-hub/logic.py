import re
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

    # COMMAND HANDLING
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
        
        # SLOT
        if "CMD:SLOT:" in upper_text:
            try:
                parts = upper_text.split(':')
                val = parts[-1].strip()
                if val.isdigit(): return {'type': 'command', 'cmd': 'slot', 'value': val}
            except: pass
        
        # AUDIT
        if "CMD:AUDIT" in upper_text: return {'type': 'command', 'cmd': 'audit'}
        
        # SLOT ASSIGNMENT (LOC:x:SLOT:y)
        if "LOC:" in upper_text and ":SLOT:" in upper_text:
            try:
                # robust parsing for LOC:NAME:SLOT:1
                parts = upper_text.split(':')
                if 'LOC' in parts and 'SLOT' in parts:
                    loc_idx = parts.index('LOC')
                    slot_idx = parts.index('SLOT')
                    if slot_idx > loc_idx:
                        loc_val = parts[loc_idx+1]
                        slot_val = parts[slot_idx+1]
                        return {'type': 'assignment', 'location': loc_val, 'slot': slot_val}
            except: pass

        return {'type': 'error', 'msg': 'Malformed Command'}

    # [ALEX FIX] EXPLICIT LOCATION SCAN (LOC: Prefix)
    # This prevents accidental manual entries unless they explicitly start with LOC:
    if upper_text.startswith("LOC:"):
        # Strip the prefix and use the rest as the ID
        clean_loc = upper_text[4:].strip()
        if clean_loc:
             return {'type': 'location', 'id': clean_loc}
        return {'type': 'error', 'msg': 'Empty Location Code'}

    # DIRECT SPOOL ID
    if upper_text.startswith("ID:") or upper_text.startswith("SPL:"):
        # Normalize SPL: to just ID logic
        prefix_len = 3 if upper_text.startswith("ID:") else 4
        clean_id = text[prefix_len:].strip()
        if clean_id.isdigit(): return {'type': 'spool', 'id': int(clean_id)}
        return {'type': 'error', 'msg': 'Invalid Spool ID Format'}

    # NEW: FILAMENT DEFINITION ID
    if upper_text.startswith("FIL:"):
        clean_id = text[4:].strip()
        if clean_id.isdigit(): return {'type': 'filament', 'id': int(clean_id)}
        return {'type': 'error', 'msg': 'Invalid Filament ID Format'}

    # LEGACY / URL PARSING
    if any(x in text.lower() for x in ['http', 'www.', '.com', 'google', '/', '\\', '{', '}', '[', ']']):
        m = re.search(r'range=(\d+)', decoded, re.IGNORECASE)
        if m:
            rid = spoolman_api.find_spool_by_legacy_id(m.group(1), strict_mode=True)
            if rid: return {'type': 'spool', 'id': rid}
        rid = spoolman_api.find_spool_by_legacy_id(text, strict_mode=True)
        if rid: return {'type': 'spool', 'id': rid}
        return {'type': 'error', 'msg': 'Unknown/Invalid Link'}

    # PURE NUMBER SCAN (Priority Stack)
    if text.isdigit():
        # 1. PRIORITY: Legacy Spool Match
        rid = spoolman_api.find_spool_by_legacy_id(text, strict_mode=True)
        if rid: return {'type': 'spool', 'id': rid}
        
        # 2. PRIORITY: Legacy Filament Match
        fid = spoolman_api.find_filament_by_legacy_id(text)
        if fid: return {'type': 'filament', 'id': fid}
        
        # 3. FALLBACK: Direct Spool ID
        spool_check = spoolman_api.get_spool(text)
        if spool_check and spool_check.get('id'):
            return {'type': 'spool', 'id': int(text)}

        # 4. FALLBACK: Direct Filament ID
        fil_check = spoolman_api.get_filament(text)
        if fil_check and fil_check.get('id'):
            return {'type': 'filament', 'id': int(text)}
        
        return {'type': 'error', 'msg': 'ID Not Found'}
        
    # [ALEX FIX] LEGACY LOCATION FALLBACK (With Validation)
    # Only accept a "random string" as a location IF it exists in the DB.
    # This stops typos (e.g. "Spool") from becoming location "SPOOL".
    if len(text) > 2: 
        # Check against known locations
        loc_list = locations_db.load_locations_list()
        # Create a set of valid IDs for fast lookup
        valid_ids = {row['LocationID'].upper() for row in loc_list}
        
        if text.upper() in valid_ids:
            return {'type': 'location', 'id': text.upper()}
        else:
            return {'type': 'error', 'msg': 'Unknown Code (Use LOC: prefix)'}
        
    return {'type': 'error', 'msg': 'Unknown Code'}

def perform_smart_move(target, raw_spools, target_slot=None):
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
    
    if is_printer or is_toolhead:
        # Check if anyone is already home
        residents = spoolman_api.get_spools_at_location(target)
        for rid in residents:
            # Don't eject the spool we are currently trying to move (if it's already there)
            if str(rid) not in [str(s) for s in spools]:
                state.add_log_entry(f"⚠️ <b>Smart Load:</b> Ejecting #{rid} from {target}...", "WARNING")
                perform_smart_eject(rid)
    # ----------------------------------------------

    undo_record = {"target": target, "moves": {}, "summary": f"Moved {len(spools)} -> {target}"}

    for sid in spools:
        spool_data = spoolman_api.get_spool(sid)
        if not spool_data: continue
        current_loc = spool_data.get('location', '').strip().upper()
        undo_record['moves'][sid] = current_loc
        current_extra = spool_data.get('extra') or {}
        info = spoolman_api.format_spool_display(spool_data)
        
        new_extra = current_extra.copy()
        
        # Handle Slot Assignment
        if target_slot:
            existing_items = spoolman_api.get_spools_at_location_detailed(target)
            for existing in existing_items:
                if str(existing.get('slot', '')).strip('"') == str(target_slot) and existing['id'] != int(sid):
                    state.logger.info(f"🪑 Unseating Spool {existing['id']} from Slot {target_slot}")
                    spoolman_api.update_spool(existing['id'], {'extra': {'container_slot': ''}})
            new_extra['container_slot'] = str(target_slot)
        else:
            # If moving to a non-slotted location, clear the slot
            new_extra.pop('container_slot', None)

        # PRINTER MOVE
        if target in printer_map:
            src_info = loc_info_map.get(current_loc)
            if src_info and src_info.get('Type') == 'Dryer Box':
                new_extra['physical_source'] = current_loc
            
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
            if spoolman_api.update_spool(sid, {"location": target, "extra": new_extra}):
                slot_txt = f" [Slot {target_slot}]" if target_slot else ""
                state.add_log_entry(f"📦 {info['text']} -> Dryer {target}{slot_txt}", "INFO", info['color'])
            
        # GENERIC MOVE
        else:
            if spoolman_api.update_spool(sid, {"location": target, "extra": new_extra}):
                state.add_log_entry(f"🚚 {info['text']} -> {target}", "INFO", info['color'])

    state.UNDO_STACK.append(undo_record)
    return {"status": "success"}

def perform_smart_eject(spool_id):
    spool_data = spoolman_api.get_spool(spool_id)
    if not spool_data: return False
    
    extra = spool_data.get('extra', {})
    saved_source = extra.get('physical_source')
    
    extra.pop('container_slot', None)
    
    if saved_source:
        if saved_source.startswith('"'): saved_source = saved_source.strip('"') 
        extra.pop('physical_source', None) 
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
    last = state.UNDO_STACK.pop(); moves = last['moves']; target = last.get('target')
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
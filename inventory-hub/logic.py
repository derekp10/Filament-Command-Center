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
        return {'type': 'error', 'msg': 'Malformed Command'}

    # DIRECT ID
    if upper_text.startswith("ID:"):
        clean_id = text[3:].strip()
        if clean_id.isdigit(): return {'type': 'spool', 'id': int(clean_id)}
        return {'type': 'error', 'msg': 'Invalid Spool ID Format'}

    # LEGACY / URL PARSING
    if any(x in text.lower() for x in ['http', 'www.', '.com', 'google', '/', '\\', '{', '}', '[', ']']):
        m = re.search(r'range=(\d+)', decoded, re.IGNORECASE)
        if m:
            rid = spoolman_api.find_spool_by_legacy_id(m.group(1), strict_mode=True)
            if rid: return {'type': 'spool', 'id': rid}
        rid = spoolman_api.find_spool_by_legacy_id(text, strict_mode=True)
        if rid: return {'type': 'spool', 'id': rid}
        return {'type': 'error', 'msg': 'Unknown/Invalid Link'}

    if text.isdigit():
        rid = spoolman_api.find_spool_by_legacy_id(text, strict_mode=False)
        if rid: return {'type': 'spool', 'id': rid}
        return {'type': 'spool', 'id': int(text)}
        
    if len(text) > 2: 
        return {'type': 'location', 'id': text.upper()}
        
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
import requests # type: ignore
import state # type: ignore
import config_loader # type: ignore

# Constants for JSON sanitation
# [ALEX FIX] Added 'physical_source_slot', and 'product_url' to ensure strict JSON string formatting
JSON_STRING_FIELDS = ["spool_type", "container_slot", "physical_source", "physical_source_slot", "original_color", "spool_temp", "product_url"]

def get_spool(sid):
    sm_url, _ = config_loader.get_api_urls()
    try: return requests.get(f"{sm_url}/api/v1/spool/{sid}", timeout=3).json()
    except: return None

def get_all_locations():
    """Fetches all locations from Spoolman."""
    sm_url, _ = config_loader.get_api_urls()
    try: 
        resp = requests.get(f"{sm_url}/api/v1/location", timeout=3)
        if resp.ok:
            return resp.json()
        return []
    except: 
        return []

def get_filament(fid):
    """Fetches a specific filament definition."""
    sm_url, _ = config_loader.get_api_urls()
    try: return requests.get(f"{sm_url}/api/v1/filament/{fid}", timeout=3).json()
    except: return None

def sanitize_outbound_data(data):
    """Ensures extra fields are properly formatted as JSON strings for Spoolman."""
    if 'extra' not in data or not data['extra']: return data
    clean_extra = {}
    for key, value in data['extra'].items(): # type: ignore
        if value is None: continue 
        if type(value) is bool:
            clean_extra[key] = "true" if value else "false"
        elif key in JSON_STRING_FIELDS:
            val_str = str(value).strip()
            if not (val_str.startswith('"') and val_str.endswith('"')):
                clean_extra[key] = f'"{val_str}"'
            else:
                clean_extra[key] = val_str
        else:
            val_str = str(value)
            if val_str.lower() == 'false': clean_extra[key] = "false"
            elif val_str.lower() == 'true': clean_extra[key] = "true"
            else: clean_extra[key] = val_str
    data['extra'] = clean_extra
    return data

def update_spool(sid, data):
    sm_url, _ = config_loader.get_api_urls()
    try:
        # [ALEX FIX] Intercept "UNASSIGNED" and coerce into empty string for Spoolman API
        if 'location' in data and isinstance(data['location'], str):
            if data['location'].strip().upper() == 'UNASSIGNED':
                data['location'] = ''
                
        clean_data = sanitize_outbound_data(data)
        r = requests.patch(f"{sm_url}/api/v1/spool/{sid}", json=clean_data)
        if r.ok: return r.json()
        state.logger.error(f"Failed to update spool {sid}: {r.status_code} - {r.text}")
    except Exception as e:
        state.logger.error(f"API Error updating spool {sid}: {e}")
    return None

def create_spool(data):
    """Creates a new spool via POST to Spoolman."""
    sm_url, _ = config_loader.get_api_urls()
    try:
        if 'location' in data and isinstance(data['location'], str):
            if data['location'].strip().upper() == 'UNASSIGNED':
                data['location'] = ''
        
        clean_data = sanitize_outbound_data(data)
        r = requests.post(f"{sm_url}/api/v1/spool", json=clean_data, timeout=5)
        if r.ok:
            return r.json()
        state.logger.error(f"Failed to create spool: {r.status_code} - {r.text}")
    except Exception as e:
        state.logger.error(f"API Error creating spool: {e}")
    return None

def update_filament(fid, data):
    sm_url, _ = config_loader.get_api_urls()
    sanitized = sanitize_outbound_data(data)
    try:
        r = requests.patch(f"{sm_url}/api/v1/filament/{fid}", json=sanitized, timeout=2)
        if r.ok: return r.json()
        state.logger.error(f"Failed to update filament {fid}: {r.status_code} - {r.text}")
    except Exception as e:
        state.logger.error(f"API Error updating filament {fid}: {e}")
    return None

def create_filament(data):
    """Creates a new filament via POST to Spoolman."""
    sm_url, _ = config_loader.get_api_urls()
    sanitized = sanitize_outbound_data(data)
    try:
        r = requests.post(f"{sm_url}/api/v1/filament", json=sanitized, timeout=5)
        if r.ok: 
            return r.json()
        state.logger.error(f"Failed to create filament: {r.status_code} - {r.text}")
    except Exception as e:
        state.logger.error(f"API Error creating filament: {e}")
    return None

def get_vendors():
    """Fetches the list of all vendors from Spoolman."""
    sm_url, _ = config_loader.get_api_urls()
    try:
        r = requests.get(f"{sm_url}/api/v1/vendor", timeout=5)
        if r.ok:
            return r.json()
    except Exception as e:
        state.logger.error(f"API Error fetching vendors: {e}")
    return []

def create_vendor(data):
    """Creates a brand new vendor via POST to Spoolman."""
    sm_url, _ = config_loader.get_api_urls()
    sanitized = sanitize_outbound_data(data)
    try:
        r = requests.post(f"{sm_url}/api/v1/vendor", json=sanitized, timeout=5)
        if r.ok:
            return r.json()
        state.logger.error(f"Failed to create vendor: {r.status_code} - {r.text}")
    except Exception as e:
        state.logger.error(f"API Error creating vendor: {e}")
    return None

def update_extra_field_choices(entity_type, key, new_choices):
    """Pulls existing field config, appends new choices, and PUTs back to Spoolman."""
    sm_url, _ = config_loader.get_api_urls()
    try:
        r = requests.get(f"{sm_url}/api/v1/field/{entity_type}", timeout=5)
        if r.ok:
            fields = r.json()
            target = next((f for f in fields if f['key'] == key), None)
            if target and 'choices' in target:
                updated_choices = list(set(target['choices'] + new_choices))
                updated_choices.sort()
                
                # PUT requires all required config parameters, not just the choices delta
                payload = {
                    "name": target["name"],
                    "field_type": target["field_type"],
                    "multi_choice": target.get("multi_choice", False),
                    "choices": updated_choices
                }
                
                post_r = requests.post(f"{sm_url}/api/v1/field/{entity_type}/{key}", json=payload, timeout=5)
                if post_r.ok:
                    return {"success": True, "msg": "Choices updated"}
                else:
                    return {"success": False, "msg": f"POST failed: {post_r.text}"}
            else:
                return {"success": False, "msg": "Field key not found or doesn't support choices"}
    except Exception as e:
        state.logger.error(f"API Error updating field choices: {e}")
        return {"success": False, "msg": str(e)}

def format_spool_display(spool_data):
    """Creates the text and color for the UI."""
    try:
        sid = spool_data.get('id', '?')
        # Legacy ID Check
        ext_id = str(spool_data.get('external_id', '')).replace('"', '').strip()
        if not ext_id or ext_id.lower() == 'none':
            fil_data = spool_data.get('filament', {})
            ext_id = str(fil_data.get('external_id', '')).replace('"', '').strip()
            if ext_id.lower() == 'none': ext_id = ""

        rem = int(spool_data.get('remaining_weight', 0) or 0)
        fil = spool_data.get('filament')
        extra = spool_data.get('extra', {})
        slot = extra.get('container_slot', '')
        if slot: slot = slot.strip('"')

        if not fil:
            return {"text": f"#{sid} [No Filament Data]", "color": "888888", "slot": slot}

        vendor_obj = fil.get('vendor')
        brand = vendor_obj.get('name', 'Generic') if vendor_obj else 'Generic'
        mat = fil.get('material', 'PLA')
        
        fil_extra = fil.get('extra') or {}
        col_name = fil_extra.get('original_color')
        if not col_name: col_name = fil.get('name', 'Unknown')

        parts = [f"#{sid}"]
        if ext_id: parts.append(f"[Legacy: {ext_id}]")
        parts.append(brand)
        parts.append(mat)
        parts.append(f"({col_name})")
        parts.append(f"[{rem}g]")

        display_text = " ".join(parts)
        
        # Color Logic
        multi_hex = fil.get('multi_color_hexes')
        if multi_hex:
            final_color = multi_hex 
        else:
            final_color = fil.get('color_hex', 'ffffff')

        return {
            "text": display_text, 
            "color": final_color, 
            "slot": slot,
            "details": {
                "id": sid,
                "brand": brand,
                "material": mat,
                "color_name": col_name,
                "weight": rem,
                "temp": f"{fil.get('settings_extruder_temp', '')}°C" if fil.get('settings_extruder_temp') else ""
            }
        }

    except Exception as e:
        state.logger.error(f"Format Error: {e}")
        return {"text": f"#{spool_data.get('id', '?')} Error", "color": "ff0000", "slot": ""}

def get_spools_at_location_detailed(loc_name):
    sm_url, _ = config_loader.get_api_urls()
    found = []
    # [ALEX FIX] Handle Unassigned (No Location)
    check_unassigned = (str(loc_name).upper() == 'UNASSIGNED')
    target_loc_upper = str(loc_name).upper()

    try:
        resp = requests.get(f"{sm_url}/api/v1/spool", timeout=5)
        if resp.ok:
            for s in resp.json():
                sloc = s.get('location', '').strip()
                extra = s.get('extra', {})
                match = False
                is_ghost = False
                ghost_slot = None
                
                # 1. Direct Location Match
                if check_unassigned:
                    if not sloc: match = True
                elif sloc.upper() == target_loc_upper:
                    match = True
                    
                # 2. [ALEX FIX] Physical Source Match (The Ghost Logic)
                # Strip the literal quotes that Spoolman adds to JSON String Fields!
                if not match and not check_unassigned:
                    p_source = str(extra.get('physical_source', '')).strip().upper().replace('"', '')
                    if p_source == target_loc_upper:
                        match = True
                        is_ghost = True
                        # Strip quotes from the slot too!
                        ghost_slot = str(extra.get('physical_source_slot', '')).strip('"')

                if match:
                    info = format_spool_display(s)
                    
                    # [ALEX FIX] If Ghost, override the slot so it appears in the grid correctly
                    final_slot = info['slot']
                    if is_ghost and ghost_slot:
                        final_slot = ghost_slot

                    found.append({
                        'id': s['id'], 
                        'display': info['text'], 
                        'color': info['color'], 
                        'slot': final_slot,
                        'is_ghost': is_ghost,             # Flag for UI
                        'deployed_to': sloc if is_ghost else None # Where is it really?
                    })
    except: pass
    return found

def get_spools_at_location(loc_name):
    return [s['id'] for s in get_spools_at_location_detailed(loc_name)]

def find_spool_by_legacy_id(legacy_id, strict_mode=False):
    """Finds a spool based on the Filament's legacy ID."""
    sm_url, _ = config_loader.get_api_urls()
    legacy_id = str(legacy_id).strip()
    try:
        fil_resp = requests.get(f"{sm_url}/api/v1/filament", timeout=5)
        target_filament_id = None
        if fil_resp.ok:
            for fil in fil_resp.json():
                ext = str(fil.get('external_id', '')).strip().replace('"','')
                if ext == legacy_id:
                    target_filament_id = fil['id']
                    break
        if target_filament_id:
            spool_resp = requests.get(f"{sm_url}/api/v1/spool", timeout=5)
            if spool_resp.ok:
                candidates = []
                for spool in spool_resp.json():
                    if spool.get('filament', {}).get('id') == target_filament_id:
                        if (spool.get('remaining_weight') or 0) > 10:
                            return spool['id']
                        candidates.append(spool['id'])
                if candidates: return candidates[0]
                if strict_mode: return None
        
        # FIX: Removed the "Blind Direct ID" check here.
        # Direct IDs are now handled explicitly in logic.py
        
    except Exception as e: state.logger.error(f"Legacy Spool Lookup Error: {e}")
    return None

def find_filament_by_legacy_id(legacy_id):
    """Finds a filament definition directly by legacy ID."""
    sm_url, _ = config_loader.get_api_urls()
    legacy_id = str(legacy_id).strip()
    try:
        resp = requests.get(f"{sm_url}/api/v1/filament", timeout=5)
        if resp.ok:
            for fil in resp.json():
                ext = str(fil.get('external_id', '')).strip().replace('"','')
                if ext == legacy_id:
                    return fil['id']
    except Exception as e: state.logger.error(f"Legacy Filament Lookup Error: {e}")
    return None
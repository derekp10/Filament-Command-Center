import requests # type: ignore
import state # type: ignore
import config_loader # type: ignore
import json

def parse_inbound_data(data):
    """Recursively intercepts data incoming from Spoolman and deserializes JSON strings safely."""
    if isinstance(data, list):
        for item in data:
            parse_inbound_data(item)
    elif isinstance(data, dict):
        if 'extra' in data and isinstance(data['extra'], dict):
            for key, value in data['extra'].items():
                if isinstance(value, str):
                    try:
                        parsed = json.loads(value)
                        data['extra'][key] = parsed
                    except ValueError:
                        pass
        if 'filament' in data and isinstance(data['filament'], dict):
            parse_inbound_data(data['filament'])
    return data

# Constants for JSON sanitation
# [ALEX FIX] Added 'physical_source_slot', and 'product_url' to ensure strict JSON string formatting
JSON_STRING_FIELDS = ["spool_type", "container_slot", "physical_source", "physical_source_slot", "original_color", "spool_temp", "product_url", "purchase_url"]

# Captures the last Spoolman non-ok response body so callers like
# api_update_filament can surface the actual rejection reason to the UI
# instead of returning a generic "rejected" message. Reset on each successful
# call. Kept module-global rather than threaded through every return signature
# so existing callers (which check `if result:`) keep working unchanged.
LAST_SPOOLMAN_ERROR = None

def get_spool(sid):
    sm_url, _ = config_loader.get_api_urls()
    try: return parse_inbound_data(requests.get(f"{sm_url}/api/v1/spool/{sid}", timeout=3).json())
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
    try: return parse_inbound_data(requests.get(f"{sm_url}/api/v1/filament/{fid}", timeout=3).json())
    except: return None

def sanitize_outbound_data(data):
    """Ensures extra fields are properly formatted as JSON strings for Spoolman."""
    if 'extra' not in data or not data['extra']: return data
    clean_extra = {}
    for key, value in data['extra'].items(): # type: ignore
        if value is None: continue 
        if isinstance(value, bool):
            clean_extra[key] = "true" if value else "false"
        elif isinstance(value, (int, float, list, dict)):
            clean_extra[key] = json.dumps(value)
        elif isinstance(value, str):
            val_str = value.strip()
            if val_str.lower() == 'true':
                clean_extra[key] = "true"
            elif val_str.lower() == 'false':
                clean_extra[key] = "false"
            elif key in JSON_STRING_FIELDS:
                # [ALEX FIX] bypass json.loads() for specifically strict string fields (like container_slot)
                # to prevent numbers inside strings like "4" from becoming integer 4 and breaking Spoolman's DB constraints.
                clean_extra[key] = json.dumps(val_str)
            else:
                # [ALEX FIX] Spoolman strictly requires that *all* custom Extra fields, even plain strings, 
                # be sent as valid JSON strings. This means they must include the literal double-quotes.
                # A value of `Basic` will fail, but `"Basic"` will pass.
                try:
                    # If it's already a valid JSON object/array/number/quoted-string, leave it
                    json.loads(val_str)
                    clean_extra[key] = val_str
                except ValueError:
                    # If it's a naked string, wrap it in double quotes via json.dumps
                    clean_extra[key] = json.dumps(val_str)
        else:
            clean_extra[key] = json.dumps(str(value))
    data['extra'] = clean_extra
    return data

def _auto_archive_on_empty(data, existing_initial, existing_used):
    """Mutates `data` in-place to add {archived: True, location: ''} when the
    post-update state would leave remaining_weight at 0 (or below).

    Called from update_spool and create_spool so any path that empties a spool
    (weigh-out, wizard edit, slurp-in from CSV, etc.) automatically archives
    and unassigns it — per the user's 2026-04-22 answer of "Auto" on the
    archive-on-zero backlog item.

    The caller's explicit intent always wins: if the payload already sets
    `archived` or `location`, we leave those keys alone.
    """
    if 'used_weight' not in data and 'initial_weight' not in data:
        return  # nothing weight-related in this update
    new_used = data.get('used_weight', existing_used)
    new_initial = data.get('initial_weight', existing_initial)
    if new_used is None or new_initial is None:
        return
    try:
        remaining = float(new_initial) - float(new_used)
    except (TypeError, ValueError):
        return
    if remaining > 0:
        return
    # Only inject the auto-settings if the caller didn't provide them.
    if 'archived' not in data:
        data['archived'] = True
    if 'location' not in data:
        data['location'] = ''


def update_spool(sid, data):
    sm_url, _ = config_loader.get_api_urls()
    try:
        # [ALEX FIX] Intercept "UNASSIGNED" and coerce into empty string for Spoolman API
        if 'location' in data and isinstance(data['location'], str):
            if data['location'].strip().upper() == 'UNASSIGNED':
                data['location'] = ''

        # Fetch the existing spool once — used for the used_weight cap AND the
        # auto-archive-on-empty check below. Cheaper than two round-trips.
        existing = get_spool(sid) or {}

        # [ALEX FIX] Ensure used_weight never crashes SQLAlchemy due to constraint by artificially capping to initial_weight
        if 'used_weight' in data:
            current_initial = data.get('initial_weight', existing.get('initial_weight'))
            if current_initial is not None and data['used_weight'] > current_initial:
                state.logger.warning(f"Capping used_weight {data['used_weight']} to initial_weight {current_initial} for Spool {sid}")
                data['used_weight'] = current_initial

        # Auto-archive + unassign when remaining weight hits 0.
        pre_archived = existing.get('archived', False)
        _auto_archive_on_empty(data, existing.get('initial_weight'), existing.get('used_weight'))
        if data.get('archived') and not pre_archived:
            try:
                state.add_log_entry(
                    f"📦 Auto-archived Spool #{sid} (remaining weight hit 0) — moved to UNASSIGNED",
                    "INFO", "00ccff",
                )
            except Exception:
                pass

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
                
        # [ALEX FIX] Ensure used_weight never crashes SQLAlchemy due to constraint on creation
        if 'used_weight' in data and 'initial_weight' in data:
            if data['used_weight'] > data['initial_weight']:
                state.logger.warning(f"Capping used_weight {data['used_weight']} to initial_weight {data['initial_weight']} during creation.")
                data['used_weight'] = data['initial_weight']
        
        clean_data = sanitize_outbound_data(data)
        r = requests.post(f"{sm_url}/api/v1/spool", json=clean_data, timeout=5)
        if r.ok:
            return r.json()
        state.logger.error(f"Failed to create spool: {r.status_code} - {r.text}")
    except Exception as e:
        state.logger.error(f"API Error creating spool: {e}")
    return None

def update_filament(fid, data):
    """Returns the updated filament dict on success, or None on failure.
    The last Spoolman error message is stashed in module-global
    LAST_SPOOLMAN_ERROR for callers that want to surface the actual
    rejection reason to the UI (see api_update_filament)."""
    global LAST_SPOOLMAN_ERROR
    sm_url, _ = config_loader.get_api_urls()
    sanitized = sanitize_outbound_data(data)
    try:
        r = requests.patch(f"{sm_url}/api/v1/filament/{fid}", json=sanitized, timeout=2)
        if r.ok:
            LAST_SPOOLMAN_ERROR = None
            return r.json()
        err_body = r.text
        state.logger.error(f"Failed to update filament {fid}: {r.status_code} - {err_body}")
        LAST_SPOOLMAN_ERROR = f"HTTP {r.status_code}: {err_body[:400]}"
    except Exception as e:
        state.logger.error(f"API Error updating filament {fid}: {e}")
        LAST_SPOOLMAN_ERROR = str(e)[:400]
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

def get_materials() -> list[str]:
    """Fetches a unique list of all materials across all filaments from Spoolman."""
    sm_url, _ = config_loader.get_api_urls()
    materials = set()
    try:
        r = requests.get(f"{sm_url}/api/v1/filament", timeout=5)
        if r.ok:
            for fil in r.json():
                mat = fil.get("material")
                if mat:
                    materials.add(mat)
    except Exception as e:
        state.logger.error(f"API Error fetching materials: {e}")
    return sorted(list(materials))

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
        brand = str(brand).strip()
        
        mat = fil.get('material', 'PLA')
        mat = str(mat).strip().upper()
        
        fil_extra = fil.get('extra') or {}
        
        raw_attrs = fil_extra.get('filament_attributes', '[]')
        try:
            attrs_list = json.loads(raw_attrs) if isinstance(raw_attrs, str) else raw_attrs
            if not isinstance(attrs_list, list): attrs_list = []
        except: attrs_list = []
        clean_attrs = [str(a).strip().strip('"').strip("'") for a in attrs_list if a]
        smart_mat = f"{' '.join(clean_attrs)} {mat}".strip() if clean_attrs else mat
        
        col_name = fil_extra.get('original_color')
        if not col_name: col_name = fil.get('name', 'Unknown')
        if col_name: col_name = str(col_name).strip().title()

        parts = [f"#{sid}"]
        if ext_id: parts.append(f"[Legacy: {ext_id}]")
        parts.append(brand)
        parts.append(mat)
        parts.append(f"({col_name})")

        display_text = " ".join(parts)
        
        # [ALEX FIX] Generate a clean, non-redundant string for the new rich UI cards
        display_short = f"{brand} {mat} ({col_name})"
        
        # Color Logic
        multi_hex = fil.get('multi_color_hexes')
        if multi_hex:
            final_color = multi_hex 
        else:
            final_color = fil.get('color_hex', 'ffffff')
            
        direction = fil.get('multi_color_direction') or fil_extra.get('multi_color_direction') or 'longitudinal'

        return {
            "text": display_text, 
            "text_short": display_short,
            "color": final_color, 
            "color_direction": direction,
            "slot": slot,
            "details": {
                "id": sid,
                "brand": brand,
                "material": smart_mat,
                "color_name": col_name,
                "weight": rem,
                "temp": f"{fil.get('settings_extruder_temp', '')}°C" if fil.get('settings_extruder_temp') else "",
                # Spoolman stores needs_label_print loosely (bool, 'true'/'false' string, or missing).
                # Normalize to a strict bool so the card can branch without re-checking types.
                "needs_label_print": str(extra.get('needs_label_print', '')).lower() in ('true', '1'),
            }
        }

    except Exception as e:
        state.logger.error(f"Format Error: {e}")
        return {"text": f"#{spool_data.get('id', '?')} Error", "text_short": "Error", "color": "ff0000", "slot": ""}

def get_spools_at_location_detailed(loc_name):
    sm_url, _ = config_loader.get_api_urls()
    found = []
    # [ALEX FIX] Handle Unassigned (No Location)
    check_unassigned = (str(loc_name).upper() == 'UNASSIGNED')
    target_loc_upper = str(loc_name).upper()

    try:
        resp = requests.get(f"{sm_url}/api/v1/spool", timeout=5)
        if resp.ok:
            for s in parse_inbound_data(resp.json()):
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
                elif "-" not in target_loc_upper and sloc.upper().startswith(target_loc_upper + "-"):
                    match = True
                    
                # 2. [ALEX FIX] Physical Source Match (The Ghost Logic)
                # Strip the literal quotes that Spoolman adds to JSON String Fields!
                p_source_raw = str(extra.get('physical_source', '')).strip().replace('"', '')
                if not match and not check_unassigned:
                    p_source = p_source_raw.upper()
                    if p_source == target_loc_upper or ("-" not in target_loc_upper and p_source.startswith(target_loc_upper + "-")):
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
                        'color_direction': info.get('color_direction', 'longitudinal'),
                        'slot': final_slot,
                        'location': p_source_raw if is_ghost else sloc,                 # [ALEX FIX] Ensure UI can access exact physical location
                        'archived': s.get('archived', False),
                        'is_ghost': is_ghost,             # Flag for UI
                        'deployed_to': sloc if is_ghost else None, # Where is it really?
                        'remaining_weight': s.get('remaining_weight'),
                        'details': info.get('details', {})
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
            for fil in parse_inbound_data(fil_resp.json()):
                ext = str(fil.get('external_id', '')).strip().replace('"','')
                if ext == legacy_id:
                    target_filament_id = fil['id']
                    break
        if target_filament_id:
            spool_resp = requests.get(f"{sm_url}/api/v1/spool", timeout=5)
            if spool_resp.ok:
                candidates = []
                for spool in parse_inbound_data(spool_resp.json()):
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
            for fil in parse_inbound_data(resp.json()):
                ext = str(fil.get('external_id', '')).strip().replace('"','')
                if ext == legacy_id:
                    return fil['id']
    except Exception as e: state.logger.error(f"Legacy Filament Lookup Error: {e}")
    return None

def hex_to_rgb(hex_str):
    """Converts a #RRGGBB hex string to an (R, G, B) tuple. Returns None if invalid."""
    if not hex_str: return None
    h = hex_str.lstrip('#')
    try:
        if len(h) == 6:
            return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
        if len(h) == 3:
            return tuple(int(h[i]*2, 16) for i in (0, 1, 2))
    except ValueError:
        pass
    return None

def hex_distance(hex1, hex2):
    """Calculates roughly the visual distance between two hex colors."""
    rgb1 = hex_to_rgb(hex1)
    rgb2 = hex_to_rgb(hex2)
    if rgb1 is None or rgb2 is None: return float('inf')
    return sum((rgb1[i] - rgb2[i]) ** 2 for i in range(3)) ** 0.5

def get_best_color_distance(target_hex, compare_hex_csv):
    """
    Given a target_hex, evaluates one or more hex codes separated by commas (multi-color).
    Returns the shortest distance among the options.
    """
    if not compare_hex_csv:
        return float('inf')
        
    distances = []
    for h in compare_hex_csv.split(','):
        h = h.strip()
        if h:
            distances.append(hex_distance(target_hex, h))
            
    if not distances:
        return float('inf')
    return min(distances)

def search_inventory(query="", material="", vendor="", color_hex="", only_in_stock=False, empty=False, target_type="spool", min_weight="", deployed_state=""):
    """
    Searches Spoolman inventory objects (spools or filaments) based on fuzzy attributes and color closeness.
    Returns a sorted list of dictionaries matching the criteria.

    `deployed_state` (spool-only): '' or 'any' = no filter, 'deployed' = only
    spools currently on a toolhead (location ∈ printer_map) OR with a ghost
    physical_source set, 'undeployed' = the inverse. Filaments ignore this.
    """
    sm_url, _ = config_loader.get_api_urls()
    results = []

    # Load printer_map once so deployed_state filtering can check whether a
    # spool's location maps to a toolhead without touching the filesystem
    # per item. Cheap: config_loader caches internally.
    deployed_targets = set()
    if deployed_state and deployed_state.lower() in ('deployed', 'undeployed'):
        try:
            cfg = config_loader.load_config()
            pm = cfg.get('printer_map', {}) or {}
            deployed_targets = {str(k).strip().upper() for k in pm.keys()}
        except Exception:
            deployed_targets = set()
    
    try:
        # If the user toggles 'In Stock' off (meaning they want to see everything), we must explicitly tell Spoolman API to return archived items
        archived_param = "" if only_in_stock else "?allow_archived=true"
        
        spools_for_count = []
        if target_type == "filament":
            resp = requests.get(f"{sm_url}/api/v1/filament{archived_param}", timeout=10)
            try:
                s_resp = requests.get(f"{sm_url}/api/v1/spool{archived_param}", timeout=10)
                if s_resp.ok:
                    spools_for_count = parse_inbound_data(s_resp.json())
            except: pass
        else:
            resp = requests.get(f"{sm_url}/api/v1/spool{archived_param}", timeout=10)
            
        if not resp.ok:
            state.logger.error(f"Failed to fetch {target_type}s for search: {resp.status_code}")
            return []
            
        all_items = parse_inbound_data(resp.json())
        
        # Build quick lookup for spool counts if we are answering a filament search
        spool_counts = {}
        if target_type == "filament" and spools_for_count:
            for s in spools_for_count:
                fid = s.get('filament', {}).get('id')
                if fid:
                    spool_counts[fid] = spool_counts.get(fid, 0) + 1
        
        # Tokenize the query for ANY-ORDER matching (e.g. "pla green" == "green pla")
        raw_query = query.strip().lower()
        query_tokens = [t for t in raw_query.split() if t]
        
        mat_lower = material.strip().lower()
        ven_lower = vendor.strip().lower()
        
        for item in all_items:
            # Normalize access whether it's a spool containing a filament, or the filament itself
            if target_type == "filament":
                fil = item
                spool = None
            else:
                spool = item
                fil = spool.get('filament', {})
                
            vid = fil.get('vendor', {}) or {}
            
            # 1. Evaluate explicit dropdown text filters
            if mat_lower and mat_lower not in str(fil.get('material', '')).lower(): continue
            if ven_lower and ven_lower not in str(vid.get('name', '')).lower(): continue
            
            # 2. Evaluate Weight states (Spool Only)
            rem = 0
            if spool:
                rem = spool.get('remaining_weight')
                if rem is None: rem = 0
                if only_in_stock and rem <= 0: continue
                if empty and rem > 0: continue
                if min_weight:
                    try:
                        if rem < float(min_weight): continue
                    except: pass

                # 2b. Deployment filter (spool-only). A spool counts as
                # deployed if its Spoolman location is a known toolhead OR
                # it carries a ghost physical_source hint (meaning it's
                # currently visually on a toolhead elsewhere).
                if deployed_state and deployed_state.lower() in ('deployed', 'undeployed'):
                    sloc_up = str(spool.get('location') or '').strip().upper()
                    extra_map = spool.get('extra') or {}
                    ghost_src = str(extra_map.get('physical_source') or '').strip().replace('"', '').upper()
                    is_deployed = (sloc_up in deployed_targets) or (
                        ghost_src and ghost_src in deployed_targets
                    )
                    if deployed_state.lower() == 'deployed' and not is_deployed:
                        continue
                    if deployed_state.lower() == 'undeployed' and is_deployed:
                        continue
            
            # 3. Fuzzy Keyword Match (Tokenized)
            # Support `color_hexes` for multi-color gradients
            base_color = str(fil.get('multi_color_hexes', ''))
            if not base_color:
                base_color = str(fil.get('color_hex', ''))
                
            color_name = str(fil.get('extra', {}).get('original_color', '')).lower() if fil.get('extra') else ""
            
            if query_tokens:
                # Build a single robust string representing all the item's metadata
                item_id = str(item.get('id', ''))
                matchable = f"{item_id} {str(fil.get('name', '')).lower()} {str(fil.get('material', '')).lower()} {str(vid.get('name', '')).lower()} {color_name}"
                
                # ALL tokens must be present somewhere in the matchable string
                token_match_failed = False
                for token in query_tokens:
                    if token not in matchable:
                        token_match_failed = True
                        break
                
                if token_match_failed:
                    continue
                    
            # 4. Color Matching Algorithm (Gradient Aware)
            c_dist = 0
            if color_hex:
                c_dist = get_best_color_distance(color_hex, base_color)
                # If they explicitly wanted a color and parsing failed or no color exists, light penalty
                if c_dist == float('inf'): c_dist = 999 
                
            # 5. Format display & Inject Context
            # We adapt format_spool_display to handle returning standard data, then extract it for our unified card list
            locDisplay = ""
            is_ghost = False
            final_slot = ""
            
            if spool:
                info = format_spool_display(spool)
                sloc = str(spool.get('location', '')).strip()
                
                extra = spool.get('extra', {})
                p_source = str(extra.get('physical_source', '')).strip().replace('"', '')
                if p_source and p_source.upper() != sloc.upper():
                    is_ghost = True
                    ghost_slot = str(extra.get('physical_source_slot', '')).strip('"')
                
                final_slot = info['slot']
                if is_ghost and locals().get('ghost_slot'): final_slot = ghost_slot
                locDisplay = p_source if is_ghost else sloc
            else:
                # Formatting a raw Filament context
                v_name = str(vid.get('name', 'Generic')).strip()
                m_name = str(fil.get('material', 'PLA')).strip().upper()
                
                raw_attrs = fil.get('extra', {}).get('filament_attributes', '[]')
                try:
                    attrs_list = json.loads(raw_attrs) if isinstance(raw_attrs, str) else raw_attrs
                    if not isinstance(attrs_list, list): attrs_list = []
                except: attrs_list = []
                clean_attrs = [str(a).strip().strip('"').strip("'") for a in attrs_list if a]
                smart_m_name = f"{' '.join(clean_attrs)} {m_name}".strip() if clean_attrs else m_name
                
                c_name = str(color_name).strip().title() if color_name else str(fil.get('name', 'Unknown')).strip().title()
                
                base_text = f"{v_name} {m_name} ({c_name})"
                info = {
                    "text": f"#{fil.get('id', '?')} {base_text}",
                    "text_short": base_text,
                    # Pass the full multi-color hex string through so filament cards
                    # render the same gradient / coextruded visuals as spool cards.
                    # getFilamentStyle() on the frontend handles CSV/JSON lists.
                    "color": base_color if base_color else "888888",
                    "slot": "",
                    "details": {
                        "id": fil.get('id', '?'),
                        "brand": v_name,
                        "material": smart_m_name,
                        "color_name": c_name,
                        "weight": 0,
                        "temp": f"{fil.get('settings_extruder_temp', '')}°C" if fil.get('settings_extruder_temp') else ""
                    }
                }
                
            direction = str(fil.get('multi_color_direction') or fil.get('extra', {}).get('multi_color_direction') or 'longitudinal')
            
            results.append({
                'id': item['id'],
                'display': info['text'],
                'display_short': info.get('text_short', info['text']),
                'color': info['color'],
                'color_direction': direction,
                'slot': final_slot,
                'location': locDisplay,
                'is_ghost': is_ghost,
                'remaining': round(rem) if isinstance(rem, float) else rem,
                'color_dist': c_dist,
                'type': target_type,
                'archived': item.get('archived', False),
                'spools_count': spool_counts.get(item['id'], 0) if target_type == "filament" else None,
                'details': info.get('details', {})
            })
            
        # Sort by color distance (closest first), then by ID (newest first usually)
        # If min_weight is present, we prioritize sorting by ascending weight to surface near-empty spools first
        if color_hex:
            if min_weight:
                results.sort(key=lambda x: (x['color_dist'], x['remaining'], -x['id']))
            else:
                results.sort(key=lambda x: (x['color_dist'], -x['id']))
        else:
            if min_weight:
                results.sort(key=lambda x: (x['remaining'], -x['id']))
            else:
                results.sort(key=lambda x: -x['id'])
            
        return results
        
    except Exception as e:
        state.logger.error(f"Search Spools API Error: {e}")
        return []
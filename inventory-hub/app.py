from flask import Flask, request, jsonify, render_template # type: ignore
import requests # type: ignore
import state # type: ignore
import config_loader # type: ignore
import locations_db # type: ignore
import spoolman_api # type: ignore
import logic # type: ignore
import csv
import os
import json
import logging

VERSION = "v154.26 (Scale Weights Update)"
app = Flask(__name__)

# One-time feeder_map → slot_targets migration. Kept behind an explicit
# `feeder_map` key check so old installs that still have it get upgraded
# automatically the first time they boot the new code. No-op on modern
# installs where the key has been removed.
#
# Safety: the migration is purely additive (only sets extra.slot_targets
# on Dryer Box records; never removes keys). Spool data lives in
# Spoolman's DB and is untouched. Before the first successful migration
# we still write a timestamped backup of locations.json so there's a
# recovery path if anything ever goes wrong on a production restart.
try:
    _startup_cfg = config_loader.load_config()
    _legacy_feeder_map = _startup_cfg.get('feeder_map') or {}
    if _legacy_feeder_map:
        _startup_locs = locations_db.load_locations_list()
        _migrated, _changed = locations_db.migrate_feeder_map_if_needed(
            _startup_locs, _legacy_feeder_map
        )
        if _changed:
            # Backup before persisting — cheap insurance.
            try:
                import shutil, time as _t
                _stamp = _t.strftime('%Y%m%d-%H%M%S')
                _backup = f"{locations_db.JSON_FILE}.pre-feedermap-migration-{_stamp}.bak"
                shutil.copy2(locations_db.JSON_FILE, _backup)
                state.logger.info(f"📦 Backed up locations.json → {_backup}")
            except Exception as _bk_err:
                state.logger.warning(f"Could not write pre-migration backup: {_bk_err}")
            locations_db.save_locations_list(_migrated)
            state.logger.info("💾 Legacy feeder_map migrated into locations.json — you can safely delete feeder_map from config.json now.")
except Exception as _mig_err:
    state.logger.error(f"feeder_map migration skipped due to error: {_mig_err}")

# [ALEX FIX] Suppress Werkzeug Console Spam (Fixes Infinite Log Growth)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

@app.after_request
def add_header(r):
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return r

@app.route('/')
def dashboard():
    # Load config to generate the correct Spoolman URL
    cfg = config_loader.load_config()
    ip = cfg.get('server_ip', '127.0.0.1')
    if ip == '0.0.0.0': ip = '127.0.0.1'
    port = cfg.get('spoolman_port', 7912)
    sm_url = f"http://{ip}:{port}"
    # [Code Guardian] Fetch FilaBridge URL for Dashboard Button
    _, fb_api_url = config_loader.get_api_urls()
    fb_ui_url = fb_api_url.replace('/api', '')
    buy_more_url_template = cfg.get('buy_more_url_template', '')
    
    return render_template('dashboard.html', version=VERSION, spoolman_url=sm_url, filabridge_url=fb_ui_url, buy_more_template=buy_more_url_template)

# --- HELPER FUNCTIONS ---
def clean_string(s):
    if isinstance(s, str): return s.strip('"').strip("'")
    return s

def hex_to_rgb(hex_str):
    if not hex_str or len(hex_str) < 6: return "", "", ""
    try:
        clean_hex = hex_str.lstrip('#')
        return int(clean_hex[0:2], 16), int(clean_hex[2:4], 16), int(clean_hex[4:6], 16)
    except ValueError:
        return "", "", ""

def get_smart_type(material, extra_data):
    material = clean_string(material) or ""
    raw_attrs = extra_data.get('filament_attributes', '[]')
    try:
        attrs_list = json.loads(raw_attrs) if isinstance(raw_attrs, str) else raw_attrs
        if not isinstance(attrs_list, list): attrs_list = []
    except json.JSONDecodeError: attrs_list = []
    
    clean_attrs = [clean_string(a) for a in attrs_list if a]
    if clean_attrs: return f"{' '.join(clean_attrs)} {material}"
    return material

def get_color_name(item_data):
    extra = item_data.get('extra', {})
    if 'original_color' in extra:
        val = clean_string(extra['original_color'])
        if val: return val
    return item_data.get('name', 'Unknown')

def get_best_hex(item_data):
    extra = item_data.get('extra', {})
    multi_hex = item_data.get('multi_color_hexes') or extra.get('multi_color_hexes')
    if multi_hex:
        first_hex = multi_hex.split(',')[0].strip()
        if first_hex: return first_hex
    return item_data.get('color_hex', '')

def sanitize_label_text(text):
    if not isinstance(text, str): return str(text)
    # 🛠️ EMOJI TRANSLATION MAP
    replacements = {
        "🦝": "Raccoon",
        "⚡": "Bolt",
        "🔥": "Fire",
        "📦": "Box",
        "⚠️": "Warn"
    }
    for char, name in replacements.items():
        text = text.replace(char, name)
    return text

def flatten_json(y):
    out = {}
    def flatten(x, name=''):
        if type(x) is dict:
            for a in x:
                flatten(x[a], name + a + '_')
        elif type(x) is list:
            i = 0
            for a in x:
                flatten(a, name + str(i) + '_')
                i += 1
        else:
            out[name[:-1]] = x
    flatten(y)
    return out

# --- PRINT ROUTES ---
@app.route('/api/print_label', methods=['POST'])
def api_print_label():
    sid = request.json.get('id')
    if not sid: return jsonify({"success": False, "msg": "No ID provided"})

    spool = spoolman_api.get_spool(sid)

    # Browser Mode: Just return data
    return jsonify({"success": True, "method": "browser", "data": spool})

# --- INVENTORY WIZARD ---
@app.route('/api/external/vendors', methods=['GET'])
def api_external_vendors():
    """Proxy route to fetch Spoolman vendors for the Wizard dropdowns."""
    vendors = spoolman_api.get_vendors()
    return jsonify({"success": True, "vendors": vendors})

@app.route('/api/vendors', methods=['GET'])
def api_vendors():
    """Returns a list of all vendors in Spoolman."""
    try:
        return jsonify({"success": True, "vendors": spoolman_api.get_vendors()})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500

@app.route('/api/materials', methods=['GET'])
def api_materials():
    """Returns a list of all unique materials in Spoolman."""
    try:
        return jsonify({"success": True, "materials": spoolman_api.get_materials()})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500

@app.route('/api/filaments', methods=['GET'])
def api_filaments():
    """Proxy route to fetch Spoolman filaments, preventing CORS on port mismatch."""
    sm_url, _ = config_loader.get_api_urls()
    try:
        r = requests.get(f"{sm_url}/api/v1/filament", timeout=5)
        if r.ok:
            return jsonify({"success": True, "filaments": r.json()})
    except Exception as e:
        state.logger.error(f"API Error fetching filaments: {e}")
    return jsonify({"success": False, "filaments": []})

@app.route('/api/filaments/<int:filament_id>', methods=['GET'])
def api_get_filament(filament_id):
    """Fetches a specific filament to read its details."""
    try:
        data = spoolman_api.get_filament(filament_id)
        if data:
            return jsonify({"success": True, "data": data})
        return jsonify({"success": False, "msg": "Filament not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500

@app.route('/api/spools/<int:spool_id>', methods=['GET'])
def api_get_spool(spool_id):
    """Fetches a specific spool to read its complete filament mapping."""
    try:
        spool = spoolman_api.get_spool(spool_id)
        if spool:
            return jsonify({"success": True, "data": spool})
        return jsonify({"success": False, "msg": "Spool not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500

@app.route('/api/external/fields', methods=['GET'])
def api_external_fields():
    """Proxy route to fetch Spoolman custom Extra fields configuration (e.g. Filament Attributes, Spool Types)."""
    sm_url, _ = config_loader.get_api_urls()
    out = {"filament": [], "spool": []}
    try:
        rf = requests.get(f"{sm_url}/api/v1/field/filament", timeout=5)
        if rf.ok: out["filament"] = rf.json()
        
        rs = requests.get(f"{sm_url}/api/v1/field/spool", timeout=5)
        if rs.ok: out["spool"] = rs.json()
        
        return jsonify({"success": True, "fields": out})
    except Exception as e:
        state.logger.error(f"API Error fetching extra fields config: {e}")
    return jsonify({"success": False, "fields": out})

@app.route('/api/external/fields/add_choice', methods=['POST'])
def api_external_fields_add_choice():
    """Appends a new choice to a multi-choice field in Spoolman and updates the schema."""
    data = request.json
    entity_type = data.get('entity_type')
    key = data.get('key')
    new_choice = data.get('new_choice')
    
    if not all([entity_type, key, new_choice]):
         return jsonify({"success": False, "msg": "Missing required fields."})
         
    res = spoolman_api.update_extra_field_choices(entity_type, key, [new_choice])
    return jsonify(res)

@app.route('/api/create_inventory_wizard', methods=['POST'])
def api_create_inventory_wizard():
    """Monolithic endpoint to handle creating Filaments and Spools in one shot."""
    data = request.json
    filament_id = data.get('filament_id')
    filament_data = data.get('filament_data')
    spool_data = data.get('spool_data')
    quantity = int(data.get('quantity', 1))

    created_spool_ids = []

    try:
        # Step 1: Resolve Filament
        if not filament_id and filament_data:
            # Check if a new vendor needs to be created
            extra = filament_data.get('extra', {})
            external_vendor = extra.pop('external_vendor_name', None)
            if external_vendor:
                new_ven = spoolman_api.create_vendor({"name": external_vendor})
                if new_ven and 'id' in new_ven:
                    filament_data['vendor_id'] = new_ven['id']
                else:
                    return jsonify({"success": False, "msg": f"Failed to create new Vendor '{external_vendor}' in Spoolman."})

            # Create a brand new filament
            new_fil = spoolman_api.create_filament(filament_data)
            if new_fil and 'id' in new_fil:
                filament_id = new_fil['id']
            else:
                return jsonify({"success": False, "msg": "Failed to create new Filament in Spoolman."})
        
        if not filament_id:
            return jsonify({"success": False, "msg": "Missing Filament ID or valid Filament Data."})

        # If user is adding spool(s) to a pre-existing (possibly archived) filament,
        # auto-unarchive it so the filament reappears in normal views. Skip when the
        # filament was just created in Step 1 — new filaments start un-archived.
        if data.get('filament_id') and spool_data:
            existing_fil = spoolman_api.get_filament(filament_id)
            if existing_fil and existing_fil.get('archived'):
                if spoolman_api.update_filament(filament_id, {'archived': False}):
                    state.add_log_entry(f"📤 Auto-unarchived Filament #{filament_id} (new spool added)", "INFO")
                else:
                    state.logger.warning(f"Failed to auto-unarchive Filament #{filament_id}")

        # Step 2: Create Spool(s)
        if spool_data:
            spool_data['filament_id'] = filament_id
            
            for _ in range(quantity):
                # Copy properties to ensure unique timestamps per spool creation request if needed
                payload = dict(spool_data)
                new_spool = spoolman_api.create_spool(payload)
                if new_spool and 'id' in new_spool:
                    created_spool_ids.append(new_spool['id'])
                else:
                    state.logger.error("A spool creation failed during bulk wizard execution.")
            
        return jsonify({
            "success": True, 
            "filament_id": filament_id, 
            "created_spools": created_spool_ids
        })

    except Exception as e:
        state.logger.error(f"Wizard Creation Error: {e}")
        return jsonify({"success": False, "msg": str(e)})


@app.route('/api/edit_spool_wizard', methods=['POST'])
def api_edit_spool_wizard():
    """Endpoint to handle natively editing Filaments and Spools from the Wizard Edit UI."""
    data = request.json
    spool_id = data.get('spool_id')
    filament_id = data.get('filament_id')
    filament_data = data.get('filament_data')
    spool_data = data.get('spool_data')

    if not spool_id:
        return jsonify({"success": False, "msg": "Missing Spool ID for edit session."})

    try:
        # Update Spool First
        if spool_data:
            # Prevent 500 errors by only passing actual changes to Spoolman
            original_spool = spoolman_api.get_spool(spool_id)
            if original_spool:
                dirty_spool_data = {}
                for k, v in spool_data.items():
                    if k == 'spool_weight':
                        if v != original_spool.get('spool_weight'):
                            dirty_spool_data['spool_weight'] = v
                    elif k == 'extra':
                        # Diff extra fields dict
                        original_extra = original_spool.get('extra', {})
                        dirty_extra = {}
                        for ek, ev in v.items():
                            if str(ev) != str(original_extra.get(ek)):
                                dirty_extra[ek] = ev
                        if dirty_extra:
                            dirty_spool_data['extra'] = dirty_extra
                    elif k in original_spool and original_spool[k] != v:
                        dirty_spool_data[k] = v
                    elif k not in original_spool:
                         dirty_spool_data[k] = v
                
                spool_data = dirty_spool_data
                state.logger.info(f"DIRTY SPOOL DATA: {dirty_spool_data}")

            if spool_data:
                spool_res = spoolman_api.update_spool(spool_id, spool_data)
                if not spool_res:
                    return jsonify({"success": False, "msg": f"Failed to gracefully update Spool {spool_id}."})
        
        # Update Filament Second (if applicable)
        if filament_id and filament_data:
            # Handle spontaneous vendor generation explicitly
            if 'extra' in filament_data:
                external_vendor = filament_data['extra'].pop('external_vendor_name', None)
                if external_vendor:
                    new_ven = spoolman_api.create_vendor({"name": external_vendor})
                    if new_ven and 'id' in new_ven:
                        filament_data['vendor_id'] = new_ven['id']
                    
            fil_res = spoolman_api.update_filament(filament_id, filament_data)
            if not fil_res:
                state.logger.warning(f"Failed to cleanly update Filament {filament_id} during spool edit.")
                return jsonify({"success": False, "msg": "Filament database update rejected. Check data formats mapping."})

        return jsonify({"success": True, "spool_id": spool_id})

    except Exception as e:
        state.logger.error(f"Wizard Edit Error: {e}")
        return jsonify({"success": False, "msg": str(e)})

@app.route('/api/spool/update', methods=['POST'])
def api_spool_update():
    """Generic endpoint to partially update a spool from frontend modules"""
    try:
        data = request.json
        spool_id = data.get('id')
        updates = data.get('updates')
        
        if not spool_id or not updates:
            return jsonify({"status": "error", "msg": "Missing id or updates"})
            
        res = spoolman_api.update_spool(spool_id, updates)
        if res:
            return jsonify({"status": "success"})
        return jsonify({"status": "error", "msg": "Failed to update spool"})
    except Exception as e:
        state.logger.error(f"Spool Update Error: {e}")
        return jsonify({"status": "error", "msg": str(e)})

import external_parsers # Added for plugin architecture

@app.route('/api/external/search', methods=['GET'])
def api_external_search():
    """
    Extensible handler for pulling template parameters from external databases.
    Powered by `external_parsers.py` Plugins.
    """
    source = request.args.get('source', 'spoolman')
    query = request.args.get('q', '').strip()
    
    try:
        results = external_parsers.search_external(source, query)
        return jsonify({"success": True, "source": source, "results": results})
    except ValueError as e:
        state.logger.warning(f"External API Router Error: {e}")
        return jsonify({"success": False, "msg": str(e)})
    except Exception as e:
        state.logger.error(f"External Search Handler Error: {e}")
        return jsonify({"success": False, "msg": f"An error occurred pulling data: {e}"})

@app.route('/api/search', methods=['GET'])
def api_search_inventory():
    """
    Search endpoint for finding spools based on fuzzy queries, attributes, and colors.
    Used by the new global Offcanvas search component.
    """
    query = request.args.get('q', '')
    material = request.args.get('material', '')
    vendor = request.args.get('vendor', '')
    color_hex = request.args.get('hex', '')
    
    only_in_stock = request.args.get('in_stock', 'false').lower() == 'true'
    empty = request.args.get('empty', 'false').lower() == 'true'
    min_weight = request.args.get('min_weight', '')
    target_type = request.args.get('type', 'spool')
    
    try:
        results = spoolman_api.search_inventory(
            query=query, 
            material=material, 
            vendor=vendor, 
            color_hex=color_hex, 
            only_in_stock=only_in_stock, 
            empty=empty,
            target_type=target_type,
            min_weight=min_weight
        )
        return jsonify({"success": True, "results": results})
    except Exception as e:
        state.logger.error(f"API Search Error: {e}")
        return jsonify({"success": False, "msg": str(e)})

# ... (Imports same as before) ...

@app.route('/api/print_batch_csv', methods=['POST'])
def api_print_batch_csv():
    data = request.json
    ids = data.get('ids', [])
    mode = data.get('mode', 'spool')
    clear_old = data.get('clear_old', False)
    
    if not ids: return jsonify({"success": False, "msg": "Empty Queue"})

    cfg = config_loader.load_config()
    
    # --- 1. DETERMINE FILENAME ---
    if mode == 'spool': filename = "labels_spool.csv"
    elif mode == 'location': filename = "labels_locations.csv"
    else: filename = "labels_swatch.csv"
    
    csv_path = cfg.get("print_settings", {}).get("csv_path", filename)
    
    # 🛠️ AUTO-CREATE FOLDER FIX
    if "/" in csv_path or "\\" in csv_path:
        folder = os.path.dirname(csv_path)
        try: 
            os.makedirs(folder, exist_ok=True)
        except Exception as e:
            state.logger.warning(f"Could not create folder {folder}: {e}")
        csv_path = os.path.join(folder, filename)

    try:
        items_to_print = []
        slots_to_print = []

        # --- 2. DEFINE HEADERS ---
        if mode == 'spool':
            core_headers = ['ID', 'Brand', 'Color', 'Type', 'Hex', 'Red', 'Green', 'Blue', 'Weight', 'QR_Code']
        elif mode == 'location':
            # [ALEX FIX] Added 'Slot' to headers
            core_headers = ['LocationID', 'Name', 'Cleaned_Name', 'QR_Code']
        else:
            core_headers = ['ID', 'Brand', 'Color', 'Type', 'Hex', 'Red', 'Green', 'Blue', 'Temp_Nozzle', 'Temp_Bed', 'Density', 'QR_Code']

        # --- 3. PRE-LOAD DATA (Optimization) ---
        loc_lookup = {}
        if mode == 'location':
            # Load local CSV first
            loc_list = locations_db.load_locations_list()
            loc_lookup = {str(row['LocationID']): row for row in loc_list}

        # --- 4. BUILD ROWS ---
        seen_ids = set() # [ALEX FIX] Deduplication tracker

        for item_id in ids:
            # [ALEX FIX] Prevent processing duplicates in the same batch
            if item_id in seen_ids: continue
            seen_ids.add(item_id)

            row_data = {}
            
            # === SPOOL MODE ===
            if mode == 'spool':
                raw_data = spoolman_api.get_spool(item_id)
                if not raw_data: continue
                fil_data = raw_data.get('filament', {})
                vendor_data = fil_data.get('vendor', {})
                fil_extra = fil_data.get('extra', {})
                
                row_data['ID'] = item_id
                row_data['Brand'] = sanitize_label_text(vendor_data.get('name', 'Unknown') if vendor_data else 'Unknown')
                row_data['Color'] = sanitize_label_text(get_color_name(fil_data))
                raw_material = fil_data.get('material', 'Unknown')
                row_data['Type'] = sanitize_label_text(get_smart_type(raw_material, fil_extra))
                hex_val = get_best_hex(fil_data)
                row_data['Hex'] = hex_val
                r, g, b = hex_to_rgb(hex_val)
                row_data['Red'] = r; row_data['Green'] = g; row_data['Blue'] = b
                row_data['Weight'] = f"{raw_data.get('remaining_weight', 0):.0f}g"
                row_data['QR_Code'] = f"ID:{item_id}"
                
                flat_data = flatten_json(raw_data)
                for k, v in flat_data.items():
                    if k not in row_data: row_data[k] = v

            # === LOCATION MODE (HYBRID LOOKUP) ===
            elif mode == 'location':
                # 1. Try Local CSV
                loc_data = loc_lookup.get(str(item_id)) 
                
                if loc_data:
                    name = loc_data.get('Name', 'Unknown')
                else:
                    # 2. Try Spoolman API (Fallback)
                    sm_url, _ = config_loader.get_api_urls()
                    try:
                        resp = requests.get(f"{sm_url}/api/v1/location/{item_id}", timeout=2)
                        if resp.ok:
                            s_data = resp.json()
                            name = s_data.get('name', str(item_id))
                        else:
                            name = str(item_id)
                    except:
                        name = str(item_id)
                
                row_data['LocationID'] = item_id
                row_data['Name'] = name
                # [ALEX FIX] Enforce LOC: prefix for Location QR Codes
                row_data['QR_Code'] = f"LOC:{item_id}" 

                # --- CLEAN NAME & SLOT GENERATION ---
                clean_name = sanitize_label_text(name)
                row_data['Cleaned_Name'] = clean_name

                max_spools = 0
                if loc_data:
                    for k, v in loc_data.items():
                        if k.strip().lower() == 'max spools':
                            try: max_spools = int(v)
                            except: max_spools = 0
                            break
                
                # [ALEX FIX] Removed the DUPLICATE "Slot Generation" block that was here.
                # [ALEX FIX] Added "Slot" column logic.
                if max_spools > 1:
                    for i in range(1, max_spools + 1):
                        slots_to_print.append({
                            "LocationID": item_id,
                            "Slot": f"Slot {i}", # <--- NEW FIELD
                            "Name": f"{name} Slot {i}",
                            "Cleaned_Name": f"{clean_name} Slot {i}",
                            "QR_Code": f"LOC:{item_id}:SLOT:{i}"
                        })

                items_to_print.append(row_data)
                continue 

            # === FILAMENT MODE ===
            else:
                raw_data = spoolman_api.get_filament(item_id)
                if not raw_data: continue
                fil_data = raw_data
                vendor_data = raw_data.get('vendor', {})
                fil_extra = raw_data.get('extra', {})
                
                row_data['ID'] = item_id
                row_data['Brand'] = vendor_data.get('name', 'Unknown') if vendor_data else 'Unknown'
                row_data['Color'] = get_color_name(fil_data)
                raw_material = fil_data.get('material', 'Unknown')
                row_data['Type'] = get_smart_type(raw_material, fil_extra)
                hex_val = get_best_hex(fil_data)
                row_data['Hex'] = hex_val
                r, g, b = hex_to_rgb(hex_val)
                row_data['Red'] = r; row_data['Green'] = g; row_data['Blue'] = b

                t_noz = fil_data.get('settings_extruder_temp')
                row_data['Temp_Nozzle'] = f"{t_noz}°C" if t_noz else ""
                t_bed = fil_data.get('settings_bed_temp')
                row_data['Temp_Bed'] = f"{t_bed}°C" if t_bed else ""
                dens = fil_data.get('density')
                row_data['Density'] = f"{dens} g/cm³" if dens else ""
                row_data['QR_Code'] = f"FIL:{item_id}"

                flat_data = flatten_json(raw_data)
                for k, v in flat_data.items():
                    if k not in row_data: row_data[k] = v
            
            # Append Spool/Filament rows
            if mode != 'location':
                items_to_print.append(row_data)

        if not items_to_print: return jsonify({"success": False, "msg": "No valid data found"})

        # --- SMART HEADER LOGIC ---
        file_exists = os.path.exists(csv_path)
        write_mode = 'w' if clear_old else 'a'
        
        target_headers = []

        if not clear_old and file_exists:
            try:
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    target_headers = next(reader, None)
            except: pass
        
        if not target_headers:
            target_headers = list(core_headers)
            all_keys = set()
            for item in items_to_print: all_keys.update(item.keys())
            extra_headers = sorted([k for k in all_keys if k not in core_headers])
            target_headers.extend(extra_headers)

        with open(csv_path, write_mode, newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=target_headers, extrasaction='ignore')
            if clear_old or not file_exists: writer.writeheader()
            writer.writerows(items_to_print)

        # --- WRITE SLOTS IF GENERATED ---
        slots_filename = "slots_to_print.csv"
        if slots_to_print:
            slots_path = os.path.join(folder, slots_filename)
            slots_exists = os.path.exists(slots_path)
            
            with open(slots_path, write_mode, newline='', encoding='utf-8') as f:
                # [ALEX FIX] Added "Slot" to fieldnames
                writer = csv.DictWriter(f, fieldnames=["LocationID", "Slot", "Name", "Cleaned_Name", "QR_Code"])
                if clear_old or not slots_exists: writer.writeheader()
                writer.writerows(slots_to_print)

        action_word = "Overwritten" if clear_old else "Appended"
        msg = f"{action_word} {len(items_to_print)} items."
        if slots_to_print: msg += f" (+{len(slots_to_print)} Slots)"
        
        return jsonify({"success": True, "count": len(items_to_print), "file": filename, "msg": msg})

    except PermissionError:
        return jsonify({"success": False, "msg": f"{filename} Locked! Close Excel."})
    except Exception as e:
        state.logger.error(f"Batch CSV Error: {e}")
        return jsonify({"success": False, "msg": str(e)})

# --- EXISTING ROUTES ---

@app.route('/api/locations', methods=['GET'])
def api_get_locations(): 
    local_rows = locations_db.load_locations_list()
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
                "Max Spools": 0
            }
            
    csv_rows = list(local_map.values())
    occupancy_map: dict[str, int] = {}
    unassigned_count: int = 0 
    
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
                
                if loc: 
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

    except: pass

    # [ALEX FIX] Support Room logic correctly by adding grouped floating data
    room_occupancy: dict[str, int] = {}
    room_floating: dict[str, int] = {}
    csv_rows = list(local_map.values())
    
    # 1. First Pass: Compute total Room occupancies
    for loc, count in occupancy_map.items():
        if loc and "-" in loc:
            parent = loc.split("-")[0]
            # Verify prefix is valid (not TST, PM, PJ, etc)
            if parent not in ["TST", "TEST", "PM", "PJ"]:
                room_occupancy[parent] = room_occupancy.get(parent, 0) + count
        else:
            # It's floating in a parent directly
            if loc:
                room_occupancy[loc] = room_occupancy.get(loc, 0) + count
                room_floating[loc] = room_floating.get(loc, 0) + count

    # 2. Inject Virtual Rooms/Printers if they don't exist
    for parent in room_occupancy.keys():
        if parent not in local_map:
            # Check children types to determine if this is a Printer or a Room
            is_printer = False
            for c_loc, meta in local_map.items():
                if c_loc.startswith(parent + "-"):
                    t = str(meta.get('Type', '')).lower()
                    if 'printer' in t or 'tool head' in t or 'mmu' in t:
                        is_printer = True
                        break
                        
            csv_rows.append({
                "LocationID": parent,
                "Name": f"{parent} System" if is_printer else f"{parent} (Room)",
                "Type": "Printer" if is_printer else "Virtual Room",
                "Max Spools": 0,
                "OccupancyRaw": 0
            })

    final_list = []
    # [ALEX FIX] Inject Virtual Unassigned Row
    final_list.append({
        "LocationID": "Unassigned",
        "Name": "Workbench / Unsorted",
        "Type": "Virtual",
        "Occupancy": f"{unassigned_count} items",
        "Max Spools": 0
    })

    for row in csv_rows:
        lid = str(row.get('LocationID', '')).upper()
        if lid == "UNASSIGNED": continue # Skip if somehow in CSV
        
        max_s = row.get('Max Spools', '')
        try:
            max_val = int(max_s) if max_s else 0
        except (ValueError, TypeError):
            max_val = 0
            
        curr_val = occupancy_map.get(lid, 0)
        
        # If this is a Room or parent, show aggregated plus floating
        if lid in room_occupancy and "-" not in lid:
            total_room = room_occupancy[lid]
            floating = room_floating.get(lid, 0)
            row['OccupancyRaw'] = total_room
            if floating > 0:
                row['Occupancy'] = f"{total_room} Total ({floating} floating)"
            else:
                row['Occupancy'] = f"{total_room} Total"
        else:
            row['OccupancyRaw'] = curr_val 
            if max_val > 0: row['Occupancy'] = f"{curr_val}/{max_val}"
            else: row['Occupancy'] = f"{curr_val} items"
            
        final_list.append(row)
    return jsonify(final_list)

@app.route('/api/locations', methods=['POST'])
def api_save_location():
    data = request.json
    old_id = data.get('old_id')
    new_entry = data.get('new_data')
    current_list = locations_db.load_locations_list()
    if old_id:
        current_list = [row for row in current_list if row['LocationID'] != old_id]
        state.add_log_entry(f"📝 Updated: {new_entry['LocationID']}")
    else:
        state.add_log_entry(f"✨ Created: {new_entry['LocationID']}")
    current_list.append(new_entry)
    current_list.sort(key=lambda x: str(x.get('LocationID', '')))
    locations_db.save_locations_list(current_list)
    return jsonify({"success": True})

@app.route('/api/locations', methods=['DELETE'])
def api_delete_location():
    target = request.args.get('id', '').strip()
    if not target: return jsonify({"success": False})
    try:
        contents = spoolman_api.get_spools_at_location(target)
        for sid in contents: spoolman_api.update_spool(sid, {"location": ""})
    except: pass
    
    current = locations_db.load_locations_list()
    new_list = [row for row in current if row['LocationID'] != target]
    locations_db.save_locations_list(new_list)
    state.add_log_entry(f"🗑️ Deleted: {target}", "WARNING")
    return jsonify({"success": True})

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


@app.route('/api/update_filament', methods=['POST'])
def api_update_filament():
    """Direct filament-level edit hook for the Edit Filament button on the
    Filament Details modal. Accepts {id, data} where `data` is any subset of
    Spoolman filament fields (name, material, vendor_id, spool_weight,
    density, color_hex, settings_extruder_temp, settings_bed_temp, comment,
    extra, archived, etc.). Returns {success, filament|msg}.

    Deliberately thinner than /api/edit_spool_wizard — no spool coupling,
    no cross-inherit logic — since this endpoint's sole caller is the
    filament-only edit flow.
    """
    payload = request.json or {}
    fid = payload.get('id')
    data = payload.get('data') or {}
    if not fid:
        return jsonify({"success": False, "msg": "Missing filament id."})
    if not isinstance(data, dict) or not data:
        return jsonify({"success": False, "msg": "No fields to update."})
    try:
        updated = spoolman_api.update_filament(fid, data)
        if updated:
            state.add_log_entry(
                f"✏️ Filament #{fid} edited ({', '.join(sorted(data.keys()))})",
                "SUCCESS", "00ff00",
            )
            return jsonify({"success": True, "filament": updated})
        return jsonify({"success": False, "msg": "Spoolman rejected the update."})
    except Exception as e:
        state.logger.error(f"Failed to update filament #{fid}: {e}")
        return jsonify({"success": False, "msg": str(e)})

@app.route('/api/manage_contents', methods=['POST'])
def api_manage_contents():
    data = request.json
    action = data.get('action') 
    loc_id = data.get('location', '').strip().upper() 
    spool_input = data.get('spool_id') 
    slot_arg = data.get('slot') 

    if action == 'clear_location':
        contents = spoolman_api.get_spools_at_location_detailed(loc_id)
        for spool in contents:
            # [ALEX FIX] Protect "Ghost" items from being ejected when a box is cleared
            if spool.get('is_ghost'):
                continue
                
            slot_val = spool.get('slot', '')
            if not slot_val or slot_val == 'None' or slot_val == '':
                logic.perform_smart_eject(spool['id'])
        return jsonify({"success": True})

    spool_id = None
    if action == 'add':
        if spool_input:
            resolution = logic.resolve_scan(str(spool_input))
            if resolution and resolution['type'] == 'spool':
                spool_id = resolution['id']
            elif resolution and resolution['type'] == 'error':
                 return jsonify({"success": False, "msg": resolution['msg']})
    elif action in ['remove', 'force_unassign']:
        if str(spool_input).isdigit(): spool_id = int(spool_input)
        
    if not spool_id: return jsonify({"success": False, "msg": "Spool not found"})

    if action == 'remove':
        is_confirmed = data.get('confirmed', False)
        result = logic.perform_smart_eject(spool_id, confirmed_unassign=is_confirmed)
        if result == "REQUIRE_CONFIRM":
            return jsonify({"success": False, "require_confirm": True, "msg": "Spool is already in a room. Confirm true unassign to nowhere?"})
        elif result is True:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "msg": "DB Update Failed"})
    elif action == 'force_unassign':
        if logic.perform_force_unassign(spool_id): return jsonify({"success": True})
        else: return jsonify({"success": False, "msg": "DB Update Failed"})
    elif action == 'add':
        origin = data.get('origin', '')
        return jsonify(logic.perform_smart_move(loc_id, [spool_id], target_slot=slot_arg, origin=origin))
    return jsonify({"success": False})

@app.route('/api/identify_scan', methods=['POST'])
def api_identify_scan():
    text = request.json.get('text', '')
    source = request.json.get('source', '')
    res = logic.resolve_scan(text)

    if res and res.get('type') == 'command' and res.get('cmd') == 'audit':
        state.reset_audit()
        state.AUDIT_SESSION['active'] = True
        state.add_log_entry("🕵️‍♀️ <b>AUDIT MODE STARTED</b>", "INFO", "ff00ff")
        state.add_log_entry("Scan a Location label to begin checking.", "INFO")
        return jsonify({"type": "command", "cmd": "clear"}) 

    if state.AUDIT_SESSION.get('active'):
        logic.process_audit_scan(res)
        return jsonify({"type": "command", "cmd": "clear"})

    if not res: return jsonify({"type": "unknown"})
    
    if res['type'] == 'location':
        lid = res['id']; 
        items = spoolman_api.get_spools_at_location_detailed(lid)
        state.add_log_entry(f"🔎 {lid}: {len(items)} item(s)")
        return jsonify({"type": "location", "id": lid, "display": f"LOC: {lid}", "contents": items})
        
    if res['type'] == 'spool':
        sid = res['id']; data = spoolman_api.get_spool(sid)
        if data:
            if source == 'barcode' and text.strip().upper().startswith('ID:'):
                extra = data.get('extra', {})
                dirty = False
                if extra.get('needs_label_print') is True or extra.get('needs_label_print') == 'true' or extra.get('needs_label_print') == 'True':
                    extra['needs_label_print'] = False
                    dirty = True
                
                if dirty:
                    if spoolman_api.update_spool(sid, {'extra': extra}):
                        state.add_log_entry(f"✔️ Spool #{sid} Label Verified", "SUCCESS", "00ff00")
                    else:
                        state.add_log_entry(f"❌ Failed to verify Spool #{sid} label", "WARNING")
            
            info = spoolman_api.format_spool_display(data)
            
            # Ensure ghost and slot location logic is provided directly in buffer payloads
            sloc = str(data.get('location', '')).strip()
            extra = data.get('extra', {})
            is_ghost = False
            p_source = str(extra.get('physical_source', '')).strip().replace('"', '')
            if p_source and sloc.upper() != p_source.upper():
                is_ghost = True
            ghost_slot = str(extra.get('physical_source_slot', '')).strip('"')
            
            final_slot = info.get('slot', '')
            if is_ghost and ghost_slot:
                final_slot = ghost_slot

            return jsonify({
                "type": "spool", 
                "id": int(sid), 
                "display": info['text'], 
                "color": info['color'],
                "color_direction": info.get("color_direction", "longitudinal"),
                "remaining_weight": data.get("remaining_weight"),
                "details": info.get("details", {}),
                "archived": data.get("archived", False),
                "location": p_source if is_ghost else sloc,
                "is_ghost": is_ghost,
                "slot": final_slot,
                "deployed_to": sloc if is_ghost else None
            })
            
    if res['type'] == 'filament':
        fid = res['id']
        data = spoolman_api.get_filament(fid)
        if data:
            if source == 'barcode' and text.strip().upper().startswith('FIL:'):
                extra = data.get('extra', {})
                dirty = False
                if extra.get('needs_label_print') is True or extra.get('needs_label_print') == 'true' or extra.get('needs_label_print') == 'True':
                    extra['needs_label_print'] = False
                    dirty = True

                if dirty:
                    if spoolman_api.update_filament(fid, {'extra': extra}):
                        state.add_log_entry(f"✔️ Filament #{fid} Label & Sample Verified", "SUCCESS", "00ff00")
                    else:
                        state.add_log_entry(f"❌ Failed to verify Filament #{fid} label", "WARNING")
            
            name = data.get('name', 'Unknown Filament')
            return jsonify({"type": "filament", "id": int(fid), "display": name})

    # --- SLOT ASSIGNMENT (Phase 1) ---
    # LOC:X:SLOT:Y scans mean "drop the buffered spool into slot Y of location X".
    # perform_smart_move already handles auto-eject, container_slot, physical_source,
    # and the Filabridge map_toolhead notification when the target is a printer.
    if res.get('type') == 'assignment':
        target = str(res.get('location', '')).strip().upper()
        slot = str(res.get('slot', '')).strip()
        loc_list = locations_db.load_locations_list()
        loc_info_map = {row['LocationID'].upper(): row for row in loc_list}
        tgt_info = loc_info_map.get(target)

        # Validate target exists and is a container type.
        container_types = {'Dryer Box', 'MMU Slot', 'Tool Head', 'No MMU Direct Load'}
        if not tgt_info or tgt_info.get('Type') not in container_types:
            found_type = tgt_info.get('Type') if tgt_info else 'missing'
            state.add_log_entry(
                f"❌ Slot scan target <b>{target}</b> invalid (type={found_type}) — scan dropped",
                "ERROR", "ff0000"
            )
            return jsonify({
                "type": "assignment",
                "action": "assignment_bad_target",
                "location": target, "slot": slot,
                "found_type": found_type,
            }), 400

        # Validate slot is within Max Spools range.
        try:
            max_slots = int(str(tgt_info.get('Max Spools', '0')).strip() or '0')
        except ValueError:
            max_slots = 0
        try:
            slot_num = int(slot)
        except ValueError:
            slot_num = 0
        if max_slots > 0 and (slot_num < 1 or slot_num > max_slots):
            state.add_log_entry(
                f"❌ Slot <b>{slot}</b> out of range for {target} (has {max_slots} slots) — scan dropped",
                "ERROR", "ff0000"
            )
            return jsonify({
                "type": "assignment",
                "action": "assignment_bad_slot",
                "location": target, "slot": slot,
                "max_slots": max_slots,
            }), 400

        # Pull the first spool off the buffer.
        # Note: if the buffer is empty, the frontend treats the scan as a
        # "pickup" request (read slot contents and put them in the buffer).
        # That path emits its own log entry on success, so we don't add one
        # here — otherwise every pickup would generate a misleading warning.
        buffer = getattr(state, 'GLOBAL_BUFFER', []) or []
        first_spool = next((item for item in buffer if isinstance(item, dict) and item.get('id')), None)
        if not first_spool:
            return jsonify({
                "type": "assignment",
                "action": "assignment_no_buffer",
                "location": target, "slot": slot,
            }), 200

        spool_id = int(first_spool['id'])
        move_result = logic.perform_smart_move(
            target, [spool_id], target_slot=slot, origin='slot_qr_scan'
        )
        # perform_smart_move now handles auto-deploy internally when the
        # target slot is bound to a toolhead. Pick up the deployed-to
        # hint from its response so we can surface it in the toast.
        auto_deployed_to = (move_result or {}).get('auto_deployed_to')

        # Remove the spool from the backend's buffer replica.
        state.GLOBAL_BUFFER = [
            item for item in buffer
            if not (isinstance(item, dict) and int(item.get('id') or 0) == spool_id)
        ]
        remaining = len(state.GLOBAL_BUFFER)
        action = 'assignment_partial' if remaining > 0 else 'assignment_done'

        suffix = f" ({remaining} still in buffer)" if remaining else ""
        if auto_deployed_to:
            log_msg = (
                f"✅ Spool #{spool_id} → <b>{target}:SLOT:{slot}</b> "
                f"→ <b>{auto_deployed_to}</b>{suffix}"
            )
        else:
            log_msg = f"✅ Spool #{spool_id} → <b>{target}:SLOT:{slot}</b>{suffix}"
        state.add_log_entry(log_msg, "SUCCESS", "00ff00")
        return jsonify({
            "type": "assignment",
            "action": action,
            "location": target, "slot": slot,
            "moved": spool_id,
            "auto_deployed_to": auto_deployed_to,
            "remaining_buffer": remaining,
            "smart_move": move_result,
        }), 200

    return jsonify(res)


@app.route('/api/buffer/clear', methods=['POST'])
def api_buffer_clear():
    """Wipe the backend's buffer replica. Used by tests + frontend reset."""
    state.GLOBAL_BUFFER = []
    return jsonify({"success": True, "buffer": []})


# ---------------------------------------------------------------------------
# Phase 2 — Dryer Box ↔ Toolhead bindings
# ---------------------------------------------------------------------------

@app.route('/api/dryer_box/<loc_id>/bindings', methods=['GET'])
def api_dryer_box_bindings_get(loc_id):
    bindings = locations_db.get_dryer_box_bindings(loc_id)
    if bindings is None:
        return jsonify({"error": "not_a_dryer_box", "location": loc_id}), 404
    return jsonify({"location": loc_id, "slot_targets": bindings})


@app.route('/api/dryer_box/<loc_id>/bindings', methods=['PUT'])
def api_dryer_box_bindings_put(loc_id):
    data = request.get_json(silent=True) or {}
    slot_targets = data.get('slot_targets')
    if slot_targets is None:
        state.add_log_entry(
            f"❌ Feeds save rejected on <b>{loc_id}</b>: missing slot_targets",
            "ERROR", "ff0000"
        )
        return jsonify({"error": "missing_slot_targets"}), 400
    cfg = config_loader.load_config()
    printer_map = cfg.get('printer_map', {}) or {}
    ok, errors, warnings = locations_db.set_dryer_box_bindings(loc_id, slot_targets, printer_map)
    if not ok:
        reasons = "; ".join(f"slot {e[0]} → {e[1]}: {e[2]}" for e in errors) or "validation failed"
        state.add_log_entry(
            f"❌ Feeds save rejected on <b>{loc_id}</b>: {reasons}",
            "ERROR", "ff0000"
        )
        return jsonify({
            "error": "validation_failed",
            "location": loc_id,
            "errors": [
                {"slot": e[0], "target": e[1], "reason": e[2]} for e in errors
            ],
        }), 400
    state.add_log_entry(
        f"🔗 Bindings updated for <b>{loc_id}</b>"
        + (f" ⚠️ {len(warnings)} warning(s)" if warnings else ""),
        "INFO", "00d4ff"
    )
    for w_slot, w_target, w_reason in warnings:
        state.add_log_entry(
            f"⚠️ Binding warning on <b>{loc_id}</b> slot {w_slot} → {w_target}: {w_reason}",
            "WARNING", "ffaa00"
        )
    return jsonify({
        "location": loc_id,
        "slot_targets": locations_db.get_dryer_box_bindings(loc_id) or {},
        "warnings": [
            {"slot": w[0], "target": w[1], "reason": w[2]} for w in warnings
        ],
    })


@app.route('/api/printer_map', methods=['GET'])
def api_printer_map():
    """Read-only view of config.json's printer_map, grouped for UI use:
    {
      "printers": {
        "🦝 XL": [{"location_id": "XL-1", "position": 0}, ...],
        "🦝 Core One": [...]
      }
    }
    """
    cfg = config_loader.load_config()
    printer_map = cfg.get('printer_map', {}) or {}
    grouped = {}
    for loc_id, info in printer_map.items():
        name = info.get('printer_name', 'Unknown')
        grouped.setdefault(name, []).append({
            "location_id": loc_id.upper(),
            "position": info.get('position', 0),
        })
    # Stable sort within each printer by position.
    for entries in grouped.values():
        entries.sort(key=lambda e: (e['position'], e['location_id']))
    return jsonify({"printers": grouped})


@app.route('/api/dryer_boxes/slots', methods=['GET'])
def api_all_dryer_box_slots():
    """Enumerate every slot across every Dryer Box, flat. Each entry carries
    current binding (may be null). Powers the "bind a slot to this toolhead"
    quick-picker. Cheap — single locations.json read, no Spoolman calls.
    """
    loc_list = locations_db.load_locations_list()
    out = []
    for row in loc_list:
        if row.get('Type') != locations_db.DRYER_BOX_TYPE:
            continue
        box_id = str(row.get('LocationID', '')).strip()
        try:
            max_slots = int(str(row.get('Max Spools', '0')).strip() or '0')
        except ValueError:
            max_slots = 0
        targets = (row.get('extra') or {}).get('slot_targets') or {}
        for n in range(1, max_slots + 1):
            slot = str(n)
            target = targets.get(slot)
            out.append({
                "box": box_id,
                "box_name": row.get('Name', box_id),
                "slot": slot,
                "target": target,  # None => unbound
            })
    # Sort: unbound first (so the picker can promote quickly), then by box id.
    out.sort(key=lambda e: (e['target'] is not None, e['box'], int(e['slot'])))
    return jsonify({"slots": out})


@app.route('/api/dryer_box/<loc_id>/bindings/<slot>', methods=['PUT'])
def api_single_slot_binding_put(loc_id, slot):
    """Patch a single slot's binding without needing to send the whole
    slot_targets map. Used by the quick-bind picker on the toolhead view.
    """
    data = request.get_json(silent=True) or {}
    target = data.get('target')

    # Load current bindings, update just this slot, persist through the
    # full validator so the same rules apply.
    current = locations_db.get_dryer_box_bindings(loc_id)
    if current is None:
        state.add_log_entry(
            f"❌ Binding rejected: <b>{loc_id}</b> is not a dryer box",
            "ERROR", "ff0000"
        )
        return jsonify({"error": "not_a_dryer_box", "location": loc_id}), 404
    next_targets = dict(current)
    if target in (None, '', 'null', 'None'):
        next_targets.pop(str(slot), None)
    else:
        next_targets[str(slot)] = str(target)

    cfg = config_loader.load_config()
    printer_map = cfg.get('printer_map', {}) or {}
    ok, errors, warnings = locations_db.set_dryer_box_bindings(loc_id, next_targets, printer_map)
    if not ok:
        reasons = "; ".join(f"slot {e[0]} → {e[1]}: {e[2]}" for e in errors) or "validation failed"
        state.add_log_entry(
            f"❌ Binding rejected on <b>{loc_id}</b>: {reasons}",
            "ERROR", "ff0000"
        )
        return jsonify({
            "error": "validation_failed",
            "location": loc_id, "slot": slot,
            "errors": [{"slot": e[0], "target": e[1], "reason": e[2]} for e in errors],
        }), 400
    suffix = f" → {target}" if target else " → (none)"
    state.add_log_entry(
        f"🔗 {loc_id} slot {slot}{suffix}"
        + (f" ⚠️ {len(warnings)} warning(s)" if warnings else ""),
        "INFO", "00d4ff"
    )
    for w_slot, w_target, w_reason in warnings:
        state.add_log_entry(
            f"⚠️ Binding warning on <b>{loc_id}</b> slot {w_slot} → {w_target}: {w_reason}",
            "WARNING", "ffaa00"
        )
    return jsonify({
        "location": loc_id,
        "slot": slot,
        "slot_targets": locations_db.get_dryer_box_bindings(loc_id) or {},
        "warnings": [{"slot": w[0], "target": w[1], "reason": w[2]} for w in warnings],
    })


@app.route('/api/quickswap/return', methods=['POST'])
def api_quickswap_return():
    """Reverse quick-swap: take whatever spool is currently on `toolhead`
    and send it back to the first dryer-box slot bound to that toolhead.

    Accepts either a specific toolhead location ID (e.g. "XL-1") or a
    virtual-printer prefix (e.g. "XL") — in the latter case we fan out
    across every toolhead of that printer and return the first one that
    has a spool loaded.
    """
    data = request.get_json(silent=True) or {}
    toolhead = str(data.get('toolhead', '')).strip().upper()
    if not toolhead:
        state.add_log_entry(
            "❌ Return rejected: missing toolhead in request",
            "ERROR", "ff0000"
        )
        return jsonify({"action": "return_bad_request", "error": "toolhead required"}), 400

    cfg = config_loader.load_config()
    printer_map = cfg.get('printer_map', {}) or {}

    # Build the list of toolhead IDs we should check. For a virtual
    # printer prefix, this is every toolhead in printer_map that starts
    # with "<prefix>-". For a specific toolhead, it's just that ID.
    pm_keys_up = {k.upper() for k in printer_map.keys()}
    candidate_toolheads = []
    if toolhead in pm_keys_up:
        candidate_toolheads = [toolhead]
    else:
        prefix = toolhead + '-'
        candidate_toolheads = sorted(k for k in pm_keys_up if k.startswith(prefix))

    if not candidate_toolheads:
        state.add_log_entry(
            f"⚠️ Return: {toolhead} is not a registered toolhead or printer",
            "WARNING", "ffaa00"
        )
        return jsonify({"action": "return_bad_toolhead", "toolhead": toolhead}), 404

    # 1) Find the first candidate toolhead that has a loaded spool.
    active_toolhead, spool_id = None, None
    for th in candidate_toolheads:
        residents = spoolman_api.get_spools_at_location(th)
        if residents:
            active_toolhead = th
            spool_id = int(residents[0])
            break
    if not active_toolhead:
        names = ", ".join(candidate_toolheads) if len(candidate_toolheads) > 1 else candidate_toolheads[0]
        state.add_log_entry(
            f"⚠️ Return: {names} is empty — nothing to return",
            "WARNING", "ffaa00"
        )
        return jsonify({
            "action": "return_no_spool",
            "toolhead": toolhead,
            "candidates": candidate_toolheads,
        }), 404

    # 2) Figure out where to send the spool back.
    #    Preferred: the spool's recorded physical_source (where it came
    #    from when it was deployed to this toolhead). That's what the
    #    user's mental model of "return" maps to, and it handles the
    #    multi-box-per-toolhead case correctly.
    #    Fallback: the first dryer-box slot bound to this toolhead.
    spool_data = spoolman_api.get_spool(spool_id) or {}
    extra = spool_data.get('extra') or {}
    src_loc = str(extra.get('physical_source', '') or '').strip().strip('"').upper()
    src_slot = str(extra.get('physical_source_slot', '') or '').strip().strip('"')

    loc_list = locations_db.load_locations_list()
    found_box, found_slot, found_source = None, None, None

    # Preferred path: physical_source points at a Dryer Box and that slot
    # is currently bound to `active_toolhead`. If the slot has drifted
    # (e.g. user reassigned it elsewhere), we still honor physical_source
    # as long as the box exists — it's where the user pulled the spool from.
    if src_loc:
        for row in loc_list:
            if str(row.get('LocationID', '')).strip().upper() != src_loc:
                continue
            if row.get('Type') != locations_db.DRYER_BOX_TYPE:
                break
            found_box = row['LocationID']
            found_slot = src_slot or None
            found_source = 'physical_source'
            break

    # Fallback: scan bindings for the first dryer-box slot bound to this toolhead.
    if not found_box:
        for row in loc_list:
            if row.get('Type') != locations_db.DRYER_BOX_TYPE:
                continue
            targets = (row.get('extra') or {}).get('slot_targets') or {}
            for slot, target in targets.items():
                if target and str(target).upper() == active_toolhead:
                    found_box = row['LocationID']
                    found_slot = slot
                    found_source = 'first_binding'
                    break
            if found_box:
                break

    if not found_box:
        state.add_log_entry(
            f"⚠️ Return: {active_toolhead} has no bound dryer box slot and no physical_source — can't return",
            "WARNING", "ffaa00"
        )
        return jsonify({
            "action": "return_no_binding",
            "toolhead": active_toolhead,
            "requested": toolhead,
        }), 404
    # Re-tag toolhead in the response to the actual one we acted on.
    toolhead = active_toolhead

    # 3) Send the spool back. perform_smart_move handles Filabridge + extras.
    move_result = logic.perform_smart_move(
        found_box, [spool_id], target_slot=found_slot, origin='quickswap_return'
    )
    src_note = " (original source)" if found_source == 'physical_source' else " (first bound slot)"
    slot_part = f":SLOT:{found_slot}" if found_slot else ""
    state.add_log_entry(
        f"↩️ Return: Spool #{spool_id} from <b>{toolhead}</b> → <b>{found_box}{slot_part}</b>{src_note}",
        "SUCCESS", "00ff00"
    )
    return jsonify({
        "action": "return_done",
        "moved": spool_id,
        "toolhead": toolhead,
        "box": found_box,
        "slot": found_slot,
        "source": found_source,
        "smart_move": move_result,
    }), 200


@app.route('/api/quickswap', methods=['POST'])
def api_quickswap():
    """Tap-to-swap: move the spool currently in (box, slot) into the given
    toolhead. Reuses perform_smart_move for the actual move — that
    function already handles auto-eject of any occupant, container_slot
    cleanup, physical_source tracking, and the Filabridge map_toolhead
    notification.
    """
    data = request.get_json(silent=True) or {}
    toolhead = str(data.get('toolhead', '')).strip().upper()
    box = str(data.get('box', '')).strip().upper()
    slot = str(data.get('slot', '')).strip()

    if not toolhead or not box or not slot:
        state.add_log_entry(
            f"❌ Quick-swap rejected: missing required field "
            f"(toolhead={toolhead or '—'}, box={box or '—'}, slot={slot or '—'})",
            "ERROR", "ff0000"
        )
        return jsonify({
            "action": "quickswap_bad_request",
            "error": "toolhead, box, and slot are all required",
        }), 400

    # Verify the binding actually exists. Guards against stale UI state
    # racing against a concurrent binding edit elsewhere.
    bindings = locations_db.get_dryer_box_bindings(box)
    if bindings is None:
        state.add_log_entry(
            f"❌ Quick-swap rejected: <b>{box}</b> is not a dryer box",
            "ERROR", "ff0000"
        )
        return jsonify({
            "action": "quickswap_bad_box",
            "box": box,
            "error": "not a dryer box",
        }), 404
    bound_target = bindings.get(slot)
    if not bound_target or str(bound_target).upper() != toolhead:
        state.add_log_entry(
            f"⚠️ Quick-swap: stale binding — <b>{box}:SLOT:{slot}</b> is "
            f"bound to <b>{bound_target or '(nothing)'}</b>, not {toolhead}",
            "WARNING", "ffaa00"
        )
        return jsonify({
            "action": "quickswap_not_bound",
            "box": box, "slot": slot, "toolhead": toolhead,
            "bound_to": bound_target,
            "error": "slot is not bound to this toolhead",
        }), 400

    spool_id = logic.find_spool_in_slot(box, slot)
    if not spool_id:
        state.add_log_entry(
            f"⚠️ Quick-swap: slot {box}:SLOT:{slot} is empty — no spool to move to {toolhead}",
            "WARNING", "ffaa00"
        )
        return jsonify({
            "action": "quickswap_empty_slot",
            "box": box, "slot": slot, "toolhead": toolhead,
        }), 404

    move_result = logic.perform_smart_move(
        toolhead, [spool_id], target_slot=None, origin='quickswap'
    )
    state.add_log_entry(
        f"⚡ Quick-swap: Spool #{spool_id} from <b>{box}:SLOT:{slot}</b> → <b>{toolhead}</b>",
        "SUCCESS", "00ff00"
    )
    return jsonify({
        "action": "quickswap_done",
        "moved": spool_id,
        "toolhead": toolhead, "box": box, "slot": slot,
        "smart_move": move_result,
    }), 200


@app.route('/api/machine/<path:printer_name>/toolhead_slots', methods=['GET'])
def api_machine_toolhead_slots(printer_name):
    """Reverse lookup: for a printer, return every (box, slot) pair that
    feeds each of its toolheads. `printer_name` may contain emoji and
    spaces — the <path:> converter keeps them intact across the URL."""
    cfg = config_loader.load_config()
    printer_map = cfg.get('printer_map', {}) or {}
    result = locations_db.get_bindings_for_machine(printer_name, printer_map)
    # 404 when the printer_name matches zero printer_map entries.
    if not result['toolheads']:
        return jsonify({
            "printer_name": printer_name,
            "toolheads": {},
            "error": "printer_not_found",
        }), 404
    return jsonify(result)

@app.route('/api/print_queue/pending', methods=['GET'])
def api_print_queue_pending():
    filter_type = request.args.get('filter', 'all')
    sort_type = request.args.get('sort', 'created_newest')
    
    sm_url, _ = config_loader.get_api_urls()
    items = []
    
    try:
        # Fetch Spools
        if filter_type in ['all', 'spool']:
            r_spools = requests.get(f"{sm_url}/api/v1/spool?extra=%7B%22needs_label_print%22%3Atrue%7D", timeout=2)
            if r_spools.ok:
                for s in r_spools.json():
                    s['type'] = 'spool'
                    if 'vendor' in s.get('filament', {}): s['brand'] = s['filament']['vendor'].get('name', 'Unknown')
                    items.append(s)
        
        # Fetch Filaments
        if filter_type in ['all', 'filament']:
            r_fils = requests.get(f"{sm_url}/api/v1/filament?extra=%7B%22needs_label_print%22%3Atrue%7D", timeout=2)
            if r_fils.ok:
                for f in r_fils.json():
                    f['type'] = 'filament'
                    if 'vendor' in f: f['brand'] = f['vendor'].get('name', 'Unknown')
                    items.append(f)
        
        # Sorting
        if sort_type == 'created_newest':
            items.sort(key=lambda x: x.get('registered', ''), reverse=True)
        elif sort_type == 'created_oldest':
            items.sort(key=lambda x: x.get('registered', ''))
        elif sort_type == 'id_desc':
            items.sort(key=lambda x: x.get('id', 0), reverse=True)
        elif sort_type == 'id_asc':
            items.sort(key=lambda x: x.get('id', 0))
        elif sort_type == 'brand_asc':
            items.sort(key=lambda x: (x.get('brand', '').lower(), x.get('id', 0)))
            
        return jsonify({"success": True, "items": items})
    except Exception as e:
        state.logger.error(f"Error fetching pending print queue: {e}")
        return jsonify({"success": False, "msg": str(e)})

@app.route('/api/print_queue/mark_printed', methods=['POST'])
def api_print_queue_mark_printed():
    data = request.json
    item_id = data.get('id')
    item_type = data.get('type')
    
    if not item_id or not item_type:
        return jsonify({"success": False, "msg": "Missing ID or Type"})
        
    # Strictly reject legacy IDs (they usually start with strings or have weird formats). Make sure it's int convertible.
    try:
        item_id = int(item_id)
    except ValueError:
        return jsonify({"success": False, "msg": "Legacy IDs cannot be manually marked printed. Please scan."})
        
    try:
        if item_type == 'spool':
            spool_data = spoolman_api.get_spool(item_id)
            if spool_data:
                extra = spool_data.get('extra', {})
                extra['needs_label_print'] = False   
                res = spoolman_api.update_spool(item_id, {'extra': extra})
                if res: return jsonify({"success": True})
        elif item_type == 'filament':
            fil_data = spoolman_api.get_filament(item_id)
            if fil_data:
                extra = fil_data.get('extra', {})
                extra['needs_label_print'] = False
                res = spoolman_api.update_filament(item_id, {'extra': extra})
                if res: return jsonify({"success": True})
                
        return jsonify({"success": False, "msg": "Item not found or update failed"})
    except Exception as e:
        state.logger.error(f"Error marking {item_type} #{item_id} printed: {e}")
        return jsonify({"success": False, "msg": str(e)})

@app.route('/api/print_queue/set_flag', methods=['POST'])
def api_print_queue_set_flag():
    data = request.json
    item_id = data.get('id')
    item_type = data.get('type')
    
    try:
        if item_type == 'spool':
            sd = spoolman_api.get_spool(item_id)
            if sd:
                ex = sd.get('extra', {})
                ex['needs_label_print'] = True
                spoolman_api.update_spool(item_id, {'extra': ex})
                return jsonify({"success": True})
        elif item_type == 'filament':
            fd = spoolman_api.get_filament(item_id)
            if fd:
                ex = fd.get('extra', {})
                ex['needs_label_print'] = True
                spoolman_api.update_filament(item_id, {'extra': ex})
                return jsonify({"success": True})
        return jsonify({"success": False})
    except Exception as e:
        state.logger.error(f"Error setting needs_label_print: {e}")
        return jsonify({"success": False})

@app.route('/api/print_location_label', methods=['POST'])
def api_print_location_label():
    # 1. Robust Input Handling
    raw_id = request.json.get('id')
    if not raw_id: return jsonify({"success": False, "msg": "No ID provided"})
    target_id = str(raw_id).strip().upper()
    
    state.logger.info(f"🖨️ [LABEL] Request for: {target_id}")

    # 2. Determine Output Path
    cfg = config_loader.load_config()
    base_path = cfg.get("print_settings", {}).get("csv_path", "labels.csv")
    
    output_dir = os.path.dirname(base_path)
    if not output_dir or (os.name == 'nt' and output_dir.startswith(('/', '\\'))):
        output_dir = "."
    
    if output_dir != ".":
        try: os.makedirs(output_dir, exist_ok=True)
        except: output_dir = "." 

    loc_file = os.path.join(output_dir, "labels_locations.csv")
    slot_file = os.path.join(output_dir, "slots_to_print.csv")

    try:
        locs = locations_db.load_locations_list()
        
        # 3. Robust Lookup 
        loc_data = None
        if target_id == "UNASSIGNED":
             loc_data = {"LocationID": "Unassigned", "Name": "Unassigned", "Max Spools": 0}
        else:
            for row in locs:
                if not isinstance(row, dict): continue
                row_id = ""
                for k, v in row.items():
                    if str(k).strip().lower() == 'locationid': 
                        row_id = str(v).strip().upper()
                        break
                
                if row_id == target_id:
                    loc_data = row
                    break
        
        if not loc_data:
             state.logger.warning(f"❌ [LABEL] ID {target_id} not found in DB")
             return jsonify({"success": False, "msg": "ID Not Found in DB"})

        # Get Name safely
        loc_name = target_id
        if isinstance(loc_data, dict):
            for k, v in loc_data.items():
                if str(k).strip().lower() == 'name':
                    loc_name = str(v)
                    break
        
        # Sanitize
        clean_name = sanitize_label_text(loc_name)

        # 4. Write Main Label
        file_exists = os.path.exists(loc_file)
        with open(loc_file, 'a', newline='', encoding='utf-8') as f:
            headers = ["LocationID", "Name", "Cleaned_Name", "QR_Code"]
            writer = csv.DictWriter(f, fieldnames=headers)
            if not file_exists: writer.writeheader()
            writer.writerow({
                "LocationID": target_id, 
                "Name": loc_name,
                "Cleaned_Name": clean_name,
                "QR_Code": f"LOC:{target_id}" # [ALEX FIX] Added Prefix
            })
            
        # 5. Robust Slot Logic
        max_spools = 1
        if isinstance(loc_data, dict):
            for k, v in loc_data.items():
                if str(k).strip().lower() == 'max spools':
                    try: max_spools = int(v)
                    except: max_spools = 1
                    break
            
        state.logger.info(f"ℹ️ [LABEL] Found {target_id}. Max Spools: {max_spools}")

        slots_generated = False
        if max_spools > 1:
            slot_exists = os.path.exists(slot_file)
            with open(slot_file, 'a', newline='', encoding='utf-8') as f:
                # [ALEX FIX] Added "Slot" field
                headers = ["LocationID", "Slot", "Name", "Cleaned_Name", "QR_Code"]
                writer = csv.DictWriter(f, fieldnames=headers)
                if not slot_exists: writer.writeheader()
                
                for i in range(1, max_spools + 1):
                    writer.writerow({
                        "LocationID": target_id,
                        "Slot": f"Slot {i}",
                        "Name": f"{loc_name} Slot {i}",
                        "Cleaned_Name": f"{clean_name} Slot {i}",
                        "QR_Code": f"LOC:{target_id}:SLOT:{i}"
                    })
            slots_generated = True

        # 6. Build User Message
        abs_path = str(os.path.abspath(output_dir))
        short_path = "..." + abs_path[-30:] if len(abs_path) > 30 else abs_path # type: ignore
        
        msg = f"Queue: {target_id}"
        if slots_generated: msg += f" (+{max_spools} Slots)"
        msg += f" in {short_path}"
        
        return jsonify({"success": True, "msg": msg})

    except Exception as e:
        state.logger.error(f"Print Label Error: {e}")
        return jsonify({"success": False, "msg": str(e)})

# --- REPLACED: Multi-Spool Logic instead of Multi-Color ---
@app.route('/api/get_multi_spool_filaments', methods=['GET'])
def api_get_multi_spool_filaments():
    sm_url, _ = config_loader.get_api_urls()
    try:
        # 1. Get ALL active spools
        resp = requests.get(f"{sm_url}/api/v1/spool", timeout=10)
        if not resp.ok: return jsonify([])
        all_spools = resp.json()
        
        # 2. Group by Filament ID
        fil_counts = {}
        fil_spools = {}
        fil_names = {}
        fil_vendors = {}
        
        if isinstance(all_spools, list):
            for s in all_spools:
                if not isinstance(s, dict) or s.get('archived'): continue # Skip archived
                fid = s.get('filament', {}).get('id')
                if not fid: continue
                
                if fid not in fil_counts: 
                    fil_counts[fid] = 0
                    fil_spools[fid] = []
                    fil_names[fid] = s.get('filament', {}).get('name', '')
                    fil_vendors[fid] = s.get('filament', {}).get('vendor', {}).get('name', '')
                    
                fil_counts[fid] += 1
                fil_spools[fid].append(s['id'])
            
        # 3. Filter for > 1
        candidates = []
        for fid, count in fil_counts.items():
            if count > 1:
                display_name = f"{fil_vendors.get(fid, '')} - {fil_names.get(fid, '')}".strip(" -")
                candidates.append({
                    "id": fid,
                    "display": display_name,
                    "count": count,
                    "spool_ids": fil_spools.get(fid, [])
                })
        
        return jsonify(candidates)
    except Exception as e:
        state.logger.error(f"Multi-Spool Error: {e}")
        return jsonify([])

# --- NEW ROUTE: Fetch Active Spools for a specific Filament ---
@app.route('/api/spools_by_filament', methods=['GET'])
def api_get_spools_by_filament():
    fid = request.args.get('id')
    if not fid: return jsonify([])
    
    allow_archived = request.args.get('allow_archived', 'false').lower() == 'true'
    
    sm_url, _ = config_loader.get_api_urls()
    try:
        # Get spools filtered by filament_id
        # We ask Spoolman directly: "Give me all spools for Filament ID X"
        sm_req_url = f"{sm_url}/api/v1/spool?filament_id={fid}"
        if allow_archived:
            sm_req_url += "&allow_archived=true"
        resp = requests.get(sm_req_url, timeout=5)
        if resp.ok:
            if allow_archived:
                spools = resp.json()
            else:
                spools = [s for s in resp.json() if not s.get('archived')]
            return jsonify(spools)
        return jsonify([])
    except:
        return jsonify([])

@app.route('/api/smart_move', methods=['POST'])
def api_smart_move():
    return jsonify(logic.perform_smart_move(
        request.json.get('location'), 
        request.json.get('spools'),
        target_slot=request.json.get('slot'),
        origin=request.json.get('origin', '')
    ))

# --- FILABRIDGE ERROR RECOVERY ROUTES ---

import prusalink_api

@app.route('/api/fb_recovery_spools', methods=['GET'])
def api_fb_recovery_spools():
    import os
    printer_name = request.args.get('printer_name')
    error_id = request.args.get('error_id')
    if not printer_name:
        return jsonify({"success": False, "msg": "Missing printer_name"})
        
    if error_id:
        try:
            snap_path = os.path.join(os.path.dirname(__file__), "data", "filabridge_error_snapshots.json")
            if os.path.exists(snap_path):
                with open(snap_path, 'r', encoding='utf-8') as f:
                    snapshots = json.load(f)
                if error_id in snapshots:
                    return jsonify({"success": True, "spools": snapshots[error_id]})
        except Exception:
            pass
    
    cfg = config_loader.load_config()
    printer_map = cfg.get("printer_map", {})
    
    # Find which FilaBridge toolheads map to which spoolman location keys
    # Typically, the location ID is the key in printer_map, and it has 'printer_name'
    target_locations = []
    for loc_id, p_info in printer_map.items():
        if p_info.get('printer_name') == printer_name:
            target_locations.append(loc_id)
            
    if not target_locations:
        return jsonify({"success": False, "msg": "Printer name not found in printer_map"})
        
    spools = []
    for loc in target_locations:
        loc_spools = spoolman_api.get_spools_at_location_detailed(loc)
        spools.extend(loc_spools)
        
    return jsonify({"success": True, "spools": spools})

@app.route('/api/fb_parse_status', methods=['GET'])
def api_fb_parse_status():
    import prusalink_api
    return jsonify({"msg": prusalink_api.FB_PARSE_STATUS})

@app.route('/api/fb_aggressive_parse', methods=['POST'])
def api_fb_aggressive_parse():
    data = request.json
    printer_name = data.get('printer_name')
    filename = data.get('filename')
    error_id = data.get('error_id')
    
    if not all([printer_name, filename, error_id]):
        return jsonify({"success": False, "msg": "Missing parameters"})
        
    _, fb_url = config_loader.get_api_urls()
    fb_base = fb_url.replace('/api', '')
    
    # 1. Fetch credentials
    creds = prusalink_api.fetch_printer_credentials(fb_url, printer_name)
    if not creds:
        return jsonify({"success": False, "msg": "Could not fetch printer credentials from FilaBridge"})
        
    ip_addr = creds['ip_address']
    api_key = creds['api_key']
    
    # 2. Parse GCode
    state.add_log_entry(f"🔍 Starting aggressive parse for '{filename}' on {printer_name}...", "INFO")
    usage_map = prusalink_api.download_gcode_and_parse_usage(ip_addr, api_key, filename)
    
    if not usage_map:
        return jsonify({"success": False, "msg": "Failed to parse filament usage from GCode"})
        
    # 3. Apply weights to mapped spools
    cfg = config_loader.load_config()
    printer_map = cfg.get("printer_map", {})
    
    spools_updated = 0
    for loc_id, p_info in printer_map.items():
        if p_info.get('printer_name') == printer_name:
            toolhead_idx = p_info.get('position', 0)
            if toolhead_idx in usage_map:
                weight_used = usage_map[toolhead_idx]
                loc_spools = spoolman_api.get_spools_at_location(loc_id)
                # Deduct weight directly
                for sid in loc_spools:
                    spool_data = spoolman_api.get_spool(sid)
                    if spool_data and weight_used > 0:
                        used = float(spool_data.get('used_weight', 0))
                        initial = float(spool_data.get('initial_weight', 0) or 0)
                        remaining = max(0, initial - used)
                        new_remaining = max(0, remaining - weight_used)
                        new_used = used + weight_used
                        if spoolman_api.update_spool(sid, {"used_weight": new_used}):
                            spools_updated += 1
                            info = spoolman_api.format_spool_display(spool_data)
                            strat = "Fast-Fetch" if "Fast" in prusalink_api.FB_PARSE_STATUS else "RAM-Fetch"
                            state.add_log_entry(f"✔️ Auto-deducted {weight_used:.1f}g from Spool #{sid} ({strat}): [{remaining:.1f}g at start ➔ {new_remaining:.1f}g remaining]", "SUCCESS", info['color'])
                            
    # 4. Acknowledge Error
    if spools_updated > 0:
        ack = prusalink_api.acknowledge_filabridge_error(fb_url, error_id)
        if ack:
            return jsonify({"success": True, "msg": f"Successfully parsed and updated {spools_updated} spools."})
        else:
            return jsonify({"success": True, "msg": "Updated spools but failed to acknowledge error."})
            
    return jsonify({"success": False, "msg": "Parsed usage but no matching active spools found."})

@app.route('/api/fb_manual_recovery', methods=['POST'])
def api_fb_manual_recovery():
    data = request.json
    error_id = data.get('error_id')
    updates = data.get('updates', {}) # dict of sid -> weight_used (diff)
    
    if not error_id:
        return jsonify({"success": False, "msg": "Missing error_id"})
        
    spools_updated = 0
    for sid, weight_used in updates.items():
        try:
            w = float(weight_used)
            if w > 0:
                spool_data = spoolman_api.get_spool(sid)
                if spool_data:
                    used = float(spool_data.get('used_weight', 0))
                    initial = float(spool_data.get('initial_weight', 0) or 0)
                    remaining = max(0, initial - used)
                    new_remaining = max(0, remaining - w)
                    new_used = used + w
                    if spoolman_api.update_spool(sid, {"used_weight": new_used}):
                        spools_updated += 1
                        info = spoolman_api.format_spool_display(spool_data)
                        state.add_log_entry(f"✔️ Manually deducted {w:.1f}g from Spool #{sid}: [{remaining:.1f}g at start ➔ {new_remaining:.1f}g remaining]", "SUCCESS", info['color'])
        except ValueError:
            pass
            
    _, fb_url = config_loader.get_api_urls()
    prusalink_api.acknowledge_filabridge_error(fb_url, error_id)
    
    return jsonify({"success": True, "msg": f"Updated {spools_updated} spools."})

# --- PERSISTENCE ROUTES ---
@app.route('/api/state/buffer', methods=['GET', 'POST'])
def api_state_buffer():
    if request.method == 'POST':
        state.GLOBAL_BUFFER = request.json.get('buffer', [])
        return jsonify({"success": True})
    return jsonify(state.GLOBAL_BUFFER)

@app.route('/api/state/queue', methods=['GET', 'POST'])
def api_state_queue():
    if request.method == 'POST':
        state.GLOBAL_QUEUE = request.json.get('queue', [])
        return jsonify({"success": True})
    return jsonify(state.GLOBAL_QUEUE)

@app.route('/api/spools/refresh', methods=['POST'])
def api_spools_refresh():
    spools = request.json.get('spools', [])
    if not isinstance(spools, list):
        return jsonify({"error": "spools must be a list"}), 400
    if len(spools) == 0:
        return jsonify({})
    return jsonify(logic.get_live_spools_data(spools))

@app.route('/api/log_event', methods=['POST'])
def api_log_event():
    msg = request.json.get('msg', '')
    level = request.json.get('level', 'INFO')
    if msg: state.add_log_entry(msg, level)
    return jsonify({"success": True})

@app.route('/api/logs', methods=['GET'])
def api_get_logs_route():
    sm_url, fb_url = config_loader.get_api_urls()
    sm_ok, fb_ok = False, False
    try: sm_ok = requests.get(f"{sm_url}/api/v1/health", timeout=3).ok
    except: pass
    
    try: 
        fb_resp = requests.get(f"{fb_url}/status", timeout=3)
        fb_ok = fb_resp.ok
        
        # [NEW] Check for FilaBridge Print Errors
        if fb_ok:
            try:
                err_resp = requests.get(f"{fb_url}/print-errors", timeout=2)
                if err_resp.ok:
                    fb_errors = err_resp.json().get('errors', [])
                    
                    cfg = config_loader.load_config()
                    auto_recover = cfg.get("auto_recover_filabridge_errors", True)
                    
                    for err in fb_errors:
                        err_id = err.get('id')
                        # Only alert if we haven't seen it and the user hasn't naturally acknowledged it in FilaBridge
                        if err_id and not err.get('acknowledged', False):
                            if err_id not in state.ACKNOWLEDGED_FILABRIDGE_ERRORS:
                                state.ACKNOWLEDGED_FILABRIDGE_ERRORS.add(err_id)
                                p_name = err.get('printer_name', 'Unknown Printer')
                                f_name = err.get('filename', 'Unknown File')
                                err_msg = err.get('error', 'Unknown Error')
                                
                                # Snapshot active spools at time of error
                                try:
                                    import os
                                    target_locations = []
                                    printer_map = config_loader.load_config().get("printer_map", {})
                                    for loc_id, p_info in printer_map.items():
                                        if p_info.get('printer_name') == p_name:
                                            target_locations.append(loc_id)
                                    spools = []
                                    for loc in target_locations:
                                        spools.extend(spoolman_api.get_spools_at_location_detailed(loc))
                                    snap_path = os.path.join(os.path.dirname(__file__), "data", "filabridge_error_snapshots.json")
                                    snapshots = {}
                                    if os.path.exists(snap_path):
                                        with open(snap_path, 'r', encoding='utf-8') as f:
                                            snapshots = json.load(f)
                                    snapshots[err_id] = spools
                                    os.makedirs(os.path.dirname(snap_path), exist_ok=True)
                                    with open(snap_path, 'w', encoding='utf-8') as f:
                                        json.dump(snapshots, f)
                                except Exception as snap_e:
                                    state.logger.error(f"Failed to snapshot spools for error {err_id}: {snap_e}")

                                def _auto_recover_task(e_id, printer_name, filename, error_msg):
                                    state.add_log_entry(f"🔄 Auto-Recovering FilaBridge Error for {printer_name}...", "INFO")
                                    creds = prusalink_api.fetch_printer_credentials(fb_url, printer_name)
                                    if creds:
                                        usage_map = prusalink_api.download_gcode_and_parse_usage(creds['ip_address'], creds['api_key'], filename)
                                        if usage_map:
                                            printer_map = config_loader.load_config().get("printer_map", {})
                                            spools_updated = 0
                                            for loc_id, p_info in printer_map.items():
                                                if p_info.get('printer_name') == printer_name:
                                                    toolhead_idx = p_info.get('position', 0)
                                                    if toolhead_idx in usage_map:
                                                        w_used = usage_map[toolhead_idx]
                                                        for sid in spoolman_api.get_spools_at_location(loc_id):
                                                            spool = spoolman_api.get_spool(sid)
                                                            if spool and w_used > 0:
                                                                used = float(spool.get('used_weight', 0))
                                                                initial = float(spool.get('initial_weight', 0) or 0)
                                                                remaining = max(0, initial - used)
                                                                new_rem = max(0, remaining - w_used)
                                                                new_used = used + w_used
                                                                if spoolman_api.update_spool(sid, {"used_weight": new_used}):
                                                                    spools_updated += 1
                                                                    inf = spoolman_api.format_spool_display(spool)
                                                                    strat = "Fast-Fetch" if "Fast" in prusalink_api.FB_PARSE_STATUS else "RAM-Fetch"
                                                                    state.add_log_entry(f"✔️ Auto-deducted {w_used:.1f}g from Spool #{sid} ({strat}): [{remaining:.1f}g at start ➔ {new_rem:.1f}g remaining]", "SUCCESS", inf['color'])
                                            if spools_updated > 0:
                                                prusalink_api.acknowledge_filabridge_error(fb_url, e_id)
                                                return # Success
                                                
                                    # Fallback if auto-recover fails or wasn't applicable
                                    state.add_log_entry(
                                        f"🔴 FilaBridge: [{printer_name}] failed to parse weight for '{filename}': {error_msg}",
                                        "WARNING",
                                        meta={"type": "filabridge_error", "error_id": e_id, "printer_name": printer_name, "filename": filename}
                                    )

                                if auto_recover:
                                    import threading
                                    threading.Thread(target=_auto_recover_task, args=(err_id, p_name, f_name, err_msg), daemon=True).start()
                                else:
                                    state.add_log_entry(
                                        f"🔴 FilaBridge: [{p_name}] failed to parse weight for '{f_name}': {err_msg}",
                                        "WARNING",
                                        meta={"type": "filabridge_error", "error_id": err_id, "printer_name": p_name, "filename": f_name}
                                    )
            except Exception as e:
                pass # Don't crash the log poller if FilaBridge errors endpoint times out
                
    except: pass
    
    return jsonify({
        "logs": state.RECENT_LOGS,
        "undo_available": len(state.UNDO_STACK) > 0,
        "audit_active": state.AUDIT_SESSION.get('active', False),
        "status": {"spoolman": sm_ok, "filabridge": fb_ok}
    })

if __name__ == '__main__':
    state.logger.info(f"🛠️ Server {VERSION} Started")
    app.run(host='0.0.0.0', port=8000)
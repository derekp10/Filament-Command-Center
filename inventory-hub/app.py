from flask import Flask, request, jsonify, render_template
import requests
import state
import config_loader
import locations_db
import spoolman_api
import logic
import csv
import os
import json

VERSION = "v154.25 (Overwrite CSV Logic)"
app = Flask(__name__)

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
    
    return render_template('dashboard.html', version=VERSION, spoolman_url=sm_url)

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
    if not spool: return jsonify({"success": False, "msg": "Spool not found"})

    # Browser Mode: Just return data
    return jsonify({"success": True, "method": "browser", "data": spool})

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
            # 🧹 STRICT HEADERS for Locations (No Spool data allowed)
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
        for item_id in ids:
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
                    # This handles cases where the location exists in Spoolman but not the CSV
                    sm_url, _ = config_loader.get_api_urls()
                    try:
                        # Attempt to fetch location details from Spoolman
                        resp = requests.get(f"{sm_url}/api/v1/location/{item_id}", timeout=2)
                        if resp.ok:
                            s_data = resp.json()
                            name = s_data.get('name', str(item_id))
                        else:
                            name = str(item_id) # 404/Error: Fallback to ID
                    except:
                        name = str(item_id) # Network Error: Fallback to ID
                
                row_data['LocationID'] = item_id
                row_data['Name'] = name
                row_data['QR_Code'] = item_id

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
                
                if max_spools > 1:
                    for i in range(1, max_spools + 1):
                        slots_to_print.append({
                            "LocationID": item_id,
                            "Name": f"{name} Slot {i}",
                            "Cleaned_Name": f"{clean_name} Slot {i}",
                            "QR_Code": f"LOC:{item_id}:SLOT:{i}"
                        })

                # --- SLOT GENERATION ---
                max_spools = 0
                if loc_data:
                    # Robust lookup for 'Max Spools' in the CSV data
                    for k, v in loc_data.items():
                        if k.strip().lower() == 'max spools':
                            try: max_spools = int(v)
                            except: max_spools = 0
                            break
                
                if max_spools > 1:
                    for i in range(1, max_spools + 1):
                        slots_to_print.append({
                            "LocationID": item_id,
                            "Name": f"{name} Slot {i}",
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
        slots_filename = "labels_slots.csv"
        if slots_to_print:
            slots_path = os.path.join(folder, slots_filename)
            slots_exists = os.path.exists(slots_path)
            
            with open(slots_path, write_mode, newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=["LocationID", "Name", "Cleaned_Name", "QR_Code"])
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
    csv_rows = locations_db.load_locations_list()
    occupancy_map = {}
    sm_url, _ = config_loader.get_api_urls()
    try:
        resp = requests.get(f"{sm_url}/api/v1/spool", timeout=5)
        if resp.ok:
            for s in resp.json():
                loc = s.get('location', '').upper().strip()
                if loc: occupancy_map[loc] = occupancy_map.get(loc, 0) + 1
    except: pass

    final_list = []
    for row in csv_rows:
        lid = row['LocationID'].upper()
        max_s = row.get('Max Spools', '')
        max_val = int(max_s) if max_s and max_s.isdigit() else 0
        curr_val = occupancy_map.get(lid, 0)
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
    current_list.sort(key=lambda x: x['LocationID'])
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
    elif action == 'remove':
        if str(spool_input).isdigit(): spool_id = int(spool_input)
        
    if not spool_id: return jsonify({"success": False, "msg": "Spool not found"})

    if action == 'remove':
        if logic.perform_smart_eject(spool_id): return jsonify({"success": True})
        else: return jsonify({"success": False, "msg": "DB Update Failed"})
    elif action == 'add':
        return jsonify(logic.perform_smart_move(loc_id, [spool_id], target_slot=slot_arg))
    return jsonify({"success": False})

@app.route('/api/identify_scan', methods=['POST'])
def api_identify_scan():
    text = request.json.get('text', '')
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
            info = spoolman_api.format_spool_display(data)
            return jsonify({"type": "spool", "id": int(sid), "display": info['text'], "color": info['color']})
            
    if res['type'] == 'filament':
        fid = res['id']
        data = spoolman_api.get_filament(fid)
        if data:
            name = data.get('name', 'Unknown Filament')
            return jsonify({"type": "filament", "id": int(fid), "display": name})

    return jsonify(res)

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
    # Fallback to current dir if config path is empty or root-bound on Windows without drive letter
    if not output_dir or (os.name == 'nt' and output_dir.startswith(('/', '\\'))):
        output_dir = "."
    
    # Ensure directory exists
    if output_dir != ".":
        try: os.makedirs(output_dir, exist_ok=True)
        except: output_dir = "." # Fallback on permission error

    loc_file = os.path.join(output_dir, "labels_locations.csv")
    slot_file = os.path.join(output_dir, "slots_to_print.csv")

    try:
        locs = locations_db.load_locations_list()
        
        # 3. Robust Lookup (Find row where LocationID matches, ignoring case/whitespace)
        loc_data = None
        for row in locs:
            row_id = ""
            # Iterate keys to find 'LocationID' case-insensitively
            for k, v in row.items():
                if k.strip().lower() == 'locationid': 
                    row_id = v.strip().upper()
                    break
            
            if row_id == target_id:
                loc_data = row
                break
        
        if not loc_data:
             state.logger.warning(f"❌ [LABEL] ID {target_id} not found in DB")
             return jsonify({"success": False, "msg": "ID Not Found in DB"})

        # Get Name safely
        loc_name = target_id
        for k, v in loc_data.items():
            if k.strip().lower() == 'name':
                loc_name = v
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
                "QR_Code": target_id
            })
            
        # 5. Robust Slot Logic
        max_spools = 1
        for k, v in loc_data.items():
            if k.strip().lower() == 'max spools':
                try: max_spools = int(v)
                except: max_spools = 1
                break
            
        state.logger.info(f"ℹ️ [LABEL] Found {target_id}. Max Spools: {max_spools}")

        slots_generated = False
        if max_spools > 1:
            slot_exists = os.path.exists(slot_file)
            with open(slot_file, 'a', newline='', encoding='utf-8') as f:
                headers = ["LocationID", "Name", "Cleaned_Name", "QR_Code"]
                writer = csv.DictWriter(f, fieldnames=headers)
                if not slot_exists: writer.writeheader()
                
                for i in range(1, max_spools + 1):
                    writer.writerow({
                        "LocationID": target_id,
                        "Name": f"{loc_name} Slot {i}",
                        "Cleaned_Name": f"{clean_name} Slot {i}",
                        "QR_Code": f"LOC:{target_id}:SLOT:{i}"
                    })
            slots_generated = True

        # 6. Build User Message
        abs_path = os.path.abspath(output_dir)
        short_path = "..." + abs_path[-30:] if len(abs_path) > 30 else abs_path
        
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
        for s in all_spools:
            if s.get('archived'): continue # Skip archived
            fid = s.get('filament', {}).get('id')
            if not fid: continue
            
            if fid not in fil_counts: 
                fil_counts[fid] = {
                    "count": 0, 
                    "spools": [], 
                    "name": s.get('filament', {}).get('name'),
                    "vendor": s.get('filament', {}).get('vendor', {}).get('name')
                }
            fil_counts[fid]["count"] += 1
            fil_counts[fid]["spools"].append(s['id'])
            
        # 3. Filter for > 1
        candidates = []
        for fid, data in fil_counts.items():
            if data['count'] > 1:
                display_name = f"{data['vendor']} - {data['name']}"
                candidates.append({
                    "id": fid,
                    "display": display_name,
                    "count": data['count'],
                    "spool_ids": data['spools']
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
    
    sm_url, _ = config_loader.get_api_urls()
    try:
        # Get spools filtered by filament_id
        # We ask Spoolman directly: "Give me all spools for Filament ID X"
        resp = requests.get(f"{sm_url}/api/v1/spool?filament_id={fid}", timeout=5)
        if resp.ok:
            # Filter out archived ones just in case
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
        target_slot=request.json.get('slot')
    ))

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

@app.route('/api/logs', methods=['GET'])
def api_get_logs_route():
    sm_url, fb_url = config_loader.get_api_urls()
    sm_ok, fb_ok = False, False
    try: sm_ok = requests.get(f"{sm_url}/api/v1/health", timeout=1).ok
    except: pass
    try: fb_ok = requests.get(f"{fb_url}/status", timeout=1).ok
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
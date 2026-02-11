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

VERSION = "v154.20 (Queue + Explicit CSV Columns)"
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

# --- HELPER FUNCTIONS (PRESERVED) ---
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

@app.route('/api/print_batch_csv', methods=['POST'])
def api_print_batch_csv():
    data = request.json
    ids = data.get('ids', [])
    mode = data.get('mode', 'spool') # 'spool' or 'filament'
    
    if not ids: return jsonify({"success": False, "msg": "Empty Queue"})

    cfg = config_loader.load_config()
    
    # Filename strategy
    filename = "labels_spool.csv" if mode == 'spool' else "labels_swatch.csv"
    csv_path = cfg.get("print_settings", {}).get("csv_path", filename)
    
    if "/" in csv_path or "\\" in csv_path:
        folder = os.path.dirname(csv_path)
        csv_path = os.path.join(folder, filename)

    try:
        items_to_print = []
        
        # 1. Define the MANDATORY columns that must exist and be first
        core_headers = ['ID', 'Brand', 'Color', 'Type', 'Hex', 'Red', 'Green', 'Blue', 'Weight', 'QR_Code']
        
        for item_id in ids:
            # Fetch Data
            if mode == 'spool':
                raw_data = spoolman_api.get_spool(item_id)
                if not raw_data: continue
                fil_data = raw_data.get('filament', {})
                vendor_data = fil_data.get('vendor', {})
                fil_extra = fil_data.get('extra', {})
            else:
                raw_data = spoolman_api.get_filament(item_id)
                if not raw_data: continue
                fil_data = raw_data
                vendor_data = raw_data.get('vendor', {})
                fil_extra = raw_data.get('extra', {})

            # --- CALCULATE CORE FIELDS (USER LOGIC RESTORED) ---
            row_data = {}
            
            row_data['ID'] = item_id
            
            # Brand
            row_data['Brand'] = vendor_data.get('name', 'Unknown') if vendor_data else 'Unknown'
            
            # Color
            row_data['Color'] = get_color_name(fil_data)
            
            # Type (Smart Type)
            raw_material = fil_data.get('material', 'Unknown')
            row_data['Type'] = get_smart_type(raw_material, fil_extra)
            
            # Hex & RGB
            hex_val = get_best_hex(fil_data)
            row_data['Hex'] = hex_val
            r, g, b = hex_to_rgb(hex_val)
            row_data['Red'] = r
            row_data['Green'] = g
            row_data['Blue'] = b
            
            # Weight (Filament Capacity for labels)
            # Using fil.get('weight') as per user request to match original snippet
            row_data['Weight'] = f"{fil_data.get('weight', 0):.0f}g"
            
            # QR Code
            prefix = "ID:" if mode == 'spool' else "FIL:"
            row_data['QR_Code'] = f"{prefix}{item_id}"

            # --- FLATTEN & MERGE EXTRA DATA ---
            # This ensures we have the "Dump All" feature while keeping Core fields prioritized
            flat_data = flatten_json(raw_data)
            
            # Merge flat data into row_data, but DO NOT overwrite the Core keys we just calculated
            for k, v in flat_data.items():
                if k not in row_data:
                    row_data[k] = v
            
            items_to_print.append(row_data)

        if not items_to_print:
            return jsonify({"success": False, "msg": "No valid data found"})

        # 2. Determine Final Header List
        # Start with Core Headers (in order)
        final_headers = list(core_headers)
        
        # Add any other keys found in the items, sorted
        all_keys = set()
        for item in items_to_print:
            all_keys.update(item.keys())
            
        extra_headers = sorted([k for k in all_keys if k not in core_headers])
        final_headers.extend(extra_headers)

        # 3. Write to CSV
        file_exists = os.path.exists(csv_path)
        
        with open(csv_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=final_headers)
            
            # Logic: If file doesn't exist, write headers.
            # If it does exist, we append. 
            # Note: DictWriter will raise ValueError if we try to write fields not in 'fieldnames'
            # if the file was opened with different fieldnames previously.
            # However, since we are re-defining fieldnames based on THIS batch, 
            # we need to be careful if appending to a file with FEWER columns.
            # For robustness in "Append" mode with variable schemas, 'extrasaction=ignore' 
            # is safer if we want to preserve the OLD file structure, 
            # BUT the user wants ALL data.
            # Ideally, the user deletes the file to get a fresh schema. 
            
            if not file_exists:
                writer.writeheader()
                writer.writerows(items_to_print)
            else:
                # If appending, we must respect the headers we just calculated for THIS batch.
                # But we can't change the physical headers of the existing file easily.
                # We will try to write. If the new data has columns the old file didn't,
                # they will just be appended without a header in the CSV text (which is messy but preserves data),
                # OR we accept that appending only works perfectly if schema is stable.
                
                # To be safe and compliant with DictWriter:
                writer = csv.DictWriter(f, fieldnames=final_headers, extrasaction='ignore')
                writer.writerows(items_to_print)

        return jsonify({"success": True, "count": len(items_to_print), "file": filename})

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

# NEW: Filament Details Route
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

    # --- AUDIT MODE INTERCEPTION ---
    if res and res.get('type') == 'command' and res.get('cmd') == 'audit':
        state.reset_audit()
        state.AUDIT_SESSION['active'] = True
        state.add_log_entry("🕵️‍♀️ <b>AUDIT MODE STARTED</b>", "INFO", "ff00ff")
        state.add_log_entry("Scan a Location label to begin checking.", "INFO")
        return jsonify({"type": "command", "cmd": "clear"}) 

    if state.AUDIT_SESSION.get('active'):
        logic.process_audit_scan(res)
        return jsonify({"type": "command", "cmd": "clear"})

    # Standard Operation
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
            
    # NEW: Filament Scan Handling
    if res['type'] == 'filament':
        fid = res['id']
        data = spoolman_api.get_filament(fid)
        if data:
            name = data.get('name', 'Unknown Filament')
            return jsonify({"type": "filament", "id": int(fid), "display": name})

    return jsonify(res)

@app.route('/api/smart_move', methods=['POST'])
def api_smart_move():
    return jsonify(logic.perform_smart_move(request.json.get('location'), request.json.get('spools')))

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
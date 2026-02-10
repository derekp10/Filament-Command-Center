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

VERSION = "v154.9 (Spoolman Link Fixed)"
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
    # FIX: Added /#/ for Spoolman's SPA routing
    sm_url = f"http://{ip}:{port}"
    
    return render_template('dashboard.html', version=VERSION, spoolman_url=sm_url)

# --- HELPER FUNCTIONS FOR LABELS ---
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
    if not ids: return jsonify({"success": False, "msg": "Empty Queue"})

    cfg = config_loader.load_config()
    csv_path = cfg.get("print_settings", {}).get("csv_path", "labels.csv")

    try:
        file_exists = os.path.exists(csv_path)
        with open(csv_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['ID', 'Brand', 'Color', 'Type', 'Hex', 'Red', 'Green', 'Blue', 'Weight', 'QR_Code'])
            
            for sid in ids:
                spool = spoolman_api.get_spool(sid)
                if not spool: continue
                
                fil = spool.get('filament', {})
                vend = fil.get('vendor', {})
                fil_extra = fil.get('extra', {})

                brand = vend.get('name', 'Unknown')
                name = get_color_name(fil)
                material = fil.get('material', 'Unknown')
                smart_type = get_smart_type(material, fil_extra)
                hex_val = get_best_hex(fil)
                r, g, b = hex_to_rgb(hex_val)
                weight = f"{fil.get('weight', 0):.0f}g"
                qr = f"ID:{sid}"
                
                writer.writerow([sid, brand, name, smart_type, hex_val, r, g, b, weight, qr])

        return jsonify({"success": True, "count": len(ids)})
    except PermissionError:
        return jsonify({"success": False, "msg": "CSV File Locked! Close Excel."})
    except Exception as e:
        state.logger.error(f"Batch CSV Error: {e}")
        return jsonify({"success": False, "msg": str(e)})

# --- EXISTING ROUTES ---

@app.route('/api/locations', methods=['GET'])
def api_get_locations(): 
    csv_rows = locations_db.load_locations_list()
    # Merge with Occupancy Data
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

@app.route('/api/manage_contents', methods=['POST'])
def api_manage_contents():
    # This function handles Manual Add/Remove/Move actions from the UI buttons
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
    # This function handles the "Enter Spool ID" text box input
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
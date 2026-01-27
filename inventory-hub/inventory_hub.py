from flask import Flask, request, jsonify, Response, render_template
import requests
import logging
from logging.handlers import RotatingFileHandler
import re
import sys
import json
import urllib.parse
import time
import os
import csv
import io

# --- LOGGING SETUP ---
logger = logging.getLogger("InventoryHub")
logger.setLevel(logging.INFO)
c_handler = logging.StreamHandler(sys.stdout)
c_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(c_handler)
f_handler = RotatingFileHandler('hub.log', maxBytes=1000000, backupCount=5)
f_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(f_handler)

app = Flask(__name__)

# --- CONFIG & CONSTANTS ---
CONFIG_FILE = 'config.json'
CSV_FILE = '3D Print Supplies - Locations.csv'
UNDO_STACK = []
RECENT_LOGS = [] 
VERSION = "v95.0 (Detail Restoration)"

def load_config():
    defaults = {
        "server_ip": "127.0.0.1", "spoolman_port": 7912, "filabridge_port": 5000,
        "sync_delay": 0.5, "printer_map": {}, "feeder_map": {}, "dryer_slots": []
    }
    final_config = defaults.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f: 
                loaded = json.load(f)
                final_config.update(loaded)
        except Exception as e: logger.error(f"Config Load Error: {e}")
            
    # Normalize Printer Keys to Upper Case for matching
    if 'printer_map' in final_config:
        final_config['printer_map'] = {k.upper(): v for k, v in final_config['printer_map'].items()}
    return final_config

def load_locations_list():
    locs = []
    if not os.path.exists(CSV_FILE): return []
    try:
        with open(CSV_FILE, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('LocationID'): locs.append(row)
    except Exception as e: logger.error(f"CSV Read Error: {e}")
    return locs

def save_locations_list(new_list):
    if not new_list: return
    fieldnames = ['LocationID', 'Name', 'Type', 'Location', 'Device Identifier', 'Device Type', 'Order', 'Row', 'Max Spools', 'Label Printed']
    try:
        with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(new_list)
        logger.info("💾 Locations CSV updated")
    except Exception as e: logger.error(f"CSV Write Error: {e}")

def add_log_entry(msg, category="INFO", color_hex=None):
    timestamp = time.strftime("%H:%M:%S")
    if color_hex:
        swatch = f'<span style="display:inline-block;width:24px;height:24px;border-radius:50%;background-color:#{color_hex};margin-right:10px;border:2px solid #fff;vertical-align:middle;"></span>'
        msg = swatch + f'<span style="vertical-align:middle;">{msg}</span>'
    entry = {"time": timestamp, "msg": msg, "type": category}
    RECENT_LOGS.insert(0, entry)
    if len(RECENT_LOGS) > 50: RECENT_LOGS.pop()

cfg = load_config()
SERVER_IP = cfg.get("server_ip")
SPOOLMAN_URL = f"http://{SERVER_IP}:{cfg.get('spoolman_port')}"
FILABRIDGE_API_BASE = f"http://{SERVER_IP}:{cfg.get('filabridge_port')}/api"

# --- LOGIC HELPERS ---
def get_spool(sid):
    try: return requests.get(f"{SPOOLMAN_URL}/api/v1/spool/{sid}", timeout=3).json()
    except: return None

def update_spool(sid, data):
    try: requests.patch(f"{SPOOLMAN_URL}/api/v1/spool/{sid}", json=data)
    except: pass

def format_spool_display(spool_data):
    # RESTORED: Full detail string
    sid = spool_data.get('id', '?')
    rem = int(spool_data.get('remaining_weight', 0))
    fil = spool_data.get('filament', {})
    brand = fil.get('vendor', {}).get('name', 'Unknown')
    mat = fil.get('material', 'PLA')
    col = fil.get('name', 'Unknown')
    hex_color = fil.get('color_hex', 'ffffff')
    if 'original_color' in fil.get('extra', {}): col = fil.get('extra')['original_color']
    
    display_text = f"#{sid} {brand} {mat} ({col}) [{rem}g]"
    return {"text": display_text, "color": hex_color}

def find_spool_by_legacy_id(legacy_id):
    legacy_id = str(legacy_id).strip()
    try:
        resp = requests.get(f"{SPOOLMAN_URL}/api/v1/spool", timeout=5)
        if resp.ok:
            data = resp.json()
            # 1. Check Extra Field matches
            for spool in data:
                ext = str(spool.get('external_id', '')).strip().replace('"','')
                if ext == legacy_id: return spool['id']
            # 2. Check direct ID matches (Just in case)
            for spool in data:
                if str(spool['id']) == legacy_id: return spool['id']
    except: pass
    return None

def get_spools_at_location_detailed(loc_name):
    found = []
    try:
        resp = requests.get(f"{SPOOLMAN_URL}/api/v1/spool", timeout=5)
        if resp.ok:
            for s in resp.json():
                if s.get('location', '').upper() == loc_name.upper():
                    info = format_spool_display(s)
                    found.append({'id': s['id'], 'display': info['text'], 'color': info['color']})
    except: pass
    return found

def get_spools_at_location(loc_name):
    return [s['id'] for s in get_spools_at_location_detailed(loc_name)]

def resolve_scan(text):
    text = text.strip(); decoded = urllib.parse.unquote(text)
    
    if "CMD:UNDO" in text.upper(): return {'type': 'command', 'cmd': 'undo'}
    if "CMD:CLEAR" in text.upper(): return {'type': 'command', 'cmd': 'clear'}
    if "CMD:EJECT" in text.upper(): return {'type': 'command', 'cmd': 'eject'} 
    if "CMD:CONFIRM" in text.upper(): return {'type': 'command', 'cmd': 'confirm'}

    if text.upper().startswith("ID:"):
        clean_id = text[3:].strip()
        if clean_id.isdigit(): return {'type': 'spool', 'id': int(clean_id)}

    if 'google.com' in decoded.lower() or 'range=' in decoded.lower():
        m = re.search(r'range=(?:.*!)?(\d+)', decoded, re.IGNORECASE)
        if m:
            rid = find_spool_by_legacy_id(m.group(1))
            if rid: return {'type': 'spool', 'id': rid}

    # FIX: Robust Number Handling
    if text.isdigit():
        # First, try to see if it's a legacy mapping
        rid = find_spool_by_legacy_id(text)
        if rid: return {'type': 'spool', 'id': rid}
        
        # If not legacy, assume it is a Direct Spoolman ID
        return {'type': 'spool', 'id': int(text)}
        
    if len(text) > 2: return {'type': 'location', 'id': text.upper()}
    return None

def perform_smart_move(target, raw_spools):
    target = target.strip().upper()
    cfg = load_config(); printer_map = cfg.get("printer_map", {})
    loc_list = load_locations_list()
    loc_info_map = {row['LocationID'].upper(): row for row in loc_list}

    def get_max_capacity(lid):
        if lid in printer_map: return 1
        if lid in loc_info_map:
            try: return int(loc_info_map[lid]['Max Spools'])
            except: pass
        return 9999

    max_cap = get_max_capacity(target)
    occupants = get_spools_at_location(target)
    incoming_count = 0
    for s in raw_spools:
        if str(s) not in [str(x) for x in occupants]: incoming_count += 1
            
    if (len(occupants) + incoming_count) > max_cap:
        add_log_entry(f"❌ Aborted: {target} Full! ({len(occupants)}/{max_cap})", "ERROR")
        return {"status": "error", "msg": f"Full! ({len(occupants)}/{max_cap})"}

    spools = []
    for item in raw_spools:
        if str(item).isdigit(): spools.append(item)
        else:
            found = get_spools_at_location(str(item))
            if found: spools.extend(found)

    if not spools: return {"status": "error", "msg": "No spools found"}
    undo_record = {"target": target, "moves": {}, "summary": f"Moved {len(spools)} -> {target}"}

    for sid in spools:
        spool_data = get_spool(sid)
        if not spool_data: continue
        current_loc = spool_data.get('location', '').strip().upper()
        undo_record['moves'][sid] = current_loc
        current_extra = spool_data.get('extra') or {}
        info = format_spool_display(spool_data)
        
        if target in printer_map:
            new_extra = current_extra.copy()
            src_info = loc_info_map.get(current_loc)
            if src_info and src_info.get('Type') == 'Dryer Box':
                new_extra['physical_source'] = current_loc
            update_spool(sid, {"location": target, "extra": new_extra})
            
            p = printer_map[target]
            # --- FILABRIDGE WITH LOGGING ---
            try:
                add_log_entry(f"🔌 FilaBridge: Setting {p['printer_name']} T{p['position']}...", "INFO")
                fb_resp = requests.post(f"{FILABRIDGE_API_BASE}/map_toolhead", 
                              json={"printer_name": p['printer_name'], "toolhead_id": p['position'], "spool_id": int(sid)}, timeout=3)
                if fb_resp.ok:
                    add_log_entry(f"✅ FilaBridge Success", "INFO")
                else:
                    add_log_entry(f"❌ FilaBridge Fail: {fb_resp.text}", "ERROR")
            except Exception as e:
                add_log_entry(f"❌ FilaBridge Error: {e}", "ERROR")
            # -------------------------------
            
            add_log_entry(f"🖨️ {info['text']} -> {target}", "INFO", info['color'])
            
        elif target in loc_info_map and loc_info_map[target].get('Type') == 'Dryer Box':
            new_extra = current_extra.copy(); new_extra.pop('physical_source', None)
            update_spool(sid, {"location": target, "extra": new_extra})
            add_log_entry(f"📦 {info['text']} -> Dryer {target}", "INFO", info['color'])
            
        else:
            update_spool(sid, {"location": target})
            add_log_entry(f"🚚 {info['text']} -> {target}", "INFO", info['color'])

    UNDO_STACK.append(undo_record)
    return {"status": "success"}

# --- ROUTES ---
logger.info(f"🛠️ Server {VERSION} Started")

@app.route('/')
def dashboard(): return render_template('dashboard.html', version=VERSION)

@app.route('/api/locations', methods=['GET'])
def api_get_locations(): 
    csv_rows = load_locations_list()
    occupancy_map = {}
    try:
        resp = requests.get(f"{SPOOLMAN_URL}/api/v1/spool", timeout=5)
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
    current_list = load_locations_list()
    
    if old_id:
        current_list = [row for row in current_list if row['LocationID'] != old_id]
        add_log_entry(f"📝 Updated: {new_entry['LocationID']}")
    else:
        add_log_entry(f"✨ Created: {new_entry['LocationID']}")
    
    current_list.append(new_entry)
    current_list.sort(key=lambda x: x['LocationID'])
    save_locations_list(current_list)
    return jsonify({"success": True})

@app.route('/api/locations', methods=['DELETE'])
def api_delete_location():
    target = request.args.get('id', '').strip()
    if not target: return jsonify({"success": False})
    
    try:
        contents = get_spools_at_location(target)
        for sid in contents: update_spool(sid, {"location": ""})
        if contents: add_log_entry(f"🏚️ Evicted {len(contents)} spools from {target}", "WARNING")
    except: pass

    current = load_locations_list()
    new_list = [row for row in current if row['LocationID'] != target]
    save_locations_list(new_list)
    add_log_entry(f"🗑️ Deleted: {target}", "WARNING")
    return jsonify({"success": True})

@app.route('/api/undo', methods=['POST'])
def api_undo(): return undo_last_move()

@app.route('/api/get_contents', methods=['GET'])
def api_get_contents_route():
    loc = request.args.get('id', '').strip().upper()
    return jsonify(get_spools_at_location_detailed(loc))

@app.route('/api/manage_contents', methods=['POST'])
def api_manage_contents():
    data = request.json
    action = data.get('action') 
    loc_id = data.get('location', '').strip().upper() 
    spool_input = data.get('spool_id') 

    if action == 'clear_location':
        contents = get_spools_at_location(loc_id)
        for sid in contents: update_spool(sid, {"location": ""})
        add_log_entry(f"🧹 Cleared {len(contents)} items from {loc_id}", "WARNING")
        return jsonify({"success": True})

    spool_id = None
    if spool_input:
        resolution = resolve_scan(str(spool_input))
        if resolution and resolution['type'] == 'spool':
            spool_id = resolution['id']
    
    if not spool_id: return jsonify({"success": False, "msg": "Spool not found"})

    spool_data = get_spool(spool_id)
    if not spool_data: return jsonify({"success": False, "msg": "ID not in DB"})
    info = format_spool_display(spool_data)

    if action == 'remove':
        update_spool(spool_id, {"location": ""})
        add_log_entry(f"⏏️ Ejected: {info['text']}", "WARNING")
        return jsonify({"success": True})

    elif action == 'add':
        res_data = perform_smart_move(loc_id, [spool_id])
        return jsonify(res_data)

    return jsonify({"success": False})

@app.route('/api/identify_scan', methods=['POST'])
def api_identify_scan():
    res = resolve_scan(request.json.get('text', ''))
    if not res: return jsonify({"type": "unknown"})
    if res['type'] == 'location':
        lid = res['id']; 
        items = get_spools_at_location_detailed(lid)
        if items: add_log_entry(f"🔎 {lid}: {len(items)} item(s)")
        else: add_log_entry(f"🔎 {lid}: Empty")
        return jsonify({"type": "location", "id": lid, "display": f"LOC: {lid}", "contents": items})
    
    if res['type'] == 'spool':
        sid = res['id']; data = get_spool(sid)
        if data:
            info = format_spool_display(data)
            return jsonify({"type": "spool", "id": int(sid), "display": info['text'], "color": info['color']})
    if res['type'] == 'command': return jsonify(res)
    return jsonify({"type": "error"})

@app.route('/api/smart_move', methods=['POST'])
def api_smart_move():
    return jsonify(perform_smart_move(request.json.get('location'), request.json.get('spools')))

@app.route('/api/logs', methods=['GET'])
def api_get_logs_route():
    sm_ok, fb_ok = False, False
    try: sm_ok = requests.get(f"{SPOOLMAN_URL}/api/v1/health", timeout=1).ok
    except: pass
    try: fb_ok = requests.get(f"{FILABRIDGE_API_BASE}/status", timeout=1).ok
    except: pass
    return jsonify({
        "logs": RECENT_LOGS,
        "undo_available": len(UNDO_STACK) > 0,
        "status": {"spoolman": sm_ok, "filabridge": fb_ok}
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
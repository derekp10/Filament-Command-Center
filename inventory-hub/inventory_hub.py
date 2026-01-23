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
VERSION = "v82.0 (Modular)"

def load_config():
    defaults = {
        "server_ip": "127.0.0.1", "spoolman_port": 7912, "filabridge_port": 5000,
        "sync_delay": 0.5, "printer_map": {}, "feeder_map": {}, "dryer_slots": [],
        "safe_source_patterns": ["Dryer"]
    }
    
    final_config = defaults.copy()
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f: 
                loaded = json.load(f)
                final_config.update(loaded)
        except Exception as e:
            logger.error(f"Config Load Error: {e}")
            
    # --- NORMALIZATION FIX ---
    if 'printer_map' in final_config:
        final_config['printer_map'] = {k.upper(): v for k, v in final_config['printer_map'].items()}
        
    if 'feeder_map' in final_config:
        final_config['feeder_map'] = {k.upper(): v for k, v in final_config['feeder_map'].items()}
        
    if 'dryer_slots' in final_config:
        final_config['dryer_slots'] = [x.upper() for x in final_config['dryer_slots']]

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
        logger.info("💾 Locations CSV updated via Web UI")
    except Exception as e: logger.error(f"CSV Write Error: {e}")

def add_log_entry(msg, category="INFO", color_hex=None):
    timestamp = time.strftime("%H:%M:%S")
    # GIANT SWATCHES (24px)
    if color_hex:
        swatch = f'<span style="display:inline-block;width:24px;height:24px;border-radius:50%;background-color:#{color_hex};margin-right:10px;border:2px solid #fff;vertical-align:middle;"></span>'
        msg = swatch + f'<span style="vertical-align:middle;">{msg}</span>'
        
    entry = {"time": timestamp, "msg": msg, "type": category}
    RECENT_LOGS.insert(0, entry)
    if len(RECENT_LOGS) > 50: RECENT_LOGS.pop()

# --- INITIAL LOAD ---
cfg = load_config()
SERVER_IP = cfg.get("server_ip")
SPOOLMAN_URL = f"http://{SERVER_IP}:{cfg.get('spoolman_port')}"
FILABRIDGE_API_BASE = f"http://{SERVER_IP}:{cfg.get('filabridge_port')}/api"

logger.info(f"🛠️ Server {VERSION} Started")

@app.route('/')
def dashboard():
    # Renders the HTML file from the /templates folder
    return render_template('dashboard.html', version=VERSION)

@app.route('/api/locations', methods=['GET'])
def api_get_locations(): return jsonify(load_locations_list())

@app.route('/api/locations', methods=['POST'])
def api_save_location():
    data = request.json
    old_id, new_entry = data.get('old_id'), data.get('new_data')
    current_list = load_locations_list()
    if old_id:
        current_list = [row for row in current_list if row['LocationID'] != old_id]
        add_log_entry(f"Modified: {old_id}")
    else:
        add_log_entry(f"New Location: {new_entry['LocationID']}")
    current_list.append(new_entry)
    current_list.sort(key=lambda x: x['LocationID'])
    save_locations_list(current_list)
    return jsonify({"success": True})

@app.route('/api/locations', methods=['DELETE'])
def api_delete_location():
    target = request.args.get('id')
    save_locations_list([row for row in load_locations_list() if row['LocationID'] != target])
    add_log_entry(f"Removed: {target}", "WARNING")
    return jsonify({"success": True})

@app.route('/api/export_locations', methods=['GET'])
def api_export_locations():
    si = io.StringIO()
    cw = csv.DictWriter(si, fieldnames=['LocationID', 'Name', 'Type', 'Location', 'Device Identifier', 'Device Type', 'Order', 'Row', 'Max Spools', 'Label Printed'])
    cw.writeheader()
    cw.writerows(load_locations_list())
    return Response(si.getvalue(), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=locations_export.csv"})

@app.route('/api/logs', methods=['GET'])
def api_get_logs():
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

@app.route('/api/undo', methods=['POST'])
def undo_last_move():
    if not UNDO_STACK: return jsonify({"success": False, "msg": "History empty."})
    last = UNDO_STACK.pop(); moves = last['moves']; target = last.get('target')
    
    cfg = load_config()
    printer_map = cfg.get("printer_map", {})
    
    if target in printer_map:
        try:
            p = printer_map[target]
            requests.post(f"{FILABRIDGE_API_BASE}/map_toolhead", 
                          json={"printer_name": p['printer_name'], "toolhead_id": p['position'], "spool_id": 0})
        except: pass
        
    for sid, loc in moves.items():
        requests.patch(f"{SPOOLMAN_URL}/api/v1/spool/{sid}", json={"location": loc})
        if loc in printer_map:
            p = printer_map[loc]
            try:
                requests.post(f"{FILABRIDGE_API_BASE}/map_toolhead", 
                              json={"printer_name": p['printer_name'], "toolhead_id": p['position'], "spool_id": int(sid)})
            except: pass
            
    add_log_entry(f"↩️ Undid: {last['summary']}", "WARNING")
    return jsonify({"success": True})

# --- CORE LOGIC ---
def get_spool(sid):
    try: return requests.get(f"{SPOOLMAN_URL}/api/v1/spool/{sid}", timeout=3).json()
    except: return None

def update_spool(sid, data):
    try: requests.patch(f"{SPOOLMAN_URL}/api/v1/spool/{sid}", json=data)
    except: pass

def get_spools_at_location_detailed(loc_name):
    # UPDATED: Returns full object list instead of just IDs
    found = []
    try:
        resp = requests.get(f"{SPOOLMAN_URL}/api/v1/spool", timeout=5)
        if resp.ok:
            for s in resp.json():
                if s.get('location', '').upper() == loc_name.upper():
                    # Format standard display data
                    info = format_spool_display(s)
                    found.append({
                        'id': s['id'],
                        'display': info['text'],
                        'color': info['color']
                    })
    except: pass
    return found

def get_spools_at_location(loc_name):
    return [s['id'] for s in get_spools_at_location_detailed(loc_name)]

def format_spool_display(spool_data):
    sid = spool_data.get('id', '?')
    fil = spool_data.get('filament', {})
    brand = fil.get('vendor', {}).get('name', '?')
    mat = fil.get('material', '?')
    col = fil.get('name', 'Unknown')
    hex_color = fil.get('color_hex', 'ffffff')
    if 'original_color' in fil.get('extra', {}): col = fil.get('extra')['original_color']
    return {"text": f"#{sid} {brand} {mat} ({col})", "color": hex_color}

def find_spool_by_legacy_id(legacy_id):
    legacy_id = str(legacy_id).strip()
    try:
        resp = requests.get(f"{SPOOLMAN_URL}/api/v1/spool", timeout=5)
        if resp.ok:
            data = resp.json()
            for spool in data:
                ext = str(spool.get('external_id', '')).strip().replace('"','')
                fil_ext = str(spool.get('filament',{}).get('external_id','')).strip().replace('"','')
                if ext == legacy_id or fil_ext == legacy_id:
                    return spool['id']
            for spool in data:
                if str(spool['id']) == legacy_id:
                    return spool['id']
    except: pass
    return None

def resolve_scan(text):
    text = text.strip(); decoded = urllib.parse.unquote(text)
    if "CMD:UNDO" in text.upper(): return {'type': 'command', 'cmd': 'undo'}
    if "CMD:CLEAR" in text.upper(): return {'type': 'command', 'cmd': 'clear'}
    if 'google.com' in decoded.lower() or 'range=' in decoded.lower():
        m = re.search(r'range=(?:.*!)?(\d+)', decoded, re.IGNORECASE)
        if m:
            rid = find_spool_by_legacy_id(m.group(1))
            if rid: return {'type': 'spool', 'id': rid}
    if text.isdigit():
        rid = find_spool_by_legacy_id(text)
        if rid: return {'type': 'spool', 'id': rid}
        return {'type': 'spool', 'id': text}
    if len(text) > 2: return {'type': 'location', 'id': text.upper()}
    return None

@app.route('/api/identify_scan', methods=['POST'])
def identify_scan():
    res = resolve_scan(request.json.get('text', ''))
    if not res: return jsonify({"type": "unknown"})
    if res['type'] == 'location':
        lid = res['id']; 
        items = get_spools_at_location_detailed(lid)
        
        if items: add_log_entry(f"🔎 {lid} contains {len(items)} item(s)")
        else: add_log_entry(f"🔎 {lid} is Empty")
        
        return jsonify({"type": "location", "id": lid, "display": f"LOC: {lid}", "contents": items})
    
    if res['type'] == 'spool':
        sid = res['id']; data = get_spool(sid)
        if data:
            info = format_spool_display(data)
            add_log_entry(f"📡 Scanned: {info['text']}", "INFO", info['color'])
            return jsonify({"type": "spool", "id": sid, "display": info['text'], "color": info['color']})
    if res['type'] == 'command':
        add_log_entry(f"⚠️ Command: {res['cmd'].upper()}")
        return jsonify(res)
    return jsonify({"type": "error"})

@app.route('/api/smart_move', methods=['POST'])
def smart_move():
    data = request.json
    target = data.get('location', '').strip().upper()
    raw_spools = data.get('spools', [])
    cfg = load_config(); printer_map = cfg.get("printer_map", {}); dryer_slots = cfg.get("dryer_slots", [])
    
    # SAFETY: Single-Slot Dryer Check
    if target in dryer_slots:
        occupants = get_spools_at_location(target)
        if len(occupants) > 0 and str(occupants[0]) not in [str(x) for x in raw_spools]:
            add_log_entry(f"❌ Aborted: {target} is full!", "ERROR")
            return jsonify({"status": "error", "msg": "Dryer Full"})

    # SAFETY: Single-Slot Printer Check
    if target in printer_map:
        if len(raw_spools) > 1:
            add_log_entry(f"❌ Error: {target} is single-slot!", "ERROR")
            return jsonify({"status": "error", "msg": "Target full"})
        occupants = get_spools_at_location(target)
        if len(occupants) > 0 and str(occupants[0]) not in [str(x) for x in raw_spools]:
            add_log_entry(f"❌ Aborted: {target} is occupied!", "ERROR")
            return jsonify({"status": "error", "msg": "Target occupied"})

    spools = []
    for item in raw_spools:
        if str(item).isdigit(): spools.append(item)
        else:
            found = get_spools_at_location(str(item))
            if found: spools.extend(found)

    if not spools: return jsonify({"status": "error"})
    undo_record = {"target": target, "moves": {}, "summary": f"Moved {len(spools)} -> {target}"}

    for sid in spools:
        spool_data = get_spool(sid)
        if not spool_data: continue
        
        # --- FIX #4: CHECK IF LEAVING A PRINTER ---
        current_loc = spool_data.get('location', '').strip().upper()
        if current_loc in printer_map:
             p = printer_map[current_loc]
             try:
                add_log_entry(f"🔌 Clearing Toolhead: {p['printer_name']} T{p['position']}", "WARNING")
                resp = requests.post(f"{FILABRIDGE_API_BASE}/map_toolhead", 
                              json={"printer_name": p['printer_name'], "toolhead_id": p['position'], "spool_id": 0}, timeout=2)
                if not resp.ok: add_log_entry(f"❌ FilaBridge Error: {resp.status_code}", "ERROR")
             except Exception as e: add_log_entry(f"❌ FilaBridge Exception: {e}", "ERROR")
        # -------------------------------------------

        undo_record['moves'][sid] = current_loc
        current_extra = spool_data.get('extra') or {}
        info = format_spool_display(spool_data)
        
        if target in dryer_slots:
            new_extra = current_extra.copy(); new_extra.pop('physical_source', None)
            update_spool(sid, {"location": target, "extra": new_extra})
            add_log_entry(f"📦 {info['text']} -> Dryer {target}", "INFO", info['color'])
        elif target in printer_map:
            new_extra = current_extra.copy()
            if spool_data.get('location', '') in dryer_slots: new_extra['physical_source'] = spool_data.get('location', '')
            update_spool(sid, {"location": target, "extra": new_extra})
            p = printer_map[target]
            try:
                add_log_entry(f"🔌 Mapping Toolhead: {p['printer_name']} T{p['position']} -> Spool {sid}", "INFO")
                resp = requests.post(f"{FILABRIDGE_API_BASE}/map_toolhead", 
                                     json={"printer_name": p['printer_name'], "toolhead_id": p['position'], "spool_id": int(sid)}, timeout=2)
                if not resp.ok: add_log_entry(f"❌ FilaBridge Error: {resp.status_code}", "ERROR")
            except Exception as e: add_log_entry(f"❌ FilaBridge Exception: {e}", "ERROR")
            
            add_log_entry(f"🖨️ {info['text']} -> {target}", "INFO", info['color'])
        else:
            update_spool(sid, {"location": target})
            add_log_entry(f"🚚 {info['text']} -> {target}", "INFO", info['color'])

    UNDO_STACK.append(undo_record)
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
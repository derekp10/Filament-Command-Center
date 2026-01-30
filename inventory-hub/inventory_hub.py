from flask import Flask, request, jsonify, Response, render_template, make_response
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
VERSION = "v137.0 (Undo P-Fix)"

# Fields that MUST be double-quoted strings (JSON strings)
JSON_STRING_FIELDS = ["spool_type", "container_slot", "physical_source", "original_color", "spool_temp"]

@app.after_request
def add_header(r):
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"
    return r

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

def sanitize_outbound_data(data):
    if 'extra' not in data or not data['extra']: return data
    clean_extra = {}
    for key, value in data['extra'].items():
        if value is None: continue 
        if isinstance(value, bool):
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
    try:
        clean_data = sanitize_outbound_data(data)
        resp = requests.patch(f"{SPOOLMAN_URL}/api/v1/spool/{sid}", json=clean_data)
        if not resp.ok:
            logger.error(f"❌ DB REJECTED: {resp.status_code} | Msg: {resp.text}")
            add_log_entry(f"❌ DB Error {resp.status_code}: {resp.text[:50]}...", "ERROR")
            return False
        return True
    except Exception as e:
        logger.error(f"Spoolman Connection Failed: {e}")
        add_log_entry("❌ DB Connection Fail", "ERROR")
        return False

def format_spool_display(spool_data):
    try:
        sid = spool_data.get('id', '?')
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
        hex_color = fil.get('color_hex', 'ffffff')
        return {"text": display_text, "color": hex_color, "slot": slot}

    except Exception as e:
        logger.error(f"Format Error: {e}")
        return {"text": f"#{spool_data.get('id', '?')} Error", "color": "ff0000", "slot": ""}

def find_spool_by_legacy_id(legacy_id, strict_mode=False):
    legacy_id = str(legacy_id).strip()
    try:
        fil_resp = requests.get(f"{SPOOLMAN_URL}/api/v1/filament", timeout=5)
        target_filament_id = None
        
        if fil_resp.ok:
            for fil in fil_resp.json():
                ext = str(fil.get('external_id', '')).strip().replace('"','')
                if ext == legacy_id:
                    target_filament_id = fil['id']
                    break
        
        if target_filament_id:
            spool_resp = requests.get(f"{SPOOLMAN_URL}/api/v1/spool", timeout=5)
            if spool_resp.ok:
                candidates = []
                for spool in spool_resp.json():
                    if spool.get('filament', {}).get('id') == target_filament_id:
                        if (spool.get('remaining_weight') or 0) > 10:
                            return spool['id']
                        candidates.append(spool['id'])
                if candidates: return candidates[0]
                if strict_mode: return None

        if not strict_mode:
            check_resp = requests.get(f"{SPOOLMAN_URL}/api/v1/spool/{legacy_id}", timeout=2)
            if check_resp.ok: return int(legacy_id)

    except Exception as e: logger.error(f"Legacy Lookup Error: {e}")
    return None

def get_spools_at_location_detailed(loc_name):
    found = []
    try:
        resp = requests.get(f"{SPOOLMAN_URL}/api/v1/spool", timeout=5)
        if resp.ok:
            for s in resp.json():
                if s.get('location', '').upper() == loc_name.upper():
                    info = format_spool_display(s)
                    found.append({'id': s['id'], 'display': info['text'], 'color': info['color'], 'slot': info['slot']})
    except: pass
    return found

def get_spools_at_location(loc_name):
    return [s['id'] for s in get_spools_at_location_detailed(loc_name)]

def resolve_scan(text):
    text = text.strip().strip('"').strip("'")
    decoded = urllib.parse.unquote(text)
    upper_text = text.upper()

    if "CMD:" in upper_text:
        if "CMD:UNDO" in upper_text: return {'type': 'command', 'cmd': 'undo'}
        if "CMD:CLEAR" in upper_text: return {'type': 'command', 'cmd': 'clear'}
        if "CMD:EJECT" in upper_text: return {'type': 'command', 'cmd': 'eject'} 
        if "CMD:CONFIRM" in upper_text: return {'type': 'command', 'cmd': 'confirm'}
        if "CMD:EJECTALL" in upper_text: return {'type': 'command', 'cmd': 'ejectall'} 
        if "CMD:SLOT:" in upper_text:
            try:
                parts = upper_text.split(':')
                val = parts[-1].strip()
                if val.isdigit(): return {'type': 'command', 'cmd': 'slot', 'value': val}
            except: pass
        return {'type': 'error', 'msg': 'Malformed Command'}

    if upper_text.startswith("ID:"):
        clean_id = text[3:].strip()
        if clean_id.isdigit(): return {'type': 'spool', 'id': int(clean_id)}
        return {'type': 'error', 'msg': 'Invalid Spool ID Format'}

    if any(x in text.lower() for x in ['http', 'www.', '.com', 'google', '/', '\\', '{', '}', '[', ']']):
        m = re.search(r'range=(\d+)', decoded, re.IGNORECASE)
        if m:
            rid = find_spool_by_legacy_id(m.group(1), strict_mode=True)
            if rid: return {'type': 'spool', 'id': rid}
        rid = find_spool_by_legacy_id(text, strict_mode=True)
        if rid: return {'type': 'spool', 'id': rid}
        return {'type': 'error', 'msg': 'Unknown/Invalid Link'}

    if text.isdigit():
        rid = find_spool_by_legacy_id(text, strict_mode=False)
        if rid: return {'type': 'spool', 'id': rid}
        return {'type': 'spool', 'id': int(text)}
        
    if len(text) > 2: 
        return {'type': 'location', 'id': text.upper()}
        
    return {'type': 'error', 'msg': 'Unknown Code'}

def perform_smart_move(target, raw_spools, target_slot=None):
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
        pass 

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
        
        new_extra = current_extra.copy()
        
        if target_slot:
            existing_items = get_spools_at_location_detailed(target)
            for existing in existing_items:
                if str(existing.get('slot', '')).strip('"') == str(target_slot) and existing['id'] != int(sid):
                    logger.info(f"🪑 Unseating Spool {existing['id']} from Slot {target_slot} to make room.")
                    update_spool(existing['id'], {'extra': {'container_slot': ''}})
            
            new_extra['container_slot'] = str(target_slot)
        else:
            new_extra.pop('container_slot', None)

        if target in printer_map:
            src_info = loc_info_map.get(current_loc)
            if src_info and src_info.get('Type') == 'Dryer Box':
                new_extra['physical_source'] = current_loc
            
            if update_spool(sid, {"location": target, "extra": new_extra}):
                p = printer_map[target]
                try:
                    requests.post(f"{FILABRIDGE_API_BASE}/map_toolhead", 
                                  json={"printer_name": p['printer_name'], "toolhead_id": p['position'], "spool_id": int(sid)}, timeout=3)
                except: pass
                add_log_entry(f"🖨️ {info['text']} -> {target}", "INFO", info['color'])
            
        elif target in loc_info_map and loc_info_map[target].get('Type') == 'Dryer Box':
            new_extra.pop('physical_source', None)
            if update_spool(sid, {"location": target, "extra": new_extra}):
                slot_txt = f" [Slot {target_slot}]" if target_slot else ""
                add_log_entry(f"📦 {info['text']} -> Dryer {target}{slot_txt}", "INFO", info['color'])
            
        else:
            if update_spool(sid, {"location": target, "extra": new_extra}):
                add_log_entry(f"🚚 {info['text']} -> {target}", "INFO", info['color'])

    UNDO_STACK.append(undo_record)
    return {"status": "success"}

def perform_undo():
    if not UNDO_STACK: return jsonify({"success": False, "msg": "History empty."})
    last = UNDO_STACK.pop(); moves = last['moves']; target = last.get('target')
    cfg = load_config(); printer_map = cfg.get("printer_map", {})
    
    if target in printer_map:
        p = printer_map[target]
        try:
            requests.post(f"{FILABRIDGE_API_BASE}/map_toolhead", 
                          json={"printer_name": p['printer_name'], "toolhead_id": p['position'], "spool_id": 0})
        except: pass
        
    for sid, loc in moves.items():
        requests.patch(f"{SPOOLMAN_URL}/api/v1/spool/{sid}", json={"location": loc})
        if loc in printer_map:
            p = printer_map[loc]
            try: requests.post(f"{FILABRIDGE_API_BASE}/map_toolhead", 
                              json={"printer_name": p['printer_name'], "toolhead_id": p['position'], "spool_id": int(sid)})
            except: pass
            
    add_log_entry(f"↩️ Undid: {last['summary']}", "WARNING")
    return jsonify({"success": True})

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
    except: pass
    
    current = load_locations_list()
    new_list = [row for row in current if row['LocationID'] != target]
    save_locations_list(new_list)
    add_log_entry(f"🗑️ Deleted: {target}", "WARNING")
    return jsonify({"success": True})

@app.route('/api/undo', methods=['POST'])
def api_undo(): return perform_undo()

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
    slot_arg = data.get('slot') 

    if action == 'clear_location':
        contents = get_spools_at_location_detailed(loc_id)
        ejected_count = 0
        for spool in contents:
            slot_val = spool.get('slot', '')
            if not slot_val or slot_val == 'None' or slot_val == '':
                if update_spool(spool['id'], {"location": ""}):
                    ejected_count += 1
        
        add_log_entry(f"🧹 Cleared {ejected_count} unassigned items from {loc_id}", "WARNING")
        return jsonify({"success": True})

    spool_id = None
    if action == 'add':
        if spool_input:
            resolution = resolve_scan(str(spool_input))
            if resolution and resolution['type'] == 'spool':
                spool_id = resolution['id']
            elif resolution and resolution['type'] == 'error':
                 return jsonify({"success": False, "msg": resolution['msg']})
    elif action == 'remove':
        if str(spool_input).isdigit(): spool_id = int(spool_input)
        
    if not spool_id: return jsonify({"success": False, "msg": "Spool not found"})

    if action == 'remove':
        spool_data = get_spool(spool_id)
        spool_extra = spool_data.get('extra', {})
        spool_extra.pop('container_slot', None)
        
        if update_spool(spool_id, {"location": "", "extra": spool_extra}):
            add_log_entry(f"⏏️ Ejected #{spool_id}", "WARNING")
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "msg": "DB Update Failed"})

    elif action == 'add':
        res_data = perform_smart_move(loc_id, [spool_id], target_slot=slot_arg)
        return jsonify(res_data)

    return jsonify({"success": False})

@app.route('/api/identify_scan', methods=['POST'])
def api_identify_scan():
    res = resolve_scan(request.json.get('text', ''))
    if not res: return jsonify({"type": "unknown"})
    if res['type'] == 'location':
        lid = res['id']; 
        items = get_spools_at_location_detailed(lid)
        add_log_entry(f"🔎 {lid}: {len(items)} item(s)")
        return jsonify({"type": "location", "id": lid, "display": f"LOC: {lid}", "contents": items})
    
    if res['type'] == 'spool':
        sid = res['id']; data = get_spool(sid)
        if data:
            info = format_spool_display(data)
            return jsonify({"type": "spool", "id": int(sid), "display": info['text'], "color": info['color']})
    if res['type'] == 'command': return jsonify(res)
    if res['type'] == 'error': return jsonify(res)
    return jsonify(res)

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
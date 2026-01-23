from flask import Flask, request, jsonify, Response
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
VERSION = "v77.0 (Focus Guard)"

def load_config():
    defaults = {
        "server_ip": "127.0.0.1", "spoolman_port": 7912, "filabridge_port": 5000,
        "sync_delay": 0.5, "printer_map": {}, "feeder_map": {}, "dryer_slots": [],
        "safe_source_patterns": ["Dryer"]
    }
    if not os.path.exists(CONFIG_FILE): return defaults
    try:
        with open(CONFIG_FILE, 'r') as f: return {**defaults, **json.load(f)}
    except Exception as e:
        logger.error(f"Config Load Error: {e}")
        return defaults

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

# --- WEB UI HTML ---
# NOTE: Using standard string to avoid f-string conflicts with CSS/JS braces
RAW_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Filament Command Center {{VERSION}}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
    <style>
        body { background-color: #0e0e0e; color: #f0f0f0; font-family: 'Segoe UI', monospace; }
        .navbar { background-color: #1a1a1a; border-bottom: 2px solid #00d4ff; }
        .navbar-brand { color: #00d4ff !important; font-weight: bold; font-size: 1.8rem; }
        .version-tag { color: #888; font-size: 1.2rem; margin-left: 15px; font-weight: bold; }
        
        .status-card { background-color: #1a1a1a !important; border: 1px solid #444 !important; box-shadow: 0 4px 15px rgba(0,0,0,0.6); }
        .status-header { background-color: #222 !important; color: #00d4ff !important; border-bottom: 1px solid #333 !important; }
        
        .card { background-color: #181818; border: 1px solid #333; margin-bottom: 20px; }
        .card-header { background-color: #222; color: #00d4ff; font-weight: bold; border-bottom: 1px solid #333; font-size: 1.3rem; }
        
        .btn-success { background-color: #00d4ff; color: #000; font-weight: bold; border: none; }
        .table { color: #d0d0d0; font-size: 1.1rem; }
        
        .log-box { height: 400px; overflow-y: auto; background: #000; border: 1px solid #444; padding: 15px; font-family: 'Consolas', monospace; font-size: 1.2rem; line-height: 1.8; }
        .log-INFO { color: #00ff00; } .log-WARNING { color: #ffcc00; } .log-ERROR { color: #ff4444; }
        
        .stat-num { font-size: 4rem; font-weight: bold; color: #00d4ff; line-height: 1; }
        
        .modal-content { background-color: #1e1e1e; color: #f0f0f0; border: 1px solid #444; }
        .form-control, .form-select { background-color: #2a2a2a; color: #fff; border: 1px solid #444; font-size: 1.1rem; }
        .form-control:focus { background-color: #333; color: #fff; border-color: #00d4ff; box-shadow: 0 0 0 0.25rem rgba(0, 212, 255, 0.25); }
        label { color: #00d4ff; font-weight: 600; margin-bottom: 5px; font-size: 1rem; }
        
        .alert-protocol { background-color: #553300; color: #ffd700; border: 1px solid #ffd700; font-weight: bold; }
        code { color: #00d4ff; background: #222; padding: 2px 5px; border-radius: 3px; font-size: 1.1rem; }
        
        #scan-buffer { position: fixed; bottom: 10px; right: 10px; background: #333; color: #fff; padding: 10px; opacity: 0.9; font-size: 1.2rem; border: 1px solid #555; border-radius: 4px; }
        
        /* Command Deck Styles */
        .cmd-deck { display: flex; justify-content: space-around; background: #111; padding: 10px; border-top: 1px solid #333; }
        .qr-wrapper { text-align: center; background: #fff; padding: 10px; border-radius: 8px; margin: 5px; }
        .qr-label { color: #000; font-weight: bold; font-size: 1.2rem; margin-top: 5px; display: block; }
        .health-text { color: #ffffff !important; font-size: 1.1rem; }

        /* --- FOCUS GUARD CSS --- */
        #focus-guard {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.85); z-index: 10000;
            display: none; /* Hidden by default */
            justify-content: center; align-items: center;
            border: 20px solid #ff4444; 
            text-align: center; 
            backdrop-filter: blur(5px);
        }
        .guard-icon { font-size: 5rem; margin-bottom: 20px; }
        .guard-msg { font-size: 3rem; color: #ff4444; font-weight: bold; text-shadow: 0 0 10px #000; text-transform: uppercase; }
        .guard-sub { color: white; font-size: 1.5rem; margin-top: 20px; animation: blink 1.5s infinite; }
        @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }

    </style>
</head>
<body>
    <div id="focus-guard" onclick="document.body.focus()">
        <div>
            <div class="guard-icon">🚫</div>
            <div class="guard-msg">Scanner Paused</div>
            <div class="guard-sub">Window lost focus! Click here to resume.</div>
        </div>
    </div>

    <nav class="navbar navbar-expand-lg">
        <div class="container-fluid">
            <div>
                <span class="navbar-brand">Filament Command Center</span>
                <span class="version-tag">{{VERSION}}</span>
            </div>
            <div class="d-flex align-items-center">
                 <button onclick="triggerUndo()" class="btn btn-warning btn-sm me-3" id="undo-btn" disabled>↩️ UNDO LAST ACTION</button>
                 <div class="alert alert-protocol py-1 px-3 mb-0 me-3">⚠️ HTTP ONLY</div>
                 <a href="/api/export_locations" class="btn btn-outline-info btn-sm">💾 Export CSV</a>
            </div>
        </div>
    </nav>

    <div class="container-fluid mt-4">
        <div class="row">
            <div class="col-md-3">
                <div class="card status-card">
                    <div class="card-header status-header">System Health</div>
                    <div class="card-body">
                        <div id="status-display" class="health-text">Checking...</div>
                        <hr style="border-color: #444; margin: 20px 0;">
                        <div class="text-center">
                            <div class="stat-num" id="loc-count">0</div>
                            <div style="color: #fff; font-size: 1.2rem;">Locations</div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="col-md-5">
                <div class="card">
                    <div class="card-header">Live Activity 📡</div>
                    <div class="card-body p-0">
                        <div id="live-logs" class="log-box"></div>
                        <div id="cmd-deck" class="cmd-deck" style="display:none;">
                            <div class="qr-wrapper">
                                <div id="qr-clear"></div>
                                <span class="qr-label">CMD:CLEAR</span>
                            </div>
                            <div class="qr-wrapper">
                                <div id="qr-undo"></div>
                                <span class="qr-label">CMD:UNDO</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="col-md-4">
                <div class="card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <span>Location Manager</span>
                        <button class="btn btn-success btn-sm" onclick="openAddModal()">+ Add New Slot</button>
                    </div>
                    <div class="card-body">
                        <div style="max-height: 500px; overflow-y: auto;">
                            <table class="table table-hover">
                                <thead class="table-dark"><tr><th>ID</th><th>Name</th><th>Type</th><th class="text-end">Actions</th></tr></thead>
                                <tbody id="location-table"></tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <div id="scan-buffer">Ready</div>

    <div class="modal fade" id="locModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header"><h5 class="modal-title" id="modalTitle">Edit Location</h5><button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button></div>
                <div class="modal-body">
                    <input type="hidden" id="edit-original-id">
                    <div class="mb-3"><label>Location ID</label><input type="text" class="form-control" id="edit-id"></div>
                    <div class="mb-3"><label>Friendly Name</label><input type="text" class="form-control" id="edit-name"></div>
                    <div class="mb-3"><label>Type</label>
                        <select class="form-select" id="edit-type">
                            <option value="Dryer Box">Dryer Box</option><option value="Cart">Cart</option><option value="Shelf">Shelf</option>
                            <option value="Printer">Printer/Toolhead</option><option value="MMU Slot">MMU Slot</option>
                        </select>
                    </div>
                </div>
                <div class="modal-footer"><button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button><button type="button" class="btn btn-primary" onclick="saveLocation()">Save</button></div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        window.onload = function() {
            new QRCode(document.getElementById("qr-undo"), {text: "CMD:UNDO", width: 128, height: 128});
            new QRCode(document.getElementById("qr-clear"), {text: "CMD:CLEAR", width: 128, height: 128});
        };

        // --- FOCUS GUARD LOGIC ---
        window.onblur = function() {
            document.getElementById('focus-guard').style.display = 'flex';
        };
        
        window.onfocus = function() {
            document.getElementById('focus-guard').style.display = 'none';
        };

        let scanBuffer = "";
        let bufferTimeout;
        let heldSpools = []; 

        document.addEventListener('keydown', (e) => {
            // Ignore input if focus guard is active (double safety)
            if (document.getElementById('focus-guard').style.display === 'flex') return;

            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
            if (e.ctrlKey || e.altKey || e.metaKey) return;
            
            if (e.key === 'Enter') { processScan(scanBuffer); scanBuffer = ""; } 
            else if (e.key.length === 1) { 
                scanBuffer += e.key; 
                document.getElementById('scan-buffer').innerText = "Scanning: " + scanBuffer; 
                clearTimeout(bufferTimeout); 
                bufferTimeout = setTimeout(() => { scanBuffer = ""; document.getElementById('scan-buffer').innerText = "Ready"; }, 2000); 
            }
        });

        function updateCmdDeck() {
            const deck = document.getElementById('cmd-deck');
            if (heldSpools.length > 0) {
                deck.style.display = "flex";
            } else {
                deck.style.display = "none";
            }
        }

        function processScan(text) {
            fetch('/api/identify_scan', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({text: text}) }).then(r => r.json()).then(res => {
                if (res.type === 'spool') {
                    if (!heldSpools.includes(res.id)) { 
                        heldSpools.push(res.id); 
                        updateCmdDeck();
                    }
                } else if (res.type === 'location') {
                    if (heldSpools.length > 0) { executeMove(res.id); } 
                } else if (res.type === 'command') {
                    if (res.cmd === 'undo') triggerUndo();
                    if (res.cmd === 'clear') { heldSpools = []; updateCmdDeck(); }
                }
            });
        }

        function executeMove(targetLoc) {
            fetch('/api/smart_move', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({location: targetLoc, spools: heldSpools}) }).then(r => r.json()).then(data => { 
                heldSpools = []; 
                updateCmdDeck();
                fetchLogs(); 
            });
        }
        
        function triggerUndo() { fetch('/api/undo', { method: 'POST' }).then(() => fetchLogs()); }

        let allLocations = []; const modal = new bootstrap.Modal(document.getElementById('locModal'));
        function fetchLogs() {
            fetch('/api/logs').then(r => r.json()).then(data => {
                document.getElementById('live-logs').innerHTML = data.logs.map(l => `<div class="log-${l.type}">[${l.time}] ${l.msg}</div>`).join('');
                document.getElementById('status-display').innerHTML = `
                    <div class="status-row" style="display:flex; justify-content:space-between; margin-bottom:10px;">
                        <span>Spoolman</span><span class="badge ${data.status.spoolman ? 'bg-success' : 'bg-danger'}">${data.status.spoolman?'ON':'OFF'}</span>
                    </div>
                    <div class="status-row" style="display:flex; justify-content:space-between;">
                        <span>FilaBridge</span><span class="badge ${data.status.filabridge ? 'bg-success' : 'bg-danger'}">${data.status.filabridge?'ON':'OFF'}</span>
                    </div>`;
                const undoBtn = document.getElementById('undo-btn');
                undoBtn.disabled = !data.undo_available;
                updateCmdDeck();
            });
        }
        function fetchLocations() {
            fetch('/api/locations').then(r => r.json()).then(data => {
                allLocations = data; document.getElementById('loc-count').innerText = data.length;
                document.getElementById('location-table').innerHTML = data.map(l => `<tr><td><code>${l.LocationID}</code></td><td>${l.Name}</td><td><span class="badge bg-secondary">${l.Type}</span></td><td class="text-end"><button class="btn btn-sm btn-outline-warning me-1" onclick="openEdit('${l.LocationID}')">Edit</button><button class="btn btn-sm btn-outline-danger" onclick="deleteLoc('${l.LocationID}')">Del</button></td></tr>`).join('');
            });
        }
        function openAddModal() { document.getElementById('modalTitle').innerText = "Add New Location"; document.getElementById('edit-original-id').value = ""; modal.show(); }
        function openEdit(id) { const l = allLocations.find(x => x.LocationID === id); if(!l)return; document.getElementById('modalTitle').innerText="Edit Location"; document.getElementById('edit-id').value=l.LocationID; document.getElementById('edit-name').value=l.Name; document.getElementById('edit-type').value=l.Type; document.getElementById('edit-original-id').value=l.LocationID; modal.show(); }
        function saveLocation() { 
            const payload = { old_id: document.getElementById('edit-original-id').value, new_data: { LocationID: document.getElementById('edit-id').value, Name: document.getElementById('edit-name').value, Type: document.getElementById('edit-type').value, Location: "", "Device Identifier": "", "Device Type": "", Order: "", Row: "", "Max Spools": "1", "Label Printed": "No" } };
            fetch('/api/locations', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) }).then(() => { modal.hide(); fetchLocations(); });
        }
        function deleteLoc(id) { if(confirm("Delete " + id + "?")) fetch('/api/locations?id=' + id, { method: 'DELETE' }).then(() => fetchLocations()); }
        fetchLocations(); setInterval(fetchLogs, 2500);
    </script>
</body>
</html>
"""

# Inject Version Safe
DASHBOARD_HTML = RAW_HTML.replace("{{VERSION}}", VERSION)

@app.route('/')
def dashboard(): return DASHBOARD_HTML

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

def get_spools_at_location(loc_name):
    found = []
    try:
        resp = requests.get(f"{SPOOLMAN_URL}/api/v1/spool", timeout=5)
        if resp.ok:
            for s in resp.json():
                if s.get('location', '').upper() == loc_name.upper():
                    found.append(s['id'])
    except: pass
    return found

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
        lid = res['id']; items = get_spools_at_location(lid)
        if items: add_log_entry(f"🔎 {lid} contains {len(items)} item(s)")
        else: add_log_entry(f"🔎 {lid} is Empty")
        return jsonify({"type": "location", "id": lid, "display": f"LOC: {lid}"})
    if res['type'] == 'spool':
        sid = res['id']; data = get_spool(sid)
        if data:
            info = format_spool_display(data)
            add_log_entry(f"📡 Scanned: {info['text']}", "INFO", info['color'])
            return jsonify({"type": "spool", "id": sid, "display": info['text']})
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
        undo_record['moves'][sid] = spool_data.get('location', '')
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
            try: requests.post(f"{FILABRIDGE_API_BASE}/map_toolhead", json={"printer_name": p['printer_name'], "toolhead_id": p['position'], "spool_id": int(sid)})
            except: pass
            add_log_entry(f"🖨️ {info['text']} -> {target}", "INFO", info['color'])
        else:
            update_spool(sid, {"location": target})
            add_log_entry(f"🚚 {info['text']} -> {target}", "INFO", info['color'])

    UNDO_STACK.append(undo_record)
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
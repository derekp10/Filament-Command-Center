import csv
import requests
import json
import math

# --- CONFIGURATION ---
SPOOLMAN_IP = "http://192.168.1.29:7912"
CSV_FILE = "3D Print Supplies - Filament.csv"

# --- DENSITY MAP ---
DENSITY_MAP = {
    "PLA": 1.24, "PLA+": 1.24, "SILK": 1.24, "PETG": 1.27, "ABS": 1.04,
    "ASA": 1.07, "TPU": 1.21, "PC": 1.20, "NYLON": 1.14, "PA": 1.14,
    "CF-PLA": 1.29, "PVB": 1.08, "HIPS": 1.04, "PVA": 1.19
}

print("⏳ Fetching existing Spoolman data...")
try:
    ALL_VENDORS = {v['name'].lower(): v['id'] for v in requests.get(f"{SPOOLMAN_IP}/api/v1/vendor").json()}
    ALL_FILAMENTS = {} 
    raw_filaments = requests.get(f"{SPOOLMAN_IP}/api/v1/filament").json()
    
    # Match using native external_id
    for f in raw_filaments:
        if f.get('external_id'):
            ALL_FILAMENTS[str(f['external_id'])] = f['id']
            
    print(f"✅ Loaded {len(ALL_FILAMENTS)} existing matched filaments.")
except Exception as e:
    print(f"❌ Error connecting to Spoolman: {e}")
    exit()

# --- HELPER FUNCTIONS ---
def safe_str(val):
    if val is None: return ""
    return str(val).strip()

def safe_json(val):
    """
    CRITICAL FIX: Spoolman expects a JSON-encoded string for text fields.
    """
    s = safe_str(val)
    return json.dumps(s) 

def safe_float(val, default=0.0):
    try:
        if not val: return default
        clean = str(val).replace("$", "").replace(",", "").strip()
        return float(clean)
    except:
        return default

def clean_hex(hex_str):
    if not hex_str: return None
    clean = hex_str.strip().replace("#", "")
    return clean if len(clean) == 6 else None

def get_density(material_name):
    if not material_name: return 1.24
    mat_key = material_name.strip().upper()
    for key, val in DENSITY_MAP.items():
        if key in mat_key: return val
    return 1.24

def ensure_vendor(name):
    if name.lower() in ALL_VENDORS: return ALL_VENDORS[name.lower()]
    print(f"  🆕 Creating Vendor: {name}")
    resp = requests.post(f"{SPOOLMAN_IP}/api/v1/vendor", json={"name": name})
    if resp.status_code < 400:
        new_id = resp.json()['id']
        ALL_VENDORS[name.lower()] = new_id
        return new_id
    return None

def format_ui_comment(row):
    lines = []
    if row.get('Purchase Link'): lines.append(f"🛒 Purchase: {row['Purchase Link']}")
    if row.get('Product Page Link'): lines.append(f"ℹ️ Product Info: {row['Product Page Link']}")
    lines.append("\n--- SPECS ---")
    if row.get('Drying Temp (C)') or row.get('Drying Length (Hrs)'):
        lines.append(f"🔥 Dry: {safe_str(row.get('Drying Temp (C)'))}°C for {safe_str(row.get('Drying Length (Hrs)'))}hr")
    if row.get('Spool Type'): lines.append(f"📦 Spool: {row['Spool Type']}")
    if row.get('Special Notes'): lines.append(f"\n📝 Note: {row['Special Notes']}")
    return "\n".join(lines)

def find_header(headers, target):
    for h in headers:
        if h and target.lower() == h.strip().replace('\ufeff', '').lower():
            return h
    return target

# --- SYNC LOGIC ---
def sync_filament(row, header_map):
    brand_key = header_map.get('Brand', 'Brand')
    color_key = header_map.get('Color', 'Color')
    
    vid = ensure_vendor(row[brand_key])
    if not vid: return None

    # Identity
    color = row.get(color_key, 'Unknown')
    attr = row.get('Filament Attributes', '')
    final_name = f"{color} {attr}".strip()
    
    material = row.get('Filament Type', 'PLA')
    shore = row.get('TPU Shore', '')
    if shore: material = f"{material} {shore}"

    hexes = [h for h in [clean_hex(row.get(f'Hex {i}')) for i in range(1, 4)] if h]
    
    # Extra Data (JSON Encoded)
    extra_data = {
        "sheet_label":      safe_json(row.get('Label Printed')),
        "sheet_qr":         safe_json(row.get('Spool QR Generated')),
        "sheet_prod_url":   safe_json(row.get('Product Page Link')),
        "sheet_purch_url":  safe_json(row.get('Purchase Link')),
        "sheet_row_link":   safe_json(row.get('Row Link')),
        "sheet_material":   safe_json(row.get('Spool Type')),
        "sheet_shore":      safe_json(row.get('TPU Shore')),
        "sheet_dry_temp":   safe_json(row.get('Drying Temp (C)')),
        "sheet_dry_time":   safe_json(row.get('Drying Length (Hrs)'))
    }

    try:
        nozzle = int((safe_float(row.get('Print Temp 1 Min (C)'), 200) + safe_float(row.get('Print Temp 1 Max (C)'), 200)) / 2)
        bed = int((safe_float(row.get('Bed Temp 1 Min (C)'), 60) + safe_float(row.get('Bed Temp 1 Max (C)'), 60)) / 2)
    except: nozzle, bed = 200, 60
    
    roid_key = header_map.get('ROID', 'ROID')
    
    payload = {
        "name": final_name,
        "vendor_id": vid,
        "material": material,
        "density": get_density(material),
        "weight": safe_float(row.get('Weight (g)'), 1000),
        "spool_weight": safe_float(row.get('Empty Spool Weight (g)'), 0),
        "diameter": safe_float(row.get('Diameter'), 1.75), # FIXED: Included
        "price": safe_float(row.get('Purchase Price')),
        "settings_extruder_temp": nozzle,
        "settings_bed_temp": bed,
        "comment": format_ui_comment(row),
        "extra": extra_data,
        "external_id": safe_str(row.get(roid_key))
    }

    if len(hexes) > 1:
        payload["multi_color_hexes"] = ",".join(hexes)
        payload["multi_color_direction"] = "longitudinal"
        payload["color_hex"] = None
    elif len(hexes) == 1:
        payload["color_hex"] = hexes[0]
        payload["multi_color_hexes"] = None
    else:
        payload["color_hex"] = None
        payload["multi_color_hexes"] = None

    # SYNC
    roid = safe_str(row.get(roid_key))
    if roid in ALL_FILAMENTS:
        fid = ALL_FILAMENTS[roid]
        print(f"  🔄 Updating: {final_name}")
        requests.patch(f"{SPOOLMAN_IP}/api/v1/filament/{fid}", json=payload)
        return fid
    else:
        print(f"  ✨ Creating: {final_name}")
        resp = requests.post(f"{SPOOLMAN_IP}/api/v1/filament", json=payload)
        if resp.status_code >= 400:
            print(f"    ❌ Error: {resp.text}")
            return None
        new_id = resp.json()['id']
        ALL_FILAMENTS[roid] = new_id
        return new_id

# --- MAIN LOOP ---
print("--- Starting Sync V17 (Final) ---")
with open(CSV_FILE, newline='', encoding='utf-8-sig') as csvfile:
    reader = csv.DictReader(csvfile)
    
    field_map = {}
    for target in ['ROID', 'Brand', 'Color']:
        field_map[target] = find_header(reader.fieldnames, target)
    
    for row in reader:
        if not row.get(field_map['Brand']) or not row.get(field_map['Color']): continue
        
        fid = sync_filament(row, field_map)
        
        roid_key = field_map['ROID']
        if fid and safe_str(row.get(roid_key)) not in ALL_FILAMENTS:
             loc = row.get('Location', '')
             try: new_count = int(safe_float(row.get('Unopened Spools'), 0) + safe_float(row.get('Refills'), 0))
             except: new_count = 0
             for _ in range(new_count): 
                 requests.post(f"{SPOOLMAN_IP}/api/v1/spool", json={"filament_id": fid, "remaining_weight": 1000, "location": loc})

             try: open_count = math.ceil(safe_float(row.get('Opened Spools'), 0))
             except: open_count = 0
             for _ in range(open_count): 
                 requests.post(f"{SPOOLMAN_IP}/api/v1/spool", json={"filament_id": fid, "remaining_weight": 500, "location": loc})

print("--- Sync Complete ---")
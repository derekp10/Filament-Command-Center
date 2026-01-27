import csv
import requests
import json
import math
import os
import sys

# --- CONFIGURATION ---
SPOOLMAN_IP = "http://192.168.1.29:7912"
DATA_FOLDER_NAME = "3D Print Data"
FILAMENT_FILENAME = "3D Print Supplies - Filament.csv"

# --- PATH FINDER HELPER ---
def find_file(filename):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    for _ in range(4):
        data_path = os.path.join(current_dir, DATA_FOLDER_NAME)
        file_path = os.path.join(data_path, filename)
        if os.path.exists(data_path) and os.path.exists(file_path):
            print(f"Found CSV at: {file_path}")
            return file_path
        parent_dir = os.path.dirname(current_dir)
        if parent_dir == current_dir: break
        current_dir = parent_dir
    print(f"❌ Error: Could not find '{filename}' inside '{DATA_FOLDER_NAME}'.")
    sys.exit(1)

CSV_FILE = find_file(FILAMENT_FILENAME)

# --- MAPPINGS & LOGIC ---
MATERIAL_PURIFY_MAP = {
    "CF-PETG": ("PETG", "Carbon Fiber"),
    "CF-PC": ("PC", "Carbon Fiber"),
    "PA6-GF": ("PA6", "Glass Fiber"),
    "PA612-CF15": ("PA612", "Carbon Fiber"),
    "PLA PRO": ("PLA", "Pro"),
    "PLA+": ("PLA", "Plus"),
    "PLA Pro": ("PLA", "Pro"),
}

ATTR_NORMALIZE_MAP = {
    "Carbon-Fiber": "Carbon Fiber",
    "High-Speed": "High Speed",
    "Matte Pro": "Matte"
}

AMBIGUOUS_MAP = {
    "Goldfish": "Orange", "Oak": "Brown", "Wood": "Brown", "Pine": "Brown", "Bamboo": "Brown",
    "Chocolate": "Brown", "Coffee": "Brown", "Marble": "White", "Stone": "Grey", "Rock": "Grey",
    "Ceramic": "White", "Bone": "Beige", "Skin": "Beige", "Flesh": "Beige", "Onyx": "Black",
    "Charcoal": "Grey", "Slate": "Grey", "Sakura": "Pink", "Midnight": "Blue", "Olive": "Green"
}

BASE_COLORS = [
    "Black", "White", "Red", "Blue", "Green", "Yellow", "Orange", "Purple", "Pink", 
    "Brown", "Grey", "Gray", "Silver", "Gold", "Beige", "Cyan", "Magenta", "Teal", 
    "Maroon", "Navy", "Lime", "Ivory", "Bronze", "Copper", "Turquoise", "Violet", 
    "Indigo", "Lavender", "Coral", "Salmon", "Crimson", "Amber"
]

COLORLESS_TERMS = ["Clear", "Transparent", "Translucent"]

COLOR_PALETTE = {
    "Black": ((0, 0, 0), "Black"), "White": ((255, 255, 255), "White"), "Grey": ((128, 128, 128), "Grey"),
    "Red": ((255, 0, 0), "Red"), "Blue": ((0, 0, 255), "Blue"), "Green": ((0, 128, 0), "Green"),
    "Yellow": ((255, 255, 0), "Yellow"), "Orange": ((255, 165, 0), "Orange"), "Purple": ((128, 0, 128), "Purple"),
    "Pink": ((255, 192, 203), "Pink"), "Brown": ((165, 42, 42), "Brown"), "Silver": ((192, 192, 192), "Silver"),
    "Gold": ((255, 215, 0), "Gold"), "Beige": ((245, 245, 220), "Beige"), "Cyan": ((0, 255, 255), "Cyan"),
    "Teal": ((0, 128, 128), "Teal"), "Olive": ((128, 128, 0), "Olive"), "Maroon": ((128, 0, 0), "Maroon"),
    "Clear": ((255, 255, 255), "Clear")
}

VISUAL_ATTRS = [
    "Transparent", "Translucent", "Matte", "Silk", "Marble", "Galaxy", "Glitter", 
    "Sparkle", "Neon", "Glow", "Glow in the Dark", "Carbon Fiber", "Glass Fiber", 
    "Wood Filled", "High Speed", "Gradient", "Rainbow", "Dual Color", "Tri Color"
]

CSV_COLUMNS = {
    "brand": "Brand", "color_name": "Color", "material": "Filament Type",
    "location": "Location", "weight_total": "Weight (g)", "diameter": "Diameter",
    "attributes": "Filament Attributes", "tpu_shore": "TPU Shore",
    "tare_weight": "Empty Spool Weight", "roid": "ROID",
    "hex_1": "Hex 1", "hex_2": "Hex 2", "hex_3": "Hex 3",
    "label_printed": "Label Printed", "sample_printed": "Sample Printed", 
    "refill_count": "Refills", "unopened_count": "Unopened Spools", "opened_count": "Opened Spools",     
    "spool_type": "Spool Type", "spool_res": "Spool Temp Resistance (C)",
    "profile": "Filament Profile", "purchase_date": "Purchase Date", "notes": "Notes", 
    "price_base": "Purchase Price", "price_total": "Price Total",
    "product_url": "Product Page Link", "purchase_url": "Purchase Link",
    "sheet_row_link": "Row Link",
    "t1_min": "Print Temp 1 Min (C)", "t1_max": "Print Temp 1 Max (C)",
    "b1_min": "Bed Temp 1 Min (C)", "drying_temp": "Drying Temp (C)",
    "drying_time": "Drying Length (Hrs)", "fan": "Fan", "retraction": "Retraction Speed (mm/s)", 
    "raft": "Raft Separation Distance (mm)"
}

DENSITY_MAP = { "PLA": 1.24, "PETG": 1.27, "ABS": 1.04, "ASA": 1.07, "TPU": 1.21, "PC": 1.20, "NYLON": 1.14, "PVB": 1.08, "HIPS": 1.07, "PVA": 1.19, "PA6": 1.14, "PA612": 1.06 }

# --- HELPERS ---
def hex_to_rgb(hex_str):
    if not hex_str: return None
    hex_str = hex_str.lstrip('#')
    if len(hex_str) != 6: return None
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))

def get_closest_parent_color(hex_str):
    target_rgb = hex_to_rgb(hex_str)
    if not target_rgb: return None
    min_dist = float('inf')
    best_parent = None
    r1, g1, b1 = target_rgb
    for _, (target_rgb_val, parent_name) in COLOR_PALETTE.items():
        r2, g2, b2 = target_rgb_val
        dist = math.sqrt((r2 - r1)**2 + (g2 - g1)**2 + (b2 - b1)**2)
        if dist < min_dist:
            min_dist = dist
            best_parent = parent_name
    return best_parent

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

def to_bool(value):
    if not value: return False
    return str(value).strip().lower() in ['yes', 'true', '1', 'y', 'checked']

def clean_price(price_str):
    if not price_str: return 0.0
    return float(str(price_str).replace("$", "").replace(",", "").strip() or 0)

def clean_int(val):
    try: return int(val)
    except: return 0

def get_or_create_vendor(name):
    response = requests.get(f"{SPOOLMAN_IP}/api/v1/vendor")
    for v in response.json():
        if v['name'].lower() == name.lower(): return v['id']
    resp = requests.post(f"{SPOOLMAN_IP}/api/v1/vendor", json={"name": name})
    return resp.json()['id'] if resp.status_code < 400 else None

CREATED_CACHE = set()

def get_or_create_filament(d, vendor_id):
    raw_type = d['material'].strip()
    raw_attrs_list = d.get('attributes', "").replace(";", ",").split(",")
    final_attrs = set()
    
    for x in raw_attrs_list:
        clean = x.strip()
        if not clean or clean.lower() in ["basic", "standard"]: continue
        if clean in ATTR_NORMALIZE_MAP:
            final_attrs.add(ATTR_NORMALIZE_MAP[clean])
        else:
            final_attrs.add(clean)
    
    if raw_type in MATERIAL_PURIFY_MAP:
        final_material, added_attr = MATERIAL_PURIFY_MAP[raw_type]
        final_attrs.add(added_attr)
    elif "High Speed" in raw_type:
        final_material = raw_type.replace("High Speed", "").strip()
        final_attrs.add("High Speed")
        if not final_material: final_material = raw_type
    else:
        final_material = raw_type

    raw_name = d['color_name'].strip()
    detected_base = None
    
    for key, val in AMBIGUOUS_MAP.items():
        if key.lower() in raw_name.lower():
            detected_base = val
            break

    if not detected_base:
        matches = []
        for color in BASE_COLORS:
            idx = raw_name.lower().find(color.lower())
            if idx != -1:
                matches.append((idx, color))
        if matches:
            matches.sort(key=lambda x: x[0]) 
            detected_base = matches[0][1]

    if not detected_base:
        for term in COLORLESS_TERMS:
            if term.lower() in raw_name.lower():
                detected_base = "Clear"
                break

    if not detected_base:
        hex1 = clean_hex(d.get('hex_1'))
        if hex1:
            detected_base = get_closest_parent_color(hex1)

    suffix_parts = []
    if detected_base and detected_base.lower() != raw_name.lower():
        final_name_prefix = detected_base
        suffix_parts.append(raw_name) 
    else:
        final_name_prefix = raw_name

    for attr in VISUAL_ATTRS:
        if attr in final_attrs:
            is_in_prefix = attr.lower() in final_name_prefix.lower()
            is_in_suffix = False
            if suffix_parts:
                is_in_suffix = attr.lower() in suffix_parts[0].lower()
            if not is_in_prefix and not is_in_suffix:
                suffix_parts.append(attr)

    final_name = f"{final_name_prefix} ({', '.join(suffix_parts)})" if suffix_parts else final_name_prefix

    cache_key = (vendor_id, final_name, final_material)
    if cache_key in CREATED_CACHE: pass 

    response = requests.get(f"{SPOOLMAN_IP}/api/v1/filament")
    for f in response.json():
        if (f['vendor']['id'] == vendor_id and f['name'] == final_name and f['material'] == final_material):
            CREATED_CACHE.add(cache_key)
            return f['id'], False

    hexes = [h for h in [clean_hex(d.get('hex_1')), clean_hex(d.get('hex_2')), clean_hex(d.get('hex_3'))] if h]
    multi_color_direction = "coaxial" if len(hexes) > 1 else None
    color_hex = None if len(hexes) > 1 else (hexes[0] if hexes else None)
    multi_color_hexes = ",".join(hexes) if len(hexes) > 1 else None

    comments = []
    if d.get('notes'): comments.append(d['notes'])
    tech_specs = []
    if d.get('drying_temp') or d.get('drying_time'): tech_specs.append(f"[Drying: {d.get('drying_temp', '?')}C / {d.get('drying_time', '?')}h]")
    if d.get('fan'): tech_specs.append(f"[Fan: {d.get('fan')}]")
    if d.get('retraction'): tech_specs.append(f"[Retract: {d.get('retraction')}mm/s]")
    if d.get('raft'): tech_specs.append(f"[Raft: {d.get('raft')}mm]")
    if tech_specs: comments.append(" ".join(tech_specs))
    final_comment = " \n".join(comments)

    extra_data = {}
    
    # FIX: Restored json.dumps because Spoolman API requires strings for extra fields!
    if final_attrs: extra_data["filament_attributes"] = json.dumps(sorted(list(final_attrs)))
    if d.get('tpu_shore'): extra_data["shore_hardness"] = json.dumps(d.get('tpu_shore'))
    if d.get('profile'): extra_data["slicer_profile"] = json.dumps(d.get('profile'))
    if d.get('price_total'): extra_data["price_total"] = d.get('price_total')
    if d.get('product_url'): extra_data["product_url"] = d.get('product_url')
    if d.get('purchase_url'): extra_data["purchase_url"] = d.get('purchase_url')
    if d.get('sheet_row_link'): extra_data["sheet_link"] = d.get('sheet_row_link')
    
    # FIX: Wrap booleans in json.dumps -> "true"/"false"
    extra_data["label_printed"] = json.dumps(to_bool(d.get('label_printed')))
    extra_data["sample_printed"] = json.dumps(to_bool(d.get('sample_printed')))
    extra_data["spoolman_reprint"] = json.dumps(True)
    
    extra_data["original_color"] = d.get('color_name')
    
    if d.get('drying_temp'): extra_data["drying_temp"] = d.get('drying_temp')
    if d.get('drying_time'): extra_data["drying_time"] = d.get('drying_time')
    if d.get('fan'): extra_data["flush_multiplier"] = d.get('fan')

    base_nozzle = int(d.get('t1_min') or 200)
    base_bed = int(d.get('b1_min') or 60)

    payload = {
        "name": final_name,
        "vendor_id": vendor_id,
        "material": final_material,
        "density": get_density(final_material),
        "weight": float(d.get('weight_total', 1000) or 1000),
        "spool_weight": float(d.get('tare_weight', 0) or 0),
        "diameter": float(d.get('diameter', 1.75) or 1.75),
        "price": clean_price(d.get('price_base')),
        "settings_extruder_temp": base_nozzle,
        "settings_bed_temp": base_bed,
        "comment": final_comment,
        "external_id": str(d.get('roid', "")),
        "color_hex": color_hex,
        "multi_color_hexes": multi_color_hexes,
        "multi_color_direction": multi_color_direction,
        "extra": extra_data
    }
    
    print(f"Creating: {final_name} ({final_material})")
    resp = requests.post(f"{SPOOLMAN_IP}/api/v1/filament", json=payload)
    if resp.status_code >= 400: 
        print(f"Error creating filament: {resp.text}")
        return None, False
    
    CREATED_CACHE.add(cache_key)
    return resp.json()['id'], True

def create_spool(filament_id, remaining, location, purchased, is_refill, spool_type, spool_temp):
    extra_payload = {
        "label_printed": json.dumps(False), # Fix
        "is_refill": json.dumps(is_refill)  # Fix
    }
    if spool_type: extra_payload["spool_type"] = json.dumps(spool_type) # Choice field needs stringified
    if spool_temp: extra_payload["spool_temp"] = spool_temp

    payload = {
        "filament_id": filament_id,
        "remaining_weight": remaining,
        "location": location,
        "purchased": purchased if purchased else None,
        "extra": extra_payload
    }
    resp = requests.post(f"{SPOOLMAN_IP}/api/v1/spool", json=payload)
    
    if resp.status_code >= 400:
        print(f"❌ Spool Create Failed: {resp.text}")

# --- MAIN ---
print("Starting Migration (Inventory)...")
with open(CSV_FILE, newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        d = {}
        for key, header in CSV_COLUMNS.items():
            val = row.get(header)
            d[key] = val.strip() if val else ""

        if not d['brand'] or not d['color_name']: continue
        
        vid = get_or_create_vendor(d['brand'])
        if not vid: continue
        
        fid, is_new = get_or_create_filament(d, vid)
        if not fid: continue

        # Spool Data
        stype = d.get('spool_type')
        stemp = d.get('spool_res')

        # 1. Standard Unopened
        count_unopened = clean_int(d.get('unopened_count'))
        for _ in range(count_unopened):
            create_spool(fid, 1000, d['location'], d['purchase_date'], False, stype, stemp)

        # 2. Refills
        count_refills = clean_int(d.get('refill_count'))
        for _ in range(count_refills):
            create_spool(fid, 1000, d['location'], d['purchase_date'], True, stype, stemp)

        # 3. Opened (969g)
        count_open = clean_int(d.get('opened_count'))
        for _ in range(count_open):
            create_spool(fid, 969, d['location'], d['purchase_date'], False, stype, stemp)

print("Migration Complete!")
import requests
import csv
import sys
import os
import json

# --- CONFIGURATION ---
SPOOLMAN_IP = "192.168.1.29"
PORT = "7912"
BASE_URL = f"http://{SPOOLMAN_IP}:{PORT}"
HUB_BASE = f"http://{SPOOLMAN_IP}:8000"

DATA_FOLDER_NAME = "3D Print Data"

# --- PATH FINDER LOGIC ---
def find_data_dir():
    """Climbs up the directory tree until it finds the Data Folder."""
    current_path = os.path.abspath(os.path.dirname(__file__))
    
    # Safety limit: Don't climb more than 5 levels (avoids infinite loops at root)
    for _ in range(5):
        check_path = os.path.join(current_path, DATA_FOLDER_NAME)
        if os.path.isdir(check_path):
            print(f"📂 Found Data Directory: {check_path}")
            return check_path
        
        # Move up one level
        parent = os.path.dirname(current_path)
        if parent == current_path: # Hit filesystem root
            break
        current_path = parent

    print(f"❌ Error: Could not find '{DATA_FOLDER_NAME}' in any parent directory.")
    sys.exit(1)

OUTPUT_DIR = find_data_dir()

def get_output_path(filename):
    return os.path.join(OUTPUT_DIR, filename)

# --- SPOOLMAN HELPERS ---

def fetch_from_api(endpoint):
    url = f"{BASE_URL}/api/v1/{endpoint}"
    print(f"Connecting to {url}...")
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        sys.exit(1)

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

def get_best_hex(item_data):
    extra = item_data.get('extra', {})
    multi_hex = item_data.get('multi_color_hexes') or extra.get('multi_color_hexes')
    if multi_hex:
        first_hex = multi_hex.split(',')[0].strip()
        if first_hex: return first_hex
    return item_data.get('color_hex', '')

def get_color_name(item_data):
    extra = item_data.get('extra', {})
    if 'original_color' in extra:
        val = clean_string(extra['original_color'])
        if val: return val
    return item_data.get('name', 'Unknown')

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

def should_process(extra, key_checked):
    is_done = str(clean_string(extra.get(key_checked, ''))).lower() in ['true', 'yes', '1']
    force_reprint = str(clean_string(extra.get('spoolman_reprint', ''))).lower() in ['true', 'yes', '1']
    return True if force_reprint else not is_done

def process_filaments():
    print("\n--- Processing Filaments (Samples) ---")
    data = fetch_from_api("filament")
    headers = ['ID', 'Brand', 'Color', 'Type', 'Hex', 'Red', 'Green', 'Blue', 'QR_Code']
    rows = []
    
    for item in data:
        extra = item.get('extra', {})
        if not should_process(extra, 'sample_printed'): continue

        fid = item.get('id')
        brand = item.get('vendor', {}).get('name', 'Unknown')
        name = get_color_name(item)
        material = item.get('material', 'Unknown')
        smart_type = get_smart_type(material, extra)
        hex_val = get_best_hex(item)
        r, g, b = hex_to_rgb(hex_val)
        
        qr_link = f"{HUB_BASE}/scan/filament/{fid}"
        rows.append([fid, brand, name, smart_type, hex_val, r, g, b, qr_link])

    if rows:
        output_file = get_output_path('filaments_to_sample.csv')
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerows([headers] + rows)
        print(f"SUCCESS: Generated '{output_file}' with {len(rows)} samples.")
    else:
        print("No new filament samples to print.")

def process_spools():
    print("\n--- Processing Spools (Labels) ---")
    data = fetch_from_api("spool")
    headers = ['ID', 'Brand', 'Color', 'Type', 'Hex', 'Red', 'Green', 'Blue', 'Weight', 'QR_Code']
    rows = []
    
    for item in data:
        extra = item.get('extra', {})
        if not should_process(extra, 'label_printed'): continue

        filament = item.get('filament', {})
        sid = item.get('id')
        brand = filament.get('vendor', {}).get('name', 'Unknown')
        name = get_color_name(filament)
        material = filament.get('material', 'Unknown')
        weight = f"{item.get('initial_weight', 0):.0f}g"
        smart_type = get_smart_type(material, filament.get('extra', {}))
        hex_val = get_best_hex(filament)
        r, g, b = hex_to_rgb(hex_val)

        qr_link = f"{HUB_BASE}/scan/{sid}"
        rows.append([sid, brand, name, smart_type, hex_val, r, g, b, weight, qr_link])

    if rows:
        output_file = get_output_path('spools_to_label.csv')
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerows([headers] + rows)
        print(f"SUCCESS: Generated '{output_file}' with {len(rows)} spool labels.")
    else:
        print("No new spool labels to print.")

if __name__ == "__main__":
    process_filaments()
    process_spools()
    print("\nDone.")
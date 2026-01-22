import csv
import requests
import json
import os
import sys

# --- CONFIGURATION ---
SPOOLMAN_IP = "http://192.168.1.29:7912"
DATA_FOLDER_NAME = "3D Print Data"
LISTS_FILENAME = "3D Print Supplies - Lists.csv"
FILAMENT_FILENAME = "3D Print Supplies - Filament.csv"

# --- PATH FINDER HELPER ---
def find_file(filename):
    """Locates a file inside '3D Print Data' by searching up the directory tree."""
    # Start at the script's physical location
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Walk up 4 levels to find the data folder
    for _ in range(4):
        # Check if the data folder exists here
        data_path = os.path.join(current_dir, DATA_FOLDER_NAME)
        file_path = os.path.join(data_path, filename)
        
        if os.path.exists(data_path) and os.path.exists(file_path):
            print(f"Found {filename} at: {file_path}")
            return file_path
        
        # Stop if we hit the root of the drive
        parent_dir = os.path.dirname(current_dir)
        if parent_dir == current_dir:
            break
        current_dir = parent_dir
        
    print(f"❌ Error: Could not find '{filename}' inside a '{DATA_FOLDER_NAME}' folder nearby.")
    sys.exit(1)

# Locate Files
LISTS_CSV = find_file(LISTS_FILENAME)
FILAMENT_CSV = find_file(FILAMENT_FILENAME)

# --- CLEANUP MAP ---
NORMALIZE_MAP = {
    "Carbon-Fiber": "Carbon Fiber",
    "High-Speed": "High Speed",
    "Matte Pro": "Matte", 
    "Transparent; High-Speed": "Transparent"
}

def get_clean_choices(filepath, column_name, is_multi=False):
    unique_vals = set()
    # Path Finder handles existence check, but double check doesn't hurt
    if not os.path.exists(filepath): return unique_vals
    
    with open(filepath, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            val = row.get(column_name, "").strip()
            if not val: continue
            parts = val.replace(";", ",").split(",") if is_multi else [val]
            for part in parts:
                clean = part.strip()
                if clean:
                    clean = NORMALIZE_MAP.get(clean, clean)
                    unique_vals.add(clean)
    return unique_vals

def create_field(entity, key, name, ftype, choices=None, multi=False):
    url = f"{SPOOLMAN_IP}/api/v1/field/{entity}/{key}"
    payload = {"name": name, "field_type": ftype}
    if ftype == "choice":
        payload["multi_choice"] = multi
        payload["choices"] = sorted(list(choices)) if choices else []

    print(f"Creating {entity} field: {name} ({ftype})...")
    try:
        resp = requests.post(url, json=payload)
        if resp.status_code in [200, 201]: print(" -> Success!")
        elif resp.status_code == 409: print(" -> Field already exists.")
        else: print(f" -> Error {resp.status_code}: {resp.text}")
    except Exception as e: print(f" -> Connection Failed: {e}")

# --- MAIN ---
print(f"Configuring Spoolman at {SPOOLMAN_IP}...")

# 1. SCANNING
print("Scanning CSVs for dropdown choices...")
attrs = get_clean_choices(LISTS_CSV, "Filament Attributes", is_multi=True)
attrs.update(get_clean_choices(FILAMENT_CSV, "Filament Attributes", is_multi=True))
attrs.update(["Carbon Fiber", "Glass Fiber", "Pro", "Plus", "High Speed"])
attrs.discard("Basic"); attrs.discard("Standard")

spool_types = get_clean_choices(LISTS_CSV, "Spool Type")
spool_types.update(get_clean_choices(FILAMENT_CSV, "Spool Type"))

shores = get_clean_choices(LISTS_CSV, "TPU Shore")
shores.update(get_clean_choices(FILAMENT_CSV, "TPU Shore"))

profiles = get_clean_choices(LISTS_CSV, "Filament Profile")
profiles.update(get_clean_choices(FILAMENT_CSV, "Filament Profile"))

# 2. CREATE FILAMENT FIELDS
create_field("filament", "filament_attributes", "Filament Attributes", "choice", choices=attrs, multi=True)
create_field("filament", "shore_hardness", "Shore Hardness", "choice", choices=shores, multi=False)
create_field("filament", "slicer_profile", "Slicer Profile", "choice", choices=profiles, multi=False)

filament_standards = [
    ("label_printed", "Label Printed", "boolean"),
    ("sample_printed", "Sample Printed", "boolean"),
    ("product_url", "Product Page Link", "text"),
    ("purchase_url", "Purchase Link", "text"),
    ("sheet_link", "Sheet Row Link", "text"),
    ("price_total", "Price (w/ Tax)", "text"),
    ("spoolman_reprint", "Spoolman Reprint", "boolean"),
    ("original_color", "Original Color", "text")
]

for key, name, ftype in filament_standards:
    create_field("filament", key, name, ftype)

# 3. CREATE SPOOL FIELDS
create_field("spool", "label_printed", "Label Printed", "boolean")
create_field("spool", "is_refill", "Is Refill", "boolean")
create_field("spool", "spool_type", "Spool Type", "choice", choices=spool_types, multi=False)
create_field("spool", "spool_temp", "Spool Max Temp", "text")

print("Setup Complete!")
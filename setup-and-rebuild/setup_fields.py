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
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    for _ in range(4):
        # Check relative to current location
        check_path = os.path.join(current_dir, filename)
        if os.path.exists(check_path):
            return check_path

        # Check inside Data Folder
        data_path = os.path.join(current_dir, DATA_FOLDER_NAME)
        file_path = os.path.join(data_path, filename)
        if os.path.exists(data_path) and os.path.exists(file_path):
            print(f"📂 Found {filename} at: {file_path}")
            return file_path
        
        # Stop if we hit root
        parent_dir = os.path.dirname(current_dir)
        if parent_dir == current_dir:
            break
        current_dir = parent_dir
        
    print(f"⚠️ Warning: Could not find '{filename}'. Creating fields without dynamic choices.")
    return None

# --- API HELPER (FIXED) ---
def create_field(entity_type, key, name, f_type, choices=None, multi=False):
    payload = {
        "name": name,
        "field_type": f_type, 
    }
    
    # CRITICAL FIX: Only add 'multi_choice' and 'choices' if type is 'choice'
    if f_type == "choice":
        payload["multi_choice"] = multi
        if choices:
            # Filter empty strings and sort
            clean_choices = sorted([c for c in list(set(choices)) if c.strip()])
            payload["choices"] = clean_choices

    print(f"Creating {entity_type} field: {name} ({key})...")
    
    url = f"{SPOOLMAN_IP}/api/v1/field/{entity_type}/{key}"
    
    try:
        resp = requests.post(url, json=payload)
        if resp.status_code in [200, 201]:
            print("✅ Created/Updated.")
        elif resp.status_code == 400 and "already exists" in resp.text:
            print("⚠️ Already exists.")
        else:
            print(f"❌ Error {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"❌ Connection Error: {e}")

# --- CHOICE EXTRACTOR ---
def get_clean_choices(csv_path, column_name):
    choices = set()
    if not csv_path or not os.path.exists(csv_path):
        return list(choices)
        
    try:
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                val = row.get(column_name)
                if val:
                    # Handle comma-separated lists (e.g., "Silk, Matte")
                    parts = val.split(',')
                    for p in parts:
                        clean = p.strip()
                        if clean: choices.add(clean)
    except Exception as e:
        print(f"⚠️ Error reading {csv_path}: {e}")
        
    return list(choices)

# ==========================================
# MAIN EXECUTION
# ==========================================

LISTS_CSV = find_file(LISTS_FILENAME)
FILAMENT_CSV = find_file(FILAMENT_FILENAME)

# 1. GATHER CHOICES
print("\n--- Gathering Choices from CSVs ---")
attrs = set()
attrs.update(get_clean_choices(LISTS_CSV, "Filament Attributes"))
attrs.update(get_clean_choices(FILAMENT_CSV, "Filament Attributes"))

shores = set()
shores.update(get_clean_choices(LISTS_CSV, "TPU Shore"))
shores.update(get_clean_choices(FILAMENT_CSV, "TPU Shore"))

profiles = set()
profiles.update(get_clean_choices(LISTS_CSV, "Filament Profile"))
profiles.update(get_clean_choices(FILAMENT_CSV, "Filament Profile"))

# 2. CREATE SPOOL FIELDS (The New One)
print("\n--- Setting up SPOOL Fields ---")
create_field("spool", "physical_source", "Physical Source", "text")

# 3. CREATE FILAMENT FIELDS (The Original Ones)
print("\n--- Setting up FILAMENT Fields ---")

# Choice Fields
create_field("filament", "filament_attributes", "Filament Attributes", "choice", choices=list(attrs), multi=True)
create_field("filament", "shore_hardness", "Shore Hardness", "choice", choices=list(shores), multi=False)
create_field("filament", "slicer_profile", "Slicer Profile", "choice", choices=list(profiles), multi=False)

# Text/Bool Fields
filament_standards = [
    ("label_printed", "Label Printed", "boolean"),
    ("sample_printed", "Sample Printed", "boolean"),
    ("product_url", "Product Page Link", "text"),
    ("purchase_url", "Purchase Link", "text"),
    ("sheet_link", "Sheet Row Link", "text"),
    ("price_total", "Price (w/ Tax)", "text"),
    ("spoolman_reprint", "Spoolman Reprint", "boolean"),
    ("original_color", "Original Color", "text"),
    # Adding helpful ones for good measure
    ("drying_temp", "Drying Temp", "text"),
    ("drying_time", "Drying Time", "text"),
    ("flush_multiplier", "Flush Multiplier", "text")
]

for key, name, ftype in filament_standards:
    create_field("filament", key, name, ftype)

print("\n🎉 All Fields Restored Successfully!")
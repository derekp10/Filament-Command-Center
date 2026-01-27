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
    current_dir = os.path.dirname(os.path.abspath(__file__))
    for _ in range(4):
        check_path = os.path.join(current_dir, filename)
        if os.path.exists(check_path): return check_path
        data_path = os.path.join(current_dir, DATA_FOLDER_NAME)
        file_path = os.path.join(data_path, filename)
        if os.path.exists(data_path) and os.path.exists(file_path):
            print(f"📂 Found {filename} at: {file_path}")
            return file_path
        parent_dir = os.path.dirname(current_dir)
        if parent_dir == current_dir: break
        current_dir = parent_dir
    print(f"⚠️ Warning: Could not find '{filename}'.")
    return None

# --- API HELPERS ---
def delete_field(entity_type, key):
    print(f"🗑️ Deleting {entity_type} field: {key}...")
    try:
        resp = requests.delete(f"{SPOOLMAN_IP}/api/v1/field/{entity_type}/{key}")
        if resp.status_code in [200, 204]: print("✅ Deleted.")
        elif resp.status_code == 404: print("ℹ️ Did not exist (OK).")
        else: print(f"❌ Error {resp.status_code}: {resp.text}")
    except Exception as e: print(f"❌ Connection Error: {e}")

def create_field(entity_type, key, name, f_type, choices=None, multi=False):
    payload = {"name": name, "field_type": f_type}
    if f_type == "choice":
        payload["multi_choice"] = multi
        if choices:
            payload["choices"] = sorted([c for c in list(set(choices)) if c.strip()])

    print(f"🆕 Creating {entity_type} field: {name} ({key})...")
    try:
        resp = requests.post(f"{SPOOLMAN_IP}/api/v1/field/{entity_type}/{key}", json=payload)
        if resp.status_code in [200, 201]: print("✅ Created.")
        else: print(f"❌ Error {resp.status_code}: {resp.text}")
    except Exception as e: print(f"❌ Connection Error: {e}")

def get_clean_choices(csv_path, column_name):
    choices = set()
    if not csv_path or not os.path.exists(csv_path): return list(choices)
    try:
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                val = row.get(column_name)
                if val:
                    for p in val.split(','):
                        clean = p.strip()
                        if clean: choices.add(clean)
    except Exception as e: print(f"⚠️ Error reading {csv_path}: {e}")
    return list(choices)

# ==========================================
# MAIN EXECUTION
# ==========================================

LISTS_CSV = find_file(LISTS_FILENAME)
FILAMENT_CSV = find_file(FILAMENT_FILENAME)

print("\n--- Gathering Choices ---")
attrs = set()
attrs.update(get_clean_choices(LISTS_CSV, "Filament Attributes"))
attrs.update(get_clean_choices(FILAMENT_CSV, "Filament Attributes"))
generated_attrs = ["Carbon Fiber", "Glass Fiber", "Glitter", "Marble", "Wood", "Glow", "Gradient"]
attrs.update(generated_attrs)

shores = set()
shores.update(get_clean_choices(LISTS_CSV, "TPU Shore"))
shores.update(get_clean_choices(FILAMENT_CSV, "TPU Shore"))

profiles = set()
profiles.update(get_clean_choices(LISTS_CSV, "Filament Profile"))
profiles.update(get_clean_choices(FILAMENT_CSV, "Filament Profile"))

spool_types = set()
spool_types.update(get_clean_choices(FILAMENT_CSV, "Spool Type"))

# ==========================================
# 1. RESET SPOOL FIELDS
# ==========================================
print("\n--- Resetting SPOOL Fields ---")
spool_fields = [
    ("physical_source", "text"),
    ("label_printed", "boolean"),
    ("is_refill", "boolean"),
    ("spool_temp", "text"),
    ("spool_type", "choice")
]

for key, ftype in spool_fields:
    delete_field("spool", key)
    
create_field("spool", "physical_source", "Physical Source", "text")
create_field("spool", "label_printed", "Label Printed", "boolean")
create_field("spool", "is_refill", "Is Refill", "boolean")
create_field("spool", "spool_temp", "Temp Resistance", "text")
create_field("spool", "spool_type", "Spool Type", "choice", choices=list(spool_types), multi=False)

# ==========================================
# 2. RESET FILAMENT FIELDS
# ==========================================
print("\n--- Resetting FILAMENT Fields ---")
filament_choice_fields = ["filament_attributes", "shore_hardness", "slicer_profile"]
for key in filament_choice_fields: delete_field("filament", key)

create_field("filament", "filament_attributes", "Filament Attributes", "choice", choices=list(attrs), multi=True)
create_field("filament", "shore_hardness", "Shore Hardness", "choice", choices=list(shores), multi=False)
create_field("filament", "slicer_profile", "Slicer Profile", "choice", choices=list(profiles), multi=False)

filament_standards = [
    ("label_printed", "Label Printed", "boolean"),
    ("sample_printed", "Sample Printed", "boolean"),
    ("product_url", "Product Page Link", "text"),
    ("purchase_url", "Purchase Link", "text"),
    ("sheet_link", "Sheet Row Link", "text"),
    ("price_total", "Price (w/ Tax)", "text"),
    ("spoolman_reprint", "Spoolman Reprint", "boolean"),
    ("original_color", "Original Color", "text"),
    ("drying_temp", "Drying Temp", "text"),
    ("drying_time", "Drying Time", "text"),
    ("flush_multiplier", "Flush Multiplier", "text")
]

for key, name, ftype in filament_standards:
    delete_field("filament", key)
    create_field("filament", key, name, ftype)

print("\n🎉 All Fields NUKED and REBUILT Correctly!")
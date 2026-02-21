import csv
import requests
import json
import os
import sys

# Add inventory-hub to path to import config_loader
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'inventory-hub')))
import config_loader

# --- CONFIGURATION ---
SPOOLMAN_IP, _ = config_loader.get_api_urls()
print(f"🔗 Target Spoolman Database: {SPOOLMAN_IP}")
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

# --- API HELPER ---
def create_field(entity_type, key, name, f_type, choices=None, multi=False, force_reset=False):
    """
    Creates or Updates a field in Spoolman.
    force_reset=True will DELETE the field first to ensure Type changes take effect.
    """
    print(f"🔧 Processing {entity_type} field: {name} ({key})...")
    
    if force_reset:
        print(f"   ⚠️ Force Reset enabled. Deleting old definition...")
        try:
            del_resp = requests.delete(f"{SPOOLMAN_IP}/api/v1/field/{entity_type}/{key}")
            # FIX: Spoolman returns 200 OK with list of remaining fields on success
            if del_resp.status_code in [200, 204]: 
                print("   🗑️ Deleted old field.")
            elif del_resp.status_code == 404: 
                print("   ℹ️ Old field not found (clean start).")
            else: 
                print(f"   ⚠️ Delete status {del_resp.status_code}: {del_resp.text}")
        except Exception as e: print(f"   ❌ Connection Error during delete: {e}")

    # --- [ALEX FIX] FETCH EXISTING CHOICES TO PREVENT "CANNOT REMOVE" ERROR ---
    existing_choices = []
    if f_type == "choice" and not force_reset:
        try:
            # Query the entire entity list instead of the specific key
            get_resp = requests.get(f"{SPOOLMAN_IP}/api/v1/field/{entity_type}")
            if get_resp.status_code == 200:
                all_fields = get_resp.json()
                
                # Dig through the list to find our specific field
                for field in all_fields:
                    if field.get('key') == key:
                        raw_existing = field.get('choices', [])
                        
                        if isinstance(raw_existing, str):
                            try: raw_existing = json.loads(raw_existing)
                            except: raw_existing = [c.strip() for c in raw_existing.strip('[]').replace('"', '').split(',') if c.strip()]
                            
                        if isinstance(raw_existing, list):
                            existing_choices = raw_existing
                            
                        if existing_choices:
                            print(f"   ℹ️ Found {len(existing_choices)} existing choices. Merging to protect data.")
                        break # Found it, stop searching
        except Exception as e:
            print(f"   ⚠️ Could not fetch existing choices: {e}")

    payload = {"name": name, "field_type": f_type}
    if f_type == "choice":
        payload["multi_choice"] = multi
        
        # [ALEX FIX] Combine CSV choices with Existing DB choices
        merged_choices = set()
        if choices: 
            merged_choices.update(choices)
        if existing_choices: 
            merged_choices.update(existing_choices)
            
        if merged_choices:
            payload["choices"] = sorted([c for c in list(merged_choices) if str(c).strip()])

    try:
        resp = requests.post(f"{SPOOLMAN_IP}/api/v1/field/{entity_type}/{key}", json=payload)
        if resp.status_code in [200, 201]: print("   ✅ Created/Updated.")
        elif resp.status_code == 400 and "already exists" in resp.text: print("   ℹ️ Already exists.")
        else: print(f"   ❌ Error {resp.status_code}: {resp.text}")
    except Exception as e: print(f"   ❌ Connection Error: {e}")

# --- CHOICE EXTRACTOR ---
def get_clean_choices(csv_path, column_name):
    choices = set()
    if not csv_path or not os.path.exists(csv_path): return list(choices)
    try:
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                val = row.get(column_name)
                if isinstance(val, str) and val.strip():
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
# Filament Attributes
attrs = set()
attrs.update(get_clean_choices(LISTS_CSV, "Filament Attributes"))
attrs.update(get_clean_choices(FILAMENT_CSV, "Filament Attributes"))
generated_attrs = ["Carbon Fiber", "Glass Fiber", "Glitter", "Marble", "Wood", "Glow", "Gradient"]
attrs.update(generated_attrs)

# Shore Hardness & Profiles
shores = set()
shores.update(get_clean_choices(LISTS_CSV, "TPU Shore"))
shores.update(get_clean_choices(FILAMENT_CSV, "TPU Shore"))

profiles = set()
profiles.update(get_clean_choices(LISTS_CSV, "Filament Profile"))
profiles.update(get_clean_choices(FILAMENT_CSV, "Filament Profile"))

# Spool Types (NEW)
spool_types = set()
spool_types.update(get_clean_choices(FILAMENT_CSV, "Spool Type"))

# ==========================================
# 1. SETUP SPOOL FIELDS
# ==========================================
print("\n--- Setting up SPOOL Fields ---")
create_field("spool", "physical_source", "Physical Source", "text")
# [ALEX FIX] Register the new Ghost Slot field
create_field("spool", "physical_source_slot", "Physical Source Slot", "text")
create_field("spool", "label_printed", "Label Printed", "boolean")
create_field("spool", "is_refill", "Is Refill", "boolean")
create_field("spool", "spool_temp", "Temp Resistance", "text")
create_field("spool", "product_url", "Product Page Link", "text") # [ALEX FIX] New custom field

# --- CRITICAL: FORCE RESET CONTAINER SLOT TO TEXT ---
create_field("spool", "container_slot", "Container / MMU Slot", "text", force_reset=True)

# Choice field for Spool Type
create_field("spool", "spool_type", "Spool Type", "choice", choices=list(spool_types), multi=False)


# ==========================================
# 2. SETUP FILAMENT FIELDS
# ==========================================
print("\n--- Setting up FILAMENT Fields ---")
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
    create_field("filament", key, name, ftype)

print("\n🎉 All Fields Configured Successfully!")
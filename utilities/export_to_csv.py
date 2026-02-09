import csv
import requests
import os
from datetime import datetime
import project_config  # Uses your global config system

# --- LOAD CONFIG ---
config = project_config.load_config()
SPOOLMAN_URL = config.get("spoolman_url")
EXPORT_DIR = config.get("export_directory", ".") 

def fetch_all_spools():
    """Fetch every single spool from Spoolman."""
    print(f"🔌 Connecting to {SPOOLMAN_URL}...")
    try:
        r = requests.get(f"{SPOOLMAN_URL}/api/v1/spool")
        if r.status_code != 200:
            print(f"❌ Error fetching spools: {r.status_code}")
            return []
        return r.json()
    except Exception as e:
        print(f"❌ Connection Failed: {e}")
        return []

def flatten_spool(spool):
    """
    Dynamically flattens a spool object.
    Prefixes Filament data with 'Filament_' and Vendor data with 'Vendor_'.
    """
    row = {}

    # 1. ROOT SPOOL DATA (Iterate everything to catch future fields)
    for key, val in spool.items():
        if key == "id":
            row["SpoolID"] = val # SYLK Fix
        elif key == "extra":
            continue # Handle separately
        elif key == "filament":
            continue # Handle separately
        elif isinstance(val, (str, int, float, bool, type(None))):
            row[key] = val
    
    # Calculate Remaining (Convenience)
    fil = spool.get("filament", {}) or {}
    total_w = fil.get("weight", 0)
    used_w = spool.get("used_weight", 0)
    row["calculated_remaining_weight"] = max(0, total_w - used_w)

    # 2. SPOOL EXTRA DATA
    spool_extra = spool.get("extra", {}) or {}
    for k, v in spool_extra.items():
        row[f"Extra: {k}"] = v

    # 3. FILAMENT DATA (Flatten with prefix)
    for key, val in fil.items():
        if key == "vendor":
            continue # Handle separately
        elif key == "extra":
            continue # Handle separately
        elif isinstance(val, (str, int, float, bool, type(None))):
            row[f"Filament_{key}"] = val

    # 4. FILAMENT EXTRA DATA
    fil_extra = fil.get("extra", {}) or {}
    for k, v in fil_extra.items():
        row[f"Filament_Extra: {k}"] = v

    # 5. VENDOR DATA
    vend = fil.get("vendor", {}) or {}
    for key, val in vend.items():
        if key == "extra":
            continue
        elif isinstance(val, (str, int, float, bool, type(None))):
            row[f"Vendor_{key}"] = val

    # 6. TIMESTAMP CLEANUP (Optional Polish)
    for col in ["registered", "first_used", "last_used", "Filament_registered", "Vendor_registered"]:
        if col in row and isinstance(row[col], str):
            row[col] = row[col][:19].replace("T", " ")

    return row

def main():
    if EXPORT_DIR and not os.path.exists(EXPORT_DIR):
        try: os.makedirs(EXPORT_DIR)
        except Exception as e: print(f"❌ Error: {e}"); return

    spools = fetch_all_spools()
    if not spools: return

    print(f"📦 Processing {len(spools)} spools...")

    # Flatten Data
    flattened_data = [flatten_spool(s) for s in spools]
    
    # Collect ALL Headers dynamically
    headers = []
    # We loop through all rows to find every unique key (in case some spools have unique extra fields)
    key_set = set()
    for item in flattened_data:
        key_set.update(item.keys())
    
    # Sort headers for sanity
    # Order: SpoolID, External ID, basic spool stuff, Extra:, Filament_, Filament_Extra, Vendor_
    def header_sort(k):
        if k == "SpoolID": return "000"
        if k == "external_id": return "001"
        if k.startswith("Extra:"): return "800" + k
        if k.startswith("Filament_Extra:"): return "900" + k
        if k.startswith("Filament_"): return "500" + k
        if k.startswith("Vendor_"): return "600" + k
        return "100" + k
    
    headers = sorted(list(key_set), key=header_sort)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"Spoolman_Full_Firehose_{timestamp}.csv"
    full_path = os.path.join(EXPORT_DIR, filename)

    try:
        with open(full_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(flattened_data)
        print(f"✅ Success! Full Firehose Exported to: {os.path.abspath(full_path)}")
    except Exception as e:
        print(f"❌ Failed to write CSV: {e}")

if __name__ == "__main__":
    main()
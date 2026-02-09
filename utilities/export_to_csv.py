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
    filament = spool.get("filament", {}) or {}
    vendor = filament.get("vendor", {}) or {}
    extra = spool.get("extra", {}) or {}
    
    # Calculate Remaining Weight
    total_weight = filament.get("weight", 0)
    used_weight = spool.get("used_weight", 0)
    remaining = max(0, total_weight - used_weight)

    # Base Fields
    row = {
        "SpoolID": spool.get("id"),
        "External ID": spool.get("external_id", ""), # <--- ADDED THIS (Your Legacy ID)
        "Vendor": vendor.get("name", "Unknown"),
        "Filament Name": filament.get("name", "Unknown"),
        "Material": filament.get("material", "Unknown"),
        "Color (Hex)": filament.get("color_hex", ""),
        "Location": spool.get("location", ""),
        "Lot #": spool.get("lot_nr", ""),
        "Comment": spool.get("comment", ""),
        "Archived": spool.get("archived", False),
        "Total Weight (g)": total_weight,
        "Used (g)": used_weight,
        "Remaining (g)": remaining,
        "Registered": spool.get("registered", "")[:19].replace("T", " "),
        "Last Used": (spool.get("last_used") or "")[:19].replace("T", " "),
        "Spoolman_Filament_ID": filament.get("id"),
        "Spoolman_Vendor_ID": vendor.get("id")
    }

    # --- HANDLING EXTRA FIELDS ---
    for k, v in extra.items():
        # Clean up JSON strings if needed
        row[f"Extra: {k}"] = v
    
    return row

def main():
    if EXPORT_DIR and not os.path.exists(EXPORT_DIR):
        try: os.makedirs(EXPORT_DIR)
        except Exception as e: print(f"❌ Error: {e}"); return

    spools = fetch_all_spools()
    if not spools: return

    print(f"📦 Processing {len(spools)} spools...")

    flattened_data = [flatten_spool(s) for s in spools]
    
    # Collect Headers
    headers = list(flattened_data[0].keys())
    for item in flattened_data:
        for k in item.keys():
            if k not in headers: headers.append(k)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"Spoolman_Master_Export_{timestamp}.csv"
    full_path = os.path.join(EXPORT_DIR, filename)

    try:
        with open(full_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(flattened_data)
        print(f"✅ Success! Exported to: {os.path.abspath(full_path)}")
    except Exception as e:
        print(f"❌ Failed to write CSV: {e}")

if __name__ == "__main__":
    main()
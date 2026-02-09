import csv
import requests
import os
from datetime import datetime
import project_config  # Uses your global config system

# --- LOAD CONFIG ---
config = project_config.load_config()
SPOOLMAN_URL = config.get("spoolman_url")

def fetch_all_spools():
    """Fetch every single spool from Spoolman."""
    print(f"🔌 Connecting to {SPOOLMAN_URL}...")
    try:
        # Get Spools (including archived ones, just in case)
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
    Takes a nested Spoolman object and flattens it into a CSV-friendly row.
    Handles missing vendors, filaments, etc. gracefully.
    """
    filament = spool.get("filament", {}) or {}
    vendor = filament.get("vendor", {}) or {}
    extra = spool.get("extra", {}) or {}
    fil_extra = filament.get("extra", {}) or {}

    # Calculate Remaining Weight
    # Spoolman gives 'used_weight' and 'initial_weight' (from filament)
    total_weight = filament.get("weight", 0)
    used_weight = spool.get("used_weight", 0)
    remaining = max(0, total_weight - used_weight)

    # Base Fields
    row = {
        "ID": spool.get("id"),
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
        "Registered": spool.get("registered", "")[:19].replace("T", " "), # Clean Date
        "Last Used": (spool.get("last_used") or "")[:19].replace("T", " "),
        "Spoolman_Filament_ID": filament.get("id"),
        "Spoolman_Vendor_ID": vendor.get("id")
    }

    # --- HANDLING EXTRA FIELDS ---
    # We combine Spool-level extra fields and Filament-level extra fields
    # Format: "Extra: KeyName"
    for k, v in extra.items():
        row[f"Extra: {k}"] = v
    
    # Optional: Include Filament Extra fields if you want them
    # for k, v in fil_extra.items():
    #     row[f"Filament Extra: {k}"] = v

    return row

def main():
    spools = fetch_all_spools()
    if not spools:
        print("⚠️ No data found. Exiting.")
        return

    print(f"📦 Processing {len(spools)} spools...")

    # 1. Flatten all data first to find all possible columns (dynamic extra fields)
    flattened_data = [flatten_spool(s) for s in spools]
    
    # 2. Collect all unique headers
    headers = list(flattened_data[0].keys()) # Start with standard keys from first item
    for item in flattened_data:
        for k in item.keys():
            if k not in headers:
                headers.append(k)

    # 3. Generate Filename
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"Spoolman_Master_Export_{timestamp}.csv"

    # 4. Write CSV
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(flattened_data)
        
        print(f"✅ Success! Exported to: {os.path.abspath(filename)}")
    except Exception as e:
        print(f"❌ Failed to write CSV: {e}")

if __name__ == "__main__":
    main()
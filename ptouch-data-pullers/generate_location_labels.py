import csv
import os
import sys

# --- CONFIGURATION ---
DATA_FOLDER_NAMES = ["3D Print Data", "inventory-hub"] # Added inventory-hub to search path
SOURCE_FILENAME = "3D Print Supplies - Locations.csv"

# Output Filenames
LOCATIONS_OUTPUT = "locations_to_print.csv"
SLOTS_OUTPUT = "slots_to_print.csv"

# --- PATH FINDER LOGIC ---
def find_data_file():
    """Climbs up the directory tree until it finds the Data File."""
    current_path = os.path.abspath(os.path.dirname(__file__))
    
    # 1. Search up the tree for known folder names
    scan_path = current_path
    for _ in range(5):
        # Check inside specific folder names
        for folder in DATA_FOLDER_NAMES:
            check_path = os.path.join(scan_path, folder, SOURCE_FILENAME)
            if os.path.exists(check_path):
                print(f"📂 Found Data File: {check_path}")
                return check_path, os.path.dirname(check_path)
        
        # Check if file is directly in this folder
        check_direct = os.path.join(scan_path, SOURCE_FILENAME)
        if os.path.exists(check_direct):
             print(f"📂 Found Data File (Direct): {check_direct}")
             return check_direct, scan_path
             
        parent = os.path.dirname(scan_path)
        if parent == scan_path: 
            break
        scan_path = parent

    print(f"❌ Error: Could not find '{SOURCE_FILENAME}' in any standard location.")
    sys.exit(1)

def process_locations():
    source_csv, data_dir = find_data_file()
    
    print(f"--- Reading: {SOURCE_FILENAME} ---")
    
    # Use utf-8-sig to handle Excel BOM (\ufeff) automatically
    with open(source_csv, 'r', encoding='utf-8-sig', errors='ignore') as f:
        # Read the first line to normalize headers
        raw_headers = f.readline().strip().split(',')
        # Strip whitespace from headers (e.g. "Max Spools " -> "Max Spools")
        headers = [h.strip() for h in raw_headers]
        print(f"🔎 Detected Headers: {headers}")
        
        # Reset file pointer and read with cleaned headers
        f.seek(0)
        reader = csv.DictReader(f, fieldnames=headers)
        # Skip the actual header row since we defined fieldnames manually
        next(reader, None)
        
        rows = list(reader)

    all_loc_labels = []
    all_slot_labels = []

    print(f"📊 Processing {len(rows)} rows...")

    for row in rows:
        # Robust ID Fetching
        loc_id = row.get('LocationID', '').strip().upper()
        if not loc_id: 
            continue 
        
        name = row.get('Name', '')
        
        # 1. ALWAYS generate the Main Location Label
        all_loc_labels.append({
            "LocationID": loc_id,
            "Name": name,
            "QR_Code": loc_id 
        })
        
        # 2. Check Max Spools
        try:
            raw_max = row.get('Max Spools', '1')
            if not raw_max or not raw_max.strip(): 
                max_spools = 1
            else:
                max_spools = int(raw_max)
        except (ValueError, TypeError):
            max_spools = 1
        
        # Debug print for dryer boxes to confirm logic matches
        if max_spools > 1:
            print(f"   -> Found {max_spools} slots for {loc_id} ({name})")
            
            # Generate a label for EVERY slot
            for i in range(1, max_spools + 1):
                slot_name = f"{name} Slot {i}"
                slot_qr = f"LOC:{loc_id}:SLOT:{i}"
                
                all_slot_labels.append({
                    "LocationID": loc_id,
                    "Name": slot_name,
                    "QR_Code": slot_qr
                })

    # --- WRITE FILES ---

    # 1. Write Locations Output
    if all_loc_labels:
        out_file = os.path.join(data_dir, LOCATIONS_OUTPUT)
        with open(out_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=["LocationID", "Name", "QR_Code"])
            writer.writeheader()
            writer.writerows(all_loc_labels)
        print(f"✅ Generated {len(all_loc_labels)} LOCATION labels in:")
        print(f"   {out_file}")
    else:
        print("⚠️ No valid locations found. Check 'LocationID' column header.")

    # 2. Write Slots Output
    if all_slot_labels:
        slot_file = os.path.join(data_dir, SLOTS_OUTPUT)
        with open(slot_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=["LocationID", "Name", "QR_Code"])
            writer.writeheader()
            writer.writerows(all_slot_labels)
        print(f"✅ Generated {len(all_slot_labels)} SLOT labels in:")
        print(f"   {slot_file}")
    else:
        print("ℹ️ No multi-slot locations found (Max Spools <= 1 for all entries).")

    print("\n🎉 Done! Ready for P-Touch.")

if __name__ == "__main__":
    process_locations()
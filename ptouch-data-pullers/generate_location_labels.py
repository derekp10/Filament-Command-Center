import csv
import os
import sys

# --- CONFIGURATION ---
DATA_FOLDER_NAME = "3D Print Data"
SOURCE_FILENAME = "3D Print Supplies - Locations.csv"

# Output Filenames
LOCATIONS_OUTPUT = "locations_to_print.csv"
SLOTS_OUTPUT = "slots_to_print.csv"

# --- PATH FINDER LOGIC ---
def find_data_dir():
    """Climbs up the directory tree until it finds the Data Folder."""
    current_path = os.path.abspath(os.path.dirname(__file__))
    
    for _ in range(5):
        check_path = os.path.join(current_path, DATA_FOLDER_NAME)
        if os.path.isdir(check_path):
            print(f"📂 Found Data Directory: {check_path}")
            return check_path
        
        # Check if we are IN the data folder (development environment quirk)
        if os.path.exists(os.path.join(current_path, SOURCE_FILENAME)):
            return current_path
            
        parent = os.path.dirname(current_path)
        if parent == current_path: 
            break
        current_path = parent

    # Fallback: Check strictly relative to script if searching failed
    if os.path.exists(SOURCE_FILENAME):
        return os.path.abspath(".")
        
    print(f"❌ Error: Could not find '{DATA_FOLDER_NAME}' or '{SOURCE_FILENAME}'")
    sys.exit(1)

def process_locations():
    data_dir = find_data_dir()
    source_csv = os.path.join(data_dir, SOURCE_FILENAME)
    
    print(f"--- Reading: {SOURCE_FILENAME} ---")
    
    if not os.path.exists(source_csv):
        print(f"❌ Error: File not found: {source_csv}")
        return

    # Read the data
    with open(source_csv, 'r', encoding='utf-8', errors='ignore') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    all_loc_labels = []
    all_slot_labels = []

    for row in rows:
        loc_id = row.get('LocationID', '').strip().upper()
        if not loc_id: continue # Skip empty rows
        
        name = row.get('Name', '')
        
        # 1. ALWAYS generate the Main Location Label
        all_loc_labels.append({
            "LocationID": loc_id,
            "Name": name,
            "QR_Code": loc_id 
        })
        
        # 2. ALWAYS generate Slot Labels if Max Spools > 1
        try:
            # Handle empty or invalid numbers gracefully
            raw_max = row.get('Max Spools', '1')
            if not raw_max or not raw_max.strip(): 
                max_spools = 1
            else:
                max_spools = int(raw_max)
        except (ValueError, TypeError):
            max_spools = 1
        
        if max_spools > 1:
            # Generate a label for EVERY slot
            for i in range(1, max_spools + 1):
                slot_name = f"{name} Slot {i}"
                # QR Format: LOC:ID:SLOT:NUMBER
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
        print("⚠️ No locations found in source CSV.")

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
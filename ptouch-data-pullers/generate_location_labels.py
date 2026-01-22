import csv
import os
import shutil
import sys

# --- CONFIGURATION ---
DATA_FOLDER_NAME = "3D Print Data"
SOURCE_FILENAME = "3D Print Supplies - Locations.csv"

# --- PATH FINDER LOGIC ---
def find_data_dir():
    """Climbs up the directory tree until it finds the Data Folder."""
    current_path = os.path.abspath(os.path.dirname(__file__))
    
    for _ in range(5):
        check_path = os.path.join(current_path, DATA_FOLDER_NAME)
        if os.path.isdir(check_path):
            print(f"📂 Found Data Directory: {check_path}")
            return check_path
        
        parent = os.path.dirname(current_path)
        if parent == current_path: 
            break
        current_path = parent

    print(f"❌ Error: Could not find '{DATA_FOLDER_NAME}' in any parent directory.")
    sys.exit(1)

DATA_DIR = find_data_dir()
SOURCE_CSV = os.path.join(DATA_DIR, SOURCE_FILENAME)

def get_output_path(filename):
    return os.path.join(DATA_DIR, filename)

def process_locations():
    print("--- Processing Locations ---")
    
    if not os.path.exists(SOURCE_CSV):
        print(f"Error: Could not find '{SOURCE_FILENAME}' inside '{DATA_DIR}'")
        return

    # Read the data
    with open(SOURCE_CSV, 'r', encoding='utf-8', errors='ignore') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    new_labels = []
    updates_made = False

    for row in rows:
        # Check if printed
        is_printed = row.get('Label Printed', '').lower() in ['yes', 'true', '1']
        
        if not is_printed:
            loc_id = row.get('LocationID', '').upper()
            name = row.get('Name', '')
            
            new_labels.append({
                "LocationID": loc_id,
                "Name": name,
                "QR_Code": loc_id 
            })
            
            row['Label Printed'] = 'Yes'
            updates_made = True

    # 1. Generate P-Touch CSV
    if new_labels:
        out_file = get_output_path("locations_to_print.csv")
        with open(out_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=["LocationID", "Name", "QR_Code"])
            writer.writeheader()
            writer.writerows(new_labels)
        print(f"✅ Generated {len(new_labels)} location labels in '{out_file}'")
    else:
        print("No new locations to print.")

    # 2. Update the Source CSV
    if updates_made:
        # Create backup
        shutil.copy(SOURCE_CSV, SOURCE_CSV + ".bak")
        
        with open(SOURCE_CSV, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"💾 Updated {SOURCE_FILENAME} with 'Label Printed = Yes'")

if __name__ == "__main__":
    process_locations()
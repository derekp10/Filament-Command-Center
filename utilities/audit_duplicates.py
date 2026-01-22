import csv
import os

CSV_FILE = "3D Print Supplies - Filament.csv"

# --- CONFIGURATION ---
# We normalize these just like the migration script to ensure "Matte Pro" matches "Matte"
NORMALIZE_MAP = {
    "Carbon-Fiber": "Carbon Fiber",
    "High-Speed": "High Speed",
    "Matte Pro": "Matte", 
    "Transparent; High-Speed": "Transparent"
}

def clean_int(val):
    try: return int(val)
    except: return 0

def get_clean_attributes(raw_attr_str):
    """Parses, cleans, and sorts attributes to create a consistent fingerprint."""
    if not raw_attr_str:
        return ""
    
    parts = raw_attr_str.replace(";", ",").split(",")
    cleaned_set = set()
    
    for part in parts:
        clean = part.strip()
        if not clean or clean.lower() in ["basic", "standard"]: 
            continue
        
        # Apply the same normalization as the migration script
        if clean in NORMALIZE_MAP:
            cleaned_set.add(NORMALIZE_MAP[clean])
        else:
            cleaned_set.add(clean)
            
    # Return a sorted string so "Matte, Silk" == "Silk, Matte"
    return "|".join(sorted(list(cleaned_set)))

def scan_for_duplicates():
    if not os.path.exists(CSV_FILE):
        print(f"Error: Could not find {CSV_FILE}")
        return

    # Dictionary to track occurrences
    # Key: (Brand, Color, Material, Attributes) -> Value: List of Row Data
    inventory = {}

    print(f"Scanning {CSV_FILE} for STRICT duplicates (checking Attributes)...\n")

    with open(CSV_FILE, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        
        for row_num, row in enumerate(reader, start=2):
            brand = row.get("Brand", "").strip()
            color = row.get("Color", "").strip()
            material = row.get("Filament Type", "").strip()
            raw_attrs = row.get("Filament Attributes", "").strip()

            if not brand or not color:
                continue

            # Generate the Fingerprint
            attr_fingerprint = get_clean_attributes(raw_attrs)
            
            # Key now includes the attributes
            key = (brand.lower(), color.lower(), material.lower(), attr_fingerprint.lower())

            # Gather counts
            unopened = clean_int(row.get("Unopened Spools", 0))
            opened = clean_int(row.get("Opened Spools", 0))
            refills = clean_int(row.get("Refills", 0))

            entry = {
                "row": row_num,
                "unopened": unopened,
                "opened": opened,
                "refills": refills,
                "brand": brand,
                "color": color,
                "material": material,
                "attributes": attr_fingerprint if attr_fingerprint else "(None)"
            }

            if key in inventory:
                inventory[key].append(entry)
            else:
                inventory[key] = [entry]

    # --- REPORTING ---
    duplicate_count = 0
    
    for key, entries in inventory.items():
        if len(entries) > 1:
            duplicate_count += 1
            e = entries[0]
            print(f"⚠️  DUPLICATE FOUND: {e['brand']} - {e['color']} ({e['material']})")
            if e['attributes'] != "(None)":
                print(f"    Attributes: {e['attributes']}")
            
            total_unopened = 0
            total_opened = 0
            total_refills = 0

            for x in entries:
                print(f"    Row {x['row']}:  {x['unopened']} Unopened | {x['opened']} Opened | {x['refills']} Refills")
                total_unopened += x['unopened']
                total_opened += x['opened']
                total_refills += x['refills']
            
            print(f"    >> COMBINED: {total_unopened} Unopened | {total_opened} Opened | {total_refills} Refills")
            print("-" * 60)

    if duplicate_count == 0:
        print("✅ No duplicates found! Your CSV is clean.")
    else:
        print(f"\nFound {duplicate_count} items with multiple entries.")
        print("These rows will be merged into single Filament definitions in Spoolman.")

if __name__ == "__main__":
    scan_for_duplicates()
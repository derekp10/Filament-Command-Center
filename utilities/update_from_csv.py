import csv
import requests
import json
import os
import sys
import project_config  # Uses your global config

# --- CONFIGURATION ---
config = project_config.load_config()
SPOOLMAN_URL = config.get("spoolman_url")
# We look for the CSV in the Export directory by default, but you can change this
Target_CSV = "Spoolman_Master_Export_EDIT_ME.csv" 

# Fields that Spoolman requires to be JSON-stringified (from your spoolman_api.py)
JSON_STRING_FIELDS = ["spool_type", "container_slot", "physical_source", "original_color", "spool_temp"]

def sanitize_extra_field(key, val):
    """
    Ensures 'Extra' fields are formatted exactly how Spoolman expects them.
    """
    if val is None: return None
    val_str = str(val).strip()
    
    # 1. Handle Booleans
    if val_str.lower() == 'true': return "true"
    if val_str.lower() == 'false': return "false"
    
    # 2. Handle Specific JSON String Fields
    if key in JSON_STRING_FIELDS:
        # If it's not already quoted, quote it
        if not (val_str.startswith('"') and val_str.endswith('"')):
            return f'"{val_str}"'
    
    return val_str

def get_spool(sid):
    try:
        r = requests.get(f"{SPOOLMAN_URL}/api/v1/spool/{sid}", timeout=5)
        if r.status_code == 200: return r.json()
    except: pass
    return None

def update_spool(sid, payload):
    try:
        r = requests.patch(f"{SPOOLMAN_URL}/api/v1/spool/{sid}", json=payload, timeout=5)
        if r.status_code == 200:
            print(f"✅ Updated Spool {sid}")
            return True
        else:
            print(f"❌ Failed to update {sid}: {r.status_code} - {r.text}")
            return False
    except Exception as e:
        print(f"❌ Connection Error: {e}")
        return False

def main():
    # 1. Find the CSV
    # We check the Export Dir first, then current dir
    export_dir = config.get("export_directory", ".")
    csv_path = os.path.join(export_dir, Target_CSV)
    
    if not os.path.exists(csv_path):
        # Fallback to current directory
        csv_path = Target_CSV
        if not os.path.exists(csv_path):
            print(f"❌ Could not find input file: {Target_CSV}")
            print(f"   Please rename your edited export to '{Target_CSV}' and place it in the export folder.")
            return

    print(f"📂 Reading from: {csv_path}")

    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"🔍 Analyzing {len(rows)} rows...")

    for row in rows:
        try:
            sid = row.get("SpoolID")
            if not sid: continue

            # A. Fetch Current State (The Truth)
            current_data = get_spool(sid)
            if not current_data:
                print(f"⚠️ Spool {sid} not found in DB. Skipping.")
                continue

            # B. Build Update Payload
            payload = {}
            changes_detected = False

            # 1. Standard Fields
            # Location
            new_loc = row.get("Location", "").strip()
            old_loc = str(current_data.get("location") or "").strip()
            if new_loc != old_loc:
                payload["location"] = new_loc
                changes_detected = True

            # Comment
            new_comment = row.get("Comment", "").strip()
            old_comment = str(current_data.get("comment") or "").strip()
            if new_comment != old_comment:
                payload["comment"] = new_comment
                changes_detected = True
            
            # Archived
            new_arch = str(row.get("Archived", "")).lower() == "true"
            old_arch = bool(current_data.get("archived"))
            if new_arch != old_arch:
                payload["archived"] = new_arch
                changes_detected = True

            # Remaining Weight (Optional - be careful editing this manually)
            # If you edit "Remaining (g)" in CSV, we calculate used_weight
            if "Remaining (g)" in row:
                try:
                    target_remaining = float(row["Remaining (g)"])
                    total_weight = float(row.get("Total Weight (g)", 0) or current_data['filament']['weight'])
                    new_used = max(0, total_weight - target_remaining)
                    
                    # Tolerance check (floating point math)
                    old_used = float(current_data.get("used_weight", 0))
                    if abs(new_used - old_used) > 0.1:
                        payload["used_weight"] = new_used
                        changes_detected = True
                except: pass

            # 2. Extra Fields (Dynamic)
            # We look for columns starting with "Extra: "
            extra_payload = current_data.get("extra", {}) or {} # Start with existing extras
            extra_changed = False
            
            for key, val in row.items():
                if key.startswith("Extra: "):
                    clean_key = key.replace("Extra: ", "").strip()
                    clean_val = sanitize_extra_field(clean_key, val)
                    
                    # Compare with existing
                    # Note: Spoolman returns some extras as strings, some as raw. 
                    # We cast current to string for comparison logic if needed.
                    current_val = str(extra_payload.get(clean_key, ""))
                    
                    # Simple comparison (this can be refined)
                    # If the CSV value is not empty, and differs from DB
                    if clean_val and clean_val != current_val:
                         extra_payload[clean_key] = clean_val
                         extra_changed = True
            
            if extra_changed:
                payload["extra"] = extra_payload
                changes_detected = True

            # C. Execute Update
            if changes_detected:
                print(f"📝 Updating #{sid}...", end=" ")
                update_spool(sid, payload)
            
        except Exception as e:
            print(f"❌ Error processing row {row}: {e}")

    print("--- Sync Complete ---")

if __name__ == "__main__":
    main()
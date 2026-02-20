import os
import json
import csv
import state # type: ignore

# Updated Configuration
JSON_FILE = 'locations.json'
CSV_FILE = '3D Print Supplies - Locations.csv'

def _ensure_json_migration():
    """
    Production-Safe Migration Strategy:
    If locations.json doesn't exist but the old Locations.csv does, we
    convert the CSV to JSON, save it, and rename the CSV to a backup file.
    """
    if os.path.exists(JSON_FILE) or not os.path.exists(CSV_FILE):
        return

    state.logger.info("🔄 Commencing one-time migration from CSV to JSON...")
    
    migrated_locs = []
    try:
        with open(CSV_FILE, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('LocationID'): 
                    migrated_locs.append(dict(row))
                    
        # Save to JSON
        with open(JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(migrated_locs, f, indent=4)
            
        # Protect original CSV
        backup_path = CSV_FILE.replace(".csv", "_BACKUP.csv")
        os.rename(CSV_FILE, backup_path)
        
        state.logger.info(f"✅ Migration successful! {len(migrated_locs)} locations migrated. Old CSV renamed to {backup_path}")
    except Exception as e:
        state.logger.error(f"❌ Migration Error: {e}")

def load_locations_list():
    """Loads location configurations from the JSON file."""
    _ensure_json_migration()
    
    if not os.path.exists(JSON_FILE): 
        return []
        
    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Ensure we always return a list
            if isinstance(data, list):
                return data
            return []
    except Exception as e: 
        state.logger.error(f"JSON Read Error: {e}")
    return []

def save_locations_list(new_list):
    """Saves location configurations to the JSON file."""
    if not new_list: return
    try:
        with open(JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(new_list, f, indent=4)
        state.logger.info("💾 Locations JSON updated")
    except Exception as e: 
        state.logger.error(f"JSON Write Error: {e}")
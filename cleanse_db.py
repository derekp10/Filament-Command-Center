import os
import sqlite3
import json

def fix_spoolman_db(db_path):
    print(f"Opening Database: {db_path}")
    if not os.path.exists(db_path):
        print("Database not found!")
        return
        
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # 1. FIX WEIGHT REJECTIONS
    # Ensure used_weight never exceeds initial_weight
    print("\n--- Fixing Over-Extruded Weights ---")
    cur.execute("SELECT id, used_weight, initial_weight FROM spool WHERE used_weight > initial_weight")
    over_weight_spools = cur.fetchall()
    
    if over_weight_spools:
        for s in over_weight_spools:
            spool_id, used, initial = s
            # Cap used_weight to initial_weight
            print(f"Capping Spool {spool_id}: used_weight {used}g -> {initial}g")
            cur.execute("UPDATE spool SET used_weight = ? WHERE id = ?", (initial, spool_id))
    else:
        print("No over-extruded spools found.")
        
    # 2. CLEANSE STRINGIFIED EXTRA FIELDS
    # Since Spoolman evaluates fields natively, double-encoded strings (e.g., "\"False\"" or "\"Choice\"")
    # may trigger schema mismatch panics in the UI or backend validation depending on the field type.
    
    def cleanse_table(table_name, id_col):
        print(f"\n--- Cleansing {table_name} ---")
        cur.execute(f"SELECT {id_col}, key, value FROM {table_name}")
        rows = cur.fetchall()
        
        updates = 0
        for r in rows:
            record_id, key, val_str = r
            original = val_str
            clean_str = val_str
            
            try:
                # If it perfectly parses as a string, check if it's an improperly nested string
                parsed = json.loads(val_str)
                
                if isinstance(parsed, str):
                    # We have a string. Does it look like a stringified boolean?
                    clean = parsed.strip()
                    if clean.lower() == 'true':
                        clean_str = 'true' # Native json boolean
                    elif clean.lower() == 'false':
                        clean_str = 'false' # Native json boolean
                    else:
                        # For Custom Choices, Spoolman perfectly deserializes "NFC Plastic" if stored as JSON string.
                        # It is structurally correct to keep it as json.dumps("NFC Plastic"). 
                        pass
                
                # If we made a change, apply it to the DB
                if clean_str != original:
                    cur.execute(f"UPDATE {table_name} SET value = ? WHERE {id_col} = ? AND key = ?", 
                                (clean_str, record_id, key))
                    updates += 1
                    print(f"Cleansed {table_name} ID {record_id} key '{key}': {original} -> {clean_str}")
                    
            except Exception as e:
                # Raw unparseable fields like "NFC Plastic" without quotes
                pass
                
        print(f"Fixed {updates} corrupted generic values in {table_name}.")

    cleanse_table("spool_field", "spool_id")
    cleanse_table("filament_field", "filament_id")
    cleanse_table("vendor_field", "vendor_id")
    
    conn.commit()
    conn.close()
    print("\n✅ Database Cleansing Complete!")

if __name__ == "__main__":
    fix_spoolman_db(r"\\TRUENAS\App_Data\Spoolman\SPOOLMAN_DIR_DATA\spoolman.db")

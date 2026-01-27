import requests
import sys

# --- CONFIGURATION ---
# Ensure this matches your config.json!
SPOOLMAN_IP = "http://192.168.1.29:7912"

def create_field(entity_type, key, name, field_type, choices=None, multi=False):
    # Payload now only needs the definition, not the key (since key is in URL)
    payload = {
        "name": name,
        "type": field_type,
        "multi_choice": multi
    }
    if choices:
        payload["choices"] = sorted(list(set(choices)))

    print(f"Creating {entity_type} field: {name} ({key})...")
    
    # URL CHANGED: Added /{key} to the end
    url = f"{SPOOLMAN_IP}/api/v1/field/{entity_type}/{key}"
    
    try:
        # We use POST to create/update. 
        # If POST fails with 405, it might be that we need to PUT or just use the correct endpoint.
        # Spoolman docs say: POST /api/v1/field/{entity_type}/{key} to Create/Update
        resp = requests.post(url, json=payload)
        
        if resp.status_code == 200:
            print("✅ Created/Updated.")
        elif resp.status_code == 201:
            print("✅ Created.")
        elif resp.status_code == 400 and "already exists" in resp.text:
            print("⚠️ Already exists (Skipping).")
        else:
            print(f"❌ Error {resp.status_code}: {resp.text}")
            
    except Exception as e:
        print(f"❌ Connection Error: {e}")

# --- SETUP SPOOL FIELDS ---
print("\n--- Setting up Spool Fields ---")

# 1. The Critical Field for Inventory Hub
create_field("spool", "physical_source", "Physical Source", "text")

# 2. (Optional) Re-run other fields if needed, or comment them out
# create_field("filament", "your_other_field", "DisplayName", "text")

print("\n🎉 Field Setup Complete!")
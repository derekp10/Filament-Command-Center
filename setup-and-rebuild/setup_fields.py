import requests
import sys

# --- CONFIGURATION ---
SPOOLMAN_IP = "http://192.168.1.29:7912"

def create_field(entity_type, key, name, f_type, choices=None, multi=False):
    # FIX: Changed "type" to "field_type" to match Spoolman API requirement
    payload = {
        "name": name,
        "field_type": f_type, 
        "multi_choice": multi
    }
    if choices:
        payload["choices"] = sorted(list(set(choices)))

    print(f"Creating {entity_type} field: {name} ({key})...")
    
    # URL: /api/v1/field/{entity}/{key}
    url = f"{SPOOLMAN_IP}/api/v1/field/{entity_type}/{key}"
    
    try:
        resp = requests.post(url, json=payload)
        
        if resp.status_code == 200:
            print("✅ Created/Updated.")
        elif resp.status_code == 201:
            print("✅ Created.")
        elif resp.status_code == 400 and "already exists" in resp.text:
            # If it exists but we need to ensure structure, we might try PUT
            print("⚠️ Already exists.")
        else:
            print(f"❌ Error {resp.status_code}: {resp.text}")
            
    except Exception as e:
        print(f"❌ Connection Error: {e}")

# --- SETUP SPOOL FIELDS ---
print("\n--- Setting up Spool Fields ---")

# 1. The Critical Field for Inventory Hub
create_field("spool", "physical_source", "Physical Source", "text")

print("\n🎉 Field Setup Complete!")
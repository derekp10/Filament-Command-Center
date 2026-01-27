import requests
import sys

SPOOLMAN_IP = "http://192.168.1.29:7912"

def create_field(entity_type, key, name, field_type, choices=None, multi=False):
    payload = {
        "key": key,
        "name": name,
        "type": field_type,
        "multi_choice": multi
    }
    if choices:
        payload["choices"] = sorted(list(set(choices)))

    print(f"Creating {entity_type} field: {name} ({key})...")
    try:
        resp = requests.post(f"{SPOOLMAN_IP}/api/v1/field/{entity_type}", json=payload)
        if resp.status_code == 200:
            print("✅ Created.")
        elif resp.status_code == 400 and "already exists" in resp.text:
            print("⚠️ Already exists (Skipping).")
        else:
            print(f"❌ Error {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"❌ Connection Error: {e}")

# --- SETUP SPOOL FIELDS ---
print("\n--- Setting up Spool Fields ---")
create_field("spool", "physical_source", "Physical Source", "text")

print("\n🎉 Field Setup Complete!")
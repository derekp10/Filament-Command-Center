import requests
import json
import sys
import os

# --- CONFIG ---
# CORRECT IP ADDRESS
SPOOLMAN_IP = "http://192.168.1.29:7912"

def inspect_field(key):
    print(f"\n🔍 Inspecting field '{key}' on {SPOOLMAN_IP}...")
    try:
        resp = requests.get(f"{SPOOLMAN_IP}/api/v1/field/spool", timeout=5)
        if resp.ok:
            fields = resp.json()
            found = next((f for f in fields if f['key'] == key), None)
            if found:
                print(f"   ✅ Found Definition: {json.dumps(found, indent=2)}")
                return found
            else:
                print("   ❌ Field NOT FOUND in database.")
                return None
        else:
            print(f"   ❌ Failed to fetch fields: {resp.status_code}")
            return None
    except Exception as e:
        print(f"   ❌ Connection Error: {e}")
        return None

def nuke_and_pave(key, name, f_type):
    print(f"\n💥 Nuking and Paving '{key}'...")
    
    # 1. DELETE
    try:
        print(f"   1️⃣  Deleting existing field...")
        del_resp = requests.delete(f"{SPOOLMAN_IP}/api/v1/field/spool/{key}", timeout=5)
        
        if del_resp.status_code in [200, 204]:
            print(f"      ✅ Delete Successful")
        elif del_resp.status_code == 404:
            print("      ℹ️  Field was already gone.")
        else:
            print(f"      ⚠️  Delete status: {del_resp.status_code} {del_resp.text}")
    except Exception as e:
        print(f"      ❌ Delete Exception: {e}")

    # 2. CREATE
    print(f"   2️⃣  Creating new field: {name} ({f_type})...")
    
    # FIX: Only include multi_choice if it is a choice field
    payload = {"name": name, "field_type": f_type}
    if f_type == "choice":
        payload["multi_choice"] = False
        
    try:
        create_resp = requests.post(f"{SPOOLMAN_IP}/api/v1/field/spool/{key}", json=payload, timeout=5)
        if create_resp.status_code in [200, 201]:
            print(f"      ✅ Creation Successful!")
        else:
            print(f"      ❌ Creation Failed: {create_resp.status_code} {create_resp.text}")
    except Exception as e:
        print(f"      ❌ Create Exception: {e}")

if __name__ == "__main__":
    # INSPECT BEFORE
    existing = inspect_field("container_slot")
    
    # REPAIR (Force it to be Text)
    nuke_and_pave("container_slot", "Container / MMU Slot", "text")
    
    # VERIFY AFTER
    print("\n🧐 Verifying...")
    final = inspect_field("container_slot")
    
    if final and final.get('field_type') == 'text':
        print("\n🎉 SUCCESS: 'container_slot' is confirmed as TEXT.")
    else:
        print("\n💥 FAILURE: Field is incorrect or missing.")
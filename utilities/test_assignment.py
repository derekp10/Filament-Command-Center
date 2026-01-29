import requests
import json
import os
import sys

# --- SETUP ---
# Attempt to find config.json
current_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(current_dir, '..', 'inventory-hub', 'config.json')

SPOOLMAN_IP = "http://192.168.1.29:7912" # Default
if os.path.exists(config_path):
    try:
        with open(config_path, 'r') as f:
            cfg = json.load(f)
            SPOOLMAN_IP = f"http://{cfg.get('server_ip')}:{cfg.get('spoolman_port')}"
    except: pass

print(f"🦝 Connecting to Spoolman at {SPOOLMAN_IP}")

# --- TEST 1: PURE STRING ASSIGNMENT ---
SPOOL_ID = 63 # We'll try to update Spool 63. Change if needed.

print(f"\n🧪 TEST 1: Updating Spool {SPOOL_ID} | container_slot = '1' (String)")
payload = {
    "extra": {
        "container_slot": "1"
    }
}

try:
    resp = requests.patch(f"{SPOOLMAN_IP}/api/v1/spool/{SPOOL_ID}", json=payload)
    
    if resp.status_code == 200:
        print("   ✅ SUCCESS! The field works in isolation.")
        print("   👉 CONCLUSION: The error is likely caused by the CORRUPT 'spool_type' data (double quotes) in the full payload.")
    else:
        print(f"   ❌ FAILED: {resp.status_code}")
        print(f"   MSG: {resp.text}")
        print("   👉 CONCLUSION: The field definition itself is broken/cached.")

except Exception as e:
    print(f"   ❌ CRITICAL ERROR: {e}")

# --- TEST 2: CLEANING CORRUPT DATA ---
print(f"\n🧪 TEST 2: Updating Spool {SPOOL_ID} | Cleaning 'spool_type' + 'container_slot'")
payload_clean = {
    "extra": {
        "spool_type": "Cardboard", # Clean string, no extra quotes
        "container_slot": "1"
    }
}

try:
    resp = requests.patch(f"{SPOOLMAN_IP}/api/v1/spool/{SPOOL_ID}", json=payload_clean)
    if resp.status_code == 200:
        print("   ✅ SUCCESS with clean spool_type!")
    else:
        print(f"   ❌ FAILED with clean spool_type: {resp.text}")

except Exception as e:
    print(f"   ❌ CRITICAL ERROR: {e}")
"""A repair tool (January 2026): rebuild the `container_slot` spool field as a text field.

WARNING: this script DELETES the `container_slot` spool field and creates it again. Deleting a field
wipes that extra on EVERY spool, so every spool loses its slot (CLAUDE.md: "Don't add
force_reset=True to setup_fields.py lightly"). The field has been text since Group 54.4, whose
migration keeps the values (setup_fields.migrate_container_slot_to_text), so there is no reason left
to run this one.

It writes only to dev Spoolman (the repo-root config.json's server_ip and spoolman_port: 7913 on
this PC, else http://192.168.1.29:7913) and refuses prod Spoolman before anything is sent: port 7912
on any host name, or one of prod's addresses (project_config.py). It used to name prod.
"""
import requests
import json

import project_config


def inspect_field(key, spoolman_url=None):
    spoolman_url = spoolman_url or project_config.dev_spoolman_url()
    print(f"\n🔍 Inspecting field '{key}' on {spoolman_url}...")
    try:
        resp = requests.get(f"{spoolman_url}/api/v1/field/spool", timeout=5)
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


def nuke_and_pave(key, name, f_type, spoolman_url=None):
    spoolman_url = spoolman_url or project_config.dev_spoolman_url()
    project_config.refuse_prod_spoolman(spoolman_url)      # before the DELETE
    print(f"\n💥 Nuking and Paving '{key}' on {spoolman_url}...")

    # 1. DELETE
    try:
        print(f"   1️⃣  Deleting existing field...")
        del_resp = requests.delete(f"{spoolman_url}/api/v1/field/spool/{key}", timeout=5)

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
        create_resp = requests.post(f"{spoolman_url}/api/v1/field/spool/{key}", json=payload, timeout=5)
        if create_resp.status_code in [200, 201]:
            print(f"      ✅ Creation Successful!")
        else:
            print(f"      ❌ Creation Failed: {create_resp.status_code} {create_resp.text}")
    except Exception as e:
        print(f"      ❌ Create Exception: {e}")


if __name__ == "__main__":
    SPOOLMAN_IP = project_config.dev_spoolman_url()
    project_config.refuse_prod_spoolman(SPOOLMAN_IP)       # before the first request

    # INSPECT BEFORE
    existing = inspect_field("container_slot", SPOOLMAN_IP)

    # REPAIR (Force it to be Text)
    nuke_and_pave("container_slot", "Container / MMU Slot", "text", SPOOLMAN_IP)

    # VERIFY AFTER
    print("\n🧐 Verifying...")
    final = inspect_field("container_slot", SPOOLMAN_IP)

    if final and final.get('field_type') == 'text':
        print("\n🎉 SUCCESS: 'container_slot' is confirmed as TEXT.")
    else:
        print("\n💥 FAILURE: Field is incorrect or missing.")

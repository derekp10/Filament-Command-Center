"""WARNING: this script WRITES to Spoolman. It PATCHes spool 63's extras twice (container_slot "1",
then spool_type "Cardboard" with container_slot "1"). Since 2026-11-13 dev's spool 63 is a copy of
a real spool, so a run gives that copy a slot-1 claim: put it back afterwards (reset_dev.py puts
dev's spools back to its snapshot).

It writes only to dev Spoolman. The address comes from the repo-root config.json (server_ip and
spoolman_port: 7913 on this PC), else http://192.168.1.29:7913, and prod Spoolman is refused before
anything is sent: port 7912 on any host name, or one of prod's addresses (project_config.py).

A manual probe (January 2026): does Spoolman take a plain string for the container_slot extra? That
was settled when container_slot became a text field (Group 54.4), so there is little reason to run it.

Run it by hand only:  python utilities/test_assignment.py
Everything it does sits in main(), run only under `if __name__ == "__main__":` (2026-11-13). Its
name matches pytest's test_*.py, so a `pytest .` from the repo root would collect it, and its
module-level PATCHes used to run at import, against prod. Importing it sends nothing; the root
pytest.ini's norecursedirs also keeps pytest out of utilities/.
"""
import requests

import project_config


def main(spoolman_url=None):
    # --- SETUP ---
    # Dev Spoolman (the repo-root config.json), never prod: refused before any request.
    SPOOLMAN_IP = spoolman_url or project_config.dev_spoolman_url()
    project_config.refuse_prod_spoolman(SPOOLMAN_IP)

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


if __name__ == "__main__":
    main()

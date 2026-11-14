"""A manual probe (January 2026): does Spoolman take a raw JSON list for a choice field's choices?

WARNING: this script WRITES to Spoolman. probe_create_field() POSTs a new filament extra field,
`debug_test_field`, which stays until someone deletes it. It writes only to dev Spoolman (the
repo-root config.json's server_ip and spoolman_port: 7913 on this PC, else http://192.168.1.29:7913)
and refuses prod Spoolman before anything is sent: port 7912 on any host name, or one of prod's
addresses (project_config.py).

Run it by hand only:  python utilities/debug_test.py
Until 2026-11-13 the probe was named test_create_field(), and prod was its address: pytest collects a
test_* function from any file named on its command line, so `pytest utilities/debug_test.py` would
have POSTed the field to prod.
"""
import requests

import project_config


def probe_create_field(spoolman_url=None):
    spoolman_url = spoolman_url or project_config.dev_spoolman_url()
    project_config.refuse_prod_spoolman(spoolman_url)      # before any request
    url = f"{spoolman_url}/api/v1/field/filament/debug_test_field"

    # WE ARE SENDING A RAW PYTHON LIST HERE.
    # NO json.dumps()
    choices_list = ["Option A", "Option B", "Option C"]

    payload = {
        "name": "Debug Test Field",
        "field_type": "choice",
        "multi_choice": True,
        "choices": choices_list
    }

    print(f"Sending payload to {url}...")
    try:
        # requests.post(json=...) automatically formats it as JSON.
        resp = requests.post(url, json=payload)

        if resp.status_code in [200, 201]:
            print("\n✅ SUCCESS! Spoolman accepted the Raw List.")
            print("We have proven that json.dumps() IS NOT NEEDED.")
        else:
            print(f"\n❌ FAILED with code {resp.status_code}")
            print(f"Response: {resp.text}")

    except Exception as e:
        print(f"Connection error: {e}")


if __name__ == "__main__":
    probe_create_field()

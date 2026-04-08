import requests
import json

base_url = "http://192.168.1.29:7913/api/v1/filament"

payload = {
    "name": "Live API Multi To Single Test",
    "material": "PLA",
    "vendor_id": 1, 
    "weight": 1000,
    "diameter": 1.75,
    "density": 1.24,
    "multi_color_hexes": "FF0000,00FF00",
    "multi_color_direction": "coaxial"
}

r = requests.post(base_url, json=payload)
print("Create Status:", r.status_code)

if r.status_code == 200:
    fil_id = r.json().get('id')
    
    # Try reverting to single color
    patch_payload = {
        "color_hex": "FF0000"
    }
    patch_r = requests.patch(f"{base_url}/{fil_id}", json=patch_payload)
    print("Patch Status:", patch_r.status_code)
    print("Patch Response:", patch_r.text)

    # Cleanup
    requests.delete(f"{base_url}/{fil_id}")

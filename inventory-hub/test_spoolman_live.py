import requests

base_url = "http://192.168.1.29:7913/api/v1/filament"

payload = {
    "name": "Live API Multi-Color Test",
    "material": "PLA",
    "vendor_id": 1, 
    "weight": 1000,
    "diameter": 1.75,
    "density": 1.24,
    "multi_color_hexes": "FF0000,00FF00,0000FF",
    "multi_color_direction": "coaxial"
}

r = requests.post(base_url, json=payload)
print("Create Status:", r.status_code)
print("Create Response:", r.text)

if r.status_code == 200:
    data = r.json()
    fil_id = data.get('id')
    print("Successfully saved! ID:", fil_id)
    
    # Cleanup
    del_req = requests.delete(f"{base_url}/{fil_id}")
    print("Delete Status:", del_req.status_code)
else:
    print("FAILED TO SAVE TO SPOOLMAN!!")

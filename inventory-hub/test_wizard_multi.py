import requests

payload = {
    "filament_id": None,
    "filament_data": {
        "name": "SlicerProfileTest",
        "material": "PLA",
        "weight": 1000,
        "spool_weight": 200,
        "diameter": 1.75,
        "density": 1.24,
        "color_hex": "FF0000",
        "extra": {}
    },
    "spool_data": {
        "used_weight": 0,
        "empty_weight": 200,
        "location": "",
        "comment": "",
        "extra": {}
    },
    "quantity": 1
}

r = requests.post("http://localhost:8000/api/create_inventory_wizard", json=payload)
print("Status Code:", r.status_code)
print("Response:", r.text)


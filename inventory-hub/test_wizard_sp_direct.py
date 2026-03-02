import requests, json

payload = {
    "name": "MultiChoiceDirectTest2",
    "material": "PLA",
    "weight": 1000,
    "spool_weight": 200,
    "diameter": 1.75,
    "density": 1.24,
    "color_hex": "FF0000",
    "extra": {
        "filament_attributes": '["Carbon Fiber", "Matte"]'
    }
}

r = requests.post("http://localhost:8000/api/spoolman/filament", json=payload)
print("Status Code:", r.status_code)
print("Response:", r.text)

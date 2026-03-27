import requests
import json

url = 'http://127.0.0.1:7912/api/v1/spool/142'

def test(payload):
    print(f"Testing: {payload}")
    r = requests.patch(url, json=payload)
    print(r.status_code, r.text)

test({'extra': {'spool_type': '"NFC Plastic"'}})
test({'extra': {'is_refill': 'false'}})
test({'used_weight': 0})

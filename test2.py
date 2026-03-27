import sys
sys.path.append('d:/My Documents/Documents/3D Printing/Filament Command Center/inventory-hub')
import config_loader
import requests

try:
    sm_url, _ = config_loader.get_api_urls()
    url = f"{sm_url}/api/v1/spool/142"

    def test(payload):
        print(f"Testing: {payload}")
        r = requests.patch(url, json=payload)
        print(r.status_code, r.text)

    test({'extra': {'is_refill': False}})
    test({'extra': {'is_refill': 'false'}})
    test({'extra': {'spool_type': 'NFC Plastic'}})
    test({'extra': {'spool_type': '"NFC Plastic"'}})
except Exception as e:
    print(e)

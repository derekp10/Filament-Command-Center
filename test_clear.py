import sys
import json
sys.path.append('d:/My Documents/Documents/3D Printing/Filament Command Center/inventory-hub')
import config_loader
import requests

url, _ = config_loader.get_api_urls()
target = f'{url}/api/v1/spool/142'
r = requests.patch(target, json={'extra': {'spool_type': json.dumps("")}})
print(r.status_code, r.text)

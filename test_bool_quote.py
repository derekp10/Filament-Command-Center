import sys
import json
import requests
sys.path.append('d:/My Documents/Documents/3D Printing/Filament Command Center/inventory-hub')
import config_loader

url, _ = config_loader.get_api_urls()
target = f'{url}/api/v1/spool/1'
# passing a string containing double-quotes around the boolean keyword
r = requests.patch(target, json={'extra': {'is_refill': '"false"'}})
print(r.status_code, r.text)

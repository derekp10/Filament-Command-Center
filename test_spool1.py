import sys
sys.path.append('d:/My Documents/Documents/3D Printing/Filament Command Center/inventory-hub')
import config_loader
import requests

url, _ = config_loader.get_api_urls()
target = f'{url}/api/v1/spool/1'

# Test 1: Spool Type as stringified JSON choice
r1 = requests.patch(target, json={'extra': {'spool_type': '"Cardboard"'}})
print('R1 (Double Quotes):', r1.status_code, r1.text)

# Test 2: Spool Type as naked string
r2 = requests.patch(target, json={'extra': {'spool_type': 'Cardboard'}})
print('R2 (Naked String):', r2.status_code, r2.text)

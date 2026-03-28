import sys
import json
import requests
sys.path.append('d:/My Documents/Documents/3D Printing/Filament Command Center/inventory-hub')
import config_loader

url, _ = config_loader.get_api_urls()
target = f'{url}/api/v1/field/spool/spool_type'

payload = {
    'name': 'Spool Type',
    'field_type': 'choice',
    'multi_choice': False,
    'choices': ['Cardboard', 'NFC Plastic', 'Plastic', '"Cardboard"', '"NFC Plastic"', '"Plastic"']
}

print(payload)
r2 = requests.post(target, json=payload)
print('STATUS:', r2.status_code, 'TEXT:', r2.text)

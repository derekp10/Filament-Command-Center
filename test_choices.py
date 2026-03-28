import sys
import json
import requests
sys.path.append('d:/My Documents/Documents/3D Printing/Filament Command Center/inventory-hub')
import config_loader

url, _ = config_loader.get_api_urls()
target = f'{url}/api/v1/field/spool'

r = requests.get(target)
fields = r.json()

field = None
for f in fields:
    if f.get('key') == 'spool_type':
        field = f
        break

if not field:
    print("No spool_type found")
    sys.exit(1)

new_choices = field['choices'].copy()
for c in field['choices']:
    # Add escaped version so Spoolman validator doesn't crash on older DB rows
    quoted = f'"{c}"'
    if quoted not in new_choices:
        new_choices.append(quoted)

payload = {
    'name': field['name'],
    'field_type': field['field_type'],
    'choices': new_choices
}

print("Patching spool_type choices:")
print(payload)

post_target = f'{url}/api/v1/field/spool/spool_type'
r2 = requests.post(post_target, json=payload)
print(r2.status_code, r2.text)

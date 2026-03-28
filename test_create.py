import sys
sys.path.append('d:/My Documents/Documents/3D Printing/Filament Command Center/inventory-hub')
import spoolman_api

payload = {
    'filament_id': 1,
    'used_weight': 10,
    'spool_weight': 200,
    'archived': True,
    'location': 'CORE1',
    'comment': '',
    'extra': {'is_refill': False, 'spool_type': 'NFC Plastic'}
}
sp = spoolman_api.create_spool(payload)
print('Created Spool:', sp['id'] if sp else 'Failed')
if sp:
    print('Updating:', spoolman_api.update_spool(sp['id'], {'archived': False}))

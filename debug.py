import sys
sys.path.append('d:/My Documents/Documents/3D Printing/Filament Command Center/inventory-hub')
import spoolman_api

original_spool = spoolman_api.get_spool(142)

spool_data = {
    'used_weight': 1142.0,
    'empty_weight': 277.0,
    'initial_weight': 865.0,
    'location': 'CORE1-M0',
    'comment': '',
    'archived': True,
    'extra': {
        'is_refill': False,
        'spool_type': 'NFC Plastic',
        'needs_label_print': False,
        'product_url': 'https://prusament.com/spool/?spoolId=842cd281b0',
        'physical_source': 'CR-MDB-1',
        'physical_source_slot': '1',
        'container_slot': ''
    }
}

dirty_spool_data = {}
for k, v in spool_data.items():
    if k == 'empty_weight' and v != original_spool.get('spool_weight'):
        dirty_spool_data['spool_weight'] = v
    elif k == 'extra':
        original_extra = original_spool.get('extra', {})
        dirty_extra = {}
        for ek, ev in v.items():
            if str(ev) != str(original_extra.get(ek)):
                dirty_extra[ek] = ev
        if dirty_extra:
            dirty_spool_data['extra'] = dirty_extra
    elif k != 'empty_weight' and k in original_spool and original_spool[k] != v:
        dirty_spool_data[k] = v
    elif k not in original_spool:
        dirty_spool_data[k] = v

print('RESULT:', dirty_spool_data)

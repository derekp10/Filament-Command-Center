import requests
import json

url = 'http://127.0.0.1:8000/api/edit_spool_wizard'

payload = {
    'spool_id': 142,
    'spool_data': {
        'used_weight': 1142.0,
        'empty_weight': 277.0,
        'initial_weight': 865.0,
        'location': 'CORE1-M0',
        'comment': '',
        'archived': True,
        'extra': {'is_refill': False, 'spool_type': '"NFC Plastic"', 'needs_label_print': False}
    }
}
r = requests.post(url, json=payload)
print(r.status_code, r.text)

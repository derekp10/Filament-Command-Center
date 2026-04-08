import sys
import os

sys.path.insert(0, os.path.abspath('d:/My Documents/Documents/3D Printing/Filament Command Center/inventory-hub'))

import spoolman_api
import logic
import json

spools_all = spoolman_api.get_spools_at_location_detailed("LR-MDB-1")
target_id = spools_all[0]['id'] if spools_all else 1

print(f"Setting spool {target_id} to LR-MDB-1...")
spoolman_api.update_spool(target_id, {"location": "LR-MDB-1", "extra": {"container_slot": "1"}})

print("Assigning to XL-1...")
logic.perform_smart_move("XL-1", [target_id])

print("Getting spools at LR-MDB-1...")
spools = spoolman_api.get_spools_at_location_detailed("LR-MDB-1")
for s in spools:
    if str(s['id']) == str(target_id):
        print("FOUND AS GHOST!")
        print(json.dumps(s, indent=2))
        break
else:
    print("NOT FOUND IN DRYER!")

print("Spool Details:")
print(json.dumps(spoolman_api.get_spool(target_id), indent=2))

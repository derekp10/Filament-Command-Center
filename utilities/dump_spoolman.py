# dump_spoolman.py
import csv
import requests

SPOOLMAN_IP = "http://192.168.1.29:7912"

resp = requests.get(f"{SPOOLMAN_IP}/api/v1/filament")
data = resp.json()

keys = ["id", "vendor.name", "name", "material", "extra.sheet_roid", "extra.label_printed", "extra.qr_generated"]

with open("spoolman_dump.csv", "w", newline='') as f:
    writer = csv.writer(f)
    writer.writerow(keys)
    
    for item in data:
        row = []
        row.append(item.get("id"))
        row.append(item.get("vendor", {}).get("name"))
        row.append(item.get("name"))
        row.append(item.get("material"))
        extra = item.get("extra", {}) or {}
        row.append(extra.get("sheet_roid"))
        row.append(extra.get("label_printed"))
        row.append(extra.get("qr_generated"))
        writer.writerow(row)

print("Dumped to spoolman_dump.csv")
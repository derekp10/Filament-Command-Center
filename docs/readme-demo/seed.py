"""Seed the README demo's own Spoolman (127.0.0.1:7999) with made-up spools. Demo only."""
import json
import sys

import requests

B = "http://127.0.0.1:7999/api/v1"
assert "7999" in B  # never anything but the demo's Spoolman


def post(path, body):
    r = requests.post(B + path, json=body, timeout=15)
    if not r.ok:
        sys.exit(f"{path}: HTTP {r.status_code} {r.text[:300]}")
    return r.json()


def text(v):
    return json.dumps(str(v))   # a text extra goes out JSON-encoded once (SPOOLMAN_API_RULES.md, rule 2)


if requests.get(B + "/spool", timeout=10).json():
    sys.exit("the demo Spoolman already has spools: not seeding twice")

vendors = {}
for name, empty in [("Acme Filament", 210), ("Northwind Plastics", 180), ("Bluebird 3D", 160)]:
    vendors[name] = post("/vendor", {"name": name, "empty_spool_weight": empty})["id"]

FILAMENTS = [
    # key, vendor, name, material, hex, density, nozzle, bed, price
    ("black", "Acme Filament", "Galaxy Black", "PLA", "1b1b1f", 1.24, 215, 60, 22.0),
    ("red", "Acme Filament", "Signal Red", "PLA", "d7263d", 1.24, 215, 60, 22.0),
    ("blue", "Acme Filament", "Ocean Blue", "PETG", "1e6fd9", 1.27, 240, 80, 24.0),
    ("white", "Acme Filament", "Arctic White", "PLA", "f5f5f5", 1.24, 215, 60, 22.0),
    ("gold", "Northwind Plastics", "Silk Gold", "PLA", "d4a017", 1.24, 220, 60, 27.0),
    ("clear", "Northwind Plastics", "Clear", "PETG", "dfe7ec", 1.27, 240, 80, 25.0),
    ("grey", "Northwind Plastics", "Light Grey", "ASA", "b9bec4", 1.07, 260, 100, 29.0),
    ("sky", "Northwind Plastics", "Sky Blue", "PLA", "5bc0eb", 1.24, 215, 60, 23.0),
    ("green", "Bluebird 3D", "Leaf Green", "PLA", "3fa34d", 1.24, 210, 60, 20.0),
    ("orange", "Bluebird 3D", "Sunset Orange", "PLA", "f28c28", 1.24, 210, 60, 20.0),
    ("lime", "Bluebird 3D", "Lime", "TPU", "a4d233", 1.21, 225, 50, 31.0),
    ("ruby", "Bluebird 3D", "Ruby", "PETG", "9b111e", 1.27, 235, 80, 24.0),
]
fil = {}
for key, vendor, name, material, hexc, density, nozzle, bed, price in FILAMENTS:
    fil[key] = post("/filament", {
        "name": name, "vendor_id": vendors[vendor], "material": material, "color_hex": hexc,
        "density": density, "diameter": 1.75, "weight": 1000 if key != "lime" else 500,
        "settings_extruder_temp": nozzle, "settings_bed_temp": bed, "price": price,
    })["id"]

SPOOLS = [
    # filament, used g, location, extras
    ("black", 380, "HEAD-1", {"physical_source": "DRYBOX-1", "physical_source_slot": "1"}),
    ("red", 150, "HEAD-2", {"physical_source": "DRYBOX-1", "physical_source_slot": "2"}),
    ("blue", 720, "HEAD-3", {"physical_source": "DRYBOX-1", "physical_source_slot": "3"}),
    ("gold", 90, "DRYBOX-1", {"container_slot": "4"}),
    ("green", 300, "DRYBOX-2", {"container_slot": "1"}),
    ("orange", 510, "HEAD-5", {}),
    ("clear", 0, "SHELF-1", {}),
    ("grey", 640, "SHELF-1", {}),
    ("white", 50, "SHELF-1", {}),
    ("lime", 0, "SHELF-1", {}),
    ("black", 0, "SHELF-2", {}),
    ("black", 0, "SHELF-2", {}),
    ("red", 820, "SHELF-2", {}),
    ("ruby", 880, "SHELF-2", {}),
    ("orange", 960, "BIN-1", {}),
    ("white", 0, "", {}),
]
made = []
for key, used, loc, extra in SPOOLS:
    body = {"filament_id": fil[key], "initial_weight": 500 if key == "lime" else 1000,
            "used_weight": used, "location": loc}
    if extra:
        body["extra"] = {k: text(v) for k, v in extra.items()}
    made.append(post("/spool", body)["id"])

# One filament out of stock: its only spool used up and archived.
sky = post("/spool", {"filament_id": fil["sky"], "initial_weight": 1000, "used_weight": 1000,
                      "location": "", "archived": True})["id"]
print("vendors", len(vendors), "filaments", len(fil), "spools", made + [sky])

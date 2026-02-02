import csv
import os
import state

CSV_FILE = '3D Print Supplies - Locations.csv'

def load_locations_list():
    locs = []
    if not os.path.exists(CSV_FILE): return []
    try:
        with open(CSV_FILE, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('LocationID'): locs.append(row)
    except Exception as e: 
        state.logger.error(f"CSV Read Error: {e}")
    return locs

def save_locations_list(new_list):
    if not new_list: return
    fieldnames = ['LocationID', 'Name', 'Type', 'Location', 'Device Identifier', 'Device Type', 'Order', 'Row', 'Max Spools', 'Label Printed']
    try:
        with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(new_list)
        state.logger.info("💾 Locations CSV updated")
    except Exception as e: 
        state.logger.error(f"CSV Write Error: {e}")
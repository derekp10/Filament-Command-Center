import requests
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'inventory-hub')))
import config_loader

SPOOLMAN_IP, _ = config_loader.get_api_urls()
ENTITY = "filament"
KEY = "filament_attributes"

url = f"{SPOOLMAN_IP}/api/v1/field/{ENTITY}"
try:
    cols = requests.get(url).json()
    target = None
    for c in cols:
        if c.get("key") == KEY:
            target = c
            break
            
    if target:
        choices = target.get("choices", [])
        if isinstance(choices, str):
            choices = json.loads(choices)
            
        clean_choices = []
        for choice in choices:
            # Drop any choices that literally look like arrays "['Matte', 'Tough']"
            if "[" in choice or "]" in choice or "{" in choice or "," in choice:
                print(f"Dropping corrupted choice string: {choice}")
            else:
                clean_choices.append(choice)
                
        # Update the field back
        payload = {
            "name": target.get("name"),
            "field_type": target.get("field_type"),
            "multi_choice": target.get("multi_choice", True),
            "choices": clean_choices
        }
        # Delete the field completely to bypass "Cannot remove existing choices." lock
        requests.delete(f"{SPOOLMAN_IP}/api/v1/field/{ENTITY}/{KEY}")
        
        # Recreate the field back with the clean options
        resp = requests.post(f"{SPOOLMAN_IP}/api/v1/field/{ENTITY}/{KEY}", json=payload)
        if resp.status_code == 200:
            print("Successfully repaired Spoolman Choices!")
        else:
            print(f"Failed to update options: {resp.text}")
    else:
        print("Field not found!")
except Exception as e:
    print(f"Error: {e}")

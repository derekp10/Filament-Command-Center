import json
import os
import sys
import state

# Logic to find the ROOT config.json (Go up one level)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')

def load_config():
    defaults = {
        "server_ip": "127.0.0.1", 
        "spoolman_port": 7912, 
        "filabridge_port": 5000,
        "sync_delay": 0.5, 
        "printer_map": {}, 
        "feeder_map": {}, 
        "dryer_slots": []
    }
    
    final_config = defaults.copy()
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f: 
                loaded = json.load(f)
                final_config.update(loaded)
        except Exception as e: 
            # Fallback for Docker or if file missing
            state.logger.error(f"Root Config Load Error: {e}")
    else:
        state.logger.warning(f"Root config.json not found at {CONFIG_FILE}")

    # Force Uppercase Keys for Printer Map
    if 'printer_map' in final_config:
        final_config['printer_map'] = {k.upper(): v for k, v in final_config['printer_map'].items()}
        
    return final_config

def get_api_urls():
    cfg = load_config()
    server_ip = cfg.get("server_ip")
    sm_url = f"http://{server_ip}:{cfg.get('spoolman_port')}"
    fb_url = f"http://{server_ip}:{cfg.get('filabridge_port')}/api"
    return sm_url, fb_url
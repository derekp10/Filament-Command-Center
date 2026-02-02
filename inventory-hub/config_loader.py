import json
import os
import state

CONFIG_FILE = 'config.json'

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
            with open(CONFIG_FILE, 'r') as f: 
                loaded = json.load(f)
                final_config.update(loaded)
        except Exception as e: 
            state.logger.error(f"Config Load Error: {e}")
            
    # Force Uppercase Keys for Printer Map lookups
    if 'printer_map' in final_config:
        final_config['printer_map'] = {k.upper(): v for k, v in final_config['printer_map'].items()}
        
    return final_config

# Helper to get base URLs quickly
def get_api_urls():
    cfg = load_config()
    server_ip = cfg.get("server_ip")
    sm_url = f"http://{server_ip}:{cfg.get('spoolman_port')}"
    fb_url = f"http://{server_ip}:{cfg.get('filabridge_port')}/api"
    return sm_url, fb_url
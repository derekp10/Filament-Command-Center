import json
import os
import sys

CONFIG_FILENAME = "config.json"

def load_config():
    """Locates and loads the global config.json file."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Walk up the directory tree looking for config.json
    while True:
        possible_path = os.path.join(current_dir, CONFIG_FILENAME)
        if os.path.exists(possible_path):
            try:
                with open(possible_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                    
                    # --- DYNAMIC HELPERS ---
                    # Automatically build URLs so scripts don't have to guess
                    if 'server_ip' in cfg and 'spoolman_port' in cfg:
                        cfg['spoolman_url'] = f"http://{cfg['server_ip']}:{cfg['spoolman_port']}"
                    
                    return cfg
            except json.JSONDecodeError as e:
                print(f"[CRITICAL] Config file found at {possible_path} but is invalid JSON: {e}")
                sys.exit(1)
        
        parent_dir = os.path.dirname(current_dir)
        if parent_dir == current_dir: break
        current_dir = parent_dir
    
    print(f"[CRITICAL] Could not find {CONFIG_FILENAME} in project root.")
    sys.exit(1)

def get(key, default=None):
    cfg = load_config()
    return cfg.get(key, default)
import json
import os
import sys
import state

# Logic to find the ROOT config.json (Go up one level)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_config_path():
    """Determines which config file to load based on Environment Variables."""
    env = os.environ.get('FLASK_ENV', '').lower()
    custom_env = os.environ.get('ENV', '').lower()
    
    # Priority: Explicit 'ENV' var > FLASK_ENV > Default
    if 'dev' in custom_env or 'dev' in env:
        target = os.path.join(BASE_DIR, 'config.dev.json')
        if os.path.exists(target):
            return target, "DEV"
    
    return os.path.join(BASE_DIR, 'config.json'), "PROD"

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
    config_file, mode = get_config_path()
    
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f: 
                loaded = json.load(f)
                final_config.update(loaded)

            current_mtime = str(os.path.getmtime(config_file))
            tracker_file = os.path.join(BASE_DIR, '.config_mtime')
            
            last_mtime = None
            if os.path.exists(tracker_file):
                try:
                    with open(tracker_file, 'r') as tf:
                        last_mtime = tf.read().strip()
                except:
                    pass
            
            # Log only if state logger is available AND we haven't logged this specific version recently
            if hasattr(state, 'logger'):
                if last_mtime != current_mtime:
                    if mode == "DEV":
                        state.logger.warning(f"⚠️ LOADED DEV CONFIG: {config_file}")
                    else:
                        state.logger.info(f"✅ Loaded Prod Config: {config_file}")
                    
                    try:
                        with open(tracker_file, 'w') as tf:
                            tf.write(current_mtime)
                    except:
                        pass

        except Exception as e: 
            if hasattr(state, 'logger'):
                state.logger.error(f"Config Load Error: {e}")
    else:
        if hasattr(state, 'logger'):
            state.logger.warning(f"Config file not found at {config_file}")

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
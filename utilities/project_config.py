import json
import os
import sys
import urllib.parse

CONFIG_FILENAME = "config.json"

# --- Spoolman addresses for the by-hand scripts that WRITE (2026-11-13) ---
# test_assignment.py, debug_test.py and repair_db_fields.py write to Spoolman. They default to dev
# (the repo-root config.json's server_ip and spoolman_port: 7913 on this PC) and refuse prod Spoolman
# before any request: port 7912 on any host name (an alias, or the port spelled '07912'), or one of
# prod's addresses. config.prod.json is prod's config: never read here.
PROD_SPOOLMAN_PORT = 7912
PROD_NETLOCS = frozenset({"192.168.1.29:7912", "truenas:7912", "truenas.local:7912"})
DEV_SPOOLMAN_DEFAULT = "http://192.168.1.29:7913"
REPO_CONFIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), CONFIG_FILENAME)


def dev_spoolman_url(config_path=None):
    """Dev Spoolman's address: the repo-root config.json's server_ip and spoolman_port, else
    DEV_SPOOLMAN_DEFAULT when that file is missing, unreadable or doesn't name them."""
    try:
        with open(config_path or REPO_CONFIG, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return DEV_SPOOLMAN_DEFAULT
    if isinstance(cfg, dict) and cfg.get("server_ip") and cfg.get("spoolman_port"):
        return "http://%s:%s" % (cfg["server_ip"], cfg["spoolman_port"])
    return DEV_SPOOLMAN_DEFAULT


def prod_spoolman_refusal(url):
    """Why `url` must get no write because it names prod Spoolman, or None. Read from its parsed
    parts, so another spelling of prod is still prod."""
    parts = urllib.parse.urlsplit(str(url))
    try:
        port = parts.port
    except ValueError:
        return "its port can't be read"
    if port == PROD_SPOOLMAN_PORT:
        return "port %d is prod Spoolman's, on any host name" % PROD_SPOOLMAN_PORT
    if parts.netloc.lower() in PROD_NETLOCS:
        return "it is one of prod Spoolman's addresses"
    return None


def refuse_prod_spoolman(url):
    """Exit 2, before any request, when `url` names prod Spoolman."""
    why = prod_spoolman_refusal(url)
    if why:
        print("REFUSED: %s names prod Spoolman (%s). This script writes to Spoolman, and never to prod; "
              "nothing was sent." % (url, why))
        sys.exit(2)

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
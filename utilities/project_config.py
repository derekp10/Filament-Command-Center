import json
import os
import sys

# Define the config filename
CONFIG_FILENAME = "config.json"

def load_config():
    """
    Locates and loads the global config.json file.
    Searches in the current directory, then moves up parent directories
    until it finds the file or hits the root.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Walk up the directory tree looking for config.json
    while True:
        possible_path = os.path.join(current_dir, CONFIG_FILENAME)
        if os.path.exists(possible_path):
            try:
                with open(possible_path, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                print(f"[CRITICAL] Config file found at {possible_path} but is invalid JSON: {e}")
                sys.exit(1)
        
        # Move up one level
        parent_dir = os.path.dirname(current_dir)
        if parent_dir == current_dir: # We hit the filesystem root
            break
        current_dir = parent_dir
    
    print(f"[CRITICAL] Could not find {CONFIG_FILENAME} in project root or parents.")
    print("Please copy config.json.example to config.json and fill in your details.")
    sys.exit(1)

# Helper to get specific values with defaults
def get(key, default=None):
    cfg = load_config()
    return cfg.get(key, default)
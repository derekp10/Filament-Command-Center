import logging
import sys
import time
from logging.handlers import RotatingFileHandler

# --- GLOBAL STATE ---
UNDO_STACK = []
RECENT_LOGS = []

# --- PERSISTENT STATE ---
# Stores the active Buffer and Queue for cross-window persistence
GLOBAL_BUFFER = []
GLOBAL_QUEUE = []

# --- AUDIT STATE ---
# Stores the current audit session
AUDIT_SESSION = {
    "active": False,
    "location_id": None,
    "expected_items": [], # List of Spool IDs supposed to be there
    "scanned_items": [],  # List of Spool IDs we actually found
    "rogue_items": []     # Spools we found that belong elsewhere
}

# --- LOGGING SETUP ---
logger = logging.getLogger("InventoryHub")
logger.setLevel(logging.INFO)

# Console Output
c_handler = logging.StreamHandler(sys.stdout)
c_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(c_handler)

# File Output
f_handler = RotatingFileHandler('hub.log', maxBytes=1000000, backupCount=5)
f_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(f_handler)

def add_log_entry(msg, category="INFO", color_hex=None):
    """Adds a log entry to the in-memory list and the system log."""
    timestamp = time.strftime("%H:%M:%S")
    
    # Visual Swatch for the UI log
    if color_hex:
        swatch = f'<span style="display:inline-block;width:24px;height:24px;border-radius:50%;background-color:#{color_hex};margin-right:10px;border:2px solid #fff;vertical-align:middle;"></span>'
        ui_msg = swatch + f'<span style="vertical-align:middle;">{msg}</span>'
    else:
        ui_msg = msg

    entry = {"time": timestamp, "msg": ui_msg, "type": category}
    RECENT_LOGS.insert(0, entry)
    if len(RECENT_LOGS) > 50: RECENT_LOGS.pop()
    
    # Standard Python Logging
    if category == "ERROR":
        logger.error(msg)
    elif category == "WARNING":
        logger.warning(msg)
    else:
        logger.info(msg)

def reset_audit():
    """Clears the current audit state."""
    global AUDIT_SESSION
    AUDIT_SESSION.update({
        "active": False,
        "location_id": None,
        "expected_items": [],
        "scanned_items": [],
        "rogue_items": []
    })
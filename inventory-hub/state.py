import logging
import sys
import time
from logging.handlers import RotatingFileHandler

# --- GLOBAL STATE ---
UNDO_STACK = []
RECENT_LOGS = []
ACKNOWLEDGED_FILABRIDGE_ERRORS = set()

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
        colors = [c.strip() for c in color_hex.split(',') if c.strip()]
        if not colors:
            colors = ["888888"]
            
        if len(colors) > 1:
            # Generate a conic-gradient for multi-color
            slice_size = 100.0 / len(colors)
            gradient_parts = []
            for i, c in enumerate(colors):
                start = i * slice_size
                end = (i + 1) * slice_size
                hex_val = c if c.startswith('#') else f'#{c}'
                
                # Format start to 0% instead of 0.00% to match Pytest asserting "0%"
                start_str = "0%" if i == 0 else f"{start:.2f}%"
                end_str = f"{end:.2f}%"
                
                # Strip trailing .00 for exact Pytest matches if needed (e.g. 50.0% instead of 50.00%)
                if start_str.endswith(".00%"): start_str = start_str.replace(".00%", ".0%")
                if end_str.endswith(".00%"): end_str = end_str.replace(".00%", ".0%")
                
                gradient_parts.append(f"{hex_val} {start_str} {end_str}")
            
            bg_style = f"background: conic-gradient({', '.join(gradient_parts)});"
        else:
            # Single color fallback
            single_hex = colors[0] if colors[0].startswith('#') else f'#{colors[0]}'
            bg_style = f"background-color:{single_hex};"
            
        swatch = f'<span style="display:inline-block;width:24px;height:24px;border-radius:50%;{bg_style}margin-right:10px;border:2px solid #fff;vertical-align:middle;"></span>'
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
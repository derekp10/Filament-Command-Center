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
    # Names this audit (Group 58). Unique across restarts: logic.new_audit_id,
    # set when the audit starts in api_identify_scan.
    "audit_id": None,
    "location_id": None,
    "expected_items": [], # Spool IDs whose own location is exactly this place
    "scanned_items": [],  # Every spool ID scanned, on the list or not
    "rogue_items": [],    # Extras: scanned here, filed elsewhere ("Extra" on screen)
    "trail_items": [],    # Scanned here, loaded on a head from this very place
    # str(spool id) -> the row /api/audit_session draws, stored at the scan,
    # so a poll reads no Spoolman and a blip can't blank a tile.
    "rows": {},
    "start_note": "",     # What this audit doesn't check (the places inside it)
    # The label side of a found spool (Group 58.2).
    "last_found": None,   # The spool ID "Needs a label" acts on
    "found_by": {},       # str(spool id) -> logic.AUDIT_FOUND_BY_LABEL / AUDIT_FOUND_NO_LABEL
    # str(spool id) -> the label status a mark in this audit replaced (False or
    # None): what "undo that" puts back, and nothing else can.
    "label_flagged": {},
    # Idle-timeout watchdog. Updated on every audit-mode scan and on
    # audit start. logic.check_audit_idle_timeout() ends the session when
    # stale, so a closed tab or a crashed browser can't leave the panel
    # auto-opening on every later dashboard load. (The session lives in
    # this process only: a restart ends it, and leaves no trace of it.)
    "last_activity_ts": 0.0,
}

# How the last audit ended (Group 58): None, or {id, why, location}, `why` being
# done, cancel or idle. Written by logic._end_audit and kept past reset_audit and
# past the next audit's start: a heartbeat's `audit_end` is how a page that
# believed an audit was running learns why it no longer is. None after a restart
# is itself the answer: a page still believing in an audit lost it to the restart.
AUDIT_LAST_END = None

# Audit auto-cancel threshold. 30 minutes is long enough that someone
# can pause mid-audit to physically chase a spool down without losing
# the session, but short enough that an abandoned audit doesn't haunt
# the dashboard indefinitely.
AUDIT_IDLE_TIMEOUT_SECONDS = 30 * 60

# --- BULK MOVE STATE (L298 Phase 2) ---
# The scan-driven "move everything from A to B" session. Mirrors AUDIT_SESSION
# deliberately (same in-place-mutation discipline, same lazy idle watchdog) so
# the two scan modes behave identically from the user's side.
#
# `stage` is the state machine the deck QR shapeshifts against:
#   idle           - no session (active=False)
#   awaiting_source- armed; the next location scan captures the SOURCE
#   awaiting_dest  - source captured; the next location scan captures the DEST
#   preview        - both captured + a dry-run tally computed; waits for an
#                    EXPLICIT commit (CMD:DONE / button). Scanning a dest never
#                    auto-commits — a bulk move is too destructive to fire on a
#                    stray scan.
BULK_MOVE_SESSION = {
    "active": False,
    "stage": "idle",
    "source_id": None,
    "dest_id": None,
    # Dry-run tally rendered by the preview panel: {movable:[], skipped:[], blocked:str|None}
    "preview": None,
    "last_activity_ts": 0.0,
}

# Same 30-minute rationale as the audit watchdog: long enough to walk away and
# physically gather spools, short enough that an abandoned session can't leave a
# stale source armed for the next person's dest scan.
BULK_MOVE_IDLE_TIMEOUT_SECONDS = 30 * 60

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

def add_log_entry(msg, category="INFO", color_hex=None, meta=None):
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
    if meta:
        entry["meta"] = meta
        
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
        "audit_id": None,
        "location_id": None,
        "expected_items": [],
        "scanned_items": [],
        "rogue_items": [],
        "trail_items": [],
        "rows": {},
        "start_note": "",
        "last_found": None,
        "found_by": {},
        "label_flagged": {},
        "last_activity_ts": 0.0,
    })


def reset_bulk_move():
    """Clears the current bulk-move session (L298 Phase 2).

    Mutates IN PLACE (never rebinds) so every module holding a reference to
    state.BULK_MOVE_SESSION observes the clear — the same discipline
    reset_audit() follows. Do NOT whole-replace this dict.
    """
    global BULK_MOVE_SESSION
    BULK_MOVE_SESSION.update({
        "active": False,
        "stage": "idle",
        "source_id": None,
        "dest_id": None,
        "preview": None,
        "last_activity_ts": 0.0,
    })
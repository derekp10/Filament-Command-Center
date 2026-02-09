import requests
import shutil
import os
import sqlite3
from datetime import datetime
import time

# --- CONFIGURATION (NO ASSUMPTIONS) ---
# Update these to match your exact setup
SPOOLMAN_URL = "http://192.168.1.29:5000"  # Source: Your dump_spoolman.py
SMB_SHARE_PATH = r"\\TRUENAS\App_Data\Spoolman\SPOOLMAN_DIR_DATA" # Source: Your prompt
LOCAL_BACKUP_DIR = "./Backups"

def log(msg, type="INFO"):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{type}] {msg}")

def verify_backup(filepath):
    """Try to connect to the database to ensure it's not corrupt."""
    try:
        conn = sqlite3.connect(f"file:{filepath}?mode=ro", uri=True)
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM spool")
        count = cursor.fetchone()[0]
        conn.close()
        log(f"Verification Successful! Database contains {count} spools.", "SUCCESS")
        return True
    except Exception as e:
        log(f"Verification FAILED: {e}", "ERROR")
        return False

def trigger_remote_backup():
    """Ask Spoolman to create a safe backup internally."""
    log(f"Requesting safe backup from {SPOOLMAN_URL}...")
    try:
        # The endpoint might be /api/v1/backup or just /backup depending on version
        # We try the v1 endpoint first based on your other scripts
        url = f"{SPOOLMAN_URL}/api/v1/backup"
        response = requests.post(url)
        
        if response.status_code == 404:
            # Fallback for older versions
            url = f"{SPOOLMAN_URL}/backup"
            response = requests.post(url)

        if response.status_code == 200:
            data = response.json()
            # The path returned is the INTERNAL container path (e.g. /home/app/...)
            # We need to grab just the filename
            internal_path = data.get("path", "")
            filename = os.path.basename(internal_path)
            log(f"Server created backup: {filename}", "SUCCESS")
            return filename
        else:
            log(f"Server failed to backup. Status: {response.status_code} Body: {response.text}", "ERROR")
            return None
    except Exception as e:
        log(f"Connection failed: {e}", "ERROR")
        return None

def main():
    if not os.path.exists(LOCAL_BACKUP_DIR):
        os.makedirs(LOCAL_BACKUP_DIR)

    # 1. Trigger the backup on the server
    backup_filename = trigger_remote_backup()
    
    if not backup_filename:
        log("Could not trigger remote backup. Checking for auto-backups...", "WARN")
        # Fallback: Look for the most recent file in the backups folder
        # Spoolman usually creates a 'backups' folder inside the data directory
        server_backup_dir = os.path.join(SMB_SHARE_PATH, "backups")
    else:
        server_backup_dir = os.path.join(SMB_SHARE_PATH, "backups")

    # 2. Locate the file on the NAS
    if not os.path.exists(server_backup_dir):
        log(f"Could not find backups folder at: {server_backup_dir}", "CRITICAL")
        log("Check your SMB path mapping.", "INFO")
        return

    # If we have a specific filename, look for it. Otherwise, grab the newest.
    if backup_filename:
        source_file = os.path.join(server_backup_dir, backup_filename)
    else:
        # Find newest .db file
        files = [os.path.join(server_backup_dir, f) for f in os.listdir(server_backup_dir) if f.endswith('.db')]
        if not files:
            log("No .db files found in backup folder.", "CRITICAL")
            return
        source_file = max(files, key=os.path.getctime)
        log(f"Using latest existing backup: {os.path.basename(source_file)}", "INFO")

    # 3. Copy to Local Machine
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    dest_filename = f"spoolman_backup_{timestamp}.db"
    dest_path = os.path.join(LOCAL_BACKUP_DIR, dest_filename)

    log(f"Copying from NAS to Local...", "INFO")
    try:
        shutil.copy2(source_file, dest_path)
        log(f"Copied to: {dest_path}", "SUCCESS")
        
        # 4. Verify Integrity
        verify_backup(dest_path)
        
    except Exception as e:
        log(f"Copy failed: {e}", "ERROR")

if __name__ == "__main__":
    main()
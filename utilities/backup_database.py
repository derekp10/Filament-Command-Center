import requests
import shutil
import os
import sqlite3
from datetime import datetime
import project_config  # Import our new config loader

# --- LOAD CONFIGURATION ---
config = project_config.load_config()

SPOOLMAN_URL = config.get("spoolman_url")
# We assume the config path points to the DB file itself, so we get the dir
NAS_DB_PATH = config.get("spoolman_db_path") 
NAS_DIR_PATH = os.path.dirname(NAS_DB_PATH) # Strip filename to get folder
LOCAL_BACKUP_DIR = config.get("backup_directory")

def log(msg, type="INFO"):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{type}] {msg}")

def verify_backup(filepath):
    """Try to connect to the database to ensure it's not corrupt."""
    try:
        # Connect in Read-Only mode to verify headers
        conn = sqlite3.connect(f"file:{filepath}?mode=ro", uri=True)
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM spool")
        count = cursor.fetchone()[0]
        conn.close()
        log(f"Verification Successful! Snapshot contains {count} spools.", "SUCCESS")
        return True
    except Exception as e:
        log(f"Verification FAILED: {e}", "ERROR")
        return False

def trigger_remote_backup():
    """Ask Spoolman to create a safe backup internally."""
    log(f"Requesting API backup from {SPOOLMAN_URL}...")
    try:
        # Try v1 endpoint
        url = f"{SPOOLMAN_URL}/api/v1/backup"
        response = requests.post(url)
        
        if response.status_code == 404:
            # Fallback for older Spoolman versions
            url = f"{SPOOLMAN_URL}/backup"
            response = requests.post(url)

        if response.status_code == 200:
            data = response.json()
            # The path returned is internal to the Docker container
            # We just need the filename to find it on the NAS share
            internal_path = data.get("path", "")
            filename = os.path.basename(internal_path)
            log(f"Server generated backup file: {filename}", "SUCCESS")
            return filename
        else:
            log(f"Server failed to backup. Status: {response.status_code} Body: {response.text}", "ERROR")
            return None
    except Exception as e:
        log(f"Connection failed: {e}", "ERROR")
        return None

def main():
    if not os.path.exists(LOCAL_BACKUP_DIR):
        try:
            os.makedirs(LOCAL_BACKUP_DIR)
            log(f"Created local backup directory: {LOCAL_BACKUP_DIR}", "INFO")
        except Exception as e:
            log(f"Could not create backup directory: {e}", "CRITICAL")
            return

    # 1. Trigger the backup on the server
    backup_filename = trigger_remote_backup()
    
    server_backup_dir = os.path.join(NAS_DIR_PATH, "backups")

    # 2. Locate the file on the NAS
    if not os.path.exists(server_backup_dir):
        log(f"Could not find backups folder at: {server_backup_dir}", "CRITICAL")
        log("Check 'spoolman_db_path' in config.json.", "INFO")
        return

    # If we have a specific filename from API, use it. Otherwise, find the newest .db
    if backup_filename:
        source_file = os.path.join(server_backup_dir, backup_filename)
    else:
        log("API backup failed/unknown. Checking for existing backups...", "WARN")
        files = [os.path.join(server_backup_dir, f) for f in os.listdir(server_backup_dir) if f.endswith('.db')]
        if not files:
            log("No .db files found in NAS backup folder.", "CRITICAL")
            return
        source_file = max(files, key=os.path.getctime)
        log(f"Using latest existing backup: {os.path.basename(source_file)}", "INFO")

    # 3. Copy to Local Safe Zone
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    dest_filename = f"spoolman_backup_{timestamp}.db"
    dest_path = os.path.join(LOCAL_BACKUP_DIR, dest_filename)

    log(f"Copying from NAS...", "INFO")
    try:
        shutil.copy2(source_file, dest_path)
        log(f"Saved to: {dest_path}", "SUCCESS")
        
        # 4. Verify Integrity
        verify_backup(dest_path)
        
    except Exception as e:
        log(f"Copy failed: {e}", "ERROR")

if __name__ == "__main__":
    main()
#!/bin/bash

# --- CONFIGURATION ---
# 1. Your App Name (CHECK THIS! Must match exactly what is in the UI)
APP_NAME="inventory-hub"

# 2. Your App Folder
TARGET_DIR="/mnt/LeftBankPool1/App_Data/InventoryHub"
# ---------------------

echo "🚀 STARTED: Auto-Update Sequence"

# 1. Go to folder
if [ -d "$TARGET_DIR" ]; then
    cd "$TARGET_DIR"
else
    echo "❌ Error: Could not find $TARGET_DIR"
    exit 1
fi

# 2. Parse config.json for Spoolman URL
echo "🔍 Reading configuration..."
SPOOLMAN_IP=$(python3 -c "import json; print(json.load(open('config.json')).get('server_ip', '127.0.0.1'))" 2>/dev/null)
SPOOLMAN_PORT=$(python3 -c "import json; print(json.load(open('config.json')).get('spoolman_port', '7912'))" 2>/dev/null)

if [ -z "$SPOOLMAN_IP" ] || [ -z "$SPOOLMAN_PORT" ]; then
    echo "❌ Error: Could not determine Spoolman IP/Port from config.json"
    exit 1
fi

SPOOLMAN_URL="http://${SPOOLMAN_IP}:${SPOOLMAN_PORT}"
echo "   🔗 Target Spoolman: $SPOOLMAN_URL"

# 3. Trigger Spoolman DB Backup
echo "💾 Triggering Spoolman Database Backup via API..."
# Use -s (silent), -S (show errors on failure), and -f (fail fast on non-200 HTTP codes)
if ! curl -sSf -X POST "${SPOOLMAN_URL}/api/v1/backup" > /dev/null; then
    echo "❌ CRITICAL ERROR: Spoolman database backup failed!"
    echo "   Aborting the update process to protect your data."
    
    # Send an email alert natively through TrueNAS middleware
    midclt call mail.send '{
        "subject": "⚠️ CRITICAL: Filament Command Center Update FAILED", 
        "text": "The automated cron job update for Filament Command Center was aborted because the Spoolman database backup via API failed. Please check the Spoolman container logs and verify it is running before attempting to update again."
    }'
    
    exit 1
fi
echo "✅ Backup Successful!"

# 4. Git Pull
echo "⬇️  Pulling Code..."
git fetch origin main
git reset --hard origin/main

# 5. Cleanup Python cache
find . -name "*.pyc" -delete
find . -name "__pycache__" -delete

# 6. Run Database Schema Setup & Migrations
echo "🏗️  Applying Database Configurations..."
python3 setup-and-rebuild/setup_fields.py
python3 setup-and-rebuild/migrate_spool_links.py

# 7. The Magic: Restart the App (TrueNAS Electric Eel / 24.10+)
echo "♻️  Restarting '$APP_NAME'..."

# STOP the app (waits for it to finish)
echo "   ... Stopping"
midclt call -job app.stop "$APP_NAME"

sleep 5

# START the app
echo "   ... Starting"
midclt call -job app.start "$APP_NAME"

echo "✅ COMPLETE! Update applied successfully and the App has been rebooted."

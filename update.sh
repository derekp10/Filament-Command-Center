#!/bin/bash

# --- CONFIGURATION ---
# 1. Your App Name (CHECK THIS! Must match exactly what is in the UI)
APP_NAME="inventory-hub"

# 2. Your App Folder
TARGET_DIR="/mnt/LeftPoolBank1/App_Data/InventoryHub"
# ---------------------

echo "🚀 STARTED: Auto-Update Sequence"

# 1. Go to folder
if [ -d "$TARGET_DIR" ]; then
    cd "$TARGET_DIR"
else
    echo "❌ Error: Could not find $TARGET_DIR"
    exit 1
fi

# 2. Git Pull
echo "⬇️  Pulling Code..."
git fetch origin main
git reset --hard origin/main

# 3. Cleanup Python cache
find . -name "*.pyc" -delete
find . -name "__pycache__" -delete

# 4. The Magic: Restart the App (TrueNAS Electric Eel / 24.10+)
echo "♻️  Restarting '$APP_NAME'..."

# STOP the app (waits for it to finish)
echo "   ... Stopping"
midclt call -job app.stop "$APP_NAME"

sleep 5

# START the app
echo "   ... Starting"
midclt call -job app.start "$APP_NAME"

echo "✅ COMPLETE! App has been rebooted."
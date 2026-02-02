#!/bin/bash
# -----------------------------------------------------
# Inventory Hub Update Script (TrueNAS Scale)
# -----------------------------------------------------

# 1. Navigate to the folder (Uses current folder if run from inside it)
# Change this path if you want to run it from anywhere else!
TARGET_DIR="/mnt/MyPool/App_Data/InventoryHub"

if [ -d "$TARGET_DIR" ]; then
    cd "$TARGET_DIR"
    echo "📂 Navigated to $TARGET_DIR"
else
    echo "⚠️  Could not find target dir, assuming we are already here..."
fi

# 2. Update Code
echo "⬇️  Fetching latest version from GitHub..."
git fetch origin main

echo "✨  Resetting to match 'main' branch..."
# This wipes local changes on the server to ensure a clean update
git reset --hard origin/main

# 3. Cleanup
echo "🧹  Cleaning up temporary Python files..."
find . -name "*.pyc" -delete
find . -name "__pycache__" -delete

# 4. Finish
echo "-----------------------------------------------------"
echo "✅  CODE UPDATE COMPLETE!"
echo "👉  ACTION REQUIRED: Please RESTART the app in TrueNAS UI."
echo "-----------------------------------------------------"
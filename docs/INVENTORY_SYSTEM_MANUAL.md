# 📘 Inventory Hub - System Operator Manual

**Version:** 2.0 (Service Platform Architecture)
**Date:** 2026-01-21

## 1. System Architecture
The Inventory Hub is a "Service Platform" that acts as the brain between **Spoolman**, **FilaBridge**, and your **Scanner**. It is designed to be stateless, meaning all settings are stored in external files, allowing for updates without code changes.

### The Stack
* **Server (The Brain):** `inventory_hub.py` running as a Docker Container on TrueNAS.
* **Client (The Interface):** `scanner.py` running on a local PC/Terminal.
* **Database (The Truth):** `3D Print Supplies - Locations.csv` (Valid Bins) + `config.json` (Hardware Map).

---

## 2. File Manifest (The "Source Bundle")
To redeploy or update this system, you need these 5 files in your server's mapped folder:

1.  **`inventory_hub.py`** (Server Logic): Handles API requests, conflicts, and moves.
2.  **`config.json`** (Settings): Stores IP addresses, Printer mappings, and Safety rules.
3.  **`3D Print Supplies - Locations.csv`** (Location DB): List of all valid storage bins.
4.  **`scanner.py`** (Client): The TUI dashboard running on your PC.
5.  **`SCANNER_STYLE_GUIDE.md`** (Design Rules): UI rules for future code updates.

---

## 3. Server Configuration (`config.json`)
You no longer edit Python code to change settings. Edit `config.json` and restart the container.

### Adding a Printer
Add an entry to `printer_map`.
* **Key:** The Location ID (e.g., `XL-1`).
* **printer_name:** Must match the name in **FilaBridge**.
* **position:** The slot number (0-indexed).

### Moisture Safety Rules
To prevent wet filament from reaching a printer, define safe source patterns in `safe_source_patterns`.
* Any location containing these strings is considered "Dry".
* *Example:* `["MDB", "DB", "Dryer"]`

---

## 4. TrueNAS Deployment Guide
If you need to rebuild the server, use these settings in **TrueNAS Custom Apps**.

* **Image Repository:** `python`
* **Image Tag:** `3.11-slim`
* **Pull Policy:** `IfNotPresent`
* **Command:**
    1. `/bin/sh`
    2. `-c`
    3. `pip install --no-cache-dir flask requests && python /app/inventory_hub.py`
* **Storage:** Map your data folder to `/app`.
* **Network:** Host Network or Bridge (Port 8000:8000).

---

## 5. Scanner Operations (User Guide)

### Smart Features
1.  **Smart Expand:** Scanning a Location when the buffer is empty will **FILL** the buffer with that location's contents.
2.  **Smart Swap:** If you try to move multiple spools into a Printer Slot, the system will automatically ignore the spool that is *already* there (assuming you are replacing it).
3.  **Safety Checks:**
    * **Physics:** Prevents 2 *new* spools from going into 1 slot.
    * **Moisture:** Warns if moving from Shelf -> Printer (bypassing Dryer).
    * **Occupancy:** Warns if a slot is occupied by an unknown item.

### Command Reference
| Key | Action | Note |
| :--- | :--- | :--- |
| **Enter** | Scan/Execute | Scans item or moves buffer to location. |
| **Ctrl+R** | Remove Last | Removes only the last scanned item. |
| **Ctrl+L** | Clear All | Wipes the entire buffer. |
| **Ctrl+Z** | Undo | Reverses the last move (Physical & Digital). |
| **Ctrl+C** | Quit | Exits the scanner safely. |

---

## 6. Maintenance & Updates

### How to Update the Code
1.  **Drop:** Drag the new `inventory_hub.py` into the network folder.
2.  **Restart:** Go to TrueNAS -> Apps -> Inventory Hub -> **Restart**.

### How to Add New Bins
1.  **Save:** Add the new row to `3D Print Supplies - Locations.csv`.
2.  **Done:** The server re-reads the CSV on every scan. No restart needed.

### Troubleshooting Logs
* **Live View:** TrueNAS -> Apps -> Inventory Hub -> Logs.
* **History:** Open `hub.log` in the network folder (stores last 5MB of activity).
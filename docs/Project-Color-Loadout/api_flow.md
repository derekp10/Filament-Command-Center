# 🌐 Project Color Loadout: API & Data Flow (v2.0)

## Overview
This document outlines the internal communication routing between the Project Color Loadout add-on, the local SQLite Database, the Spoolman API, and the Filament Command Center (FCC).

---

## 1. Local Database Operations (Internal API)
**Goal:** Handle UI requests at lightning speed without touching the TrueNAS file system directly.

* **List Projects:** `GET /api/loadout/projects` -> Returns fast-search columns from the `Projects` table.
* **Get Project Loadout:** `GET /api/loadout/projects/{id}` -> Returns the full `loadout_data` JSON array.
* **Reverse Lookup (FCC UI):** `GET /api/loadout/filament/{filament_id}/projects`
  * **Trigger:** User clicks the search icon on a filament card in the main FCC interface.
  * **Action:** Queries the `Filament_Index` table and returns a list of projects requiring that material/color.

---

## 2. The "Lazy Swap" Optimizer (Queue Logic)
**Goal:** Sort the print queue to minimize physical spool swaps.

* **API Call:** `POST /api/loadout/queue/optimize`
* **Payload Sent:** Array of queued `project_id`s.
* **Logic Steps:**
  1. Fetch current active loadout from FCC (e.g., "Slot 1 is Red, Slot 2 is Blue").
  2. Query `loadout_data` for all queued projects.
  3. **Sort:** Order projects by highest color overlap with the active printer state.
  4. **Auto-Remap:** If a project is `Swappable` (not Slot-Locked), virtually reassign its `slot_number`s to match the active printer state.
* **Output:** A sorted JSON array of the optimized print queue.

---

## 3. The "Scrap Buster" Fetch (Spoolman GET)
**Goal:** Find available physical spools for the optimized queue.

* **API Call:** `GET` request to Spoolman's `/api/v1/spool` endpoint.
* **Local Filtering & Sorting Logic:**
  1. **Filter by Color:** Compare `preferred_hex` to Spoolman `color_hex` (using Delta-E tolerance if exact match is missing).
  2. **Filter by Weight:** Discard spools where `remaining_weight` < (`required_weight_g` + `target_printer` buffer).
  3. **Sort (Scrap Buster):** Sort valid spools by `remaining_weight` ASCENDING to clear partial spools.
* **Smart Cart Check:** If no valid spools are found, trigger a local `POST` to the FCC Shopping List table.

---

## 4. The Printer Push (FCC POST)
**Goal:** Overwrite the current active loadout of the selected printer in the FCC environment.

* **API Call:** `POST` to the internal FCC endpoint (e.g., `/api/fcc/printer/active_loadout`).
* **Payload Sent (Example for Core One MMU3):**

    {
      "printer_id": "🦝 Core One Upgraded",
      "active_slots": [
        {
          "slot": 1,
          "spoolman_id": 104,
          "role": "Primary",
          "spool_join_target": 5 
        },
        {
          "slot": 2,
          "spoolman_id": 108,
          "role": "Support Interface",
          "spool_join_target": null
        }
      ]
    }

* **Post-Push Action:** Generate the **Scavenger Hunt List** UI, visually grouping Relay Spools (SpoolJoin targets).

---

## 5. The "Reverse Sync" (File Injector)
**Goal:** Ensure the SQLite database and the `.3mf` files stay synchronized.

* **API Call:** `POST /api/loadout/sync/file`
* **Trigger:** The TrueNAS file watcher detects that an Original `.3mf` was modified and saved (e.g., slicer settings changed).
* **Action:** 1. Read the hidden `project_id` nametag from the `.3mf`.
  2. Fetch the corresponding `loadout_data` from the SQLite database.
  3. Run the Magic Injector Python script to silently overwrite the color XML data inside the `.3mf`.
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

## 1.5. Drag & Drop + Smart Draft Import
**Goal:** Instantly build a loadout from a dropped file using local Syncthing data.
* **Trigger:** User drops `.3mf` into the browser UI.
* **Action:** Browser parses XML, sends `POST /api/loadout/import/draft`.
* **Logic:** Backend uses Delta-E to match hex colors to Spoolman DB. Resolves file path using Syncthing mirror. Returns pre-filled JSON to UI.

## 1.8. Palette Management (Global Themes)
**Goal:** Save and recall favorite color assignments.
* `POST /api/loadout/palettes` -> Saves current UI slots as a reusable Global Palette.
* `GET /api/loadout/palettes` -> Fetches saved themes for the "Apply Palette" dropdown.

---

## 2. The "4D Chess" Optimizer (Queue Logic)
**Goal:** Analyze the entire queue to minimize total physical spool swaps across a batch.
* **API Call:** `POST /api/loadout/queue/optimize_batch`
* **Payload Sent:** Array of queued `project_id`s.
* **Logic Steps:**
  1. Analyze all colors required by all queued projects.
  2. Map highest-frequency colors to static slots (e.g., Slot 1 is always Black for this batch).
  3. Sort queue order to delay necessary spool swaps until the end of the batch.
  4. Auto-remap `slot_number`s in `Swappable` projects to match this optimized timeline.
* **Output:** A JSON "Batch Roadmap" detailing print sequence and exact swap interventions required.

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
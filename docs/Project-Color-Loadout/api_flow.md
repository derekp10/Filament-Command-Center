# 🌐 Project Color Loadout: API & Data Flow

## Overview
This document outlines the internal communication between the Project Color Loadout add-on, the Spoolman API, and the Filament Command Center (FCC) active printer state.

---

## 1. The "Scrap Buster" Fetch (Spoolman GET)
**Trigger:** When a user opens a Project Card or clicks "Find Matching Spools".
**Goal:** Find available spools that match the required material, hex color, and minimum weight.

* **API Call:** `GET` request to Spoolman's `/api/v1/spool` endpoint.
* **Query Parameters Sent:**
  * `material`: Matches `preferred_material` (e.g., "PLA").
* **Local Filtering & Sorting Logic:**
  1. **Filter by Color:** Compare the `preferred_hex` to the Spoolman `color_hex`. Allow a slight tolerance (delta-E matching) if an exact match isn't found.
  2. **Filter by Weight:** Discard any spool where `remaining_weight` < (`required_weight_g` + `target_printer` buffer).
  3. **Sort (Scrap Buster):** Sort the remaining valid spools by `remaining_weight` ASCENDING.
* **Output:** The UI dropdown is populated with the sorted list, pre-selecting the spool with the lowest viable weight to clear out partial spools.

---

## 2. The Relay Map (Pre-Push Validation)
**Trigger:** When the user hits the "Assign to Printer" button.
**Goal:** Verify all assigned spools are still available and map out the fallback logic before sending to the printer.

* **Logic Steps:**
  1. Check `assigned_spool_id` for all slots.
  2. If `runout_strategy` == "SpoolJoin", map the `assigned_spool_id` of the primary slot to the `assigned_spool_id` of the `fallback_slot_number`.
  3. **Safety Check:** Ping Spoolman one last time `GET /api/v1/spool/{id}` to ensure the spool wasn't grabbed by another process recently.

---

## 3. The Printer Push (FCC POST)
**Trigger:** Post-validation successful.
**Goal:** Overwrite the current active loadout of the selected printer in the FCC environment.

* **API Call:** `POST` to the internal FCC endpoint (e.g., `/api/fcc/printer/active_loadout`).
* **Payload Sent (Example for Core One MMU3):**
```json
  {
    "printer_id": "CORE1-M0",
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
```
* **Post-Push Actions:**
  1. Generate the **Scavenger Hunt List** UI for the user based on the Spoolman `location` data from the payload (ensuring Relay Spools are grouped together).
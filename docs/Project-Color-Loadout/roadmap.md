### 🗺️ Project Color Loadout: LLM Development Roadmap (v3.0)

**Phase 1: The Hybrid Database & Core UI (The Foundation)**
* **Goal:** Create a lightning-fast relational database that retains JSON flexibility, plus the frontend UI.
* **Tasks:**
    * Build the SQLite schema (`Projects`, `Filament_Links`, `Print_Queue`).
    * Implement the `JSON1` extension: Store the complex `slots` array directly in a `loadout_data` text column for ultimate flexibility.
    * Build the "Project Library" grid view and "Project Detail" view.
    * Build the "Where is this used?" reverse-lookup UI for the existing FCC Filament modal.
* **Dependencies:** None.

**Phase 2: The Magic Parsers & Source of Truth (Reading Files)**
* **Goal:** Automate data entry and establish the "Reverse Sync" rule.
* **Tasks:**
    * **Establish Source of Truth:** The Original `.3mf` is the *Geometry/Settings Master*. The Database is the *Color Master*.
    * Build `.3mf` parser: Read XML for hex colors, extract **Slicer Roles**, and detect "Painted" (Slot-Locked) vs "Part-Based" (Swappable).
    * Build `.gcode` parser: Read metadata for weight/material, decode Base64 thumbnail for UI previews.
* **Dependencies:** Phase 1 database ready to receive parsed data.

**Phase 3: The Orchestrator & Spooler (Minimizing Physical Labor)**
* **Goal:** Optimize the printing schedule to drastically reduce manual spool swaps.
* **Tasks:**
    * Build the **Print Queue** UI.
    * Create the **"Lazy Swap" Algorithm:** Sort queued projects based on maximum overlap with the active printer's current filament loadout.
    * **Aesthetic Compromise Toggle:** Add a "Strict Colors" switch. If OFF, the app can merge similar colors (e.g., two slightly different greens) into the same loaded slot to save a spool swap.
    * **The Spooler Directory:** Create a temporary TrueNAS folder (`/fcc_spooler/`). Generate the actively color-mapped `.3mf` and `.gcode` files here to keep original project folders clean. Auto-delete when the print finishes.
* **Dependencies:** Phase 1 & 2 logic.

**Phase 4: Inventory Sync & Smart Shopping (The APIs)**
* **Goal:** Connect to Spoolman, active Printers, and track shortages.
* **Tasks:**
    * **Printer Push:** POST the optimized loadout data to the FCC active printer state.
    * **The Smart Cart:** Auto-calculate material shortages across the whole Print Queue. If low on a requested filament, add its product link to a shopping list.
    * **Delta-E Alternative Suggestion:** If a filament is out of stock, mathematically suggest the closest hex-color match from available Spoolman inventory.
* **Dependencies:** FCC Spoolman API wrapper.

**Phase 5: Reverse Sync & Tracking Resilience (Write Operations)**
* **Goal:** Keep files updated automatically without versioning nightmares.
* **Tasks:**
    * **Magic Injector:** Script to inject chosen hex colors and a hidden `project_id` nametag directly into the Spooler `.3mf` file.
    * **File Watcher (Reverse Sync):** If the user edits and saves the *Original* `.3mf` (e.g., changing support settings), the app detects the file change, pulls the saved colors from the Database, and auto-updates everything silently.
    * **Sniff Mode:** A button to crawl TrueNAS folders to fix broken file paths automatically using the hidden nametags.
* **Dependencies:** Phase 3 Spooler logic.
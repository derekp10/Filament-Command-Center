### 🗺️ Project Color Loadout: LLM Development Roadmap (v4.0)

**Phase 1: The Hybrid Database & Core UI (The Foundation)**
* **Goal:** Create a lightning-fast relational database that retains JSON flexibility, plus the frontend UI.
* **Tasks:**
    * Build the SQLite schema (`Projects`, `Global_Palettes`, `Filament_Index`, `Print_Queue`).
    * Implement the `JSON1` extension: Store the complex `slots` array directly in a `loadout_data` text column for ultimate flexibility.
    * Build the "Project Library" grid view and "Project Detail" view.
    * Build the "Where is this used?" reverse-lookup UI for the existing FCC Filament modal.
* **Dependencies:** None.

**Phase 2: Drag & Drop, Magic Parsers & Smart Draft**
* **Goal:** Zero-friction data entry and establish the "Reverse Sync" rule.
* **Tasks:**
    * **Establish Source of Truth:** The Original `.3mf` is the *Geometry/Settings Master*. The Database is the *Color Master*.
    * **Drag & Drop Zone:** UI element to drop `.3mf`/`.gcode` files directly into the browser.
    * **Smart Draft Import:** Browser unzips dropped `.3mf`, extracts XML hex colors, and auto-matches to Spoolman inventory via Delta-E math to pre-fill the loadout.
    * **Syncthing Resolution:** Match dropped file names to the mirrored TrueNAS directory so network uploads aren't required.
* **Dependencies:** Phase 1 database ready to receive parsed data.

**Phase 3: Global Palettes & 4D Queue Optimization**
* **Goal:** Manage color themes and optimize the printing schedule to drastically reduce manual spool swaps.
* **Tasks:**
    * **Global Palettes:** Ability to save a toolhead color configuration as a named theme (e.g., "Zombie Colors") and apply it to any project.
    * Build the **Print Queue** UI.
    * Create the **"4D Lazy Swap" Algorithm:** Analyze the *entire* Print Queue. Calculate the optimal print sequence and slot assignments to minimize total physical spool changes across the whole batch.
    * **Aesthetic Compromise Toggle:** Add a "Strict Colors" switch. If OFF, the app can merge similar colors into the same loaded slot.
    * **The Spooler Directory:** Create a temporary TrueNAS folder (`/fcc_spooler/`). Generate the actively color-mapped files here to keep original folders clean. Auto-delete when finished.
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
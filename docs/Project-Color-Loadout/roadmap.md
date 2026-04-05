### 🗺️ Project Color Loadout: LLM Development Roadmap

**Phase 1: The UI Shell & Data Structure (The Foundation)**
* **Goal:** Create the basic frontend interface and local data storage schema.
* **Tasks:**
    * Define the JSON structure for a "Saved Project" (Title, Path, Lock Status, Target Printer, Slot Array).
    * Build a "Printer Profiles" dictionary to define dynamic filament runout buffers (e.g., Core One MMU3 = 5g, Prusa XL = 15g).
    * Build the "Project Library" grid view (Read/Display saved projects).
    * Build the "Project Detail" view (Display toolhead slots and manual color entry).
* **Dependencies:** None. Runs independently of external APIs.

**Phase 2: The Magic Parsers (Reading Files)**
* **Goal:** Automate data entry by reading `.3mf` and `.gcode` files.
* **Tasks:**
    * Build `.3mf` parser: Unzip, read XML for hex colors, part names, and extract **Slicer Roles** (Primary vs Support Interface).
    * Detect if the `.3mf` is "Painted" (Slot-Locked) or "Part-Based" (Swappable).
    * Build `.gcode` parser: Read bottom metadata for weight/material, decode Base64 thumbnail for visual previews.
* **Dependencies:** Phase 1 UI must be ready to receive parsed data.

**Phase 3: Inventory Sync & Push (The APIs)**
* **Goal:** Connect the app to Spoolman and active Printers.
* **Tasks:**
    * **Spoolman GET (Scrap Buster):** Fetch matching spools. Sort by lowest weight that covers the `required_weight` + `target_printer` buffer.
    * **Printer Push:** POST the loadout data to the existing Filament Command Center active printer state. Map `fallback_slot_number` for SpoolJoin logic.
    * **Scavenger List:** Generate picking checklist upon assignment. Group joined spools visually (Relay Grouping) so backup spools aren't forgotten.
* **Dependencies:** Phase 1 & 2, plus access to the existing FCC Spoolman API wrapper.

**Phase 4: The "Safe Stash" & File Tracking (Write Operations)**
* **Goal:** Advanced features, file writing, and tracking resilience.
* **Tasks:**
    * **Magic Injector:** Script to inject chosen hex colors, custom part aliases, and a hidden `project_id` nametag directly into the `.3mf` file.
    * **Safe Stash Protocol:** Ensure the injector saves the file as a *new* version (e.g., `[ProjectName]_[ColorCombo].3mf`).
    * **Sniff Mode (Rescan & Re-Link):** A button to crawl TrueNAS folders, locate hidden `project_id` nametags, and fix broken file paths automatically.
* **Dependencies:** Phase 3 must be complete.
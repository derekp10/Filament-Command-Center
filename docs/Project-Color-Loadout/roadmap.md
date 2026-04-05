### 🗺️ Project Color Loadout: LLM Development Roadmap

**Phase 1: The UI Shell & Data Structure (The Foundation)**
* **Goal:** Create the basic frontend interface and local data storage schema.
* **Tasks:**
    * Define the JSON structure for a "Saved Project" (Title, Path, Lock Status, Slot Array).
    * Build the "Project Library" grid view (Read/Display saved projects).
    * Build the "Project Detail" view (Display the 5 toolhead slots and manual color entry).
* **Dependencies:** None. This runs completely independently of external APIs.

**Phase 2: The Magic Parsers (Reading Files)**
* **Goal:** Automate data entry by reading `.3mf` and `.gcode` files.
* **Tasks:**
    * Build a `.3mf` parser (Unzip, read XML for hex colors, detect "Painted" vs "Part-Based").
    * Build a `.gcode` parser (Read bottom metadata for filament weight/type, decode Base64 thumbnail for The Finished Photo Album).
    * Connect the parsed data to auto-fill the "Project Detail" view slots.
* **Dependencies:** Phase 1 UI must be ready to receive the parsed data.

**Phase 3: Inventory Sync & Push (The APIs)**
* **Goal:** Connect the app to the real world (Spoolman and Printers).
* **Tasks:**
    * **Spoolman GET:** Fetch available spools matching the required hex/material. Implement the "Scrap Buster" logic (sort by lowest weight that meets the requirement).
    * **Printer Push:** Add the "Assign" button to POST the loadout data to the existing Filament Command Center active printer state.
    * **Scavenger List:** Generate the picking checklist (Location, QR, Spool Name) upon assignment.
* **Dependencies:** Phase 1 & 2, plus access to the existing FCC Spoolman API wrapper.

**Phase 4: The "Safe Stash" & Polish (Write Operations)**
* **Goal:** Advanced features and file writing.
* **Tasks:**
    * **Magic Injector:** Write the script to inject chosen hex colors *back* into a `.3mf` file.
    * **Safe Stash Protocol:** Ensure the injector saves the file as a *new* version (e.g., `[ProjectName]_[ColorCombo].3mf`) to protect originals.
    * **Cost Calculator & Logs:** Add the math logic for project cost and the text-input for success/failure notes.
* **Dependencies:** Phase 3 must be complete so we have confirmed Spoolman colors to inject.
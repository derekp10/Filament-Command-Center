# 🖥️ UI Wireframes & Component Map

## General Layout Rules
* Keep the UI lightweight and integrated into the existing Filament Command Center (FCC) theme.
* Use clear visual indicators (Badges, Icons) to reduce text reading.

---

## Screen 1: The Project Library (Main View)
**Goal:** A scannable dashboard to see all saved projects and the current Print Queue.

* **[Top Bar: The Command Center]**
  * `[Search Bar: "Search by Name, Tag, or Required Hex..."]`
  * `[Filter Dropdown: Target Printer, Lock Status]`
  * `[Button: + Import New .3mf]` 
  * `[Button: Sniff Mode (Rescan Folders)]`
* **[The Drag & Drop Zone]**
  * *Giant dashed box overlay that appears when dragging a file.* * `[Text: Drop .3mf files here for Smart Draft Import]`
* **[Left Column: Print Queue (30% width)]**
  * `[Header: 🚦 Active Spooler]`
  * `[List: Draggable Queue Items (Mini-titles only)]`
  * `[Giant Button: 🪄 Open 4D Master Queue Editor]`
* **[Right Column: The Library Grid (70% width)]**
  * `[Grid of Project Cards]`
    * **Project Card Component (High Detail):**
      * `[Image: Thumbnail preview from G-code]`
      * `[Text: Project Name & Folder Path]`
      * `[Text: Est. Print Time] | [Text: Total Filament Weight]`
      * `[Badge: 🔒 Slot-Locked or 🔓 Swappable]`
      * `[Row of Color Swatches: Shows required hex colors]`
      * `[Button: Add to Queue]` | `[Button: Edit Slicer Roles]`

---

## Screen 2: Detail Editor & Palette Manager
**Goal:** The workspace where the user assigns Spoolman inventory or applies Global Palettes.

* **[Header Area]**
  * `[Text: Project Name]` | `[Text: Target Printer]`
  * `[Dropdown: Load Global Palette...]` | `[Button: Save as New Palette]`
  * `[Button: Save to Database]` | `[Button: Send to Print Queue]`
* **[Left Panel: File Settings]**
  * `[Image: Large Thumbnail Preview]`
  * `[Text: File Path]`
  * `[Text Box: Success/Failure Notes]`
* **[Right Panel: The Slot Rack (Dynamic List)]**
  * *Scrollable list of Slot Components (1 through X)*
  * **Slot Component Layout:**
    * **Row 1:** `[Slot #]` | `[Text: Slicer Part Name]` | `[Input: Custom Alias]`
    * **Row 2:** `[Color Swatch: Preferred Hex]` | `[Text: Material & Required Weight]` | `[Badge: Slicer Role]`
    * **Row 3:** `[Searchable Combo Box: Spoolman Inventory (Scrap Buster)]` -> *Auto-sorts by lowest viable weight.*
    * **Row 4 (Relay Logic):** `[Dropdown: Runout Strategy (Pause/SpoolJoin)]` | `[Dropdown: Fallback Slot #]`

---

## Screen 3: The 4D Master Queue Editor & Batch Roadmap
**Goal:** The global workspace to optimize the queue and view the physical swap checklist.

* **[Header Area]**
  * `[Text: 4D Master Queue Editor]`
  * `[Status Badge: Live Sync via Filabridge - Printers Loaded]`
  * `[Toggle Switch: Strict Colors / Aesthetic Compromise]`
  * `[Button: Run 4D Lazy Swap Optimizer]`
* **[The Batch Roadmap Timeline]**
  * *Generated after Optimization. Tells the user exactly what to do and when.*
  * **Phase 1 (Prints 1, 2, 3):**
    * `[Checkbox] Load Slot 1: Green PLA (Spool #104) -> Prusa XL`
    * `[Checkbox] Load Slot 2: Blue PLA (Spool #22) -> Prusa XL`
  * **Phase 2 (Before Print 4):**
    * `[Warning Icon] Swap Slot 1 to Red PLA (Spool #50)`
* **[Section: Missing Materials (Smart Cart)]**
  * *Only shows if total batch weight > Spoolman inventory.*
  * `[Warning Icon] Low on Red PLA!` -> `[Button: Add to Shopping List]`
* **[Footer]**
  * `[Button: Cancel]` | `[Giant Button: Generate Spooler Files & Start Batch]`
# 🖥️ UI Wireframes & Component Map

## General Layout Rules
* Keep the UI lightweight and integrated into the existing Filament Command Center (FCC) theme.
* Use clear visual indicators (Badges, Icons) to reduce text reading.

---

## Screen 1: The Project Library (Main View)
**Goal:** A scannable dashboard to see all saved projects and the current Print Queue.

* **[Top Bar]**
  * `[Title: Project Color Loadouts]`
  * `[Button: + Import New .3mf]` -> Opens file browser.
  * `[Button: Sniff Mode (Rescan Folders)]`
* **[Left Column: Print Queue (30% width)]**
  * `[Header: 🚦 Active Spooler]`
  * `[Toggle Switch: Strict Colors / Aesthetic Compromise]`
  * `[List: Draggable Queue Items]`
  * `[Button: 🪄 Optimize (Lazy Swap)]`
* **[Right Column: The Library Grid (70% width)]**
  * `[Grid of Project Cards]`
    * **Project Card Component:**
      * `[Image: Thumbnail preview from G-code]`
      * `[Text: Project Name]`
      * `[Badge: 🔒 Slot-Locked or 🔓 Swappable]`
      * `[Row of Mini Color Circles: Shows required hex colors]`

---

## Screen 2: Project Detail & Slot Editor
**Goal:** The workspace where the user assigns Spoolman inventory to the file's requirements.

* **[Header Area]**
  * `[Text: Project Name]` | `[Text: Target Printer]`
  * `[Button: Save to Database]` | `[Button: Send to Print Queue]`
* **[Left Panel: File Settings]**
  * `[Image: Large Thumbnail Preview]`
  * `[Text: File Path]`
  * `[Text Box: Success/Failure Notes]`
* **[Right Panel: The Slot Rack (Dynamic List)]**
  * *Scrollable list of Slot Components (1 through X)*
  * **Slot Component Layout:**
    * **Row 1:** `[Slot #]` | `[Text: Slicer Part Name]` | `[Input: Custom Alias]`
    * **Row 2:** `[Color Swatch: Preferred Hex]` | `[Text: Material & Required Weight]` | `[Badge: Slicer Role (e.g., Support)]`
    * **Row 3:** `[Dropdown: Spoolman Inventory (Scrap Buster)]` -> *Auto-sorts by lowest viable weight.*
    * **Row 4 (Relay Logic):** `[Dropdown: Runout Strategy (Pause/SpoolJoin)]` | `[Dropdown: Fallback Slot #]`

---

## Screen 3: The Active Printer Push (Modal)
**Goal:** The final confirmation and physical Scavenger Hunt list before printing.

* **[Modal Title: Push to 🦝 Core One Upgraded]**
* **[Section: Scavenger Hunt List]**
  * *Groups assigned spools by physical location for easy gathering.*
  * `[Checkbox] Grab Spool #104 (Skin/Base) from [Living Room Multi-Dryer Box]`
  * `[Checkbox] Grab Spool #36 (Skin Backup) from [Living Room Sliding Drawer 2]` -> *(Visually linked to #104 as a Relay Backup)*
* **[Section: Missing Materials (Smart Cart)]**
  * *Only shows if required weight > Spoolman inventory.*
  * `[Warning Icon] Low on Red PLA!` -> `[Button: Add to Shopping List]`
* **[Footer]**
  * `[Button: Cancel]` | `[Button: Push to Printer & Create Spooler Files]`
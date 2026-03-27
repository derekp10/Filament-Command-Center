# **Done**
* **UI/UX:** Add ability to clone/easy fill filament details for creating a new spool & filament.
* **UI/UX:** Clone button on a spool didn't properly load in the spool/filament to be duplicated into the existing filament section of the add inventory wizard.
* **UI/UX:** Fix Location Manager UI Dryer box slot locations not correctly displaying all filament information.
* **Modals:** Add spool button on the list of spools in the filament details modal that links you to the details of the spool.
* **Modals:** Added "Send to Print Queue" button for individual spools inside the Filament Details popup.
* **Bug Fix:** Live: Names are not working correctly on spools, shows "" instead of the name. (Fixed in `inv_loc_mgr.js`)
* **Bug Fix:** Live: Cannot create spools manually. (Fixed JSON serialization in `spoolman_api.py`)
* **Feature:** Support clone feature for Spools, to auto populate an existing spool. (Completed Epic 2)
* **Feature:** Figure out a way to fill in density for filaments. (Completed Epic 2)
* **Database:** Fix `container_slot` serialization error causing Spoolman database update rejections (`400 - Invalid extra field for key container_slot: Value is not a string`).
* **Location:** Added color coding to the badges on the location (Location Type).
* **Location:** Added color indicate of dryerbox/tool fullness (1/1 Green, 2/1 Red, < Max White).
* **Location:** Ejecting from slot is not showing as being ejected by setting slot to empty.
* **Location:** Trash button, which I think does the same thing as ejecting, also doesn't seem to work here, for spools that are assigned to the location, but doesn't have a slot attached to them.
* **Location:** Refactored Location DB to use JSON config instead of CSV, added native sync for Spoolman Location API, and built automated tests.
* **Logging:** Fix ghost `Label Verified` log spam when Spoolman API explicitly rejected backward backlog reductions.
* **Command Center:** Fixed Undo Buffer Restoration to correctly recall spools to the buffer and reversed Toolhead Ejection cascades.
* **Command Center:** Eject should auto disable if we move off of the command screen to any other screen or modal.
* **Command Center:** Fix backend logging to not repeat non-useful data in the logs.
* **Print Queue:** Fixed Print Queue displaying "No Loc" for all spools.
* **Live Activity:** Fixed swatch circles in the "Live Activity" Dashboard log pane to accurately display CSS conic gradients mathematically divided for multi-color filament spools.
* **Live Activity:** Implemented background polling for Filabridge `GET /api/print-errors` to expose `gcode` parsing errors in the Live Activity log.
* **System:** Engineered a native CSS physical shield inside `scripts.html` to consume hardware `mousedown`/`click` wake-up hits natively when the Scanner Pauses.
* **System:** Set it so that the screen don't sleep. Screen still times out on laptop. Fixed via robust native WakeLock API re-acquisition.
* **UI/UX:** Unify Filament/Spool UI Cards into a universal `SpoolCardBuilder` engine to guarantee all Command Center sections (Search, Location, Buffer) share the exact same structural HTML layout and style. 
* **UI/UX:** Fixed Location Manager footer action buttons squishing into each other and clipping their colorful backgrounds by properly wrapping the flexbox grid and padding the text elements.
* **UI/UX:** Addressed the "Black filaments need a better way to show border" bug by mathematically injecting a dark metallic/carbon diagonal gradient for perfectly dark spools in `getFilamentStyle`.
* **UI/UX:** Fixed the floating point display issue for weight metrics (`33.860000000014g`) by stripping backend calculations and handling clean structural `Math.round` execution securely inside the browser via the new card builder logic.
* **Bug Fix:** Fixed the Spool Edit modal bug where opening it over the Location Manager caused the editing dialog to pop up behind the backdrop, blocking interaction.
* **UI/UX:** Globally swapped the generic spool emoji (🧵) for the specific DNA vector (🧬) when referring to Filament roots across the Multi-Spool Queue Modal and UI Builders.
* **UI/UX:** Added a dedicated "Refresh" button directly natively integrated into the Search Offcanvas to easily pull immediate REST queries without clearing query states.
* **UI/UX:** Contextually renamed the "TRASH" interface button to "EJECT" inside Location Manager cards dynamically whenever the target spool does not hold a specific structural slot assignment, unifying command terminology.
* **UI/UX:** Injected `position: sticky; top: 0;` natively to all globally generated dark-table headers across the application so that structural dataset columns never vanish when scrolling a deep component list.
* **UI/UX:** Globally replaced the dark-grey-on-dark-grey Bootstrap modal close button arrays with the `.btn-close-white` variant, pushing the `X` into a high-contrast visual priority above the system backdrops.
* **UI/UX:** Explicitly unbound the `Tab` sequence bypass from the Filament Attributes multiselect tag engine loop; users can now safely form-tab to the next wizard field logically, while `Enter` retains explicit commit control logic.
* **Bug Fix:** Fixed Filament Attributes being completely non-functional — selections couldn't be made, items couldn't be added to the list, and the Add button had no effect.
* **UI/UX:** Relabeled "STEP 1: MATERIAL SELECTION" to "STEP 1: CREATION METHOD" across the Inventory Wizard structural HTML to clarify that you are determining *how* a spool is sourced rather than strictly mapping internal materials.
* **UI/UX:** Bound a global green `showToast()` confirmation feedback trigger natively onto the `+ Queue Label` action scripts within both the Filament and Spool view contexts to verify database insertion.
* **UI/UX:** Injected dynamic `item.archived` checks broadly into the universal `SpoolCardBuilder` string processor, appending a highly-visible red `[📦 ARCHIVED]` tag right onto the item name element directly dynamically so hidden obsolete artifacts are blatantly identifiable across all Location/Buffer/Search panes.
* **Bug Fix:** Fixed the Search UI completely ignoring the 'In Stock' toggle state by dynamically appending `?allow_archived=true` to the native Spoolman REST queries whenever the toggle is deactivated, bypassing Spoolman's default hidden state payload.
* **Bug Fix:** Fixed explicitly typed Command Center scan payloads dropping the archive identifier. Fixed a multi-layer disconnect where `/api/identify_scan` failed to map the JSON key, AND `inv_cmd.js` aggressively stripped unmapped keys from the `state.heldSpools` cache arrays before passing the object to the card builder.
* **Bug Fix:** Fixed explicit `[📦 ARCHIVED]` display omission across Search and Buffer UI. Resolved a secondary backend logic loop in `spoolman_api.py` dropping the archived dictionary flag during search generation, and concurrently softened Javascript boolean checks in `ui_builder.js` to ensure payload string conversions render correctly.
# Group 44: 🖨️ Printer as a First-Class Object

**Branch name (when started):** `feature/group-44-printer-first-class`
**Estimated effort:** LARGE / multi-session. A **design pass comes first** (~1 session, no code), then a migration plus 5–7 build slices.
**Risk:** **HIGH.** Printer identity is read by the deduct engine, the print monitor's latch, Quick-Swap, the dryer-box bindings, Settings and the Location Manager. A wrong migration mis-charges prints or strands pending reviews. Step 1 of every data-touching slice is a `locations.json` backup.

> **Status: `TODO` — filed 2026-10-12 (`/refresh-groups`). ⛔ DESIGN PASS BEFORE ANY CODE.**
> Derek, 2026-10-08: *"we should come back and fix this properly with a proper way to add/configure printers, instead of treating them as generic locations, and marrying them up to the toolheads in the settings based on name alone, which cannot be changed after the fact."*
> The epic itself says: *"This is the parent the surrounding printer items are all symptoms of — file fixes under it rather than as new siblings."* This group is that parent.
> Code anchors were read on `dev` @ `3949aba`.

---

## ⚠️ Read this first

- **The 2026-09-29 INDX hotfix (`main ab48e45`) papered over the worst of it:**
  - printer connections addressed by LocationID;
  - the boot `printer_map` seed retired;
  - Location Manager edits carry unsent fields forward;
  - Settings ↔ Location Manager toolhead sync;
  - **refusals** wherever a rename or delete would orphan data.

  Before designing, read the hotfix's buglist entry ("✅ HOTFIXED 2026-09-29") and `tests/test_indx_printer_setup_hotfix.py`. Those refusals are the current safety net. The design must replace each one with a real operation, never just delete it.
- **This is [Group 37](37-location-system-redesign.md)'s fork 1 applied to printers.** Fork 1 asks whether the human-readable composite LocationID is still the right model. This group asks what identifies a printer ("a stable id, not the Name and not the LocationID prefix"). Decide them together, or at least keep the printer answer consistent with fork 1.
- **Group 34's NO FORCED RELABELING invariant still binds.** Existing LocationIDs and printed QR labels stay valid.
- **[Group 35](35-config-cluster.md)'s decision G1** (key per-printer settings by display Name) depends on this answer. See the cross-group notes.

---

## The shape of the problem (from the epic)

A printer is a `locations.json` row whose Type happens to be `Printer`. Four separate things describe it:

- its heads are sibling rows joined by a LocationID prefix convention (`<printer>-<n>`);
- its tool indices live in a separate `toolheads[]` array;
- its connection lives on the row;
- its per-print runtime state is keyed by the **display Name**.

Nothing enforces that these four agree, and several can't be changed after creation.

**Evidence that this is structural, not cosmetic (2026-10-08).** `_derive_printer_room` (`locations_db.py:1401`) has three arms:

1. a `Location` column (pre-L271, no longer written);
2. a dash-prefix parse;
3. a hardcoded `PRINTER_ROOM_OVERRIDES = {"XL": "LR", "CORE1": "CR"}` (`:1362`), which still names the retired `CORE1`.

All three failed for `RCOI`. The INDX rendered as a top-level root beside the rooms instead of inside the Computer Room, with only a WARNING in `hub.log`. It was fixed by hand on dev and prod the same day. A printer created today is born mis-parented.

## Items covered (quoted from `Feature-Buglist.md`)

| # | Buglist item | Notes |
|---|---|---|
| **44.0** | **🖨️ EPIC — make a printer a FIRST-CLASS object with a real add/configure flow**, plus Derek's founding report: *"Adding/Updating a printer (Core One to a Core One Plus Gen2 INDX) is an incredibly cumbersome process…"* | The design pass. The report's asks are mapped in [Group 47](47-buglist-reconciliation.md) item 47.29. |
| **44.1** | **Printer / toolhead LocationID rename cascade.** *"A real rename needs one server operation under the write lock + active-print guard: the row id, children's `parent_id`, `toolheads[].location_id`, Dryer Box `slot_targets`, `PRINTER:<prefix>` sentinels (+ `PRINTER_ROOM_OVERRIDES`), every Spoolman `spool.location` including archived spools, and location ids inside spool extras (`physical_source(_slot)`, `fcc_pre_archive_location`, `fcc_pre_audit_location`), then a label-reprint flag."* | Needs the stable id first, or the rename has nothing fixed to hang off. |
| **44.2** | **Per-printer state is keyed by display Name.** *"renaming a printer mid-print drops the `_PRINT_TRACKER` latch / `print_tracker_latch.json`, strands `pending_cancel_fetches.json` (abandoned after 72 h with 0 g) and `no_spool` reviews, splits the deduct-ledger history, and orphans per-printer config values (`path_filament_g`, Group 35's planned per-printer map). Short term: refuse a Printer Name change while a print or pending review exists for the old name; long term: key all of it by the Printer row's LocationID (revisit Group 35 decision G1)."* | The short-term refusal is a good first slice and doesn't need the design pass. |
| **44.3** | **Settings toolhead editor: one printer-name field per printer.** *"a per-printer header row (name + connection + 'add toolhead') would make the model obvious, and the Location Manager's Printer view could show the connection status with a jump to Settings."* | Probably folds into the add/configure flow. |
| **44.4** | **Location Manager "Add child" on Printer rows can come back.** Since the hotfix, a Tool Head created under a printer as `<printer>-<n>` joins its toolhead list, so Add-child could be offered with the next `<printer>-<n>` pre-filled. | Re-enables what [Group 34](34-location-tree-cluster.md)'s add-redesign (S1–S4) suppressed on printer topology. |
| **44.5** | **Dual-role printer → multi-head: the removal guard over-counts.** *"once any `CORE1-n` head holds a spool, removing the `CORE1` self-entry is blocked by a prefix-matched 'spools are stored there'. Check removed keys with an exact-location spool lookup."* | Small. Only bites a future in-place conversion. |
| **44.6** | **Deleting a printer's last toolhead leaves `PRINTER:<prefix>` pool bindings dangling.** *"the box's Feeds save then fails with a 400 (the Settings guard blocks the same removal). Drop the sentinel when the prefix disappears, or refuse the delete with the Settings guard's reason."* | Small. |
| _(record)_ | **🧪 `test_each_row_has_minimum_schema_for_its_type` relaxed 2026-10-08.** The legacy columns are no longer required, *"with the proper fix tracked by the epic above."* | Already done as a relaxation. The schema this group defines replaces the 11-key CSV-import high-water mark. |

**Related, owned elsewhere:**
- **On-device filament storage** → cross-referenced in [Group 37](37-location-system-redesign.md), since the buglist says to evaluate it with the location redesign. If it becomes a "Spool Holder" Type under the Printer row, this group's printer model is where it attaches.
- **Bulk move treats a multi-head Printer row as single-occupancy** → [Group 40](40-slot-picker.md) 40.0a (the Printer-row placement rule).
- **Toolhead label display mode** → [Group 46](46-quick-fix-sweep-2026-10.md) 46.3 (a global setting now). A per-printer version would hang off this group's model and Group 35's map type.
- **The deduct ledger and the review stores key on `printer::job_id` by Name** ([Group 43](43-deduct-recovery.md), [Group 22](22-filabridge-phase2-detection-deduct-followups.md)). A re-key here must migrate them.

## The design pass (deliver a doc, then ask Derek)

At minimum, the epic asks:
1. **What identifies a printer?** A stable id that is neither the Name nor the LocationID prefix. Compare at least two options:
   - keep the Printer row's LocationID as the id, so a rename becomes a display-Name change only;
   - add a new opaque id field.
2. **How are heads attached and re-ordered?** Today it's the `<printer>-<n>` prefix plus the `toolheads[]` position. Position = slicer tool index (the 2026-09-29 hotfix convention).
3. **Where does the connection live?** On the row today, edited in Settings.
4. **What does per-printer runtime state key on?** The latch, pending fetches, reviews, the ledger and per-printer config are all keyed by Name today (44.2).
5. **The migration for the existing printers.** Prod has `XL` and `RCOI`; `CORE1` is retired there but still referenced by `PRINTER_ROOM_OVERRIDES` and prod's inert `config.json:printer_map`. Dev's fleet differs; see the dev-data refresh in [Group 45](45-sweep-load-tolerance-test-hygiene.md).
6. **An add/configure flow** that creates the row, its heads and its connection in one place, so Settings and the Location Manager stop being two halves of one job.

Derek wants background before any choice: where he meets it, what it's for, and a worked example with his real printers.

## Cross-group notes

- **[Group 35](35-config-cluster.md).** G1 keys the per-printer settings map by display Name. The hotfix already moved the printer-connection grid to LocationID, and 44.2 says to revisit G1. Settle the printer id here first, or re-decide G1 with Derek before Group 35 builds.
- **[Group 37](37-location-system-redesign.md).** Fork 1 (the LocationID model): decide together.
- **[Group 34](34-location-tree-cluster.md).** 44.4 re-enables the Add-child that 34's S1–S4 suppressed on printer topology.
- **[Group 39](39-confirm-on-every-door.md).** Its confirms key on toolhead LocationIDs, which is consistent with a LocationID-based printer id.

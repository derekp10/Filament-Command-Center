"""Startup locations.json migrations + backup pruning (L316 step 2).

Moved verbatim from app.py's import-time block (pre-carve lines 139-390).
app.py calls run_startup_migrations() + resurface_pending_cancel_reviews()
at the SAME import point as before, so the load -> migrate -> timestamped
.bak -> prune -> save ordering and the migration sequence (feeder_map ->
Phase 1A parent_id -> Phase 3 printer rows -> Phase 3.5 immediate parents ->
Phase 5 shelf grouping -> Phase 4 toolheads prime-only) are unchanged.
Each block is individually try/except-wrapped: a migration failure must
never prevent boot.

Python 3.9 runtime (the container image) — keep syntax 3.9-safe.
"""
import os

import state  # type: ignore
import config_loader  # type: ignore
import locations_db  # type: ignore
import cancel_review_store  # type: ignore


# L347 follow-up — prune old locations.json.pre-*.bak migration backups.
# Each migration that fires writes a timestamped .bak; nothing deletes
# them. A long-running prod install with several schema migrations would
# accumulate one per migration per restart-after-edit.
#
# Pre-carve this def had to sit ABOVE the migration block in app.py (the
# 2026-06-01 NameError incident — see the L347 comment history); now the
# module structure enforces that ordering.
MAX_LOCATIONS_BACKUPS = 5


def _prune_locations_backups(json_file_path=None, keep=MAX_LOCATIONS_BACKUPS):
    """Keep at most `keep` of the most-recently-modified
    `locations.json.pre-*.bak` files alongside `json_file_path`. Returns
    the list of deleted paths (empty when under the cap). Failures
    swallow themselves so a permissions issue can't break startup."""
    import glob
    if json_file_path is None:
        json_file_path = locations_db.JSON_FILE
    pattern = f"{json_file_path}.pre-*.bak"
    try:
        matches = glob.glob(pattern)
    except Exception:
        return []
    if len(matches) <= keep:
        return []
    try:
        matches.sort(key=lambda p: os.path.getmtime(p))
    except Exception:
        # If mtime lookup fails (permissions / race) fall through to
        # filename sort — the timestamp in the filename gives the right
        # order as a backstop.
        matches.sort()
    victims = matches[:-keep]
    deleted = []
    for p in victims:
        try:
            os.remove(p)
            deleted.append(p)
        except Exception:
            pass
    return deleted


def run_startup_migrations():
    """The six idempotent locations.json migrations, in their load-bearing
    order, plus the unconditional startup backup prune. Called once from
    app.py at import time (the pre-carve position)."""
    # One-time feeder_map → slot_targets migration. Kept behind an explicit
    # `feeder_map` key check so old installs that still have it get upgraded
    # automatically the first time they boot the new code. No-op on modern
    # installs where the key has been removed.
    #
    # Safety: the migration is purely additive (only sets extra.slot_targets
    # on Dryer Box records; never removes keys). Spool data lives in
    # Spoolman's DB and is untouched. Before the first successful migration
    # we still write a timestamped backup of locations.json so there's a
    # recovery path if anything ever goes wrong on a production restart.
    try:
        _startup_cfg = config_loader.load_config()
        _legacy_feeder_map = _startup_cfg.get('feeder_map') or {}
        if _legacy_feeder_map:
            _startup_locs = locations_db.load_locations_list()
            _migrated, _changed = locations_db.migrate_feeder_map_if_needed(
                _startup_locs, _legacy_feeder_map
            )
            if _changed:
                # Backup before persisting — cheap insurance.
                try:
                    import shutil, time as _t
                    _stamp = _t.strftime('%Y%m%d-%H%M%S')
                    _backup = f"{locations_db.JSON_FILE}.pre-feedermap-migration-{_stamp}.bak"
                    shutil.copy2(locations_db.JSON_FILE, _backup)
                    state.logger.info(f"📦 Backed up locations.json → {_backup}")
                    _prune_locations_backups()
                except Exception as _bk_err:
                    state.logger.warning(f"Could not write pre-migration backup: {_bk_err}")
                locations_db.save_locations_list(_migrated)
                state.logger.info("💾 Legacy feeder_map migrated into locations.json — you can safely delete feeder_map from config.json now.")
    except Exception as _mig_err:
        state.logger.error(f"feeder_map migration skipped due to error: {_mig_err}")

    # Phase-1A locations schema migration: backfill `parent_id` on every row.
    # Purely additive — no consumer reads parent_id yet, so a defect here cannot
    # affect dashboard rendering, scanning, smart-move, or any UI surface. Sits
    # after the feeder_map migration so any rows it touched also get parent_id.
    # Idempotent on second boot. See Feature-Buglist.md "[CRITICAL DESIGN —
    # blocks Project Color Loadout]" for the multi-phase plan.
    try:
        _phase1a_locs = locations_db.load_locations_list()
        _phase1a_migrated, _phase1a_changed = locations_db.migrate_parent_ids_if_needed(_phase1a_locs)
        if _phase1a_changed:
            try:
                import shutil, time as _t
                _stamp = _t.strftime('%Y%m%d-%H%M%S')
                _backup = f"{locations_db.JSON_FILE}.pre-parent-id-migration-{_stamp}.bak"
                shutil.copy2(locations_db.JSON_FILE, _backup)
                state.logger.info(f"📦 Backed up locations.json → {_backup}")
                _prune_locations_backups()
            except Exception as _bk_err:
                state.logger.warning(f"Could not write pre-parent-id-migration backup: {_bk_err}")
            locations_db.save_locations_list(_phase1a_migrated)
            state.logger.info("💾 parent_id backfilled across locations.json — Phase-1A migration complete.")
    except Exception as _p1a_err:
        state.logger.error(f"parent_id migration skipped due to error: {_p1a_err}")

    # L271 Phase 3 — first-class Printer rows. Persist each printer declared in
    # config.json:printer_map as a Type:"Printer" row in locations.json so the
    # /api/locations synthesizer no longer has to conjure them at runtime. Sits
    # after the parent_id backfill so the new rows are parent_id-stamped (None for
    # now — printers stay top-level roots; room-nesting is a later phase per
    # Derek 2026-06-03). Also cleans the duplicate blank-Type CORE1 stub. Idempotent
    # on second boot (a printer that already has a Type:"Printer" row is skipped);
    # timestamped backup before the first write for a prod-restart recovery path.
    try:
        _p3_cfg = config_loader.load_config()
        _p3_pm = _p3_cfg.get('printer_map', {}) or {}
        _p3_locs = locations_db.load_locations_list()
        _p3_migrated, _p3_changed = locations_db.migrate_printers_to_rows_if_needed(_p3_locs, _p3_pm)
        if _p3_changed:
            try:
                import shutil, time as _t
                _stamp = _t.strftime('%Y%m%d-%H%M%S')
                _backup = f"{locations_db.JSON_FILE}.pre-printer-rows-migration-{_stamp}.bak"
                shutil.copy2(locations_db.JSON_FILE, _backup)
                state.logger.info(f"📦 Backed up locations.json → {_backup}")
                _prune_locations_backups()
            except Exception as _bk_err:
                state.logger.warning(f"Could not write pre-printer-rows-migration backup: {_bk_err}")
            if locations_db.save_locations_list(_p3_migrated):
                state.logger.info("💾 First-class Printer rows written across locations.json — L271 Phase 3 migration complete.")
            else:
                state.logger.error("❌ L271 Phase 3 printer-rows migration save FAILED — locations.json left unchanged; will retry next boot.")
    except Exception as _p3_err:
        state.logger.error(f"printer-rows migration skipped due to error: {_p3_err}")

    # L271 Phase 3.5 — true multi-level nesting. Re-derive every row's parent_id
    # from the flat first-segment to its IMMEDIATE parent (cart-row→cart, …) and
    # nest printers under their room (XL→LR auto-derived from its toolheads'
    # Location; CORE1→CR via the recorded override). MUST run AFTER the Phase 3
    # printer-rows migration (it keys printers off Type:"Printer") and after the
    # Phase 1A backfill (it only re-derives rows still carrying the flat default).
    # Idempotent on second boot (changed=False); respects operator-set parent_ids;
    # timestamped backup before the first write for a prod-restart recovery path.
    try:
        _p35_locs = locations_db.load_locations_list()
        _p35_migrated, _p35_changed = locations_db.migrate_immediate_parent_ids_if_needed(_p35_locs)
        if _p35_changed:
            try:
                import shutil, time as _t
                _stamp = _t.strftime('%Y%m%d-%H%M%S')
                _backup = f"{locations_db.JSON_FILE}.pre-immediate-parent-migration-{_stamp}.bak"
                shutil.copy2(locations_db.JSON_FILE, _backup)
                state.logger.info(f"📦 Backed up locations.json → {_backup}")
                _prune_locations_backups()
            except Exception as _bk_err:
                state.logger.warning(f"Could not write pre-immediate-parent-migration backup: {_bk_err}")
            if locations_db.save_locations_list(_p35_migrated):
                state.logger.info("💾 parent_id re-derived to immediate parents + printers nested under rooms — L271 Phase 3.5 migration complete.")
            else:
                state.logger.error("❌ L271 Phase 3.5 immediate-parent migration save FAILED — locations.json left unchanged; will retry next boot.")
    except Exception as _p35_err:
        state.logger.error(f"immediate-parent migration skipped due to error: {_p35_err}")

    # L271 Phase 5 — shelf grouping. Synthesize the intermediate Wall + Row rows so
    # shelf sections nest Room → Wall → Row → Shelf instead of flat under the room
    # (the wall/row levels previously lived only in the LocationID string). Runs
    # AFTER the Phase 3.5 immediate-parent pass; self-contained (sets the sections'
    # parent_id itself) so order is non-critical and the result is a fixpoint for
    # 3.5 too. Idempotent on second boot; respects operator-set parent_ids;
    # timestamped backup before the first write for a prod-restart recovery path.
    try:
        _p5_locs = locations_db.load_locations_list()
        _p5_migrated, _p5_changed = locations_db.migrate_shelf_grouping_rows_if_needed(_p5_locs)
        if _p5_changed:
            try:
                import shutil, time as _t
                _stamp = _t.strftime('%Y%m%d-%H%M%S')
                _backup = f"{locations_db.JSON_FILE}.pre-wall-row-synthesis-migration-{_stamp}.bak"
                shutil.copy2(locations_db.JSON_FILE, _backup)
                state.logger.info(f"📦 Backed up locations.json → {_backup}")
                _prune_locations_backups()
            except Exception as _bk_err:
                state.logger.warning(f"Could not write pre-wall-row-synthesis-migration backup: {_bk_err}")
            if locations_db.save_locations_list(_p5_migrated):
                state.logger.info("💾 Wall/Row grouping rows synthesized + shelves nested — L271 Phase 5 migration complete.")
            else:
                state.logger.error("❌ L271 Phase 5 shelf-grouping migration save FAILED — locations.json left unchanged; will retry next boot.")
    except Exception as _p5_err:
        state.logger.error(f"shelf-grouping migration skipped due to error: {_p5_err}")

    # L271 Phase 4 (step 1 → step 4) — fold config.json:printer_map into a
    # `toolheads[]` array on each first-class Type:"Printer" row. MUST run AFTER the
    # Phase 3 printer-rows migration (it keys off Type:"Printer" rows). Timestamped
    # backup before the first write for a prod-restart recovery path.
    #
    # step 4 (the cutover): PRIME-ONLY. The rows are now the single source of truth
    # for edits (the /api/printer_map PUT writes them); config:printer_map survives
    # only as the boot-time priming seed. So this fold may PRIME a never-folded row
    # (a fresh deploy — e.g. prod's first boot after the rows exist but carry no
    # toolheads[] yet) but must NEVER overwrite an already-folded row, or it would
    # revert a UI edit from the now-vestigial config seed on the next reboot.
    try:
        _p4_cfg = config_loader.load_config()
        _p4_pm = _p4_cfg.get('printer_map', {}) or {}
        _p4_locs = locations_db.load_locations_list()
        _p4_migrated, _p4_changed = locations_db.migrate_printer_map_to_toolheads_if_needed(
            _p4_locs, _p4_pm, prime_only=True)
        if _p4_changed:
            try:
                import shutil, time as _t
                _stamp = _t.strftime('%Y%m%d-%H%M%S')
                _backup = f"{locations_db.JSON_FILE}.pre-toolheads-migration-{_stamp}.bak"
                shutil.copy2(locations_db.JSON_FILE, _backup)
                state.logger.info(f"📦 Backed up locations.json → {_backup}")
                _prune_locations_backups()
            except Exception as _bk_err:
                state.logger.warning(f"Could not write pre-toolheads-migration backup: {_bk_err}")
            if locations_db.save_locations_list(_p4_migrated):
                state.logger.info("💾 printer_map folded into Printer-row toolheads[] — L271 Phase 4 step-1 migration complete.")
            else:
                state.logger.error("❌ L271 Phase 4 toolheads migration save FAILED — locations.json left unchanged; will retry next boot.")
    except Exception as _p4_err:
        state.logger.error(f"toolheads migration skipped due to error: {_p4_err}")

    # L347 follow-up — also prune at startup so accumulated backups from
    # previous boots get trimmed even when no migration fires this boot.
    # Cheap glob; idempotent under the cap.
    try:
        _pruned = _prune_locations_backups()
        if _pruned:
            state.logger.info(f"🧹 Pruned {len(_pruned)} old locations.json backup(s)")
    except Exception as _prune_err:
        state.logger.warning(f"locations.json backup prune skipped: {_prune_err}")


def resurface_pending_cancel_reviews():
    """Re-surface any cancelled-print reviews that outlived a restart. The
    pending store persists, but the activity log (the "🛑 Review" button's
    home) is in-memory, so without this a pending review would be invisible
    after a reboot even though it's still on disk (§9.7 "never silently
    lost"). Emit one log line per pending so the button reappears."""
    try:
        _pending_reviews = cancel_review_store.list_pending()
        for _pr in _pending_reviews:
            state.add_log_entry(
                f"🛑 Pending cancel review from a previous session: {_pr.get('printer_name')} "
                f"— {_pr.get('total_grams')}g across {len(_pr.get('spools', []))} spool(s). Review to confirm/dismiss.",
                "WARNING", "ffaa00",
                meta={"type": "cancel_deduct_pending",
                      "printer_name": _pr.get('printer_name'), "job_id": _pr.get('job_id')})
        if _pending_reviews:
            state.logger.info(f"🛑 Re-surfaced {len(_pending_reviews)} pending cancel review(s) from disk.")
    except Exception as _cr_err:
        state.logger.warning(f"pending cancel-review re-surface skipped: {_cr_err}")

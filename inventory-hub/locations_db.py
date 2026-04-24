import os
import json
import csv
import shutil
import state  # type: ignore

# Runtime state lives under `data/` so a broad .gitignore rule keeps it
# out of source control. See data/README.md for the rationale — in short:
# dev testing kept accidentally committing locations.json and pull on prod
# would clobber live bindings. Moving to a dedicated subtree lets us
# blanket-ignore everything that isn't tracked documentation.
_DATA_DIR = 'data'
JSON_FILE = os.path.join(_DATA_DIR, 'locations.json')
_LEGACY_JSON_FILE = 'locations.json'  # former root-level path, auto-migrated below
CSV_FILE = '3D Print Supplies - Locations.csv'

# Location Type constants used for Dryer Box / Toolhead logic.
DRYER_BOX_TYPE = 'Dryer Box'
TOOLHEAD_TYPES = {'Tool Head', 'MMU Slot', 'No MMU Direct Load'}


def _ensure_data_dir():
    """Make sure the parent directory of JSON_FILE exists before any
    read/write. Reads JSON_FILE at call time so tests that monkeypatch it
    to a tmp location create the right directory there. Idempotent."""
    parent = os.path.dirname(JSON_FILE)
    if parent and not os.path.isdir(parent):
        try:
            os.makedirs(parent, exist_ok=True)
        except Exception as e:
            state.logger.error(f"Could not create data directory {parent!r}: {e}")


def _ensure_runtime_migration():
    """One-time move: if prod still has locations.json at the repo root (the
    legacy location) but not under data/, move it. Silent no-op once
    the new path exists. Logged once so the operator can confirm.
    """
    if os.path.exists(JSON_FILE):
        return  # already migrated
    if not os.path.exists(_LEGACY_JSON_FILE):
        return  # nothing to move (fresh install or already-migrated host)
    _ensure_data_dir()
    try:
        shutil.move(_LEGACY_JSON_FILE, JSON_FILE)
        state.logger.info(
            f"📦 Migrated runtime state: {_LEGACY_JSON_FILE} → {JSON_FILE} "
            "(runtime files now live under data/ so git pull can't clobber them)"
        )
    except Exception as e:
        state.logger.error(f"Could not migrate {_LEGACY_JSON_FILE} → {JSON_FILE}: {e}")

def _ensure_json_migration():
    """
    Production-Safe Migration Strategy:
    If locations.json doesn't exist but the old Locations.csv does, we
    convert the CSV to JSON, save it, and rename the CSV to a backup file.
    """
    if os.path.exists(JSON_FILE) or not os.path.exists(CSV_FILE):
        return

    state.logger.info("🔄 Commencing one-time migration from CSV to JSON...")
    
    migrated_locs = []
    try:
        with open(CSV_FILE, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('LocationID'): 
                    migrated_locs.append(dict(row))
                    
        # Save to JSON
        with open(JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(migrated_locs, f, indent=4)
            
        # Protect original CSV
        backup_path = CSV_FILE.replace(".csv", "_BACKUP.csv")
        os.rename(CSV_FILE, backup_path)
        
        state.logger.info(f"✅ Migration successful! {len(migrated_locs)} locations migrated. Old CSV renamed to {backup_path}")
    except Exception as e:
        state.logger.error(f"❌ Migration Error: {e}")

def load_locations_list():
    """Loads location configurations from the JSON file."""
    _ensure_data_dir()
    _ensure_runtime_migration()
    _ensure_json_migration()

    if not os.path.exists(JSON_FILE):
        return []
        
    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Ensure we always return a list
            if isinstance(data, list):
                return data
            return []
    except Exception as e: 
        state.logger.error(f"JSON Read Error: {e}")
    return []

def save_locations_list(new_list):
    """Saves location configurations to the JSON file."""
    if not new_list: return
    try:
        _ensure_data_dir()
        with open(JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(new_list, f, indent=4)
        state.logger.info("💾 Locations JSON updated")
    except Exception as e:
        state.logger.error(f"JSON Write Error: {e}")


# ---------------------------------------------------------------------------
# Dryer-Box ↔ Toolhead bindings (Phase 2)
# ---------------------------------------------------------------------------

def _find_location(loc_list, loc_id):
    """Case-insensitive lookup — returns (index, row) or (None, None)."""
    if not loc_id:
        return None, None
    needle = loc_id.strip().upper()
    for i, row in enumerate(loc_list):
        if str(row.get('LocationID', '')).strip().upper() == needle:
            return i, row
    return None, None


def _bindings_from_row(row):
    """Extract slot_targets dict from a location row's extra field (safe)."""
    extra = row.get('extra') or {}
    targets = extra.get('slot_targets')
    if isinstance(targets, dict):
        return {str(k): (None if v in (None, '') else str(v)) for k, v in targets.items()}
    return {}


def migrate_feeder_map_if_needed(loc_list, feeder_map):
    """One-time import: seed each Dryer Box's slot_targets from the legacy
    `feeder_map` entry (`PM-DB-1: XL-1` becomes `slot_targets: {"1": "XL-1"}`).

    Idempotent — skips boxes that already have slot_targets on disk.
    Returns (mutated_list, changed_bool).
    """
    if not feeder_map:
        return loc_list, False

    changed = False
    for row in loc_list:
        if row.get('Type') != DRYER_BOX_TYPE:
            continue
        loc_id = str(row.get('LocationID', '')).strip()
        if not loc_id or loc_id not in feeder_map:
            continue
        if _bindings_from_row(row):
            continue  # already migrated / user-edited; don't clobber
        target = feeder_map[loc_id]
        if not target:
            continue
        extra = dict(row.get('extra') or {})
        extra['slot_targets'] = {"1": str(target)}
        row['extra'] = extra
        state.logger.info(
            f"🔄 Migrated feeder_map entry: {loc_id} → slot_targets={{'1': '{target}'}}"
        )
        changed = True
    return loc_list, changed


def validate_slot_targets(slot_targets, loc_list, printer_map):
    """Return a list of (slot, target, reason) tuples for any invalid
    entries. Empty list means the mapping is valid.

    Rules: every non-null/non-empty target must be a known LocationID
    whose Type is a toolhead type AND must be present in printer_map.
    """
    if not isinstance(slot_targets, dict):
        return [("*", slot_targets, "slot_targets must be an object")]

    errors = []
    loc_map = {
        str(r.get('LocationID', '')).strip().upper(): r
        for r in loc_list
    }
    for slot, target in slot_targets.items():
        if target in (None, '', 'null', 'None'):
            continue  # unassigned — valid
        tgt_norm = str(target).strip().upper()
        row = loc_map.get(tgt_norm)
        if not row:
            errors.append((str(slot), target, "unknown location"))
            continue
        if row.get('Type') not in TOOLHEAD_TYPES:
            errors.append((str(slot), target, f"type '{row.get('Type')}' is not a toolhead"))
            continue
        if tgt_norm not in {k.upper() for k in printer_map.keys()}:
            errors.append((str(slot), target, "not registered in printer_map"))
    return errors


def get_dryer_box_bindings(loc_id):
    """Read slot_targets for a dryer box. Returns {} if the box has none
    or if loc_id isn't a Dryer Box."""
    loc_list = load_locations_list()
    _, row = _find_location(loc_list, loc_id)
    if not row or row.get('Type') != DRYER_BOX_TYPE:
        return None  # distinct from empty-dict to signal "not found"
    return _bindings_from_row(row)


def get_dryer_box_slot_order(loc_id):
    """Return the render order for a dryer box's slot grid ('ltr' or 'rtl').
    Defaults to 'ltr' when unset. Returns None if the location is missing or
    isn't a Dryer Box.
    """
    loc_list = load_locations_list()
    _, row = _find_location(loc_list, loc_id)
    if not row or row.get('Type') != DRYER_BOX_TYPE:
        return None
    extra = row.get('extra') or {}
    order = str(extra.get('slot_order') or '').strip().lower()
    return order if order in ('ltr', 'rtl') else 'ltr'


def set_dryer_box_slot_order(loc_id, order):
    """Persist a dryer box's slot render order ('ltr' or 'rtl'). Anything
    else falls back to 'ltr'. Returns (ok_bool, msg_or_none)."""
    order = str(order or '').strip().lower()
    if order not in ('ltr', 'rtl'):
        return False, f"invalid order '{order}' (expected 'ltr' or 'rtl')"
    loc_list = load_locations_list()
    idx, row = _find_location(loc_list, loc_id)
    if idx is None:
        return False, "location not found"
    if row.get('Type') != DRYER_BOX_TYPE:
        return False, f"type '{row.get('Type')}' is not a Dryer Box"
    extra = dict(row.get('extra') or {})
    extra['slot_order'] = order
    row['extra'] = extra
    loc_list[idx] = row
    save_locations_list(loc_list)
    return True, None


def set_dryer_box_bindings(loc_id, slot_targets, printer_map):
    """Validate + persist per-slot bindings for a dryer box.

    Returns (ok_bool, errors_list, warnings_list). Warnings don't block the
    save — they surface conditions the user should know about:
      - the same toolhead appearing on >1 slot within this box
      - the same toolhead already bound by a different dryer box (conflict)

    On success, errors_list is empty and extra.slot_targets is written.
    """
    loc_list = load_locations_list()
    idx, row = _find_location(loc_list, loc_id)
    if idx is None:
        return False, [("*", loc_id, "location not found")], []
    if row.get('Type') != DRYER_BOX_TYPE:
        return False, [("*", loc_id, f"type '{row.get('Type')}' is not a Dryer Box")], []

    errors = validate_slot_targets(slot_targets, loc_list, printer_map)
    if errors:
        return False, errors, []

    # Build the cleaned map up front so we can analyse it for warnings.
    clean = {}
    for slot, target in slot_targets.items():
        if target in (None, '', 'null', 'None'):
            continue
        clean[str(slot)] = str(target).strip().upper()

    warnings = []

    # 1) Same toolhead appearing on multiple slots within this box.
    reverse = {}
    for slot, target in clean.items():
        reverse.setdefault(target, []).append(slot)
    for target, slots in reverse.items():
        if len(slots) > 1:
            warnings.append((
                ",".join(sorted(slots)), target,
                f"multiple slots in this box bind to {target} (possible duplicate)"
            ))

    # 2) Same toolhead already bound by a different dryer box.
    my_id_up = str(loc_id).strip().upper()
    for other in loc_list:
        if other.get('Type') != DRYER_BOX_TYPE:
            continue
        if str(other.get('LocationID', '')).strip().upper() == my_id_up:
            continue
        other_targets = (other.get('extra') or {}).get('slot_targets') or {}
        for other_slot, other_target in other_targets.items():
            other_up = str(other_target or '').strip().upper()
            if other_up and other_up in reverse:
                warnings.append((
                    reverse[other_up][0], other_up,
                    f"already bound by {other['LocationID']} slot {other_slot}"
                ))

    extra = dict(row.get('extra') or {})
    extra['slot_targets'] = clean
    row['extra'] = extra
    loc_list[idx] = row
    save_locations_list(loc_list)
    return True, [], warnings


def get_bindings_for_machine(printer_name, printer_map):
    """Aggregate all (box, slot) → toolhead mappings that feed a given
    printer. Returns a dict shaped for /api/machine/<name>/toolhead_slots:

    {
      "printer_name": "🦝 XL",
      "toolheads": {
        "XL-1": [{"box": "PM-DB-XL-L", "slot": "1"}, ...],
        ...
      }
    }

    Toolheads with zero bindings get an empty list so the frontend can
    render "Link a slot…" placeholders without a separate lookup.
    """
    loc_list = load_locations_list()
    # Collect every toolhead location ID that belongs to this printer.
    toolheads = {
        loc_id.upper(): []
        for loc_id, cfg in (printer_map or {}).items()
        if cfg.get('printer_name') == printer_name
    }
    for row in loc_list:
        if row.get('Type') != DRYER_BOX_TYPE:
            continue
        box_id = str(row.get('LocationID', '')).strip()
        for slot, target in _bindings_from_row(row).items():
            if not target:
                continue
            target_up = target.strip().upper()
            if target_up in toolheads:
                toolheads[target_up].append({"box": box_id, "slot": slot})
    return {"printer_name": printer_name, "toolheads": toolheads}
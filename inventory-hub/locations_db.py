import os
import json
import csv
import shutil
import tempfile
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
    """Loads location configurations from the JSON file.

    Returns [] only when the file legitimately doesn't exist or has a
    non-list root (a fresh-install or schema-mismatch shape). On a real
    JSON parse failure (corrupt file from a manual edit gone wrong, etc.)
    we propagate as LocationsCorruptError so the operator sees the
    failure on the very first request — silently returning [] previously
    masked an XL-3 syntax error and surfaced as the entire dashboard
    losing names/types/grouping.
    """
    _ensure_data_dir()
    _ensure_runtime_migration()
    _ensure_json_migration()

    if not os.path.exists(JSON_FILE):
        return []

    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        state.logger.critical(
            f"💥 locations.json corrupt at {JSON_FILE}:{e.lineno}:{e.colno} — {e.msg}. "
            "Fix the file (manual edit gone wrong?) before the dashboard can render."
        )
        raise LocationsCorruptError(JSON_FILE, e) from e
    except Exception as e:
        state.logger.error(f"JSON Read Error: {e}")
        return []

    # Ensure we always return a list
    if isinstance(data, list):
        return data
    return []


class LocationsCorruptError(RuntimeError):
    """Raised when locations.json fails to parse. Carries the file path
    and the underlying JSONDecodeError so callers can surface a clear
    message to the operator instead of silently rendering an empty UI."""

    def __init__(self, path, decode_error):
        self.path = path
        self.decode_error = decode_error
        super().__init__(
            f"locations.json corrupt at {path} "
            f"(line {decode_error.lineno}, col {decode_error.colno}): {decode_error.msg}"
        )

def _write_locations_atomic(new_list):
    """Inner write helper — performs ONE atomic write attempt. Returns the
    path actually written to (i.e. JSON_FILE on success). Raises on failure.

    Two hardening notes vs. the previous fixed `.tmp` approach (L37):

    (1) Per-call unique temp filename via `tempfile.NamedTemporaryFile`
        instead of `JSON_FILE + ".tmp"`. Flask is multi-threaded; two
        concurrent writers sharing the same `.tmp` would corrupt each
        other's pending content before `os.replace`. A unique temp name
        per call eliminates that race.

    (2) Post-write read-back-and-verify (in `save_locations_list` below):
        after `os.replace`, immediately re-open + `json.loads` the
        target. If parsing fails, the caller logs critical and retries
        once. The previous corruption ("valid content + duplicate tail")
        could occur without raising on write — verify-after-write is the
        tripwire that would catch it.
    """
    _ensure_data_dir()
    parent_dir = os.path.dirname(JSON_FILE) or '.'
    # delete=False so we manage the lifecycle (rename or unlink); mode='w'
    # + encoding='utf-8' matches the prior text-write behaviour.
    tmp = tempfile.NamedTemporaryFile(
        mode='w', encoding='utf-8',
        dir=parent_dir, prefix='locations.', suffix='.tmp',
        delete=False,
    )
    tmp_path = tmp.name
    try:
        try:
            json.dump(new_list, tmp, indent=4)
            tmp.flush()
            os.fsync(tmp.fileno())
        finally:
            tmp.close()
        os.replace(tmp_path, JSON_FILE)
        return JSON_FILE
    except Exception:
        # Clean up the temp file if it survived the attempt (os.replace
        # would have consumed it on success; on failure it may still exist).
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        raise


def _verify_locations_file(expected_list):
    """Re-read JSON_FILE and confirm it parses to a list. Returns
    (ok: bool, detail: str). On parse failure, detail is the underlying
    error message + a short prefix of the on-disk bytes for diagnosis.
    """
    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        parsed = json.loads(content)
        if not isinstance(parsed, list):
            return False, f"parsed value is not a list (got {type(parsed).__name__})"
        return True, "ok"
    except (OSError, json.JSONDecodeError) as e:
        # Capture the first ~4KB so we can see WHERE the file went bad
        # without flooding the log on a multi-megabyte runaway.
        try:
            with open(JSON_FILE, 'rb') as f:
                snippet = f.read(4096).decode('utf-8', errors='replace')
        except OSError:
            snippet = '(could not re-read file)'
        return False, f"{e!r} — file prefix: {snippet!r}"


def save_locations_list(new_list):
    """Saves location configurations to the JSON file via atomic write
    with a verify-after-write tripwire.

    Writes a per-call uniquely-named temp file in the same directory,
    fsyncs, then `os.replace`s onto JSON_FILE (atomic on POSIX and NTFS).
    Immediately re-reads + `json.loads`es the result; on parse failure
    (the "valid content + duplicate tail" symptom seen on dev 2026-04-28),
    logs critical and retries the write ONCE. After the retry, surfaces a
    final critical log if it still fails — the caller already got
    "success" by then, so we don't raise.
    """
    # Returns True when the new list is durably persisted + verified, False on
    # any failure path (refused-empty, atomic-write error, or verify-after-write
    # never recovering). Historically returned None everywhere; callers that
    # ignore the result are unaffected, but a migration can now log honestly
    # instead of claiming success after a silent save failure.
    if not new_list:
        return False
    try:
        _write_locations_atomic(new_list)
    except Exception as e:
        state.logger.error(f"JSON Write Error (atomic-replace failed): {e}")
        return False

    ok, detail = _verify_locations_file(new_list)
    if ok:
        state.logger.info("💾 Locations JSON updated")
        return True

    # Tripwire — the file replaced cleanly but the on-disk content doesn't
    # parse. Log critical with diagnostics, then retry the write once.
    state.logger.critical(
        f"locations.json verify-after-write FAILED at {JSON_FILE!r}: {detail}. "
        f"Retrying once."
    )
    try:
        _write_locations_atomic(new_list)
    except Exception as e:
        state.logger.critical(
            f"locations.json verify-after-write retry ALSO failed (atomic-replace error): {e}"
        )
        return False

    ok2, detail2 = _verify_locations_file(new_list)
    if ok2:
        state.logger.warning("locations.json verify-after-write recovered on retry.")
        return True
    state.logger.critical(
        f"locations.json verify-after-write retry STILL failed: {detail2}. "
        f"On-disk state may be corrupt — operator inspection required."
    )
    return False


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


def derive_parent_id_from_prefix(loc_id):
    """Compute the legacy prefix-based parent for a LocationID.

    Returns the uppercased substring before the first '-', or None if the
    LocationID has no '-' (top-level rows like rooms have no parent). Used
    by the Phase-1A migration and by resolve_parent() as a fallback when a
    row has no explicit parent_id yet.
    """
    if not isinstance(loc_id, str):
        return None
    s = loc_id.strip()
    if '-' not in s:
        return None
    return s.split('-', 1)[0].upper()


def resolve_parent(row_or_id, loc_list=None):
    """Return the parent LocationID for a row dict or a LocationID string.

    Prefers an explicit `parent_id` on the row when present (Phase-1A and
    later schema). Falls back to derive_parent_id_from_prefix() for rows
    that haven't been migrated yet — keeps callers safe during the gradual
    consumer-migration phases. `loc_list` is accepted for forward-compat
    (Phase 3 will validate the FK against it) and ignored in Phase 1A.
    """
    if isinstance(row_or_id, dict):
        if 'parent_id' in row_or_id:
            explicit = row_or_id.get('parent_id')
            if explicit is None:
                return None
            s = str(explicit).strip()
            return s.upper() if s else None
        return derive_parent_id_from_prefix(row_or_id.get('LocationID'))
    return derive_parent_id_from_prefix(row_or_id)


# Prefixes that are NOT real rooms — the prefix-derivation can produce them, but
# they must never be treated as a room (no virtual room, no room rollup, no eject
# "return to room"). PM = Polymaker portable boxes, PJ = Project carts, TST/TEST
# = system tests. Single source of truth for the exclusion list that was
# previously inlined in app.py / logic.py / inv_core.js.
PSEUDO_ROOM_PREFIXES = frozenset({"TST", "TEST", "PM", "PJ"})


def build_parent_map(loc_list=None):
    """Return {LocationID_upper: parent_id_upper_or_None} for fast repeated
    hierarchy walks (is_descendant / resolve_room) without re-reading disk per
    call. Honors explicit parent_id via resolve_parent (with prefix fallback).
    Callers in per-spool loops should build this ONCE and pass it down.
    """
    if loc_list is None:
        loc_list = load_locations_list()
    pmap = {}
    for r in loc_list:
        if not isinstance(r, dict):
            continue
        lid = str(r.get('LocationID', '')).strip().upper()
        if not lid:
            continue
        pmap[lid] = resolve_parent(r)  # immediate parent (upper) or None
    return pmap


def _parent_of(loc_upper, parent_map):
    """One hop up the hierarchy for an already-uppercased LocationID. Uses the
    on-disk parent_map when the id is a known row; falls back to prefix
    derivation for an id with no row (a spool sitting at a not-yet-created
    LocationID, or a pseudo-prefix ancestor).
    """
    if loc_upper in parent_map:
        return parent_map[loc_upper]
    return derive_parent_id_from_prefix(loc_upper)


def is_descendant(child, ancestor, parent_map=None, loc_list=None):
    """True if `child` sits STRICTLY beneath `ancestor` anywhere in the
    parent_id chain (self does NOT count — callers test exact equality
    separately). Both compared upper-cased. Cycle-guarded.

    Phase 3.5: replaces the flat ``resolve_parent(child) == ancestor`` child
    test. On a 2-level tree this reduces to the old single-hop equality (a
    row's only ancestor IS its first-segment parent); on a nested tree it
    walks the full chain so a room query reaches its cart-rows / a printer's
    toolheads.
    """
    child_u = str(child or '').strip().upper()
    anc_u = str(ancestor or '').strip().upper()
    if not child_u or not anc_u or child_u == anc_u:
        return False
    if parent_map is None:
        parent_map = build_parent_map(loc_list)
    seen = {child_u}
    cur = _parent_of(child_u, parent_map)
    while cur and cur not in seen:
        if cur == anc_u:
            return True
        seen.add(cur)
        cur = _parent_of(cur, parent_map)
    return False


def resolve_room(row_or_id, parent_map=None, loc_list=None):
    """Walk the parent_id chain up to the TOP-LEVEL ancestor (the room) and
    return its LocationID (upper-cased). Returns "" when the input is empty.

    Phase 3.5: with parent_id storing the IMMEDIATE parent, a deeply-nested
    row's room is its topmost ancestor, not its direct parent — e.g.
    ``CR-CT-1-R1`` → CR-CT-1 → CR. A top-level input (a room/printer root)
    returns itself. Cycle-guarded. Pseudo-prefix exclusion (PM/PJ/TST) is the
    CALLER's contract (see get_room_from_location), not applied here.
    """
    if isinstance(row_or_id, dict):
        start = str(row_or_id.get('LocationID', '')).strip().upper()
    else:
        start = str(row_or_id or '').strip().upper()
    if not start:
        return ""
    if parent_map is None:
        parent_map = build_parent_map(loc_list)
    seen = {start}
    top = start
    cur = _parent_of(start, parent_map)
    while cur and cur not in seen:
        top = cur
        seen.add(cur)
        cur = _parent_of(cur, parent_map)
    return top


def ancestors_of(loc_id, parent_map, include_pseudo=False):
    """Yield each ancestor LocationID (immediate-first) by walking the parent_id
    chain upward. Stops BEFORE a pseudo-prefix (PM/PJ/TST) unless include_pseudo
    is True — so a spool in a PM box never rolls up into a "PM room". Cycle
    -guarded. Used by the /api/locations transitive subtree-occupancy rollup.
    """
    cur = str(loc_id or '').strip().upper()
    if not cur:
        return
    seen = {cur}
    nxt = _parent_of(cur, parent_map)
    while nxt and nxt not in seen:
        if not include_pseudo and nxt in PSEUDO_ROOM_PREFIXES:
            return
        yield nxt
        seen.add(nxt)
        nxt = _parent_of(nxt, parent_map)


def migrate_parent_ids_if_needed(loc_list):
    """One-time backfill: every row gets a `parent_id` field derived from
    its LocationID prefix (or None for top-level rows). Idempotent — skips
    rows that already have the key set (including explicit None).

    Phase 1A of the locations schema refactor (see Feature-Buglist.md
    "[CRITICAL DESIGN — blocks Project Color Loadout]"). Adds the field on
    disk; no consumer reads it yet, so a defect here cannot break dashboard
    rendering or any other surface.

    Returns (mutated_list, changed_bool).
    """
    if not isinstance(loc_list, list):
        return loc_list, False

    changed = False
    for row in loc_list:
        if not isinstance(row, dict):
            continue
        if 'parent_id' in row:
            continue  # already migrated; respect operator-set value
        loc_id = row.get('LocationID')
        parent = derive_parent_id_from_prefix(loc_id)
        row['parent_id'] = parent  # may be None for top-level rows
        state.logger.info(
            f"🔄 Backfilled parent_id: {loc_id} → {parent!r}"
        )
        changed = True
    return loc_list, changed


def _known_printer_prefixes(printer_map):
    """Return the set of uppercase printer LocationID prefixes — i.e. the
    portion of each toolhead LocationID before the first '-'. These are the
    valid suffixes for a `PRINTER:<id>` sentinel slot_target.
    """
    prefixes = set()
    for key in (printer_map or {}).keys():
        ku = str(key).strip().upper()   # strip so a padded key can't yield a "  XL" prefix
        prefixes.add(ku.split('-', 1)[0] if '-' in ku else ku)
    return prefixes


# Location types that legitimately ARE (or hold) a printer's deploy slot, and so
# may be promoted in place to a first-class Printer row. Any OTHER typed row that
# happens to share a printer-prefix LocationID is a collision — left untouched.
TOOLHEAD_TYPES = frozenset({"Tool Head", "MMU Slot", "No MMU Direct Load"})


def _resolve_printer_name(printer_id, printer_map):
    """Friendly display name for a printer LocationID, pulled from printer_map.
    An EXACT key match (e.g. 'CORE1') wins over a toolhead-prefix match
    (e.g. 'XL' ← 'XL-1'.printer_name) so a config that carries both a dash-free
    and dashed key for the same prefix resolves deterministically. Logs a
    warning and falls back to '<id> System' when no printer_name is set.
    """
    pid_u = str(printer_id).strip().upper()
    exact = None
    prefix = None
    for loc_id, info in (printer_map or {}).items():
        name = (info or {}).get('printer_name')
        if not name:
            continue
        lu = str(loc_id).strip().upper()
        if lu == pid_u:
            exact = name
            break
        if prefix is None and lu.startswith(pid_u + '-'):
            prefix = name
    chosen = exact or prefix
    if chosen:
        return chosen
    state.logger.warning(
        f"⚠️ No printer_name in printer_map for {printer_id!r}; using fallback '{printer_id} System'"
    )
    return f"{printer_id} System"


def migrate_printers_to_rows_if_needed(loc_list, printer_map):
    """L271 Phase 3: persist each printer in config.json:printer_map as a
    first-class Type:"Printer" row in locations.json, instead of synthesizing
    it at runtime in /api/locations.

    - Printer set = `_known_printer_prefixes(printer_map)`: the first segment of
      each dashed toolhead key PLUS each dash-free key (e.g. {"XL", "CORE1"}).
    - `parent_id` stays None for now — printers render as top-level roots
      exactly as the synthesizer did (Derek 2026-06-03: "first-class Printers
      now, nest under rooms later"). The nest-later phase sets parent_id to the
      room (recorded: XL → LR, CORE1 → CR) once the tree renders true nesting.
    - XL (no on-disk row): append a fresh Printer row, `Max Spools` "0" (it
      aggregates its 5 XL-* toolhead children).
    - CORE1 (dash-free dual-role: one Tool Head row + a duplicate blank-Type
      stub): promote the typed row in place to Type:"Printer" (keeping its
      `Max Spools` "1" — it IS the single deploy slot) and DELETE the blank
      duplicate. Spools stay at "CORE1" (no Spoolman migration). Extensible to
      N toolhead children later (the planned INDX upgrade) with no schema change.
    - Idempotent: a printer that already has a Type:"Printer" row is skipped, so
      the second boot is a no-op (changed=False).

    Returns (mutated_list, changed_bool). Pure locations.json transform — it
    does NOT touch Spoolman spool locations.
    """
    if not isinstance(loc_list, list):
        return loc_list, False

    printers = _known_printer_prefixes(printer_map)
    if not printers:
        return loc_list, False

    changed = False
    for pid in sorted(printers):
        matches = [
            r for r in loc_list
            if isinstance(r, dict) and str(r.get('LocationID', '')).strip().upper() == pid
        ]
        # Idempotency gate: already first-class → nothing to do for this printer.
        if any(str(r.get('Type', '')).strip().lower() == 'printer' for r in matches):
            continue

        toolheads = [r for r in matches if str(r.get('Type', '')).strip() in TOOLHEAD_TYPES]
        blanks = [r for r in matches if not str(r.get('Type', '')).strip()]
        # Collision guard: a typed row that is NEITHER a toolhead NOR a Printer
        # owns this LocationID (e.g. a Room/Cart hand-given a printer-prefix id).
        # Do NOT corrupt it into a Printer and do NOT append a duplicate — skip
        # and let the operator resolve the clash. (Can't happen for the current
        # XL/CORE1 data; this guards hand-edited / imported prod state.)
        collisions = [
            r for r in matches
            if str(r.get('Type', '')).strip() and str(r.get('Type', '')).strip() not in TOOLHEAD_TYPES
        ]
        if collisions:
            state.logger.warning(
                f"⚠️ Skipping Printer promotion for {pid}: LocationID already exists as a "
                f"{collisions[0].get('Type')!r} row — resolve the collision manually."
            )
            continue

        name = _resolve_printer_name(pid, printer_map)
        if toolheads:
            # Promote the first toolhead row in place (CORE1's Tool Head row),
            # preserving its Max Spools so the deploy-slot capacity survives.
            row = toolheads[0]
            row['Type'] = 'Printer'
            row['Name'] = name
            if 'parent_id' not in row:
                row['parent_id'] = None
            changed = True
            state.logger.info(f"🖨️ Promoted {pid} → first-class Printer row ('{name}')")
        else:
            # No on-disk toolhead row (XL): append a fresh Printer row.
            loc_list.append({
                'LocationID': pid,
                'Name': name,
                'Type': 'Printer',
                'Max Spools': '0',
                'parent_id': None,
            })
            changed = True
            state.logger.info(f"🖨️ Created first-class Printer row {pid} ('{name}')")

        # Drop any blank-Type stub rows for this printer LocationID (identity-based
        # so a value-equal kept row can never be removed by accident).
        for b in blanks:
            loc_list[:] = [r for r in loc_list if r is not b]
            changed = True
            state.logger.info(f"🧹 Removed duplicate blank-Type row for {pid}")

    return loc_list, changed


# Recorded printer→room mapping (L271 plan, Derek 2026-06-03). Used ONLY as a
# fallback when a printer's room can't be auto-derived from a toolhead child's
# Location field — e.g. CORE1 is a dual-role printer with no toolhead children
# and no Location of its own. XL is here too as a belt-and-suspenders, but it
# auto-derives from its XL-* toolheads ("Living Room" → LR).
PRINTER_ROOM_OVERRIDES = {"XL": "LR", "CORE1": "CR"}


def _immediate_parent_from_rows(loc_id, existing_upper):
    """The IMMEDIATE parent of a LocationID = the longest dash-trimmed prefix
    that exists as a real on-disk row. ``CR-CT-1-R1`` → ``CR-CT-1`` (a real
    cart) rather than the flat first-segment ``CR``. Returns None when no
    ancestor prefix is a row (caller falls back to the flat first-segment so a
    PM/PJ/TST box keeps pointing at its virtual-room prefix).
    """
    s = str(loc_id or '').strip().upper()
    if '-' not in s:
        return None
    parts = s.split('-')
    for i in range(len(parts) - 1, 0, -1):
        cand = '-'.join(parts[:i])
        if cand in existing_upper:
            return cand
    return None


def _derive_printer_room(printer_row, loc_list, room_by_name):
    """Best-effort room LocationID for a Printer row. Order:
      1. the printer's own `Location` field matched to a Room row's Name;
      2. a toolhead child's `Location` field (XL-* carry "Living Room" → LR);
      3. the recorded PRINTER_ROOM_OVERRIDES fallback (CORE1 → CR).
    Returns None when nothing resolves (caller leaves parent_id unchanged + warns).
    """
    pid = str(printer_row.get('LocationID', '')).strip().upper()

    own_loc = str(printer_row.get('Location', '')).strip().upper()
    if own_loc and own_loc in room_by_name:
        return room_by_name[own_loc]

    for r in loc_list:
        if not isinstance(r, dict):
            continue
        if str(r.get('Type', '')).strip() not in TOOLHEAD_TYPES:
            continue
        rid = str(r.get('LocationID', '')).strip().upper()
        if not rid.startswith(pid + '-'):
            continue
        loc = str(r.get('Location', '')).strip().upper()
        if loc and loc in room_by_name:
            return room_by_name[loc]

    return PRINTER_ROOM_OVERRIDES.get(pid)


def migrate_immediate_parent_ids_if_needed(loc_list):
    """L271 Phase 3.5: re-derive every row's `parent_id` from the flat
    first-segment (Phase 1A/2.5) to its IMMEDIATE parent, and nest printers
    under their room — so the tree is genuinely multi-level (room→printer→
    toolhead, cart→cart-rows) instead of flat-2-level.

    - Non-printer row → `_immediate_parent_from_rows(lid)` (longest on-disk
      prefix), falling back to the flat first-segment when no ancestor row
      exists (keeps PM/PJ/TST boxes on their virtual-room prefix).
    - Printer row (`Type:"Printer"`) → its room via `_derive_printer_room`.
      A resolved room with no on-disk Room row is rejected (warn, leave as-is).
    - **Idempotent + respects operator overrides:** a row is re-parented ONLY
      when its current `parent_id` still equals its OLD default
      (`derive_parent_id_from_prefix`, i.e. the flat value the earlier
      migrations wrote) AND the new target differs. A row already at its
      immediate target, or carrying a deliberate value that differs from both,
      is left untouched. So the 2nd boot is a no-op (changed=False), and a hand
      re-parent is never clobbered. A pre-1A row with no `parent_id` key at all
      gets the immediate target outright.

    Returns (mutated_list, changed_bool). Pure locations.json transform.
    """
    if not isinstance(loc_list, list):
        return loc_list, False

    existing_upper = {
        str(r.get('LocationID', '')).strip().upper()
        for r in loc_list
        if isinstance(r, dict) and str(r.get('LocationID', '')).strip()
    }
    room_by_name = {}
    for r in loc_list:
        if isinstance(r, dict) and str(r.get('Type', '')).strip().lower() == 'room':
            nm = str(r.get('Name', '')).strip().upper()
            rid = str(r.get('LocationID', '')).strip().upper()
            if nm and rid:
                room_by_name.setdefault(nm, rid)

    changed = False
    for row in loc_list:
        if not isinstance(row, dict):
            continue
        lid = str(row.get('LocationID', '')).strip()
        if not lid:
            continue

        if str(row.get('Type', '')).strip().lower() == 'printer':
            target = _derive_printer_room(row, loc_list, room_by_name)
            if target is not None and target not in existing_upper:
                state.logger.warning(
                    f"⚠️ Printer {lid}: resolved room {target!r} has no on-disk Room row; "
                    f"leaving parent_id unchanged."
                )
                continue
        else:
            target = _immediate_parent_from_rows(lid, existing_upper) or derive_parent_id_from_prefix(lid)

        old_default = derive_parent_id_from_prefix(lid)  # the flat value Phase 1A/2.5 wrote

        if 'parent_id' not in row:
            # Pre-1A row that never got backfilled — set the immediate target now.
            row['parent_id'] = target
            changed = True
            state.logger.info(f"🪜 parent_id set (immediate): {lid} → {target!r}")
            continue

        cur = row.get('parent_id')
        cur_norm = None if cur in (None, '') else str(cur).strip().upper()

        # Only re-derive rows still carrying the OLD flat default; respect overrides.
        if cur_norm == old_default and cur_norm != target:
            row['parent_id'] = target
            changed = True
            state.logger.info(f"🪜 Re-parented {lid}: {cur_norm!r} → {target!r}")

    return loc_list, changed


def is_printer_sentinel(target):
    """True if `target` is a `PRINTER:<id>` sentinel slot_target."""
    if not isinstance(target, str):
        return False
    return target.strip().upper().startswith('PRINTER:')


def validate_slot_targets(slot_targets, loc_list, printer_map):
    """Return a list of (slot, target, reason) tuples for any invalid
    entries. Empty list means the mapping is valid.

    Rules:
      - A non-null/non-empty target must either be a known LocationID whose
        Type is a toolhead type AND is registered in printer_map, OR a
        `PRINTER:<id>` sentinel whose <id> matches a known printer prefix.
    """
    if not isinstance(slot_targets, dict):
        return [("*", slot_targets, "slot_targets must be an object")]

    errors = []
    loc_map = {
        str(r.get('LocationID', '')).strip().upper(): r
        for r in loc_list
    }
    printer_prefixes = _known_printer_prefixes(printer_map)
    for slot, target in slot_targets.items():
        if target in (None, '', 'null', 'None'):
            continue  # unassigned — valid

        if is_printer_sentinel(target):
            suffix = str(target).strip().upper().split(':', 1)[1]
            if not suffix:
                errors.append((str(slot), target, "PRINTER: sentinel missing id"))
            elif suffix not in printer_prefixes:
                errors.append((str(slot), target, f"unknown printer id '{suffix}'"))
            continue

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
        if len(slots) > 1 and not is_printer_sentinel(target):
            warnings.append((
                ",".join(sorted(slots)), target,
                f"multiple slots in this box bind to {target} (possible duplicate)"
            ))

    # 2) Same toolhead already bound by a different dryer box. Printer-pool
    # sentinels are exempt — multiple boxes can legitimately feed the same
    # printer's staging pool without conflicting on any physical toolhead.
    my_id_up = str(loc_id).strip().upper()
    for other in loc_list:
        if other.get('Type') != DRYER_BOX_TYPE:
            continue
        if str(other.get('LocationID', '')).strip().upper() == my_id_up:
            continue
        other_targets = (other.get('extra') or {}).get('slot_targets') or {}
        for other_slot, other_target in other_targets.items():
            other_up = str(other_target or '').strip().upper()
            if other_up and other_up in reverse and not is_printer_sentinel(other_up):
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
      },
      "printer_pool": [
        {"box": "PM-DB-XL-L", "slot": "4"},  # PRINTER:XL sentinel slots
        ...
      ]
    }

    Toolheads with zero bindings get an empty list so the frontend can
    render "Link a slot…" placeholders without a separate lookup.

    `printer_pool` is the set of dryer-box slots bound to the
    `PRINTER:<id>` sentinel that affiliates with this printer (i.e. its
    LocationID prefix). Pool slots are staging/drying slots — they don't
    feed a specific toolhead, but Quick-Swap surfaces them so users can
    deposit buffered spools without leaving the toolhead view.
    """
    loc_list = load_locations_list()
    # Collect every toolhead location ID that belongs to this printer.
    machine_toolhead_ids = [
        loc_id.upper() for loc_id, cfg in (printer_map or {}).items()
        if cfg.get('printer_name') == printer_name
    ]
    toolheads = {th_id: [] for th_id in machine_toolhead_ids}
    # The printer's PRINTER:<id> prefix matches every toolhead's prefix
    # (XL-1 / XL-2 / … all share "XL"). Mirror _known_printer_prefixes.
    machine_prefixes = {
        (th_id.split('-', 1)[0] if '-' in th_id else th_id)
        for th_id in machine_toolhead_ids
    }
    printer_pool = []
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
                continue
            if is_printer_sentinel(target_up):
                suffix = target_up.split(':', 1)[1]
                if suffix in machine_prefixes:
                    printer_pool.append({"box": box_id, "slot": slot})
    return {
        "printer_name": printer_name,
        "toolheads": toolheads,
        "printer_pool": printer_pool,
    }
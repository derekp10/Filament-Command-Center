import csv
import requests
import json
import os
import sys

# Add inventory-hub to path to import config_loader
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'inventory-hub')))
import config_loader

# --- CONFIGURATION ---
SPOOLMAN_IP, _ = config_loader.get_api_urls()
print(f"🔗 Target Spoolman Database: {SPOOLMAN_IP}")
DATA_FOLDER_NAME = "3D Print Data"
LISTS_FILENAME = "3D Print Supplies - Lists.csv"
FILAMENT_FILENAME = "3D Print Supplies - Filament.csv"

# --- PATH FINDER HELPER ---
def find_file(filename):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    for _ in range(4):
        check_path = os.path.join(current_dir, filename)
        if os.path.exists(check_path): return check_path
        data_path = os.path.join(current_dir, DATA_FOLDER_NAME)
        file_path = os.path.join(data_path, filename)
        if os.path.exists(data_path) and os.path.exists(file_path):
            print(f"📂 Found {filename} at: {file_path}")
            return file_path
        parent_dir = os.path.dirname(current_dir)
        if parent_dir == current_dir: break
        current_dir = parent_dir
    print(f"⚠️ Warning: Could not find '{filename}'.")
    return None

# --- API HELPER ---
def create_field(entity_type, key, name, f_type, choices=None, multi=False, force_reset=False, error_check=False):
    """Creates or updates a field in Spoolman.

    Parameters:
        force_reset: When True, DELETE the field schema first to allow type
            changes to take effect. **DANGER:** Spoolman wipes the value of
            this extra field on every spool/filament when the schema is
            deleted. The 2026-04-26 deployment-triggered slot-loss bug was
            caused by `container_slot` being defined with force_reset=True
            in the steady-state setup script — every deploy wiped slot
            assignments on un-deployed spools. Use only as part of a
            value-preserving one-time migration like
            `migrate_container_slot_to_text` below.
        error_check: When True, raise on Spoolman non-2xx response
            (excluding the legitimate "already exists" 400). Use on
            high-stakes fields where a silent setup failure would later
            present as runtime data corruption.
    """
    print(f"🔧 Processing {entity_type} field: {name} ({key})...")

    if force_reset:
        print(f"   ⚠️ Force Reset enabled. Deleting old definition (will wipe stored values)...")
        try:
            del_resp = requests.delete(f"{SPOOLMAN_IP}/api/v1/field/{entity_type}/{key}")
            # FIX: Spoolman returns 200 OK with list of remaining fields on success
            if del_resp.status_code in [200, 204]:
                print("   🗑️ Deleted old field.")
            elif del_resp.status_code == 404:
                print("   ℹ️ Old field not found (clean start).")
            else:
                print(f"   ⚠️ Delete status {del_resp.status_code}: {del_resp.text}")
                if error_check:
                    raise RuntimeError(
                        f"create_field force_reset DELETE failed for {entity_type}/{key}: "
                        f"{del_resp.status_code} {del_resp.text}"
                    )
        except RuntimeError:
            raise
        except Exception as e:
            print(f"   ❌ Connection Error during delete: {e}")
            if error_check:
                raise

    # --- [ALEX FIX] FETCH EXISTING CHOICES TO PREVENT "CANNOT REMOVE" ERROR ---
    existing_choices = []
    if f_type == "choice" and not force_reset:
        try:
            # Query the entire entity list instead of the specific key
            get_resp = requests.get(f"{SPOOLMAN_IP}/api/v1/field/{entity_type}")
            if get_resp.status_code == 200:
                all_fields = get_resp.json()
                
                # Dig through the list to find our specific field
                for field in all_fields:
                    if field.get('key') == key:
                        raw_existing = field.get('choices', [])
                        
                        if isinstance(raw_existing, str):
                            try: raw_existing = json.loads(raw_existing)
                            except: raw_existing = [c.strip() for c in raw_existing.strip('[]').replace('"', '').split(',') if c.strip()]
                            
                        if isinstance(raw_existing, list):
                            existing_choices = raw_existing
                            
                        if existing_choices:
                            print(f"   ℹ️ Found {len(existing_choices)} existing choices. Merging to protect data.")
                        break # Found it, stop searching
        except Exception as e:
            print(f"   ⚠️ Could not fetch existing choices: {e}")

    payload = {"name": name, "field_type": f_type}
    if f_type == "choice":
        payload["multi_choice"] = multi
        
        # [ALEX FIX] Combine CSV choices with Existing DB choices
        merged_choices = set()
        if choices: 
            merged_choices.update(choices)
        if existing_choices: 
            merged_choices.update(existing_choices)
            
        if merged_choices:
            payload["choices"] = sorted([c for c in list(merged_choices) if str(c).strip()])

    try:
        resp = requests.post(f"{SPOOLMAN_IP}/api/v1/field/{entity_type}/{key}", json=payload)
        if resp.status_code in [200, 201]:
            print("   ✅ Created/Updated.")
        elif resp.status_code == 400 and "already exists" in resp.text:
            print("   ℹ️ Already exists.")
        else:
            print(f"   ❌ Error {resp.status_code}: {resp.text}")
            if error_check:
                raise RuntimeError(
                    f"create_field POST failed for {entity_type}/{key}: "
                    f"{resp.status_code} {resp.text}"
                )
    except RuntimeError:
        raise
    except Exception as e:
        print(f"   ❌ Connection Error: {e}")
        if error_check:
            raise

def delete_field(entity_type, key, error_check=False):
    """Actively retires and removes a deprecated field from Spoolman."""
    print(f"🧹 Retiring {entity_type} field: {key}...")
    try:
        resp = requests.delete(f"{SPOOLMAN_IP}/api/v1/field/{entity_type}/{key}")
        if resp.status_code in [200, 204]:
            print("   ✅ Retired and deleted.")
        elif resp.status_code == 404:
            print("   ℹ️ Already removed (Not Found).")
        else:
            print(f"   ⚠️ Could not retire {resp.status_code}: {resp.text}")
            if error_check:
                raise RuntimeError(
                    f"delete_field failed for {entity_type}/{key}: "
                    f"{resp.status_code} {resp.text}"
                )
    except RuntimeError:
        raise
    except Exception as e:
        print(f"   ❌ Connection Error during retire: {e}")
        if error_check:
            raise


def _read_field_definition(entity_type, key):
    """Spoolman's field definition for entity_type/key, said three ways:
    (field, None) when the field list holds it, (None, None) when Spoolman answered
    a list without it, and (None, why) when the list couldn't be read (no answer,
    an HTTP error, or a 200 whose body isn't JSON or isn't a list). Never raises.

    Review R3-3 (Group 54): only a RequestException was caught, so a 200 whose body
    wasn't JSON raised ValueError out of the migration (and an entry that wasn't an
    object, AttributeError). On a rebuild that failed after its DELETE, that came
    before every snapshotted value was printed, and either way it stopped
    setup_fields before every field set up after the migration, on every deploy."""
    try:
        resp = requests.get(f"{SPOOLMAN_IP}/api/v1/field/{entity_type}", timeout=5)
    except Exception as e:   # no answer: a RequestException, or anything else
        return None, f"no answer: {e}"
    if resp.status_code != 200:
        return None, f"HTTP {resp.status_code}"
    try:
        rows = resp.json()
    except ValueError:
        return None, "its answer wasn't JSON"
    if not isinstance(rows, list):
        return None, "its answer wasn't a list"
    for f in rows:
        if isinstance(f, dict) and f.get("key") == key:
            return f, None
    return None, None


def _get_field_definition(entity_type, key):
    """Return the current Spoolman field definition for entity_type/key,
    or None if absent / unreadable (`_read_field_definition` tells the two
    apart). Used by migrations to decide whether a value-preserving rebuild
    is needed."""
    return _read_field_definition(entity_type, key)[0]


def _as_text_wire(raw):
    """A stored extra value as a `text` field's wire form (a JSON string), or None
    when there is nothing to keep (JSON null, a blank).

    Spoolman stores and answers every extra value as JSON text and checks each
    write against the field's type, so a rebuild to `text` must restore values
    the new type takes: an integer field's `2` sent back as it was is refused
    ("Value is not a string."). Every value is put in this form before anything
    is deleted (Group 54.4):
      - a JSON string stays as it is ('"2"');
      - any other JSON (a number, a bool, a list) becomes its own JSON text as a
        string: '2' -> '"2"', 'true' -> '"true"', never Python's "True";
      - text that isn't JSON (a value from before Spoolman checked) becomes that
        text as a string: 'slot 2' -> '"slot 2"';
      - JSON null, '' and a blank string are skipped.
    """
    if raw is None:
        return None
    if not isinstance(raw, str):
        # Spoolman answers wire text; a parsed value goes back to it first.
        try:
            raw = json.dumps(raw)
        except (TypeError, ValueError):
            raw = str(raw)
    text = raw.strip()
    if not text:
        return None
    try:
        decoded = json.loads(text)
    except ValueError:
        return json.dumps(text)
    if decoded is None:
        return None
    if isinstance(decoded, str):
        return text if decoded.strip() else None
    return json.dumps(text)


def _spool_place(record):
    """Where a spool record says it is, '' for nowhere."""
    return str(record.get("location") or "").strip()


def _read_spool(url):
    """GET one spool: (record, None), (None, "gone") for a 404, or (None, why)."""
    try:
        r = requests.get(url, timeout=10)
    except requests.RequestException as e:
        return None, str(e)
    if r.status_code == 404:
        return None, "gone"
    if r.status_code != 200:
        return None, f"HTTP {r.status_code} {str(r.text)[:200]}"
    try:
        record = r.json()
    except ValueError:
        return None, "its answer wasn't JSON"
    if not isinstance(record, dict) or record.get("id") is None:
        return None, "its answer wasn't a spool"
    return record, None


def _print_slot_values(snapshot, sids):
    """One line per spool: its id, its slot value and where it was, so a value
    Spoolman no longer holds can be put back by hand."""
    for sid in sids:
        snap = snapshot[sid]
        print(f"      #{sid}: {json.loads(snap['value'])} (at {snap['location'] or 'no location'})")


def _restore_container_slot(sid, snap):
    """Put one snapshotted value back through a fresh read-merge-write of the
    spool's whole `extra`. Answers 'restored', 'kept', 'gone' or 'failed'.

    The read is the last look before the write. FCC keeps running through the
    deploy, so a spool may have changed since the snapshot: a spool deleted since
    is 'gone'; one that holds a `container_slot` again (FCC wrote it since the
    rebuild, a blank included, since a move to a place with no slot writes "")
    or that is somewhere else now is left as it is ('kept'); one that can't be
    read is sent nothing ('failed'), never a partial `extra`. A whole `extra`,
    as spoolman_api.update_spool sends it, because a Spoolman before 0.22
    replaced a spool's whole `extra` with a PATCH's."""
    value, was_at = snap["value"], snap["location"]
    url = f"{SPOOLMAN_IP}/api/v1/spool/{sid}"
    record, why = _read_spool(url)
    if why == "gone":
        print(f"   ℹ️ Spool #{sid} was deleted since the snapshot; nothing to restore.")
        return "gone"
    if record is None:
        print(f"   ⚠️ Couldn't read spool #{sid} again ({why}), so nothing was sent for it.")
        return "failed"
    extra = record.get("extra")
    if not isinstance(extra, dict):
        extra = {}
    if "container_slot" in extra:
        print(f"   ℹ️ Spool #{sid} was given a slot value since the rebuild "
              f"({extra.get('container_slot')!r}); kept that one.")
        return "kept"
    now_at = _spool_place(record)
    if now_at != was_at:
        print(f"   ℹ️ Spool #{sid} moved since the snapshot ({was_at or 'no location'} -> "
              f"{now_at or 'no location'}), so its old slot no longer applies; left it as it is.")
        return "kept"
    body = {"extra": {**{k: v for k, v in extra.items() if v is not None}, "container_slot": value}}
    try:
        r = requests.patch(url, json=body, timeout=10)
        if r.ok:
            return "restored"
        why = f"{r.status_code} {str(r.text)[:200]}"
    except requests.RequestException as e:
        why = str(e)
    # A write that timed out may still have landed (it is a READ timeout): look again
    # before calling it failed.
    again, _ = _read_spool(url)
    if again is not None and isinstance(again.get("extra"), dict) \
            and again["extra"].get("container_slot") == value:
        return "restored"
    print(f"   ⚠️ Failed to restore container_slot on spool #{sid}: {why}")
    return "failed"


def migrate_container_slot_to_text():
    """Guarded one-time migration: ensure `spool.container_slot` is `text` type.

    History: setup_fields.py used to call
        create_field("spool", "container_slot", ..., force_reset=True)
    on every deploy. Spoolman's field DELETE wipes the stored value on
    every spool; deploys therefore reset slot assignments unintentionally
    (Item 5 in Feature-Buglist — confirmed 2026-04-26).

    This replacement runs the destructive rebuild ONLY when the field's
    current type is something other than `text`, and snapshots+restores
    every spool's value so the rebuild is value-preserving.

    Idempotent on subsequent deploys (no-op when type is already `text`).

    The template for any type migration (Group 54.4). FCC is still running
    while update.sh runs this, so:
      0. read the field list without ever raising (`_read_field_definition`):
         one that can't be read skips the migration with nothing written, and
         says so, so the rest of setup_fields still runs (review R3-3);
      1. snapshot every spool, archived ones too (the list leaves them out
         unless asked), with where each one is;
      2. put every value in the new type's wire form (`_as_text_wire`) before
         anything is deleted;
      3. delete and re-create the field (this drops the value on every record);
      4. restore each spool through a fresh read and a write of its whole
         `extra` (`_restore_container_slot`), leaving alone a spool that
         changed since;
      5. print the counts, and every value not restored for a failure, so it
         can be put back by hand (the deploy's Spoolman backup is the other way
         back).
    Plain `requests` only: importing the inventory-hub spoolman_api module would
    pull in Flask and FCC's state.
    """
    print("\n--- Container Slot Type Migration ---")
    field, why = _read_field_definition("spool", "container_slot")

    if why:
        # Nothing read, nothing written: the next deploy checks again (review R3-3).
        print(f"   ⚠️ Couldn't read Spoolman's spool field list ({why}); skipping the"
              f" container_slot migration this run, with nothing changed.")
        return

    if field is None:
        # Field doesn't exist yet — the regular create_field call below
        # will set it up correctly. Nothing to migrate.
        print("   ℹ️ container_slot field not present yet; skipping migration.")
        return

    current_type = field.get("field_type")
    if current_type == "text":
        print("   ✅ container_slot already type=text; no migration needed.")
        return

    print(f"   ⚠️ container_slot is type={current_type!r}; running value-preserving rebuild.")

    # 1. Snapshot every spool's value, archived spools included, each already in
    #    the new type's wire form (2), with where the spool was.
    snapshot = {}  # sid -> {"value": text wire form, "location": place}
    try:
        resp = requests.get(f"{SPOOLMAN_IP}/api/v1/spool", params={"allow_archived": "true"}, timeout=15)
        if resp.status_code != 200:
            print(f"   ❌ Could not list spools for snapshot ({resp.status_code}); aborting migration.")
            return
        rows = resp.json()
    except (requests.RequestException, ValueError) as e:
        print(f"   ❌ Snapshot failed: {e}; aborting migration.")
        return
    if not isinstance(rows, list):
        print("   ❌ Spoolman's spool list wasn't a list; aborting migration.")
        return
    for sp in rows:
        if not isinstance(sp, dict) or sp.get("id") is None:
            continue
        extra = sp.get("extra")
        if not isinstance(extra, dict):
            continue
        value = _as_text_wire(extra.get("container_slot"))
        if value is not None:
            snapshot[sp["id"]] = {"value": value, "location": _spool_place(sp)}
    print(f"   📸 Snapshotted {len(snapshot)} spool container_slot values (archived spools too), each as text.")

    # 3. Force-reset the field schema (this wipes values on Spoolman's side).
    try:
        create_field("spool", "container_slot", "Container / MMU Slot", "text",
                     force_reset=True, error_check=True)
    except Exception as e:
        print(f"   ❌ Field rebuild failed: {e}")
        after, why = _read_field_definition("spool", "container_slot")
        if why:
            print(f"   ⚠️ Couldn't read Spoolman's spool field list again ({why}).")
        if after is not None and after.get("field_type") == current_type:
            print("   ℹ️ The old field is still there, so every value is still in Spoolman; nothing to put back.")
        elif snapshot:
            print("   ❌ Spoolman may no longer hold these values, and none was restored. Put them back by hand,"
                  " or restore the Spoolman backup the deploy took:")
            _print_slot_values(snapshot, list(snapshot))
        return

    # 4. Restore each snapshotted value through a fresh read-merge-write.
    counts = {"restored": 0, "kept": 0, "gone": 0, "failed": 0}
    failed = []
    for sid, snap in snapshot.items():
        outcome = _restore_container_slot(sid, snap)
        counts[outcome] += 1
        if outcome == "failed":
            failed.append(sid)
    mark = "⚠️" if failed else "✅"
    print(f"   {mark} Migration complete: {counts['restored']} restored, {counts['kept']} kept, "
          f"{counts['gone']} gone, {counts['failed']} failed.")
    # 5. Every value a failure kept from coming back.
    if failed:
        print("   ❌ Spoolman no longer holds these values. Put them back by hand, or restore the"
              " Spoolman backup the deploy took:")
        _print_slot_values(snapshot, failed)


# --- CHOICE EXTRACTOR ---
def get_clean_choices(csv_path, column_name):
    choices = set()
    if not csv_path or not os.path.exists(csv_path): return list(choices)
    try:
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                val = row.get(column_name)
                if isinstance(val, str) and val.strip():
                    for p in val.split(','):
                        clean = p.strip()
                        if clean: choices.add(clean)
    except Exception as e: print(f"⚠️ Error reading {csv_path}: {e}")
    return list(choices)

# ==========================================
# MAIN EXECUTION
# ==========================================

LISTS_CSV = find_file(LISTS_FILENAME)
FILAMENT_CSV = find_file(FILAMENT_FILENAME)

print("\n--- Gathering Choices ---")
# Filament Attributes
attrs = set()
attrs.update(get_clean_choices(LISTS_CSV, "Filament Attributes"))
attrs.update(get_clean_choices(FILAMENT_CSV, "Filament Attributes"))
generated_attrs = ["Carbon Fiber", "Glass Fiber", "Glitter", "Marble", "Glow", "Gradient"]
attrs.update(generated_attrs)

# L37 fix (2026-06-05): never SEED a choice that the app's startup cleanup
# (spoolman_api.ensure_filament_attributes_cleaned) is configured to DELETE.
# create_field() below MERGES the requested choices with the field's EXISTING
# choices and POSTs the union, so re-seeding a delete-target makes the deploy
# (which re-adds it) and the next boot (which strips it) fight on every single
# deploy — the "🧹 removed ['Wood'] (180 restored)" line Derek saw on every boot,
# plus a full DELETE+recreate+restore of all filaments each time. Stripping here
# guards ALL seed sources at once: generated_attrs above AND the two source CSVs
# (lines 286-287, which aren't in the repo). KEEP IN SYNC with
# spoolman_api.FILAMENT_ATTRIBUTES_DELETE_CHOICES (the canonical remover — do not
# delete from that set instead, it must stay to self-heal any stray re-seed).
RETIRED_FILAMENT_ATTRS = {"Carbon-Fiber", "Tran", "Transparent; High-Speed", "Wood", "F"}
attrs -= RETIRED_FILAMENT_ATTRS

# Shore Hardness & Profiles
shores = set()
shores.update(get_clean_choices(LISTS_CSV, "TPU Shore"))
shores.update(get_clean_choices(FILAMENT_CSV, "TPU Shore"))

profiles = set()
profiles.update(get_clean_choices(LISTS_CSV, "Filament Profile"))
profiles.update(get_clean_choices(FILAMENT_CSV, "Filament Profile"))

# Spool Types (NEW)
spool_types = set()
spool_types.update(get_clean_choices(FILAMENT_CSV, "Spool Type"))

# ==========================================
# 1. SETUP SPOOL FIELDS
# ==========================================
print("\n--- Setting up SPOOL Fields ---")
create_field("spool", "physical_source", "Physical Source", "text")
# [ALEX FIX] Register the new Ghost Slot field
create_field("spool", "physical_source_slot", "Physical Source Slot", "text")
# Breadcrumb planted by spoolman_api._auto_archive_on_empty so a later refill
# can restore the spool to its pre-archive location. System-managed; never
# user-editable. See spoolman_api.SYSTEM_MANAGED_EXTRAS.
create_field("spool", "fcc_pre_archive_location", "Pre-Archive Location (system)", "text")
# Note planted by an audit's park (logic.park_audit_missing) when a spool
# expected at an audited location wasn't found and the person said Yes to
# moving it to the virtual UNKNOWN bucket: <PLACE>:<slot>@<YYYY-MM-DD>, the slot
# possibly empty.
# System-managed; see spoolman_api.SYSTEM_MANAGED_EXTRAS. App startup self-heals
# via ensure_required_extras() too, so this entry is the canonical-rebuild path.
create_field("spool", "fcc_pre_audit_location", "Pre-Audit Location (system)", "text")
# Group 42.6: where a spool sat before it went into a single-slot box (a
# PolyDryer), so ejecting it out of the box puts it back there. System-managed
# (spoolman_api.SYSTEM_MANAGED_EXTRAS); app startup self-heals it too
# (ensure_required_extras).
create_field("spool", "fcc_pre_box_location", "Pre-Box Location (system)", "text")
create_field("spool", "needs_label_print", "Needs Label Print", "boolean")
create_field("spool", "is_refill", "Is Refill", "boolean")
create_field("spool", "spool_temp", "Temp Resistance", "text")
create_field("spool", "product_url", "Product Page Link", "text") # [ALEX FIX] New custom field
create_field("spool", "purchase_url", "Purchase Link", "text") # Spool-level purchase/re-order link

# --- RETIRE LEGACY FIELDS ---
delete_field("spool", "label_printed")
delete_field("filament", "label_printed")
delete_field("filament", "spoolman_reprint")

# --- CONTAINER SLOT (idempotent) ---
# Steady-state behavior: just ensure the field exists as `text`. The
# previous `force_reset=True` call here was the smoking gun for the
# 2026-04-26 deployment-triggered slot-loss bug — Spoolman wipes the
# stored value on every spool when a field schema is deleted. The
# migration below handles the rare type-change case in a value-
# preserving way; the create call below leaves existing values alone.
migrate_container_slot_to_text()
create_field("spool", "container_slot", "Container / MMU Slot", "text")

# Choice field for Spool Type
create_field("spool", "spool_type", "Spool Type", "choice", choices=list(spool_types), multi=False)


# ==========================================
# 2. SETUP FILAMENT FIELDS
# ==========================================
print("\n--- Setting up FILAMENT Fields ---")
create_field("filament", "filament_attributes", "Filament Attributes", "choice", choices=list(attrs), multi=True)
create_field("filament", "shore_hardness", "Shore Hardness", "choice", choices=list(shores), multi=False)
create_field("filament", "slicer_profile", "Slicer Profile", "choice", choices=list(profiles), multi=False)

filament_standards = [
    ("needs_label_print", "Needs Label Print", "boolean"),
    ("sample_printed", "Sample Printed", "boolean"),
    ("product_url", "Product Page Link", "text"),
    ("purchase_url", "Purchase Link", "text"),
    ("sheet_link", "Sheet Row Link", "text"),
    ("price_total", "Price (w/ Tax)", "text"),
    ("original_color", "Original Color", "text"),
    ("drying_temp", "Drying Temp", "text"),
    ("drying_time", "Drying Time", "text"),
    ("flush_multiplier", "Flush Multiplier", "text"),
    # Max-temp companions to Spoolman's native min/recommended nozzle+bed
    # fields. Added 2026-04-23 with the Edit Filament Wave 4 Specs tab so
    # prod/new-install deploys create them automatically and the UI's
    # number inputs have a schema to write into.
    ("nozzle_temp_max", "Nozzle Temp Max", "text"),
    ("bed_temp_max", "Bed Temp Max", "text"),
    # Multi-color filaments need to know the gradient direction.
    # Values: 'longitudinal' (length-wise) | 'coaxial' (radial).
    ("multi_color_direction", "Multi-Color Direction", "text"),
    # Excluded from Low and Out (2026-10-20): set from the ⚠️ Low stock list's 🔕
    # (stock_report.py). App startup self-heals them too
    # (spoolman_api.REQUIRED_FILAMENT_EXTRAS).
    ("fcc_stock_excluded", "Excluded From Low Stock", "text"),
    ("fcc_stock_excluded_note", "Excluded From Low Stock: Note", "text"),
    ("fcc_stock_excluded_at", "Excluded From Low Stock: Since", "text"),
]

for key, name, ftype in filament_standards:
    create_field("filament", key, name, ftype)


# ==========================================
# 3. SETUP VENDOR FIELDS
# ==========================================
print("\n--- Setting up VENDOR Fields ---")
# First vendor extras registration in the codebase. Backs the
# Manufacturer/Vendor Edit modal V1 (Group 6 — Edit Modal new panels).
# Stored as `vendor.extra.website`; surfaced in the modal as a plain text
# input. Handled the same way as the spool/filament `*_url` extras
# (text-typed, JSON-string-wrapped on the wire — see JSON_STRING_FIELDS in
# spoolman_api.py).
create_field("vendor", "website", "Vendor Website", "text")

print("\n🎉 All Fields Configured Successfully!")
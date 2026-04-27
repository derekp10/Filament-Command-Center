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


def _get_field_definition(entity_type, key):
    """Return the current Spoolman field definition for entity_type/key,
    or None if absent / unreachable. Used by migrations to decide whether
    a value-preserving rebuild is needed."""
    try:
        resp = requests.get(f"{SPOOLMAN_IP}/api/v1/field/{entity_type}", timeout=5)
        if resp.status_code != 200:
            return None
        for f in resp.json() or []:
            if f.get("key") == key:
                return f
    except requests.RequestException:
        return None
    return None


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
    """
    print("\n--- Container Slot Type Migration ---")
    field = _get_field_definition("spool", "container_slot")

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

    # 1. Snapshot every spool's value.
    snapshot = {}  # sid -> raw extras value (still wire-form / JSON-encoded)
    try:
        resp = requests.get(f"{SPOOLMAN_IP}/api/v1/spool", timeout=15)
        if resp.status_code != 200:
            print(f"   ❌ Could not list spools for snapshot ({resp.status_code}); aborting migration.")
            return
        for sp in resp.json() or []:
            sid = sp.get("id")
            extra = (sp.get("extra") or {})
            v = extra.get("container_slot")
            if v is not None and v != "" and v != '""':
                snapshot[sid] = v
        print(f"   📸 Snapshotted {len(snapshot)} spool container_slot values.")
    except requests.RequestException as e:
        print(f"   ❌ Snapshot failed: {e}; aborting migration.")
        return

    # 2. Force-reset the field schema (this wipes values on Spoolman's side).
    try:
        create_field("spool", "container_slot", "Container / MMU Slot", "text",
                     force_reset=True, error_check=True)
    except Exception as e:
        print(f"   ❌ Field rebuild failed: {e}; values still snapshotted but not restored.")
        return

    # 3. Restore each snapshotted value via individual PATCHes. We call
    #    the spool PATCH directly here because importing the inventory-hub
    #    spoolman_api module would pull in Flask/state init.
    restored = 0
    failed = 0
    for sid, value in snapshot.items():
        try:
            r = requests.patch(
                f"{SPOOLMAN_IP}/api/v1/spool/{sid}",
                json={"extra": {"container_slot": value}},
                timeout=5,
            )
            if r.ok:
                restored += 1
            else:
                failed += 1
                print(f"   ⚠️ Failed to restore container_slot on spool #{sid}: {r.status_code} {r.text[:200]}")
        except requests.RequestException as e:
            failed += 1
            print(f"   ⚠️ Connection error restoring spool #{sid}: {e}")
    print(f"   ✅ Migration complete: {restored} restored, {failed} failed.")


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
generated_attrs = ["Carbon Fiber", "Glass Fiber", "Glitter", "Marble", "Wood", "Glow", "Gradient"]
attrs.update(generated_attrs)

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
]

for key, name, ftype in filament_standards:
    create_field("filament", key, name, ftype)

print("\n🎉 All Fields Configured Successfully!")
"""Label/text helpers + the three label-CSV endpoints (L316 step 3).

Moved verbatim from app.py: the pure label helpers (clean_string, hex_to_rgb,
get_smart_type, get_color_name, get_best_hex, sanitize_label_text,
flatten_json), the atomic CSV writer _write_label_csv, and the routes
/api/print_label, /api/print_batch_csv, /api/print_location_label. The CSVs
these write are P-touch database sources — row dicts and column headers are
a silent contract with the .lbx templates (pinned by
tests/test_l316_charact_label_*.py + tests/test_label_csv_export.py).

Python 3.9 runtime (the container image) — keep syntax 3.9-safe.
"""
from flask import request, jsonify  # type: ignore
import requests  # type: ignore
import csv
import json
import os
import tempfile

import state  # type: ignore
import config_loader  # type: ignore
import locations_db  # type: ignore
import spoolman_api  # type: ignore

from app_core import app

def clean_string(s):
    if isinstance(s, str): return s.strip('"').strip("'")
    return s

def hex_to_rgb(hex_str):
    # 28.A1 — strip the leading '#' BEFORE the length guard so a '#'-prefixed
    # short hex (e.g. '#AABBC') is rejected instead of parsing the blue channel
    # from a single digit. len() must measure the actual hex payload.
    if not hex_str: return "", "", ""
    clean_hex = hex_str.lstrip('#')
    if len(clean_hex) < 6: return "", "", ""
    try:
        return int(clean_hex[0:2], 16), int(clean_hex[2:4], 16), int(clean_hex[4:6], 16)
    except ValueError:
        return "", "", ""

def get_smart_type(material, extra_data):
    material = clean_string(material) or ""
    raw_attrs = extra_data.get('filament_attributes', '[]')
    try:
        attrs_list = json.loads(raw_attrs) if isinstance(raw_attrs, str) else raw_attrs
        if not isinstance(attrs_list, list): attrs_list = []
    except json.JSONDecodeError: attrs_list = []
    
    clean_attrs = [clean_string(a) for a in attrs_list if a]
    # 28.A2 — join only the non-empty parts so an empty material doesn't leave a
    # trailing space ('Matte ') in the label CSV Type column.
    parts = clean_attrs + ([material] if material else [])
    return ' '.join(parts)

def get_color_name(item_data):
    extra = item_data.get('extra', {})
    if 'original_color' in extra:
        val = clean_string(extra['original_color'])
        if val: return val
    # 28.A3 — quote-strip the name fallback too (symmetry with the
    # original_color path); a JSON-quoted filament name would otherwise print
    # with literal quotes on the label.
    return clean_string(item_data.get('name', 'Unknown'))

def get_best_hex(item_data):
    extra = item_data.get('extra', {})
    multi_hex = item_data.get('multi_color_hexes') or extra.get('multi_color_hexes')
    if multi_hex:
        # 28.A4 — return the first NON-EMPTY comma-segment; an empty leading
        # segment (',445566') must not abandon multi_color_hexes entirely.
        for seg in multi_hex.split(','):
            seg = seg.strip()
            if seg: return seg
    return item_data.get('color_hex', '')

def sanitize_label_text(text):
    if not isinstance(text, str): return str(text)
    # 🛠️ EMOJI TRANSLATION MAP — keys are the BARE base code points. Each is
    # matched in both its emoji-presentation form (base + U+FE0F VS16) and its
    # bare form, so (28.A5): a bare ⚠ (U+26A0) is mapped, and an emoji-
    # presentation ⚡️ (U+26A1 U+FE0F) is replaced WITHOUT leaving a stray
    # invisible VS16 in the P-touch CSV. VS16 on unmapped emoji is untouched.
    replacements = {
        "🦝": "Raccoon",
        "⚡": "Bolt",
        "🔥": "Fire",
        "📦": "Box",
        "⚠": "Warn",
    }
    vs16 = "️"  # U+FE0F variation selector (emoji-presentation form)
    for char, name in replacements.items():
        text = text.replace(char + vs16, name)  # emoji-presentation form first
        text = text.replace(char, name)         # bare form
    return text


def flatten_json(y):
    """Flatten a nested dict/list into single-level column→value pairs for the
    label CSV extras spillover.

    28.A6 / 28.A7 — no silent data loss:
      - a bare scalar input gets a 'value' key (not an empty-string header);
      - a NESTED empty dict/list is preserved as an empty-string column instead
        of vanishing (a top-level empty container still yields {} — no key);
      - a mangled-key COLLISION (a literal 'a_b' key vs a nested {'a':{'b'}})
        is disambiguated with a '__N' suffix so neither value is overwritten.
    """
    out = {}

    def _put(key, value):
        # 28.A7 — never silently overwrite a colliding mangled key.
        if key not in out:
            out[key] = value
            return
        n = 2
        while f"{key}__{n}" in out:
            n += 1
        out[f"{key}__{n}"] = value

    def flatten(x, name=''):
        if type(x) is dict:
            if not x:
                # 28.A7 — a nested empty dict would otherwise emit no column;
                # keep it (a top-level empty container has no key → skip).
                if name:
                    _put(name[:-1], '')
                return
            for a in x:
                flatten(x[a], name + a + '_')
        elif type(x) is list:
            if not x:
                if name:
                    _put(name[:-1], '')
                return
            i = 0
            for a in x:
                flatten(a, name + str(i) + '_')
                i += 1
        else:
            # 28.A6 — a bare scalar (name='') gets a 'value' header, not ''.
            _put(name[:-1] if name else 'value', x)

    flatten(y)
    return out

# --- PRINT ROUTES ---
@app.route('/api/print_label', methods=['POST'])
def api_print_label():
    sid = request.json.get('id')
    if not sid: return jsonify({"success": False, "msg": "No ID provided"})

    spool = spoolman_api.get_spool(sid)

    # Browser Mode: Just return data
    return jsonify({"success": True, "method": "browser", "data": spool})


def _write_label_csv(path, fieldnames, rows, *, overwrite, write_header):
    """Write label rows to `path` as a CSV.

    OVERWRITE goes through a per-call temp file + ``os.replace`` so the target
    is never left torn — a crash or a held handle can't produce a half-written
    label file (the destructive path is the one that truncates, so it's the one
    worth making atomic). APPEND adds rows at the end in place.

    Either path raises ``PermissionError`` when the target is held open by
    another process — Brother P-touch keeps the CSV open when its label
    template links it as a database source, and Excel does the same. We let
    that propagate so the caller surfaces it (Activity Log + a long toast)
    instead of swallowing it; the temp file is cleaned up on failure so locked
    re-export attempts don't accumulate stray ``.tmp`` files. On a lock we tag
    the raised PermissionError with ``fcc_locked_name`` (the offending file's
    basename) so the caller names the RIGHT file — the main labels CSV and the
    slots CSV can be held independently.
    """
    def _rm_quiet(p):
        try:
            if os.path.exists(p):
                os.remove(p)
        except OSError:
            pass

    try:
        if overwrite:
            folder = os.path.dirname(path) or "."
            fd, tmp = tempfile.mkstemp(prefix=".labels_", suffix=".csv.tmp", dir=folder)
            # os.fdopen takes ownership of fd; if it raises (it won't with these
            # static args, but be leak-proof), close the raw fd ourselves. Once
            # the `with` owns it, never double-close (the fd number could be
            # reused) — later failures only clean the temp file.
            try:
                f = os.fdopen(fd, "w", newline="", encoding="utf-8")
            except BaseException:
                os.close(fd)
                _rm_quiet(tmp)
                raise
            try:
                with f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                    if write_header:
                        writer.writeheader()
                    writer.writerows(rows)
                    f.flush()
                    os.fsync(f.fileno())  # durability parity with the house atomic-write helpers
                # Atomic swap on the same filesystem. Raises PermissionError if
                # `path` is locked (P-touch / Excel holds the handle).
                os.replace(tmp, path)
            except BaseException:
                _rm_quiet(tmp)
                raise
        else:
            with open(path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                if write_header:
                    writer.writeheader()
                writer.writerows(rows)
    except PermissionError as e:
        # Tag which file was actually locked so the caller's message points the
        # user at the right one (not always the main labels CSV).
        if not getattr(e, "fcc_locked_name", None):
            e.fcc_locked_name = os.path.basename(path)
        raise


@app.route('/api/print_batch_csv', methods=['POST'])
def api_print_batch_csv():
    data = request.json
    ids = data.get('ids', [])
    mode = data.get('mode', 'spool')
    clear_old = data.get('clear_old', False)
    
    if not ids: return jsonify({"success": False, "msg": "Empty Queue"})

    cfg = config_loader.load_config()
    
    # --- 1. DETERMINE FILENAME ---
    if mode == 'spool': filename = "labels_spool.csv"
    elif mode == 'location': filename = "labels_locations.csv"
    else: filename = "labels_swatch.csv"
    
    csv_path = cfg.get("print_settings", {}).get("csv_path", filename)
    
    # 🛠️ AUTO-CREATE FOLDER FIX
    if "/" in csv_path or "\\" in csv_path:
        folder = os.path.dirname(csv_path)
        try: 
            os.makedirs(folder, exist_ok=True)
        except Exception as e:
            state.logger.warning(f"Could not create folder {folder}: {e}")
        csv_path = os.path.join(folder, filename)

    try:
        items_to_print = []
        slots_to_print = []

        # --- 2. DEFINE HEADERS ---
        if mode == 'spool':
            core_headers = ['ID', 'Brand', 'Color', 'Type', 'Hex', 'Red', 'Green', 'Blue', 'Weight', 'QR_Code']
        elif mode == 'location':
            # [ALEX FIX] Added 'Slot' to headers
            core_headers = ['LocationID', 'Name', 'Cleaned_Name', 'QR_Code']
        else:
            core_headers = ['ID', 'Brand', 'Color', 'Type', 'Hex', 'Red', 'Green', 'Blue', 'Temp_Nozzle', 'Temp_Bed', 'Density', 'QR_Code']

        # --- 3. PRE-LOAD DATA (Optimization) ---
        loc_lookup = {}
        if mode == 'location':
            # Load local CSV first
            loc_list = locations_db.load_locations_list()
            # 28.A8 — case-insensitive LocationID key access. One row stored with
            # a differently-cased key (e.g. 'locationid') must NOT KeyError and
            # fail the whole batch — matches the tolerant 'Max Spools' matching
            # below and api_print_location_label's lookup.
            for row in loc_list:
                rid = None
                for k, v in row.items():
                    if str(k).strip().lower() == 'locationid':
                        rid = str(v)
                        break
                if rid is not None:
                    loc_lookup[rid] = row

        # --- 4. BUILD ROWS ---
        seen_ids = set() # [ALEX FIX] Deduplication tracker

        for item_id in ids:
            # [ALEX FIX] Prevent processing duplicates in the same batch
            if item_id in seen_ids: continue
            seen_ids.add(item_id)

            row_data = {}
            
            # === SPOOL MODE ===
            if mode == 'spool':
                raw_data = spoolman_api.get_spool(item_id)
                if not raw_data: continue
                fil_data = raw_data.get('filament', {})
                vendor_data = fil_data.get('vendor', {})
                fil_extra = fil_data.get('extra', {})
                
                row_data['ID'] = item_id
                row_data['Brand'] = sanitize_label_text(vendor_data.get('name', 'Unknown') if vendor_data else 'Unknown')
                row_data['Color'] = sanitize_label_text(get_color_name(fil_data))
                raw_material = fil_data.get('material', 'Unknown')
                row_data['Type'] = sanitize_label_text(get_smart_type(raw_material, fil_extra))
                hex_val = get_best_hex(fil_data)
                row_data['Hex'] = hex_val
                r, g, b = hex_to_rgb(hex_val)
                row_data['Red'] = r; row_data['Green'] = g; row_data['Blue'] = b
                row_data['Weight'] = f"{raw_data.get('remaining_weight', 0):.0f}g"
                row_data['QR_Code'] = f"ID:{item_id}"
                
                flat_data = flatten_json(raw_data)
                for k, v in flat_data.items():
                    if k not in row_data: row_data[k] = v

            # === LOCATION MODE (HYBRID LOOKUP) ===
            elif mode == 'location':
                # 1. Try Local CSV
                loc_data = loc_lookup.get(str(item_id)) 
                
                if loc_data:
                    name = loc_data.get('Name', 'Unknown')
                else:
                    # 2. Try Spoolman API (Fallback)
                    sm_url, _ = config_loader.get_api_urls()
                    try:
                        resp = requests.get(f"{sm_url}/api/v1/location/{item_id}", timeout=2)
                        if resp.ok:
                            s_data = resp.json()
                            name = s_data.get('name', str(item_id))
                        else:
                            name = str(item_id)
                    except:
                        name = str(item_id)
                
                row_data['LocationID'] = item_id
                row_data['Name'] = name
                # [ALEX FIX] Enforce LOC: prefix for Location QR Codes
                row_data['QR_Code'] = f"LOC:{item_id}" 

                # --- CLEAN NAME & SLOT GENERATION ---
                clean_name = sanitize_label_text(name)
                row_data['Cleaned_Name'] = clean_name

                max_spools = 0
                if loc_data:
                    for k, v in loc_data.items():
                        if k.strip().lower() == 'max spools':
                            try: max_spools = int(v)
                            except: max_spools = 0
                            break
                
                # [ALEX FIX] Removed the DUPLICATE "Slot Generation" block that was here.
                # [ALEX FIX] Added "Slot" column logic.
                if max_spools > 1:
                    for i in range(1, max_spools + 1):
                        slots_to_print.append({
                            "LocationID": item_id,
                            "Slot": f"Slot {i}", # <--- NEW FIELD
                            "Name": f"{name} Slot {i}",
                            "Cleaned_Name": f"{clean_name} Slot {i}",
                            "QR_Code": f"LOC:{item_id}:SLOT:{i}"
                        })

                items_to_print.append(row_data)
                continue 

            # === FILAMENT MODE ===
            else:
                raw_data = spoolman_api.get_filament(item_id)
                if not raw_data: continue
                fil_data = raw_data
                vendor_data = raw_data.get('vendor', {})
                fil_extra = raw_data.get('extra', {})
                
                row_data['ID'] = item_id
                # 28.A9 — sanitize Brand/Color/Type in swatch mode too (spool and
                # location modes already do); without this, emoji reach the
                # P-touch swatch CSV unsanitized.
                row_data['Brand'] = sanitize_label_text(vendor_data.get('name', 'Unknown') if vendor_data else 'Unknown')
                row_data['Color'] = sanitize_label_text(get_color_name(fil_data))
                raw_material = fil_data.get('material', 'Unknown')
                row_data['Type'] = sanitize_label_text(get_smart_type(raw_material, fil_extra))
                hex_val = get_best_hex(fil_data)
                row_data['Hex'] = hex_val
                r, g, b = hex_to_rgb(hex_val)
                row_data['Red'] = r; row_data['Green'] = g; row_data['Blue'] = b

                # 28.A10 — a deliberate 0°C bed/extruder temp is a real value:
                # test `is not None`, not falsiness, so it prints '0°C' not blank.
                t_noz = fil_data.get('settings_extruder_temp')
                row_data['Temp_Nozzle'] = f"{t_noz}°C" if t_noz is not None else ""
                t_bed = fil_data.get('settings_bed_temp')
                row_data['Temp_Bed'] = f"{t_bed}°C" if t_bed is not None else ""
                dens = fil_data.get('density')
                row_data['Density'] = f"{dens} g/cm³" if dens else ""
                row_data['QR_Code'] = f"FIL:{item_id}"

                flat_data = flatten_json(raw_data)
                for k, v in flat_data.items():
                    if k not in row_data: row_data[k] = v
            
            # Append Spool/Filament rows
            if mode != 'location':
                items_to_print.append(row_data)

        if not items_to_print: return jsonify({"success": False, "msg": "No valid data found"})

        # --- SMART HEADER LOGIC ---
        # `folder` is computed unconditionally (it used to only be set when
        # csv_path contained a separator), so the slots-CSV path below can't
        # NameError on a bare-filename csv_path. os.path.dirname("") -> "".
        folder = os.path.dirname(csv_path)
        file_exists = os.path.exists(csv_path)
        overwrite = bool(clear_old)

        target_headers = []

        if not overwrite and file_exists:
            try:
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    target_headers = next(reader, None) or []
            except Exception:
                target_headers = []

        if not target_headers:
            target_headers = list(core_headers)
            all_keys = set()
            for item in items_to_print: all_keys.update(item.keys())
            extra_headers = sorted([k for k in all_keys if k not in core_headers])
            target_headers.extend(extra_headers)

        # Overwrite goes through an atomic temp+replace (never a torn file);
        # append adds in place. A held handle (P-touch / Excel) raises
        # PermissionError from either, surfaced in the handlers below.
        _write_label_csv(csv_path, target_headers, items_to_print,
                         overwrite=overwrite, write_header=(overwrite or not file_exists))

        # --- WRITE SLOTS IF GENERATED ---
        if slots_to_print:
            slots_path = os.path.join(folder, "slots_to_print.csv")
            slots_exists = os.path.exists(slots_path)
            _write_label_csv(slots_path,
                             ["LocationID", "Slot", "Name", "Cleaned_Name", "QR_Code"],
                             slots_to_print,
                             overwrite=overwrite, write_header=(overwrite or not slots_exists))

        action_word = "Overwritten" if clear_old else "Appended"
        # 28.A12 — pluralize the item count ('1 item.' not '1 items.'). Slot
        # fan-out only fires for Max Spools > 1 so the slot count is always ≥2.
        n_items = len(items_to_print)
        msg = f"{action_word} {n_items} {'item' if n_items == 1 else 'items'}."
        if slots_to_print: msg += f" (+{len(slots_to_print)} Slots)"

        # Activity Log on success too (CLAUDE.md: every outcome logs) so the
        # user can confirm an export landed even if the toast was missed.
        try:
            _slots_note = f" + {len(slots_to_print)} slot label(s)" if slots_to_print else ""
            state.add_log_entry(
                f"🏷️ Label CSV ({filename}): {action_word.lower()} {len(items_to_print)} label(s){_slots_note}",
                "INFO", "0dcaf0")
        except Exception:
            pass

        return jsonify({"success": True, "count": len(items_to_print), "file": filename, "msg": msg})

    except PermissionError as e:
        # The CSV is held open by another process — almost always Brother
        # P-touch (its label template links the CSV as a database source), but
        # any program that opens it works too. Surface it loudly: it used to
        # fail with a short toast and no Activity Log line, so a blind-scanning
        # user never knew the export hadn't landed. Name the file actually held
        # open (the main labels CSV and slots_to_print.csv can lock independently).
        locked_name = getattr(e, "fcc_locked_name", None) or filename
        lock_msg = f"{locked_name} is locked — P-touch or another program has it open. Close it and re-export."
        try:
            state.add_log_entry(f"❌ Label CSV export blocked: {lock_msg}", "ERROR", "ff4444")
        except Exception:
            pass
        return jsonify({"success": False, "locked": True, "msg": lock_msg})
    except Exception as e:
        state.logger.error(f"Batch CSV Error: {e}")
        try:
            state.add_log_entry(f"❌ Label CSV export failed ({filename}): {e}", "ERROR", "ff4444")
        except Exception:
            pass
        return jsonify({"success": False, "msg": str(e)})


@app.route('/api/print_location_label', methods=['POST'])
def api_print_location_label():
    # 1. Robust Input Handling
    raw_id = request.json.get('id')
    if not raw_id: return jsonify({"success": False, "msg": "No ID provided"})
    target_id = str(raw_id).strip().upper()
    
    state.logger.info(f"🖨️ [LABEL] Request for: {target_id}")

    # 2. Determine Output Path
    cfg = config_loader.load_config()
    base_path = cfg.get("print_settings", {}).get("csv_path", "labels.csv")
    
    output_dir = os.path.dirname(base_path)
    if not output_dir or (os.name == 'nt' and output_dir.startswith(('/', '\\'))):
        output_dir = "."
    
    if output_dir != ".":
        try: os.makedirs(output_dir, exist_ok=True)
        except: output_dir = "." 

    loc_file = os.path.join(output_dir, "labels_locations.csv")
    slot_file = os.path.join(output_dir, "slots_to_print.csv")

    try:
        locs = locations_db.load_locations_list()
        
        # 3. Robust Lookup 
        loc_data = None
        if target_id == "UNASSIGNED":
             loc_data = {"LocationID": "Unassigned", "Name": "Unassigned", "Max Spools": 0}
        else:
            for row in locs:
                if not isinstance(row, dict): continue
                row_id = ""
                for k, v in row.items():
                    if str(k).strip().lower() == 'locationid': 
                        row_id = str(v).strip().upper()
                        break
                
                if row_id == target_id:
                    loc_data = row
                    break
        
        if not loc_data:
             state.logger.warning(f"❌ [LABEL] ID {target_id} not found in DB")
             return jsonify({"success": False, "msg": "ID Not Found in DB"})

        # Get Name safely
        loc_name = target_id
        if isinstance(loc_data, dict):
            for k, v in loc_data.items():
                if str(k).strip().lower() == 'name':
                    loc_name = str(v)
                    break

        # 28.A11 — write the row's STORED LocationID casing (+ its LOC: QR)
        # rather than the uppercased scanned id, so labels printed from a
        # lowercase-stored LocationID round-trip. Falls back to target_id when
        # the row carries no LocationID key.
        stored_id = target_id
        if isinstance(loc_data, dict):
            for k, v in loc_data.items():
                if str(k).strip().lower() == 'locationid':
                    sv = str(v).strip()
                    if sv:
                        stored_id = sv
                    break

        # Sanitize
        clean_name = sanitize_label_text(loc_name)

        # 4. Write Main Label
        file_exists = os.path.exists(loc_file)
        with open(loc_file, 'a', newline='', encoding='utf-8') as f:
            headers = ["LocationID", "Name", "Cleaned_Name", "QR_Code"]
            writer = csv.DictWriter(f, fieldnames=headers)
            if not file_exists: writer.writeheader()
            writer.writerow({
                "LocationID": stored_id,
                "Name": loc_name,
                "Cleaned_Name": clean_name,
                "QR_Code": f"LOC:{stored_id}" # [ALEX FIX] Added Prefix
            })
            
        # 5. Robust Slot Logic
        max_spools = 1
        if isinstance(loc_data, dict):
            for k, v in loc_data.items():
                if str(k).strip().lower() == 'max spools':
                    try: max_spools = int(v)
                    except: max_spools = 1
                    break
            
        state.logger.info(f"ℹ️ [LABEL] Found {target_id}. Max Spools: {max_spools}")

        slots_generated = False
        if max_spools > 1:
            slot_exists = os.path.exists(slot_file)
            with open(slot_file, 'a', newline='', encoding='utf-8') as f:
                # [ALEX FIX] Added "Slot" field
                headers = ["LocationID", "Slot", "Name", "Cleaned_Name", "QR_Code"]
                writer = csv.DictWriter(f, fieldnames=headers)
                if not slot_exists: writer.writeheader()
                
                for i in range(1, max_spools + 1):
                    writer.writerow({
                        "LocationID": stored_id,
                        "Slot": f"Slot {i}",
                        "Name": f"{loc_name} Slot {i}",
                        "Cleaned_Name": f"{clean_name} Slot {i}",
                        "QR_Code": f"LOC:{stored_id}:SLOT:{i}"
                    })
            slots_generated = True

        # 6. Build User Message
        abs_path = str(os.path.abspath(output_dir))
        short_path = "..." + abs_path[-30:] if len(abs_path) > 30 else abs_path # type: ignore
        
        msg = f"Queue: {stored_id}"
        if slots_generated: msg += f" (+{max_spools} Slots)"
        msg += f" in {short_path}"
        
        return jsonify({"success": True, "msg": msg})

    except Exception as e:
        state.logger.error(f"Print Label Error: {e}")
        return jsonify({"success": False, "msg": str(e)})

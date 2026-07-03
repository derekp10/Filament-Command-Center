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
    if not hex_str or len(hex_str) < 6: return "", "", ""
    try:
        clean_hex = hex_str.lstrip('#')
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
    if clean_attrs: return f"{' '.join(clean_attrs)} {material}"
    return material

def get_color_name(item_data):
    extra = item_data.get('extra', {})
    if 'original_color' in extra:
        val = clean_string(extra['original_color'])
        if val: return val
    return item_data.get('name', 'Unknown')

def get_best_hex(item_data):
    extra = item_data.get('extra', {})
    multi_hex = item_data.get('multi_color_hexes') or extra.get('multi_color_hexes')
    if multi_hex:
        first_hex = multi_hex.split(',')[0].strip()
        if first_hex: return first_hex
    return item_data.get('color_hex', '')

def sanitize_label_text(text):
    if not isinstance(text, str): return str(text)
    # 🛠️ EMOJI TRANSLATION MAP
    replacements = {
        "🦝": "Raccoon",
        "⚡": "Bolt",
        "🔥": "Fire",
        "📦": "Box",
        "⚠️": "Warn"
    }
    for char, name in replacements.items():
        text = text.replace(char, name)
    return text


def flatten_json(y):
    out = {}
    def flatten(x, name=''):
        if type(x) is dict:
            for a in x:
                flatten(x[a], name + a + '_')
        elif type(x) is list:
            i = 0
            for a in x:
                flatten(a, name + str(i) + '_')
                i += 1
        else:
            out[name[:-1]] = x
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
            loc_lookup = {str(row['LocationID']): row for row in loc_list}

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
                row_data['Brand'] = vendor_data.get('name', 'Unknown') if vendor_data else 'Unknown'
                row_data['Color'] = get_color_name(fil_data)
                raw_material = fil_data.get('material', 'Unknown')
                row_data['Type'] = get_smart_type(raw_material, fil_extra)
                hex_val = get_best_hex(fil_data)
                row_data['Hex'] = hex_val
                r, g, b = hex_to_rgb(hex_val)
                row_data['Red'] = r; row_data['Green'] = g; row_data['Blue'] = b

                t_noz = fil_data.get('settings_extruder_temp')
                row_data['Temp_Nozzle'] = f"{t_noz}°C" if t_noz else ""
                t_bed = fil_data.get('settings_bed_temp')
                row_data['Temp_Bed'] = f"{t_bed}°C" if t_bed else ""
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
        msg = f"{action_word} {len(items_to_print)} items."
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
        
        # Sanitize
        clean_name = sanitize_label_text(loc_name)

        # 4. Write Main Label
        file_exists = os.path.exists(loc_file)
        with open(loc_file, 'a', newline='', encoding='utf-8') as f:
            headers = ["LocationID", "Name", "Cleaned_Name", "QR_Code"]
            writer = csv.DictWriter(f, fieldnames=headers)
            if not file_exists: writer.writeheader()
            writer.writerow({
                "LocationID": target_id, 
                "Name": loc_name,
                "Cleaned_Name": clean_name,
                "QR_Code": f"LOC:{target_id}" # [ALEX FIX] Added Prefix
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
                        "LocationID": target_id,
                        "Slot": f"Slot {i}",
                        "Name": f"{loc_name} Slot {i}",
                        "Cleaned_Name": f"{clean_name} Slot {i}",
                        "QR_Code": f"LOC:{target_id}:SLOT:{i}"
                    })
            slots_generated = True

        # 6. Build User Message
        abs_path = str(os.path.abspath(output_dir))
        short_path = "..." + abs_path[-30:] if len(abs_path) > 30 else abs_path # type: ignore
        
        msg = f"Queue: {target_id}"
        if slots_generated: msg += f" (+{max_spools} Slots)"
        msg += f" in {short_path}"
        
        return jsonify({"success": True, "msg": msg})

    except Exception as e:
        state.logger.error(f"Print Label Error: {e}")
        return jsonify({"success": False, "msg": str(e)})

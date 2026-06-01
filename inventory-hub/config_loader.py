import json
import os
import sys
import tempfile
import state
import config_schema

# Module-global mirroring spoolman_api.LAST_SPOOLMAN_ERROR: set to the last
# config-write failure string (None on success) so callers never have to
# guess why a save returned not-ok. save_config also returns the error in its
# result dict — this global is the belt-and-suspenders for log/inspection.
LAST_CONFIG_ERROR = None

# Logic to find the ROOT config.json (Go up one level)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_config_path():
    """Determines which config file to load based on Environment Variables."""
    env = os.environ.get('FLASK_ENV', '').lower()
    custom_env = os.environ.get('ENV', '').lower()
    
    # Priority: Explicit 'ENV' var > FLASK_ENV > Default
    if 'dev' in custom_env or 'dev' in env:
        target = os.path.join(BASE_DIR, 'config.dev.json')
        if os.path.exists(target):
            return target, "DEV"
    
    return os.path.join(BASE_DIR, 'config.json'), "PROD"

def load_config():
    defaults = {
        "server_ip": "127.0.0.1",
        "spoolman_port": 7912,
        "filabridge_port": 5000,
        "sync_delay": 0.5,
        "printer_map": {},
        "dryer_slots": [],
        "auto_recover_filabridge_errors": True
    }
    # Note: the legacy `feeder_map` key is no longer read here. Its values
    # were imported into per-Dryer-Box `extra.slot_targets` entries in
    # locations.json on first startup after M3. If it still exists in a
    # config.json, it's harmless — json.load simply doesn't care about
    # unknown keys — and can be removed manually.
    
    final_config = defaults.copy()
    config_file, mode = get_config_path()
    
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f: 
                loaded = json.load(f)
                final_config.update(loaded)

            current_mtime = str(os.path.getmtime(config_file))
            tracker_file = os.path.join(BASE_DIR, '.config_mtime')
            
            last_mtime = None
            if os.path.exists(tracker_file):
                try:
                    with open(tracker_file, 'r') as tf:
                        last_mtime = tf.read().strip()
                except:
                    pass
            
            # Log only if state logger is available AND we haven't logged this specific version recently
            if hasattr(state, 'logger'):
                if last_mtime != current_mtime:
                    if mode == "DEV":
                        state.logger.warning(f"⚠️ LOADED DEV CONFIG: {config_file}")
                    else:
                        state.logger.info(f"✅ Loaded Prod Config: {config_file}")
                    
                    try:
                        with open(tracker_file, 'w') as tf:
                            tf.write(current_mtime)
                    except:
                        pass

        except Exception as e: 
            if hasattr(state, 'logger'):
                state.logger.error(f"Config Load Error: {e}")
    else:
        if hasattr(state, 'logger'):
            state.logger.warning(f"Config file not found at {config_file}")

    # Force Uppercase Keys for Printer Map
    if 'printer_map' in final_config:
        final_config['printer_map'] = {k.upper(): v for k, v in final_config['printer_map'].items()}
        
    return final_config

def get_api_urls():
    cfg = load_config()
    server_ip = cfg.get("server_ip")
    # Spoolman and FilaBridge need NOT share a host. filabridge_ip is optional —
    # when blank/absent it falls back to server_ip, so existing single-host
    # configs behave identically.
    fb_host = cfg.get("filabridge_ip") or server_ip
    sm_url = f"http://{server_ip}:{cfg.get('spoolman_port')}"
    fb_url = f"http://{fb_host}:{cfg.get('filabridge_port')}/api"
    return sm_url, fb_url


# ---------------------------------------------------------------------------
# L18 Config System — Phase 1 safe writer
#
# load_config() above is the RUNTIME read: it injects defaults and uppercases
# printer_map. That output must NEVER be written back to disk (it would bake in
# 7 phantom defaults and re-case printer_map permanently). load_config_raw()
# below is the read side of the save round-trip. save_config() does a passthrough
# merge (only schema-owned server keys are overwritten; every other on-disk key
# is preserved verbatim) + atomic write + exact-equality verify-after-write,
# modelled on locations_db.save_locations_list. See
# docs/agent_docs/tasks/L18-config-system-design.md.
# ---------------------------------------------------------------------------

def load_config_raw():
    """Read the active config JSON WITHOUT applying defaults and WITHOUT
    uppercasing printer_map. TRI-STATE return so save_config() can tell
    'fresh install' apart from 'unreadable' and never clobber the latter:
      - {}    the file genuinely does not exist (fresh install).
      - None  the file EXISTS but can't be read as a JSON object (unreadable,
              invalid JSON, or top-level non-dict) -> callers MUST treat as
              "do not overwrite".
      - dict  the parsed config."""
    config_file, _mode = get_config_path()
    if not os.path.exists(config_file):
        return {}
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        if hasattr(state, 'logger'):
            state.logger.error(f"Config raw-load error: {e}")
        return None
    if not isinstance(data, dict):
        if hasattr(state, 'logger'):
            state.logger.error(
                f"Config raw-load: top-level JSON is {type(data).__name__}, not an object")
        return None
    return data


def _write_config_atomic(cfg_dict, path):
    """One atomic write attempt: a per-call uniquely-named temp file in the
    same directory, fsync, then os.replace onto `path` (atomic on POSIX and
    NTFS). Raises on failure; the caller decides whether to retry. Mirrors
    locations_db._write_locations_atomic (the outage-hardened precedent)."""
    parent_dir = os.path.dirname(path) or '.'
    tmp = tempfile.NamedTemporaryFile(
        mode='w', encoding='utf-8',
        dir=parent_dir, prefix='config.', suffix='.tmp', delete=False,
    )
    tmp_path = tmp.name
    try:
        try:
            # ensure_ascii=False so non-ASCII values (e.g. emoji printer names
            # like "🦝 XL" in printer_map) round-trip as real UTF-8 instead of
            # being rewritten to \uXXXX escapes on every save.
            json.dump(cfg_dict, tmp, indent=4, ensure_ascii=False)
            tmp.flush()
            os.fsync(tmp.fileno())
        finally:
            tmp.close()
        os.replace(tmp_path, path)
        return path
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        raise


def _verify_config_file(expected_dict, path):
    """Re-read `path` and confirm it parses to a dict EXACTLY equal to
    expected_dict. Config is small, so we can do a full-equality tripwire
    (stronger than the list-shape check locations.json uses). Returns
    (ok: bool, detail: str)."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            parsed = json.loads(f.read())
    except (OSError, json.JSONDecodeError) as e:
        return False, repr(e)
    if not isinstance(parsed, dict):
        return False, f"parsed value is not a dict (got {type(parsed).__name__})"
    if parsed != expected_dict:
        return False, "on-disk content does not match the written config (round-trip mismatch)"
    return True, "ok"


def save_config(new_values):
    """Persist user-edited SERVER-scope settings to the active config file.

    Contract (see CLAUDE.md write-surface conventions):
      - Validate against config_schema FIRST — bad input touches no disk.
      - Passthrough merge: start from the RAW on-disk config and overwrite
        ONLY schema-owned server keys, so secrets / paths / comments /
        print_settings / printer_map / dryer_slots are preserved verbatim.
      - Atomic write + exact-equality verify-after-write, retry once.
      - Never returns a silent None: returns
        {"ok": bool, "error": str|None, "saved": [keys]} and sets the
        module-global LAST_CONFIG_ERROR on any failure.

    Client-scope keys (localStorage prefs) are ignored here — the browser
    persists those; they live in the schema only so they render in the UI.
    """
    global LAST_CONFIG_ERROR
    LAST_CONFIG_ERROR = None

    coerced, errors = config_schema.validate_payload(new_values or {})
    if errors:
        LAST_CONFIG_ERROR = "; ".join(errors)
        return {"ok": False, "error": LAST_CONFIG_ERROR, "saved": []}

    if not coerced:
        # Nothing server-side to persist (e.g. only client prefs submitted).
        return {"ok": True, "error": None, "saved": []}

    config_file, _mode = get_config_path()
    existing = load_config_raw()

    # Guard against clobbering a config we couldn't read. load_config_raw()
    # returns None when the file EXISTS but isn't a readable JSON object;
    # merging into {} would atomically drop every other on-disk key (server_ip,
    # ports, printer_map, SCRAPER_API_KEY, paths, print_settings, dryer_slots,
    # comment_*). Refuse and surface the error rather than silently wipe.
    if existing is None:
        LAST_CONFIG_ERROR = (
            "refusing to save: the existing config could not be read as a JSON object "
            "(saving would drop all other keys) — fix or remove the file first")
        if hasattr(state, 'logger'):
            state.logger.error(LAST_CONFIG_ERROR)
        return {"ok": False, "error": LAST_CONFIG_ERROR, "saved": []}

    if not existing and not os.path.exists(config_file):
        # Genuinely fresh install (no file): seed from runtime defaults so the
        # created file is complete, not a lone 1-key object.
        merged = dict(load_config())
    else:
        merged = dict(existing)
    merged.update(coerced)  # only schema-owned server keys are overwritten

    # Rolling last-known-good snapshot: persist the PRE-EDIT config (which
    # load_config_raw just confirmed parses) to .bak on EVERY save. Skip when
    # there's nothing good to back up (fresh install). Re-serialized from the
    # parsed dict, so a corrupt file can never become the backup.
    if existing:
        try:
            with open(config_file + ".bak", 'w', encoding='utf-8') as bf:
                json.dump(existing, bf, indent=4, ensure_ascii=False)
        except OSError:
            pass  # best-effort

    def _attempt():
        _write_config_atomic(merged, config_file)
        return _verify_config_file(merged, config_file)

    try:
        ok, detail = _attempt()
    except Exception as e:
        LAST_CONFIG_ERROR = f"config write failed: {e}"
        if hasattr(state, 'logger'):
            state.logger.error(LAST_CONFIG_ERROR)
        return {"ok": False, "error": LAST_CONFIG_ERROR, "saved": []}

    if not ok:
        if hasattr(state, 'logger'):
            state.logger.critical(
                f"config verify-after-write FAILED at {config_file!r}: {detail}. Retrying once.")
        try:
            ok, detail = _attempt()
        except Exception as e:
            LAST_CONFIG_ERROR = f"config write failed on retry: {e}"
            if hasattr(state, 'logger'):
                state.logger.critical(LAST_CONFIG_ERROR)
            return {"ok": False, "error": LAST_CONFIG_ERROR, "saved": []}
        if not ok:
            LAST_CONFIG_ERROR = f"config verify-after-write failed twice: {detail}"
            if hasattr(state, 'logger'):
                state.logger.critical(LAST_CONFIG_ERROR)
            return {"ok": False, "error": LAST_CONFIG_ERROR, "saved": []}

    if hasattr(state, 'logger'):
        state.logger.info(f"💾 Config updated ({', '.join(sorted(coerced))})")
    return {"ok": True, "error": None, "saved": sorted(coerced)}
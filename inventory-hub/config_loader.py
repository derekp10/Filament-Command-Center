import errno
import json
import os
import sys
import tempfile
import threading
import state
import config_schema

# Module-global mirroring spoolman_api.LAST_SPOOLMAN_ERROR: set to the last
# config-write failure string (None on success) so callers never have to
# guess why a save returned not-ok. save_config also returns the error in its
# result dict — this global is the belt-and-suspenders for log/inspection.
LAST_CONFIG_ERROR = None

# Logic to find the ROOT config.json (Go up one level)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The app package dir (…/inventory-hub) — one level BELOW BASE_DIR. Used to
# locate the persisted data/ dir for the rolling config backup
# (see get_config_backup_path); kept distinct from BASE_DIR because inside the
# container BASE_DIR resolves to the ephemeral '/' overlay.
APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Serialize all config writes. Flask is multi-threaded; _write_merged_config is
# a read-merge-write critical section on a shared file, and on a single-file
# bind mount the final write is a NON-atomic in-place overwrite (see
# _write_config_atomic). Without this lock two concurrent saves can lose an edit
# (last-writer-wins on a stale snapshot) or tear the file mid-write. Specified in
# the L18 design doc; restored after the post-ship audit found it had been dropped.
_CONFIG_WRITE_LOCK = threading.Lock()

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

def get_config_backup_path():
    """Durable path for the rolling last-known-good config backup.

    The primary config.json is a SINGLE-FILE bind mount (../config.json:/config.json),
    so inside the container its parent directory is '/', the EPHEMERAL overlay — a
    .bak written there vanishes on container recreation, exactly when recovery is
    needed. So when the config file sits at the filesystem root, redirect the
    backup to the persisted, host-visible, gitignored data dir
    (inventory-hub/data/). In dev tests / directory-mounted layouts the parent is
    a normal directory, so the .bak stays beside the config file — and follows the
    monkeypatched get_config_path automatically, keeping tests isolated."""
    config_file, _mode = get_config_path()
    parent = os.path.dirname(config_file)
    if parent in ('', '/', os.sep):
        return os.path.join(APP_DIR, 'data', 'config.json.bak')
    return config_file + '.bak'


def _try_load_backup():
    """Best-effort parse of the rolling config backup. Returns the dict on
    success, or None if it is missing / unreadable / not a JSON object. Lets
    load_config() and _write_merged_config() auto-recover from a corrupt primary
    config.json (the in-place-overwrite crash window)."""
    bak = get_config_backup_path()
    if not os.path.exists(bak):
        return None
    try:
        with open(bak, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def load_config():
    defaults = {
        "server_ip": "127.0.0.1",
        "spoolman_port": 7912,
        "sync_delay": 0.5,
        "printer_map": {},
        "dryer_slots": [],
        # FilaBridge Phase-2 cutover: when True, FCC deducts filament on FINISHED
        # prints (the slicer footer) instead of FilaBridge. Default False so the
        # code ships DARK — flip it the same moment the FilaBridge container is
        # stopped, or completed prints double-deduct.
        "fcc_owns_completion_deduct": False
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
            # config.json EXISTS but won't parse — e.g. corrupt or half-written
            # by a crash during the non-atomic in-place overwrite. Do NOT silently
            # fall through to localhost defaults (that turns a config-corruption
            # incident into a baffling "Spoolman unreachable" outage). Auto-recover
            # from the rolling backup if it parses, and log CRITICAL either way.
            recovered = _try_load_backup()
            if recovered is not None:
                final_config.update(recovered)
                if hasattr(state, 'logger'):
                    state.logger.critical(
                        f"config.json unreadable ({e}); RECOVERED from {get_config_backup_path()}. "
                        "Re-save in the Config modal to repair the primary file.")
            elif hasattr(state, 'logger'):
                state.logger.critical(
                    f"config.json unreadable ({e}) and no usable backup — running on DEFAULTS; "
                    "the Spoolman host may be wrong until config.json is repaired.")
    else:
        if hasattr(state, 'logger'):
            state.logger.warning(f"Config file not found at {config_file}")

    # Defensive: the redaction sentinel is a reserved marker, never a real secret.
    # It only reaches disk if a REDACTED export was copied into place instead of
    # imported (normal save/import strip it). Treat it as UNSET so nothing ever
    # authenticates with the literal placeholder string. See config_schema.SECRET_KEYS.
    for _sk in config_schema.SECRET_KEYS:
        if final_config.get(_sk) == config_schema.SECRET_SENTINEL:
            final_config[_sk] = ""

    # Force Uppercase Keys for Printer Map
    if 'printer_map' in final_config:
        final_config['printer_map'] = {k.upper(): v for k, v in final_config['printer_map'].items()}
        
    return final_config

def get_api_urls():
    cfg = load_config()
    server_ip = cfg.get("server_ip")
    sm_url = f"http://{server_ip}:{cfg.get('spoolman_port')}"
    # fb_url is VESTIGIAL post-FilaBridge-decommission (2026-06-13). The
    # filabridge_ip/filabridge_port config keys were removed; the only remaining
    # dereference is a fail-soft boot credential seed against the now-stopped
    # FilaBridge. Kept as a well-formed placeholder purely so the (sm_url, fb_url)
    # signature and its ~7 `_, fb_url = get_api_urls()` callers don't change.
    # Full removal (drop fb_url + the filabridge_url params threaded through
    # prusalink_api) is filed as its own follow-up.
    fb_url = f"http://{server_ip}:5000/api"
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


# os.replace() raises one of these when `path` is a mount point you can't
# rename over — the single-file bind-mount case (see _write_config_atomic).
_BIND_MOUNT_REPLACE_ERRNOS = frozenset((errno.EBUSY, errno.EXDEV, errno.EINVAL))


def _write_config_atomic(cfg_dict, path):
    """One write attempt, as durable as the target's filesystem allows.

    PRIMARY (atomic): a per-call uniquely-named temp file in the same directory,
    fsync, then os.replace onto `path` (atomic on POSIX and NTFS). Mirrors
    locations_db._write_locations_atomic (the outage-hardened precedent).

    SINGLE-FILE BIND-MOUNT FALLBACK: config.json is bind-mounted as an
    individual file in dev (`../config.json:/config.json`) and prod, so `path`
    is itself a mount point — you CANNOT rename another file over it and
    os.replace raises EBUSY (errno 16; EXDEV/EINVAL on some storage drivers).
    locations.json never hits this because it lives inside a *directory* mount.
    When os.replace fails with that signature, fall back to an fsynced in-place
    overwrite (same inode, new bytes). That step alone isn't atomic, but the
    caller's rolling .bak snapshot + exact-equality verify-after-write +
    retry-once still guard the write.

    Raises on failure; the caller decides whether to retry."""
    parent_dir = os.path.dirname(path) or '.'
    # Serialize ONCE up front: a serialization error is caught before any file
    # is touched, and the SAME bytes feed both the temp write and the in-place
    # fallback so the two paths can never diverge. ensure_ascii=False so
    # non-ASCII values (e.g. emoji printer names like "🦝 XL") round-trip as
    # real UTF-8 instead of being rewritten to \uXXXX escapes on every save.
    payload = json.dumps(cfg_dict, indent=4, ensure_ascii=False)
    tmp = tempfile.NamedTemporaryFile(
        mode='w', encoding='utf-8',
        dir=parent_dir, prefix='config.', suffix='.tmp', delete=False,
    )
    tmp_path = tmp.name
    try:
        try:
            tmp.write(payload)
            tmp.flush()
            os.fsync(tmp.fileno())
        finally:
            tmp.close()
        try:
            os.replace(tmp_path, path)
        except OSError as e:
            if e.errno not in _BIND_MOUNT_REPLACE_ERRNOS:
                raise
            # Target is a single-file bind mount → overwrite in place, fsynced.
            with open(path, 'w', encoding='utf-8') as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            try:
                os.remove(tmp_path)
            except OSError:
                pass
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

    ok, err = _write_merged_config(coerced)
    if not ok:
        return {"ok": False, "error": err, "saved": []}

    if hasattr(state, 'logger'):
        state.logger.info(f"💾 Config updated ({', '.join(sorted(coerced))})")
    return {"ok": True, "error": None, "saved": sorted(coerced)}


def _write_merged_config(changes):
    """Shared persist path used by save_config. Passthrough-
    merges `changes` (already validated/canonicalized by the caller) onto the
    RAW on-disk config, then atomic write + exact-equality verify-after-write +
    retry-once, with a DURABLE rolling last-known-good .bak. Sets LAST_CONFIG_ERROR
    and returns (ok: bool, error: str|None).

    The whole read-merge-write runs under _CONFIG_WRITE_LOCK so concurrent saves
    can't lose an edit or tear the (non-atomic, on a single-file bind mount) write.
    If the existing config is unreadable it tries to REPAIR from the rolling backup
    rather than refuse outright (which would lock the operator out of every save);
    it only refuses when there's no usable backup either."""
    global LAST_CONFIG_ERROR
    config_file, _mode = get_config_path()

    with _CONFIG_WRITE_LOCK:
        existing = load_config_raw()
        repaired_from_backup = False

        if existing is None:
            # Primary config.json is present but unreadable (corrupt / half-written
            # by a crash mid in-place-overwrite). Rather than refuse and lock the
            # operator out of ALL saves, repair from the durable rolling backup:
            # merge the new change onto the last-known-good and write a clean file.
            backup = _try_load_backup()
            if backup is None:
                LAST_CONFIG_ERROR = (
                    "refusing to save: the existing config could not be read as a JSON object "
                    "and no usable backup exists (saving would drop all other keys) — "
                    "fix or remove config.json first")
                if hasattr(state, 'logger'):
                    state.logger.error(LAST_CONFIG_ERROR)
                return False, LAST_CONFIG_ERROR
            existing = backup
            repaired_from_backup = True
            if hasattr(state, 'logger'):
                state.logger.critical(
                    "config.json was unreadable; REPAIRING from backup and applying this save.")

        if not existing and not os.path.exists(config_file):
            # Genuinely fresh install (no file): seed from runtime defaults so the
            # created file is complete, not a lone partial object.
            merged = dict(load_config())
        else:
            merged = dict(existing)

        # Rolling last-known-good snapshot: persist the PRE-EDIT readable config to
        # a DURABLE, host-visible path (get_config_backup_path — NOT next to the
        # single-file bind mount, whose parent is the container's ephemeral
        # overlay). Skip when we just recovered FROM the backup (it already is the
        # LKG) or when there's nothing good to back up.
        if existing and not repaired_from_backup:
            bak_path = get_config_backup_path()
            try:
                os.makedirs(os.path.dirname(bak_path) or '.', exist_ok=True)
                with open(bak_path, 'w', encoding='utf-8') as bf:
                    json.dump(existing, bf, indent=4, ensure_ascii=False)
            except OSError:
                pass  # best-effort

        merged.update(changes)  # only the caller's keys overwritten; the rest preserved

        def _attempt():
            _write_config_atomic(merged, config_file)
            return _verify_config_file(merged, config_file)

        try:
            ok, detail = _attempt()
        except Exception as e:
            LAST_CONFIG_ERROR = f"config write failed: {e}"
            if hasattr(state, 'logger'):
                state.logger.error(LAST_CONFIG_ERROR)
            return False, LAST_CONFIG_ERROR

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
                return False, LAST_CONFIG_ERROR
            if not ok:
                LAST_CONFIG_ERROR = f"config verify-after-write failed twice: {detail}"
                if hasattr(state, 'logger'):
                    state.logger.critical(LAST_CONFIG_ERROR)
                return False, LAST_CONFIG_ERROR

        return True, None


def _canonicalize_printer_map(new_map):
    """Validate + canonicalize an edited printer_map for save. Uppercases keys
    (matching load_config's normalization), rejects case-insensitive collisions,
    and validates each entry's shape. Returns (canonical_dict, error_str|None)."""
    if not isinstance(new_map, dict):
        return None, "printer_map must be an object"
    canonical = {}
    for raw_key, info in new_map.items():
        key = str(raw_key).strip().upper()
        if not key:
            return None, "printer_map: a toolhead is missing its LocationID"
        if key in canonical:
            return None, f"printer_map: duplicate LocationID '{key}' (case-insensitive collision)"
        if not isinstance(info, dict):
            return None, f"printer_map['{key}'] must be an object"
        name = str(info.get("printer_name", "")).strip()
        if not name:
            return None, f"printer_map['{key}']: printer name is required"
        pos_raw = info.get("position", 0)
        if isinstance(pos_raw, bool):
            return None, f"printer_map['{key}']: position must be a number, not a boolean"
        try:
            position = int(pos_raw)
        except (TypeError, ValueError):
            return None, f"printer_map['{key}']: position must be a whole number"
        if position < 0:
            return None, f"printer_map['{key}']: position must be ≥ 0"
        canonical[key] = {"printer_name": name, "position": position}
    return canonical, None


# NOTE (L271 Phase 4 step 4 — the cutover): ``save_printer_map`` was RETIRED here.
# printer_map is no longer written to config.json — the editor PUT
# (/api/printer_map) now persists the edit onto each first-class Type:"Printer"
# row's toolheads[] in locations.json (the single source of truth) via
# locations_db. config:printer_map remains readable only as the one-time startup
# priming seed. ``_canonicalize_printer_map`` above is KEPT — it is the shared
# validator the PUT calls before the row write.
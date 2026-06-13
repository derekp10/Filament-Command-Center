import requests
import re
import threading
import traceback
from typing import Dict, Optional
import perf_trace  # L3 latency probe — zero-cost when no trace is active
import bgcode_decode  # binary-gcode (.bgcode) decoder for the cancel prefix-parse

# Per-operation memo for get_printer_state (L3 fix A). A single
# perform_smart_move probes the SAME printer in BOTH its phase-1 and phase-2
# (auto-deploy) passes; without this the recursion hits the network twice and,
# on an offline printer, pays the full timeout twice — the dominant cost in the
# slot-assign latency. The logic.perform_smart_move wrapper begins/clears it per
# top-level move, so it is strictly scoped and never serves stale state to
# unrelated requests. When no cache is active (the common case for every other
# caller) get_printer_state behaves exactly as before — no memoization.
_probe_cache = threading.local()


def begin_probe_cache():
    """Start a fresh per-operation get_printer_state memo on this thread."""
    _probe_cache.data = {}


def clear_probe_cache():
    """Tear down the per-operation memo. Idempotent."""
    _probe_cache.data = None


def fetch_printer_credentials(filabridge_url: str, printer_name: str):
    """Return ``{'ip_address','api_key'}`` for a printer, or ``None``.

    FilaBridge Phase-2 cutover: credentials now live on the first-class
    Type:"Printer" row in locations.json (``printer_creds``), read here via
    ``locations_db.get_printer_credentials``. ``filabridge_url`` is retained for
    the call-site/back-compat contract (every consumer + test stub passes it) but
    is now UNUSED — the same pattern Scope 1 used to retire ``_fb_spool_location``'s
    FilaBridge read. The one-time boot seed (``fetch_all_filabridge_printers`` →
    ``locations_db.seed_printer_credentials``) is what primes the rows from
    FilaBridge before it is decommissioned.

    Lazy local import of ``locations_db`` to avoid a circular import at module
    load (``locations_db`` / ``app`` import ``prusalink_api``).
    """
    try:
        import locations_db
        return locations_db.get_printer_credentials(printer_name)
    except Exception as e:
        print(f"Error reading printer credentials for {printer_name!r}: {e}")
        return None


def fetch_all_filabridge_printers(filabridge_url: str) -> Dict[str, Dict]:
    """Pull the full ``{printer_name: {ip_address, api_key}}`` map from FilaBridge
    ``GET /printers``. Used ONLY by the one-time boot credential SEED
    (``locations_db.seed_printer_credentials``) while FilaBridge is still up —
    NOT on any live path. Returns ``{}`` on any failure (fail-soft: a missing
    FilaBridge just means the seed retries next boot)."""
    out: Dict[str, Dict] = {}
    try:
        with perf_trace.span("prusalink.fetch_all_printers"):
            response = requests.get(f"{filabridge_url}/printers", timeout=5)
        if response.ok:
            printers = (response.json() or {}).get('printers', {}) or {}
            for _pid, pdata in printers.items():
                if not isinstance(pdata, dict):
                    continue
                name = pdata.get('name')
                if not name:
                    continue
                out[str(name)] = {
                    "ip_address": pdata.get("ip_address"),
                    "api_key": pdata.get("api_key"),
                }
    except Exception as e:
        print(f"Error fetching all printers from FilaBridge: {e}")
    return out

FB_PARSE_STATUS = ""

def _parse_weights_from_match(match) -> Dict[int, float]:
    weights_str = match.group(1)
    weights = [w.strip() for w in weights_str.split(',')]
    usage = {}
    for idx, w in enumerate(weights):
        try:
            val = float(w)
            if val > 0:
                usage[idx] = val
        except ValueError:
            pass
    return usage


def parse_footer_usage(gcode_content: str) -> Dict[int, float]:
    """Parse the slicer's full per-tool ``filament used [g]`` footer →
    ``{tool_index: grams}`` — the COMPLETE-print estimate (exactly what FilaBridge
    bills). Used by FCC's Phase-2 FINISHED-completion deduct (the footer is exact;
    the cancel prefix-parse is only for PARTIAL/cancelled prints). Same indexing
    space as ``parse_partial_filament_usage`` (the comma-separated array is tool
    0,1,2,…). Empty dict when the footer is absent."""
    if not gcode_content:
        return {}
    m = re.search(r';?\s*filament used \[g\]\s*=\s*([0-9.,\s]+)', gcode_content)
    return _parse_weights_from_match(m) if m else {}


def download_gcode_and_parse_usage(ip_address: str, api_key: str, filename: str) -> Optional[Dict[int, float]]:
    """Download a finished/errored print's gcode and parse the per-toolhead
    ``filament used [g]`` footer (the slicer's FULL-job estimate) → ``{tool: grams}``.
    Used by the FilaBridge error-recovery path (``api_fb_aggressive_parse`` /
    ``_auto_recover_task``) and, after the Phase-2 cutover, as the source for FCC's
    own FINISHED-completion deduct — the footer IS the complete-print deduct,
    exactly what FilaBridge billed (and FilaBridge's parser does no better: same
    footer, no M486 handling).

    Reuses ``download_gcode_content``, which transparently decodes binary G-code
    (``.bgcode`` — Derek's entire fleet). The old Range fast-path was REMOVED: a
    2 MB tail slice of a ``.bgcode`` file is heatshrink+MeatPack-compressed bytes
    the footer regex can never match (and the footer lives near the FRONT of the
    container, not the tail), so it only ever worked on the now-extinct plain-ASCII
    gcode and silently read ZERO on the real binary fleet. ``FB_PARSE_STATUS`` is
    still maintained for the recovery modal's progress poll. Returns None on
    failure.
    """
    global FB_PARSE_STATUS
    FB_PARSE_STATUS = f"Downloading + decoding {filename}..."
    try:
        content = download_gcode_content(ip_address, api_key, filename)
    except Exception as e:
        FB_PARSE_STATUS = f"Download/decode failed: {e}"
        print(f"Error downloading/decoding gcode for {filename}: {e}")
        traceback.print_exc()
        return None
    if content is None:
        FB_PARSE_STATUS = f"Failed to download {filename} from PrusaLink."
        print(f"Failed to download {filename} from PrusaLink.")
        return None
    match = re.search(r';?\s*filament used \[g\]\s*=\s*([0-9.,\s]+)', content)
    if match:
        FB_PARSE_STATUS = "Decoded"
        return _parse_weights_from_match(match)
    FB_PARSE_STATUS = f"No filament usage metadata found in {filename}."
    print(f"No filament usage metadata found in {filename}")
    return None


# --- Cancelled-print partial usage (FilaBridge absorption §9.2, slice 3) ------

def _download_file_bytes(ip_address: str, api_key: str, filename: str) -> Optional[bytes]:
    """Download a print file's raw bytes from PrusaLink. After a print STOPS the
    file un-404s (it's locked + 404 while printing), so this works at cancel
    time. Returns the bytes, or None on failure."""
    filename = filename.lstrip('/')
    url = f"http://{ip_address}/{filename}"
    headers = {'X-Api-Key': api_key} if api_key else {}
    try:
        resp = requests.get(url, headers=headers, timeout=60)
        if resp.ok:
            return resp.content
        print(f"download_gcode_content: HTTP {resp.status_code} for {filename}")
    except Exception as e:
        print(f"download_gcode_content failed for {filename}: {e}")
    return None


def download_gcode_content(ip_address: str, api_key: str, filename: str) -> Optional[str]:
    """Download the full print file as ASCII G-code text, transparently decoding
    binary G-code (`.bgcode`) — its body is heatshrink+MeatPack compressed, so a
    naive text decode is garbage; `bgcode_decode` reconstructs the moves so the
    prefix-parse can run on Derek's real (binary) prints. Returns None on
    failure. (For binary gcode, prefer `fetch_cancel_gcode`, which also remaps
    the progress fraction from compressed-file to decoded-text space.)"""
    raw = _download_file_bytes(ip_address, api_key, filename)
    if raw is None:
        return None
    try:
        if bgcode_decode.is_bgcode(raw):
            return bgcode_decode.decode_bgcode(raw).get("gcode") or None
        return raw.decode("utf-8", "replace")
    except Exception as e:
        print(f"download_gcode_content: decode failed for {filename}: {e}")
        return None


def fetch_cancel_gcode(ip_address: str, api_key: str, filename: str,
                       reached_fraction: float) -> Optional[Dict]:
    """Download + decode a print file for the cancelled-print parser.

    Returns ``{"gcode": ascii_text, "fraction": effective_fraction}`` or None on
    failure. For binary G-code the printer's ``progress`` (a byte position in
    the COMPRESSED .bgcode file) is remapped to the matching position in the
    DECODED text, so the prefix-parse slices at the right point even though the
    header/thumbnail/metadata blocks (which carry no extrusion) sit before the
    G-code in the file. For plain ASCII gcode the fraction passes through.
    """
    raw = _download_file_bytes(ip_address, api_key, filename)
    if raw is None:
        return None
    try:
        if bgcode_decode.is_bgcode(raw):
            dec = bgcode_decode.decode_bgcode(raw)
            if not dec.get("gcode"):
                return None
            return {"gcode": dec["gcode"],
                    "fraction": bgcode_decode.progress_to_decoded_fraction(dec, reached_fraction)}
        text = raw.decode("utf-8", "replace")
        return {"gcode": text, "fraction": max(0.0, min(1.0, float(reached_fraction)))}
    except Exception as e:
        print(f"fetch_cancel_gcode: failed for {filename}: {e}")
        return None


_GCODE_MM_RE = re.compile(r';?\s*filament used \[mm\]\s*=\s*([0-9.,\s]+)')


def parse_partial_filament_usage(gcode_content: str, reached_fraction: float) -> Dict[int, float]:
    """Per-toolhead ACTUAL grams extruded up to a cancel point — the cancelled-
    print partial-deduction core (FilaBridge absorption design §9.2, rung 1).

    A cancelled print's ``filament used [g]`` footer is the FULL-job estimate,
    so deducting it would massively over-charge. Instead we parse the gcode from
    the start up to the byte position actually reached (PrusaLink ``progress`` is
    ``sd_percent_done`` = the gcode FILE-BYTE fraction), summing each tool's real
    extrusion, then convert mm->g using the slicer's OWN per-tool grams-per-mm
    ratio (from the ``filament used [g]`` and ``[mm]`` footers — no material
    density table needed, and it's exact for that filament).

    Critically this is PER-TOOLHEAD by construction: a tool never selected
    before the cancel sums to zero extrusion and is simply absent from the
    result (the XL "untouched head deducts 0" invariant, satisfied natively).

    Args:
        gcode_content: the FULL gcode file text (footer + body). ``reached_byte``
            is computed against this content's length, so it must be the whole
            file, not a Range subset.
        reached_fraction: progress 0.0..1.0 (``progress`` percent / 100) — the
            fraction of the file reached when the print was cancelled.

    Returns:
        ``{toolhead_index: grams}`` for tools that extruded before the cancel.
        Untouched tools are omitted (caller treats absent as 0). Empty dict when
        nothing extruded (cancel before first extrusion) or the footer lacks the
        per-tool g/mm metadata needed to convert.

    Handles absolute (M82, default) and relative (M83) extrusion, ``G92 E<n>``
    extruder-origin resets, per-tool absolute-E context across ``T<n>`` changes
    (each tool changer head has its own E coordinate), and inline ``;`` comments.
    """
    if not gcode_content:
        return {}

    # --- per-tool grams-per-mm from the slicer footers ---------------------
    g_match = re.search(r';?\s*filament used \[g\]\s*=\s*([0-9.,\s]+)', gcode_content)
    mm_match = _GCODE_MM_RE.search(gcode_content)
    if not g_match or not mm_match:
        return {}
    grams = _parse_weights_from_match(g_match)
    mms = _parse_weights_from_match(mm_match)
    g_per_mm = {
        tool: grams[tool] / mm
        for tool, mm in mms.items()
        if mm > 0 and tool in grams
    }
    if not g_per_mm:
        return {}

    # --- prefix-parse the body up to the reached byte position -------------
    reached_fraction = max(0.0, min(1.0, float(reached_fraction)))
    total_bytes = len(gcode_content.encode('utf-8'))
    reached_byte = int(reached_fraction * total_bytes)
    if reached_byte <= 0:
        return {}

    # When the gcode carries no explicit `Tn` (a single-material print whose
    # one tool is selected outside the body, common on MMU), attribute all
    # extrusion to the sole tool the footer marks as used. Multi-tool prints
    # have `Tn` changes and start at tool 0.
    default_tool = next(iter(g_per_mm)) if len(g_per_mm) == 1 else 0
    active_tool = default_tool
    relative_e = False           # M82 absolute (default) vs M83 relative
    e_high: Dict[int, float] = {}   # per-tool high-water E since last G92 reset
    extruded_mm: Dict[int, float] = {}
    saw_tool = False
    consumed = 0

    for line in gcode_content.splitlines(keepends=True):
        consumed += len(line.encode('utf-8'))
        if consumed > reached_byte:
            break
        code = line.split(';', 1)[0].strip()
        if not code:
            continue
        upper = code.upper()

        tmatch = re.match(r'^T(\d+)(?![0-9])', upper)
        if tmatch:
            active_tool = int(tmatch.group(1))
            saw_tool = True
            continue
        if upper.startswith('M82'):
            relative_e = False
            continue
        if upper.startswith('M83'):
            relative_e = True
            continue
        if upper.startswith('G92'):
            em = re.search(r'E(-?\d*\.?\d+)', upper)
            if em:
                # G92 E<v> redefines the E origin: reset the high-water mark so
                # extrusion past <v> counts (filament already used stays counted).
                e_high[active_tool] = float(em.group(1))
            else:
                # Bare G92 (no params) resets all axes incl. E to 0 (RepRap) —
                # reset the high-water mark too. (PrusaSlicer emits `G92 E0`
                # explicitly, so this only guards hand/odd gcode.)
                e_high[active_tool] = 0.0
            continue
        # Match G0/G1 with or WITHOUT a trailing space (Prusa no-spaces gcode
        # emits `G1X92.3Y9.4E.001`); exclude G10/G11 etc.
        if re.match(r'^G[01](?![0-9])', upper):
            em = re.search(r'E(-?\d*\.?\d+)', upper)
            if not em:
                continue
            e = float(em.group(1))
            if relative_e:
                # Net extrusion: a retract (negative) and its later re-prime
                # cancel, so signed accumulation matches the slicer's count.
                extruded_mm[active_tool] = extruded_mm.get(active_tool, 0.0) + e
            else:
                # High-water mark: only E that EXCEEDS the running max is new
                # filament (a retract + re-prime below the max adds nothing).
                hi = e_high.get(active_tool, 0.0)
                if e > hi:
                    extruded_mm[active_tool] = extruded_mm.get(active_tool, 0.0) + (e - hi)
                    e_high[active_tool] = e

    # If we never saw a Tn but accumulated onto a default that has no g/mm,
    # fold it onto the sole footer tool (single-material, no explicit select).
    if not saw_tool and len(g_per_mm) == 1 and extruded_mm:
        sole = next(iter(g_per_mm))
        merged = sum(extruded_mm.values())
        extruded_mm = {sole: merged}

    # --- convert extruded mm -> grams via the slicer's own ratio -----------
    result = {}
    for tool, mm in extruded_mm.items():
        if mm > 0 and tool in g_per_mm:
            result[tool] = round(mm * g_per_mm[tool], 4)
    return result

def get_printer_state(filabridge_url: str, printer_name: str) -> Optional[Dict]:
    """Cached front door for the PrusaLink state probe (L3 fix A).

    Memoizes per-operation when a probe cache is active (see begin_probe_cache),
    so a single perform_smart_move probes a given printer ONCE across its
    phase-1/phase-2 auto-deploy recursion instead of twice. With no active cache
    it just calls through, so every other caller (/api/printer_state, usage
    deduction) is unchanged.
    """
    key = (filabridge_url, printer_name)
    cache = getattr(_probe_cache, "data", None)
    if cache is not None and key in cache:
        return cache[key]
    result = _probe_printer_state(filabridge_url, printer_name)
    if cache is not None:
        cache[key] = result
    return result


def _probe_printer_state(filabridge_url: str, printer_name: str) -> Optional[Dict]:
    """Best-effort PrusaLink state probe for a named printer. Returns a dict
    {state: str, is_active: bool} or None on any failure (fail-open — the
    caller treats None as "unknown" and does not block user actions).

    Tries the v1 status endpoint first (newer PrusaLink firmware), then falls
    back to the legacy /api/printer shape. Timeouts are deliberately short
    so the assignment-flow warning doesn't stall the UI when the printer is
    unreachable (offline, networked elsewhere, cold-rebooting, etc.).

    `is_active` is true only when PrusaLink reports a state in which a spool
    swap would physically disrupt the print: PRINTING, PAUSING, RESUMING.
    PAUSED, BUSY (heating/homing/prep), Operational, Idle, Finished, and
    Stopped all read as not-active so eject/swap operations can proceed —
    those are exactly the moments the user wants to swap filament (13.8).
    """
    # PrusaLink states classified as "active print" — anything outside this
    # set is fair game for eject / smart-move / quick-swap.
    _ACTIVE_PRINT_STATES = {"PRINTING", "PAUSING", "RESUMING"}
    creds = fetch_printer_credentials(filabridge_url, printer_name)
    if not creds or not creds.get("ip_address"):
        return None
    ip = creds["ip_address"]
    api_key = creds.get("api_key")
    headers = {"X-Api-Key": api_key} if api_key else {}

    # v1 status — returns {"printer": {"state": "PRINTING", ...}, ...}
    try:
        with perf_trace.span("prusalink.status"):
            r = requests.get(f"http://{ip}/api/v1/status", headers=headers, timeout=2)
        if r.ok:
            body = r.json() or {}
            printer = body.get("printer") or {}
            state_str = str(printer.get("state", "")).upper()
            if state_str:
                return {"state": state_str, "is_active": state_str in _ACTIVE_PRINT_STATES}
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
        # L3 fix B: a connection-level failure (timeout / refused / no route)
        # means the printer is unreachable. The legacy endpoint lives on the
        # SAME ip:port and will time out too — skip it instead of burning a
        # second 2s timeout. Halves the probe cost for an offline printer.
        return None
    except Exception:
        # v1 answered but the body was unusable (bad JSON / odd shape) — fall
        # through and try the legacy endpoint, which may parse on old firmware.
        pass

    # Legacy /api/printer — returns {"state": {"text": "Printing", "flags": {...}}, ...}
    try:
        with perf_trace.span("prusalink.status"):
            r = requests.get(f"http://{ip}/api/printer", headers=headers, timeout=2)
        if r.ok:
            body = r.json() or {}
            flags = (body.get("state") or {}).get("flags") or {}
            state_text = str((body.get("state") or {}).get("text", "")).upper()
            # Legacy /api/printer only exposes `printing` and `paused` flags
            # — there's no "pausing/resuming" distinction. Per 13.8 we drop
            # the paused-blocks-eject behavior; mid-print pause is exactly
            # when a user wants to swap filament. Block only on the active
            # printing flag.
            is_active = bool(flags.get("printing")) or state_text in _ACTIVE_PRINT_STATES
            if state_text:
                return {"state": state_text, "is_active": is_active}
    except Exception:
        pass

    return None


def _parse_v1_job(body: Dict) -> Optional[Dict]:
    """Normalize a PrusaLink ``/api/v1/job`` body to the tracker's shape."""
    f = body.get("file") or {}
    refs = f.get("refs") or {}
    # refs.download is the storage-relative URL PrusaLink serves the gcode at
    # (e.g. "/usb/Print.bgcode"); path/name are fallbacks for odd firmware.
    filename = refs.get("download") or f.get("path") or f.get("name")
    if not filename:
        return None
    prog = body.get("progress")
    if prog is None:
        prog = (body.get("job") or {}).get("progress")
    try:
        progress = max(0.0, min(1.0, float(prog) / 100.0)) if prog is not None else 0.0
    except (TypeError, ValueError):
        progress = 0.0
    return {
        "job_id": body.get("id"),
        "filename": filename,
        "progress": progress,
        "file_meta": f.get("meta") or {},
    }


def _parse_legacy_job(body: Dict) -> Optional[Dict]:
    """Normalize a legacy PrusaLink ``/api/job`` body (older firmware)."""
    job = body.get("job") or {}
    f = job.get("file") or {}
    filename = f.get("path") or f.get("name") or f.get("display")
    if not filename:
        return None
    completion = (body.get("progress") or {}).get("completion")
    try:
        # Legacy `completion` is a 0..1 fraction on most firmware but a
        # 0..100 percent on some builds — normalize defensively.
        c = float(completion) if completion is not None else 0.0
        progress = c / 100.0 if c > 1.0 else c
        progress = max(0.0, min(1.0, progress))
    except (TypeError, ValueError):
        progress = 0.0
    return {
        "job_id": body.get("id") or job.get("id"),
        "filename": filename,
        "progress": progress,
        "file_meta": {},
    }


def get_printer_job(filabridge_url: str, printer_name: str) -> Optional[Dict]:
    """Best-effort fetch of the CURRENTLY-LOADED print job for a named printer.

    ``get_printer_state`` returns only the state enum; the cancelled-print
    detector (FilaBridge absorption design §9.3 / build slice 2a) also needs the
    running job's filename, id, and byte-progress to compute the PARTIAL deduct.
    PrusaLink tears the job block down the instant a print STOPS, so the tracker
    calls this on every IN-PROGRESS poll and latches the values for use on the
    later terminal edge — reading it post-cancel returns nothing.

    Returns ``{"job_id", "filename", "progress", "file_meta"}`` or None when
    there's no active job or the printer is unreachable. ``progress`` is the
    gcode FILE-BYTE fraction 0.0..1.0 (PrusaLink ``progress`` percent / 100 —
    the same proxy ``parse_partial_filament_usage`` slices on). ``filename`` is
    the storage-relative path PrusaLink serves the gcode at
    (``file.refs.download``, else ``file.path`` / ``file.name``), ready to hand
    to ``download_gcode_content``. Fails open (None) on any error.
    """
    creds = fetch_printer_credentials(filabridge_url, printer_name)
    if not creds or not creds.get("ip_address"):
        return None
    ip = creds["ip_address"]
    api_key = creds.get("api_key")
    headers = {"X-Api-Key": api_key} if api_key else {}

    # v1 job — {"id", "progress"(0-100), "file": {"refs": {"download"}, "path",
    # "name", "meta": {...}}, ...}. 204/empty body when the printer is idle.
    try:
        with perf_trace.span("prusalink.job"):
            r = requests.get(f"http://{ip}/api/v1/job", headers=headers, timeout=2)
        if r.status_code == 204:
            return None  # no active job
        if r.ok and r.content:
            parsed = _parse_v1_job(r.json() or {})
            if parsed:
                return parsed
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
        # Unreachable — the legacy endpoint lives on the same host and will
        # time out too; skip it (same L3 fix-B reasoning as the state probe).
        return None
    except Exception:
        pass  # odd/empty body — fall through to the legacy shape

    # Legacy /api/job — {"job": {"file": {"name","path"}}, "progress": {"completion"}}
    try:
        with perf_trace.span("prusalink.job"):
            r = requests.get(f"http://{ip}/api/job", headers=headers, timeout=2)
        if r.ok and r.content:
            return _parse_legacy_job(r.json() or {})
    except Exception:
        pass
    return None


def get_printer_mmu_flag(filabridge_url: str, printer_name: str) -> Optional[bool]:
    """Best-effort probe of `/api/v1/info.mmu` on the named printer.

    Returns True when an MMU unit is attached/enabled, False when it's
    definitively not, or None when the printer is unreachable or the
    firmware doesn't expose the field. Callers treat None as "unknown" —
    do not block behaviour on an unknown answer.

    Note: the `mmu` field reflects hardware attachment, not per-print
    routing. A Core One with MMU3 attached but printing via direct feed
    still reports `mmu: true`. Used by the usage-deduction path to pick
    between M0/M1 alias locations when printer_map has both.
    """
    creds = fetch_printer_credentials(filabridge_url, printer_name)
    if not creds or not creds.get("ip_address"):
        return None
    ip = creds["ip_address"]
    api_key = creds.get("api_key")
    headers = {"X-Api-Key": api_key} if api_key else {}
    try:
        r = requests.get(f"http://{ip}/api/v1/info", headers=headers, timeout=2)
        if r.ok:
            body = r.json() or {}
            if "mmu" in body:
                return bool(body.get("mmu"))
    except Exception:
        pass
    return None


def acknowledge_filabridge_error(filabridge_url: str, error_id: str) -> bool:
    """
    Acknowledges the FilaBridge error to dismiss it from the server.
    """
    try:
        # Ensure we construct the URL properly, POST /api/print-errors/:id/acknowledge
        url = f"{filabridge_url}/print-errors/{error_id}/acknowledge"
        response = requests.post(url, timeout=5)
        return response.ok
    except Exception as e:
        print(f"Failed to acknowledge FilaBridge error {error_id}: {e}")
    return False

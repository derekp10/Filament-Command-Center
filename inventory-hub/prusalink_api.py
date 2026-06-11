import requests
import re
import threading
import traceback
from typing import Dict, Optional
import perf_trace  # L3 latency probe — zero-cost when no trace is active

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
    """
    Fetches the IP address and API key for a given printer name from FilaBridge.
    """
    try:
        with perf_trace.span("prusalink.fetch_creds"):
            response = requests.get(f"{filabridge_url}/printers", timeout=5)
        if response.ok:
            data = response.json()
            printers = data.get('printers', {})
            for pid, pdata in printers.items():
                if pdata.get('name') == printer_name:
                    return {
                        "ip_address": pdata.get("ip_address"),
                        "api_key": pdata.get("api_key")
                    }
    except Exception as e:
        print(f"Error fetching printer credentials from FilaBridge: {e}")
    return None

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

def download_gcode_and_parse_usage(ip_address: str, api_key: str, filename: str) -> Optional[Dict[int, float]]:
    """
    Downloads the gcode file from PrusaLink and parses the 'filament used [g]=' metadata.
    Returns a dictionary mapping toolhead index to grams used.
    """
    global FB_PARSE_STATUS
    filename = filename.lstrip('/')
    url = f"http://{ip_address}/{filename}"
    headers = {}
    if api_key:
        headers['X-Api-Key'] = api_key

    # Try Range request first (last 2MB)
    FB_PARSE_STATUS = f"Requesting Fast Meta-block for {filename}..."
    try:
        range_headers = headers.copy()
        range_headers['Range'] = 'bytes=-2097152'
        response = requests.get(url, headers=range_headers, timeout=10)
        
        if response.ok:
            if response.status_code == 206:
                content = response.text
                match = re.search(r';?\s*filament used \[g\]\s*=\s*([0-9.,\s]+)', content)
                if match:
                    FB_PARSE_STATUS = "Fast"
                    return _parse_weights_from_match(match)
                else:
                    FB_PARSE_STATUS = "Metadata not found in 2MB tail, falling back to full download..."
            elif response.status_code == 200:
                # PrusaLink completely ignored the Range header and fed us the entire file
                content = response.text
                match = re.search(r';?\s*filament used \[g\]\s*=\s*([0-9.,\s]+)', content)
                if match:
                    FB_PARSE_STATUS = "RAM"
                    return _parse_weights_from_match(match)
                else:
                    FB_PARSE_STATUS = "Full file provided automatically but metadata not found."
            else:
                FB_PARSE_STATUS = f"Range request rejected (HTTP {response.status_code}), falling back to full download..."
        else:
            FB_PARSE_STATUS = f"Range request failed (HTTP {response.status_code}), falling back to full download..."
    except requests.exceptions.ReadTimeout:
        FB_PARSE_STATUS = f"Range request timed out over PrusaLink network, falling back to full download..."
    except Exception as e:
        FB_PARSE_STATUS = f"Range request failed ({str(e)}), falling back to full download..."

    # Fallback to full download
    try:
        FB_PARSE_STATUS = f"Downloading full file into RAM for {filename} (this may take a minute)..."
        response = requests.get(url, headers=headers, timeout=60)
        
        if response.ok:
            FB_PARSE_STATUS = "File downloaded, parsing metadata..."
            content = response.text
            match = re.search(r';?\s*filament used \[g\]\s*=\s*([0-9.,\s]+)', content)
            if match:
                FB_PARSE_STATUS = "RAM"
                return _parse_weights_from_match(match)
            else:
                FB_PARSE_STATUS = f"No filament usage metadata found in {filename}."
                print(f"No filament usage metadata found in {filename}")
        else:
            msg = f"Failed to download {filename} from PrusaLink. Status: {response.status_code}"
            FB_PARSE_STATUS = msg
            print(msg)
    except Exception as e:
        FB_PARSE_STATUS = f"Full download failed: {str(e)}"
        print(f"Error aggressively downloading/parsing gcode: {e}")
        traceback.print_exc()

    return None


# --- Cancelled-print partial usage (FilaBridge absorption §9.2, slice 3) ------

def download_gcode_content(ip_address: str, api_key: str, filename: str) -> Optional[str]:
    """Download the FULL gcode file TEXT from PrusaLink.

    The cancelled-print prefix-parse needs the file BODY from byte 0 up to the
    reached position — a Range tail (as `download_gcode_and_parse_usage` uses to
    grab only the footer) won't do. After a print STOPS the file un-404s, so this
    works at cancel time. Returns the text, or None on failure.
    """
    filename = filename.lstrip('/')
    url = f"http://{ip_address}/{filename}"
    headers = {'X-Api-Key': api_key} if api_key else {}
    try:
        resp = requests.get(url, headers=headers, timeout=60)
        if resp.ok:
            return resp.text
        print(f"download_gcode_content: HTTP {resp.status_code} for {filename}")
    except Exception as e:
        print(f"download_gcode_content failed for {filename}: {e}")
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

    active_tool = 0
    relative_e = False           # M82 absolute (default) vs M83 relative
    last_e: Dict[int, float] = {}   # per-tool absolute-E position
    extruded_mm: Dict[int, float] = {}
    consumed = 0

    for line in gcode_content.splitlines(keepends=True):
        consumed += len(line.encode('utf-8'))
        if consumed > reached_byte:
            break
        code = line.split(';', 1)[0].strip()
        if not code:
            continue
        upper = code.upper()

        tmatch = re.match(r'^T(\d+)(?:\s|$)', upper)
        if tmatch:
            active_tool = int(tmatch.group(1))
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
                last_e[active_tool] = float(em.group(1))
            continue
        if upper.startswith('G1 ') or upper.startswith('G0 ') \
                or upper == 'G1' or upper == 'G0':
            em = re.search(r'E(-?\d*\.?\d+)', upper)
            if not em:
                continue
            e = float(em.group(1))
            if relative_e:
                if e > 0:
                    extruded_mm[active_tool] = extruded_mm.get(active_tool, 0.0) + e
            else:
                delta = e - last_e.get(active_tool, 0.0)
                if delta > 0:
                    extruded_mm[active_tool] = extruded_mm.get(active_tool, 0.0) + delta
                last_e[active_tool] = e

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

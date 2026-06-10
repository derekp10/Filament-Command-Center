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

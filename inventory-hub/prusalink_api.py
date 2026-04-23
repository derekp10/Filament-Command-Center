import requests
import re
import traceback
from typing import Dict, Optional

def fetch_printer_credentials(filabridge_url: str, printer_name: str):
    """
    Fetches the IP address and API key for a given printer name from FilaBridge.
    """
    try:
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
    """Best-effort PrusaLink state probe for a named printer. Returns a dict
    {state: str, is_active: bool} or None on any failure (fail-open — the
    caller treats None as "unknown" and does not block user actions).

    Tries the v1 status endpoint first (newer PrusaLink firmware), then falls
    back to the legacy /api/printer shape. Timeouts are deliberately short
    so the assignment-flow warning doesn't stall the UI when the printer is
    unreachable (offline, networked elsewhere, cold-rebooting, etc.).

    `is_active` is true only when PrusaLink reports a state in which a spool
    swap would physically disrupt the print. Finished/stopped/idle states do
    not trigger the warning.
    """
    creds = fetch_printer_credentials(filabridge_url, printer_name)
    if not creds or not creds.get("ip_address"):
        return None
    ip = creds["ip_address"]
    api_key = creds.get("api_key")
    headers = {"X-Api-Key": api_key} if api_key else {}

    # v1 status — returns {"printer": {"state": "PRINTING", ...}, ...}
    try:
        r = requests.get(f"http://{ip}/api/v1/status", headers=headers, timeout=2)
        if r.ok:
            body = r.json() or {}
            printer = body.get("printer") or {}
            state_str = str(printer.get("state", "")).upper()
            if state_str:
                return {"state": state_str, "is_active": state_str in {"PRINTING", "PAUSED", "BUSY"}}
    except Exception:
        pass

    # Legacy /api/printer — returns {"state": {"text": "Printing", "flags": {...}}, ...}
    try:
        r = requests.get(f"http://{ip}/api/printer", headers=headers, timeout=2)
        if r.ok:
            body = r.json() or {}
            flags = (body.get("state") or {}).get("flags") or {}
            state_text = str((body.get("state") or {}).get("text", "")).upper()
            is_active = bool(flags.get("printing") or flags.get("paused"))
            if state_text:
                return {"state": state_text, "is_active": is_active}
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

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

def download_gcode_and_parse_usage(ip_address: str, api_key: str, filename: str) -> Optional[Dict[int, float]]:
    """
    Downloads the gcode file from PrusaLink and parses the 'filament used [g]=' metadata.
    Returns a dictionary mapping toolhead index to grams used.
    """
    # Remove leading slash if present in filename, as PrusaLink expects it right after the host
    filename = filename.lstrip('/')
    url = f"http://{ip_address}/{filename}"
    headers = {}
    if api_key:
        headers['X-Api-Key'] = api_key

    try:
        # We use a stream request, because we only need to scan the metadata block
        # PrusaSlicer/SuperSlicer puts metadata at the end of .gcode, but .bgcode has a metadata block at the end too.
        # However, to be safe and simple, we'll download the whole file since .gcode or .bgcode sizes vary and we need the match.
        # A timeout of 60 seconds should be sufficient for a local network download.
        response = requests.get(url, headers=headers, timeout=60)
        
        if response.ok:
            content = response.text
            
            # Pattern handles:
            # - .bgcode format: "filament used [g]=1.23,4.56"
            # - .gcode format: "; filament used [g] = 1.23, 4.56"
            match = re.search(r';?\s*filament used \[g\]\s*=\s*([0-9.,\s]+)', content)
            
            if match:
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
            else:
                print(f"No filament usage metadata found in {filename}")
        else:
            print(f"Failed to download {filename} from PrusaLink. Status: {response.status_code}")
    except Exception as e:
        print(f"Error aggressively downloading/parsing gcode: {e}")
        traceback.print_exc()

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

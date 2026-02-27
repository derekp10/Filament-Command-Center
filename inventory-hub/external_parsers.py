import requests
import re
import json
import state
import config_loader

class BaseParser:
    """Abstract base class for all External Source Plugins."""
    @staticmethod
    def get_source_id():
        raise NotImplementedError()

    @staticmethod
    def search(query: str) -> list[dict]:
        """
        Given a query string, returns a list of dictionaries with standardized schema:
        {
            "id": str,
            "name": str,
            "material": str,
            "vendor": {"name": str},
            "weight": float,
            "spool_weight": float,
            "diameter": float,
            "density": float,
            "color_hex": str,
            "color_name": str,
            "external_link": str
        }
        """
        raise NotImplementedError()

class SpoolmanParser(BaseParser):
    @staticmethod
    def get_source_id():
        return "spoolman"

    @staticmethod
    def search(query: str) -> list[dict]:
        sm_url, _ = config_loader.get_api_urls()
        try:
            r = requests.get(f"{sm_url}/api/v1/external/filament", timeout=5)
            if not r.ok:
                state.logger.warning(f"Spoolman External Search Failed: {r.status_code}")
                return []
                
            results = r.json()
            if not query:
                return results
                
            terms = query.lower().split()
            filtered = []
            for f in results:
                brand = (f.get('manufacturer') or f.get('vendor', {}).get('name') or '').lower()
                mat = (f.get('material') or '').lower()
                color = (f.get('color_name') or f.get('name') or '').lower()
                combined = f"{brand} {mat} {color}"
                
                # In Spoolman's case, we return the raw native object as the frontend 
                # already knows how to handle it deeply, but we ensure basic fields.
                if all(term in combined for term in terms):
                    filtered.append(f)
            return filtered
            
        except Exception as e:
            state.logger.error(f"SpoolmanParser Error: {e}")
            return []

class PrusamentParser(BaseParser):
    @staticmethod
    def get_source_id():
        return "prusament"

    @staticmethod
    def search(query: str) -> list[dict]:
        """
        For Prusament, 'query' is expected to be the full URL (e.g. https://prusament.com/spool/...)
        If passed a standard keyword, it will likely return empty since Prusament doesn't have a public search API yet.
        """
        
        # Check if query is actually a Prusament URL
        if "prusament.com/spool/" not in query:
            return []
            
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            r = requests.get(query, headers=headers, timeout=5)
            if not r.ok:
                state.logger.warning(f"Prusament URL fetch failed: {r.status_code}")
                return []
                
            html = r.text
            match = re.search(r"var spoolData\s*=\s*'(.*?)';", html)
            if not match:
                state.logger.warning("Prusament JSON blob not found in HTML.")
                return []
                
            data = json.loads(match.group(1))
            fil = data.get("filament", {})
            
            # Extract attributes
            color_hex = fil.get("color_rgb", "#FFFFFF").replace("#", "")
            
            # Prusament spools list the 'weight' property as the net weight of the filament itself
            net_weight = data.get("weight", 1000)
            spool_g = data.get("spool_weight", 0)
            
            # Typical physical props (defaults if missing)
            diameter = 1.75
            density = 1.24 # Typical PLA placeholder, could map based on material type later
            if fil.get("material", "").upper() == "PETG": density = 1.27
            elif fil.get("material", "").upper() == "ABS": density = 1.04
            
            # Map into the expected generic schema
            standard_obj = {
                "id": str(data.get("ff_goods_id", "prusament")),
                "name": fil.get("name", "Prusament Filament"),
                "material": fil.get("material", "Unknown"),
                "vendor": {"name": "Prusament"},
                "weight": float(net_weight),
                "spool_weight": float(spool_g),
                "diameter": float(diameter),
                "density": float(density),
                "color_hex": color_hex,
                "color_name": fil.get("color_name", ""),
                "external_link": query,
                "settings_extruder_temp": fil.get("he_min") if fil.get("he_min") else None,
                "settings_bed_temp": fil.get("hb_min") if fil.get("hb_min") else None,
                "extra": {
                    "prusament_manufacturing_date": data.get("manufacture_date", ""),
                    "prusament_length_m": data.get("length", 0)
                }
            }
            return [standard_obj]
            
        except Exception as e:
            state.logger.error(f"PrusamentParser Error: {e}")
            return []

class OpenFilamentParser(BaseParser):
    @staticmethod
    def get_source_id():
        return "open_filament"

    @staticmethod
    def search(query: str) -> list[dict]:
        # Stub for future implementation
        return []

# Factory Router
PARSERS = {
    SpoolmanParser.get_source_id(): SpoolmanParser,
    PrusamentParser.get_source_id(): PrusamentParser,
    OpenFilamentParser.get_source_id(): OpenFilamentParser
}

def search_external(source: str, query: str) -> list[dict]:
    parser_class = PARSERS.get(source)
    if not parser_class:
        raise ValueError(f"Unknown external source: {source}")
    return parser_class.search(query)

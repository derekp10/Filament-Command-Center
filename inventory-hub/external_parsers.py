import requests
import re
import json
import state
import config_loader
import urllib.parse
import traceback
from typing import Dict, Type, Any, List

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
                    "prusament_length_m": data.get("length", 0),
                    **({"nozzle_temp_max": str(fil.get("he_max"))} if fil.get("he_max") else {}),
                    **({"bed_temp_max": str(fil.get("hb_max"))} if fil.get("hb_max") else {}),
                }
            }
            return [standard_obj]
            
        except Exception as e:
            state.logger.error(f"PrusamentParser Error: {e}")
            return []

class AmazonParser(BaseParser):
    @staticmethod
    def get_source_id():
        return "amazon"

    @staticmethod
    def search(query: str) -> list[dict]:
        """
        Accepts an Amazon URL (e.g. https://www.amazon.com/dp/B07DN3557G).
        Extracts the ASIN and scrapes the Amazon Search results using ScraperAPI to bypass strict AWS WAF limits.
        Attempts regex and NLP extraction of Brand, Material, Color, and Weight from the product title.
        """
        if "amazon.com" not in query and "/dp/" not in query:
            return []

        try:
            # Extract ASIN from the URL
            asin_match = re.search(r'(?:/dp/|/gp/product/)([A-Z0-9]{10})', query)
            if not asin_match:
                state.logger.error("Amazon URL does not contain a recognizable 10-character ASIN.")
                return []
            asin = asin_match.group(1)
            
            # WAF Bypass: Amazon heavily protects direct /dp/ routes.
            # However, their search endpoint (/s?k=ASIN) often has lower security thresholds.
            # We append '3D Printer Filament' to the search to prevent sponsored cross-category ads from hijacking the top result.
            search_url = f"https://www.amazon.com/s?k=3D+printer+filament+{asin}"

            cfg = config_loader.load_config()
            scraper_api_key = cfg.get("SCRAPER_API_KEY", "")
            if not scraper_api_key:
                import os
                scraper_api_key = os.environ.get("SCRAPER_API_KEY", "")
                
            if not scraper_api_key:
                state.logger.error("Amazon Parser requires a ScraperAPI key in config.json or ENV to bypass WAF.")
                return []
                
            payload = {
                'api_key': scraper_api_key,
                'url': search_url,
                'render': 'false', 
                'country_code': 'us'
            }
            
            r = requests.get('https://api.scraperapi.com/', params=payload, timeout=30)
            
            if not r.ok:
                state.logger.warning(f"Amazon ScraperAPI fetch failed: {r.status_code}")
                return []
                
            html = r.text
            
            if "To discuss automated access to Amazon data please contact" in html or "api-services-support@amazon.com" in html or "challenge-container" in html:
                state.logger.error("Amazon Scraping Blocked: Bot detection CAPTCHA served despite ScraperAPI.")
                return []
                
            try:
                from bs4 import BeautifulSoup
            except ImportError:
                state.logger.error("BeautifulSoup4 is required for Amazon parsing. Please install with: pip install beautifulsoup4")
                return []

            soup = BeautifulSoup(html, 'html.parser')
            
            title = ""
            # Strict ASIN match in the search DOM
            asin_div = soup.find('div', {'data-asin': asin})
            if asin_div:
                title_el = asin_div.find('h2')
                if title_el:
                    title = title_el.get_text(strip=True)
            
            # Fallback 1: Try finding the first long H2 tag (most likely the single product result)
            if not title:
                headers = soup.find_all('h2')
                for h in headers:
                    text = h.get_text(strip=True)
                    if len(text) > 40: # Amazon titles are typically long
                        title = text
                        break

            # Fallback 2: Regex extraction for <span a-text-normal> (used in some mobile layouts)
            if not title:
                title_match = re.search(r'<span class="a-size-medium a-color-base a-text-normal"[^>]*>(.*?)</span>', html, re.IGNORECASE)
                if title_match:
                    title = re.sub(r'<[^>]*>', '', title_match.group(1)).strip()

            if not title:
                state.logger.warning("Amazon title could not be extracted from the DOM structure.")
                return []
                
            title_upper = title.upper()
            
            # --- NLP Extraction Logic ---
            # 1. Material
            material = "Unknown"
            if "PLA+" in title_upper or "PLA PLUS" in title_upper: material = "PLA+"
            elif "PLA" in title_upper: material = "PLA"
            elif "PETG" in title_upper: material = "PETG"
            elif "ABS" in title_upper: material = "ABS"
            elif "TPU" in title_upper: material = "TPU"
            elif "ASA" in title_upper: material = "ASA"

            # 2. Brand (Usually the first word in the title)
            brand = "Generic"
            words = title.split()
            if words:
                brand = words[0]
                
            # Known Brand Corrections
            if "HATCHBOX" in title_upper: brand = "HATCHBOX"
            elif "OVERTURE" in title_upper: brand = "OVERTURE"
            elif "SUNLU" in title_upper: brand = "SUNLU"
            elif "ESUN" in title_upper: brand = "eSUN"
            elif "ELEGOO" in title_upper: brand = "ELEGOO"
            
            # 3. Weight Regex Parsing
            weight = 1000.0 # Default fallback
            
            # Try to look for total weight first e.g. "4KG" or "1.5 KG"
            total_match = re.search(r'(\d+(?:\.\d+)?)\s*KG', title_upper)
            if total_match:
                try:
                    val = float(total_match.group(1))
                    if 0.1 <= val <= 20.0: # Sanity check
                        weight = val * 1000.0
                except ValueError:
                    pass

            # If we still think it's 1000g, check if we found multipack keywords
            if weight == 1000.0:
                multipack = 1
                mp_match = re.search(r'(\d+)\s*(?:pk|pack|rolls|spools|kg/roll)', title_upper)
                if mp_match:
                    try: 
                        multipack = int(mp_match.group(1))
                        weight = 1000.0 * multipack
                    except ValueError: 
                        pass
            
            # 4. Color Names (Fuzzy Matching on common vocabulary)
            color_name = "Unknown Color"
            colors = ["Black", "White", "Red", "Blue", "Green", "Yellow", "Orange", "Purple", "Pink", "Silver", "Gold", "Grey", "Gray", "Clear", "Transparent", "Brown", "Cyan", "Magenta"]
            for c in colors:
                if c.upper() in title_upper:
                    color_name = c
                    break

            # 5. Fallback Density (Amazon rarely lists this natively in the title)
            density = 1.24
            if material == "PETG": density = 1.27
            elif material == "ABS": density = 1.04

            # Generate Standard Spoolman payload
            standard_obj = {
                "id": f"amazon_{brand.lower()}_{material.lower()}",
                "name": title[:60] + "...", # Spoolman names shouldn't be too long
                "material": material,
                "vendor": {"name": brand},
                "weight": float(weight),
                "spool_weight": 200.0, # Guess standard spool weight
                "diameter": 1.75,
                "density": float(density),
                "color_hex": "", # Leave blank so user picks it
                "color_name": color_name,
                "external_link": query,
                "extra": {
                    "amazon_title": title
                }
            }
            return [standard_obj]
            
        except Exception as e:
            state.logger.error(f"AmazonParser Error: {e}")
            return []

class ThreeDFPParser(BaseParser):
    @staticmethod
    def get_source_id():
        return "3dfp"

    @staticmethod
    def search(query: str) -> list[dict]:
        """
        Accepts a 3DFilamentProfiles URL (e.g. https://3dfilamentprofiles.com/brand/xyz).
        Scrapes their standard tabular display logic.
        """
        if "3dfilamentprofiles.com" not in query:
            return []

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml,application/xml"
        }
        
        try:
            r = requests.get(query, headers=headers, timeout=5)
            if not r.ok:
                state.logger.warning(f"3DFP URL fetch failed: {r.status_code}")
                return []
                
            html = r.text
            
            # Usually 3DFP puts the product name right in the main H1 or title
            title_match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.IGNORECASE)
            name = title_match.group(1).strip() if title_match else "Unknown Filament"
            
            # Basic fallback NLP (similar to Amazon) if their DOM structure changes
            name_upper = name.upper()
            
            material = "Unknown"
            if "PLA+" in name_upper or "PLA PLUS" in name_upper: material = "PLA+"
            elif "PLA" in name_upper: material = "PLA"
            elif "PETG" in name_upper: material = "PETG"
            elif "ABS" in name_upper: material = "ABS"
            elif "TPU" in name_upper: material = "TPU"
            
            # Let's see if we can find hex code embedded (they often use style="background-color: #...")
            hex_match = re.search(r"background-color:\s*#([0-9a-fA-F]{6})", html)
            color_hex = hex_match.group(1) if hex_match else ""
            
            # Let's extract Density if listed "Density: 1.24 g/cm3"
            density_match = re.search(r"Density[\s\S]*?(\d+\.\d+)", html, re.IGNORECASE)
            density = float(density_match.group(1)) if density_match else 1.24
            
            # Spool Weight is often explicitly listed
            spool_wt_match = re.search(r"Spool Weight[\s\S]*?(\d+)\s*g", html, re.IGNORECASE)
            spool_weight = float(spool_wt_match.group(1)) if spool_wt_match else 200.0

            standard_obj = {
                "id": f"3dfp_{name.replace(' ', '_').lower()}",
                "name": name[:60],
                "material": material,
                "vendor": {"name": name.split()[0] if name else "Generic"},
                "weight": 1000.0, # Defaulting, can be refined
                "spool_weight": spool_weight,
                "diameter": 1.75,
                "density": density,
                "color_hex": color_hex,
                "color_name": "Unknown",
                "external_link": query
            }
            return [standard_obj]
            
        except Exception as e:
            state.logger.error(f"3DFPParser Error: {e}")
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
    AmazonParser.get_source_id(): AmazonParser,
    ThreeDFPParser.get_source_id(): ThreeDFPParser,
    OpenFilamentParser.get_source_id(): OpenFilamentParser
}

def search_external(source: str, query: str) -> list[dict]:
    parser_class = PARSERS.get(source)
    if not parser_class:
        raise ValueError(f"Unknown external source: {source}")
    return parser_class.search(query)

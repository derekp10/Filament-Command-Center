import requests
import json
import config_loader

cfg = config_loader.load_config()
scraper_api_key = cfg.get("SCRAPER_API_KEY", "")

# Using a generic popular ASIN (Overture PLA Black)
url = "https://www.amazon.com/dp/B07PGY2HXS/"

payload = {
    'api_key': scraper_api_key,
    'url': url,
    'render': 'false', 
    'country_code': 'us'
}

r = requests.get('https://api.scraperapi.com/', params=payload, timeout=20)
print(f"Status: {r.status_code}")
print(f"Headers: {r.headers}")
print(f"Body: {r.text[:500]}")

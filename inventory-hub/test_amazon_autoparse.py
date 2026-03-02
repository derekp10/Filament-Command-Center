import requests
import json
import config_loader

cfg = config_loader.load_config()
scraper_api_key = cfg.get("SCRAPER_API_KEY", "")

url = "https://www.amazon.com/dp/B07DN3557G"
payload = {
    'api_key': scraper_api_key,
    'url': url,
    'autoparse': 'true', 
    'country_code': 'us'
}

r = requests.get('https://api.scraperapi.com/', params=payload, timeout=30)
print(f"Status: {r.status_code}")
try:
    print(f"Body: {json.dumps(r.json(), indent=2)}")
except json.JSONDecodeError:
    print(f"Body: {r.text[:500]}")

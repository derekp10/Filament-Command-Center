import requests
import json
import config_loader

cfg = config_loader.load_config()
scraper_api_key = cfg.get("SCRAPER_API_KEY", "")

url = "https://httpbin.org/headers"
payload = {
    'api_key': scraper_api_key,
    'url': url,
    'render': 'false', 
    'premium': 'true', 
    'country_code': 'us'
}

r = requests.get('https://api.scraperapi.com/', params=payload, timeout=30)
print(f"Status: {r.status_code}")
print(f"Body: {r.text}")

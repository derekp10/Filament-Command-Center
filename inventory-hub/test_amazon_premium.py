import requests
import json
import config_loader

cfg = config_loader.load_config()
scraper_api_key = cfg.get("SCRAPER_API_KEY", "")

# Hatchbox PLA Black (Extremely stable decade-old ASIN)
url = "https://www.amazon.com/dp/B07DN3557G/"
print(f"Testing URL: {url}")

payload = {
    'api_key': scraper_api_key,
    'url': url,
    'render': 'false', 
    'premium': 'true', 
    'device_type': 'desktop',
    'country_code': 'us'
}

r = requests.get('https://api.scraperapi.com/', params=payload, timeout=30)
print(f"Status: {r.status_code}")
if r.ok:
    import re
    title_match = re.search(r"<title>(.*?)</title>", r.text, re.IGNORECASE)
    if title_match:
         print(f"Title: {title_match.group(1)}")
    else:
         print("No title found.")
else:
    print(r.text[:500])

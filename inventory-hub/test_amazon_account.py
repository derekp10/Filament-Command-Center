import requests
import json
import config_loader

cfg = config_loader.load_config()
scraper_api_key = cfg.get("SCRAPER_API_KEY", "")

url = f"https://api.scraperapi.com/account?api_key={scraper_api_key}"
r = requests.get(url)
print(f"Status: {r.status_code}")
print(f"Account JSON: {r.text}")

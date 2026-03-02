import requests
import re

url = "https://www.amazon.com/dp/B07DN3557G"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1"
}

r = requests.get(url, headers=headers, timeout=10)
print(f"Status: {r.status_code}")
if r.ok:
    title_match = re.search(r"<title>(.*?)</title>", r.text, re.IGNORECASE)
    if title_match:
         print(f"Title: {title_match.group(1)}")
    else:
         print("No title found.")
else:
    print("Failed to fetch.")

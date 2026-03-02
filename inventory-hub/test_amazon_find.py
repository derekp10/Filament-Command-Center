import urllib.request
import re

search_url = "https://html.duckduckgo.com/html/?q=site:amazon.com+Hatchbox+PLA+Black"
req = urllib.request.Request(search_url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    html = urllib.request.urlopen(req).read().decode('utf-8')
    asins = re.findall(r'/dp/([A-Z0-9]{10})', html)
    print("Found ASINs:", list(set(asins)))
except Exception as e:
    print(f"Failed: {e}")

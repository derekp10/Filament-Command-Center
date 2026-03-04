import sys
sys.path.append('inventory-hub')
import json
from external_parsers import AmazonParser

# Hatchbox PLA Black (Extremely stable decade-old ASIN)
url = "https://www.amazon.com/dp/B07DN3557G/"
print(f"Testing URL: {url}")

results = AmazonParser.search(url)
print(json.dumps(results, indent=2))

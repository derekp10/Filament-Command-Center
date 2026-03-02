import json
from external_parsers import AmazonParser

# A known active ASIN for OVERTURE Matte PLA Black
url = "https://www.amazon.com/dp/B07Z4JCR54/"
print(f"Testing URL: {url}")

results = AmazonParser.search(url)
print(json.dumps(results, indent=2))

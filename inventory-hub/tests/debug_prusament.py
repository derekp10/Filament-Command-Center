import requests
import re

def run():
    url = "https://prusament.com/spool/17705/5b1a183b26/"
    print(f"Fetching {url}")
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            html = r.text
            
            # Extract var spoolData = '{...}';
            match = re.search(r"var spoolData\s*=\s*'(.*?)';", html)
            if match:
                import json
                data = json.loads(match.group(1))
                print(json.dumps(data, indent=2))
            else:
                print("Could not find spoolData.")
                    
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run()

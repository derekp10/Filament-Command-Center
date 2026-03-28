import requests

url = 'http://192.168.1.29:7913'
print('Fetching Spool fields...')
r = requests.get(f'{url}/api/v1/field/spool')
print("STATUS:", r.status_code)
if r.status_code == 200:
    import json
    print(json.dumps(r.json(), indent=2))
else:
    print(r.text)


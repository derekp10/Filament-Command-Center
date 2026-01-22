import requests

SPOOLMAN_IP = "http://192.168.1.29:7912"

def test_create_field():
    url = f"{SPOOLMAN_IP}/api/v1/field/filament/debug_test_field"
    
    # WE ARE SENDING A RAW PYTHON LIST HERE. 
    # NO json.dumps()
    choices_list = ["Option A", "Option B", "Option C"]
    
    payload = {
        "name": "Debug Test Field",
        "field_type": "choice",
        "multi_choice": True,
        "choices": choices_list 
    }
    
    print(f"Sending payload to {url}...")
    try:
        # requests.post(json=...) automatically formats it as JSON.
        resp = requests.post(url, json=payload)
        
        if resp.status_code in [200, 201]:
            print("\n✅ SUCCESS! Spoolman accepted the Raw List.")
            print("We have proven that json.dumps() IS NOT NEEDED.")
        else:
            print(f"\n❌ FAILED with code {resp.status_code}")
            print(f"Response: {resp.text}")
            
    except Exception as e:
        print(f"Connection error: {e}")

if __name__ == "__main__":
    test_create_field()
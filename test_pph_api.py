import requests
import json
import sys

"""
Simple diagnostic script for PeoplePerHour proxy API
----------------------------------------------------
Usage:
    python test_pph_api.py [keyword]

If no keyword is given, defaults to "logo".
"""

# Base URL of your proxy service
BASE_URL = "https://pph-proxy-service.onrender.com/api/pph"
API_KEY = "1211"  # update if needed

# Read keyword from command-line argument
keyword = sys.argv[1] if len(sys.argv) > 1 else "logo"

url = f"{BASE_URL}?key={API_KEY}&q={keyword}"

print("=" * 80)
print(f"🔍 Testing PPH proxy API with keyword: '{keyword}'")
print(f"Full request URL: {url}")
print("=" * 80)

try:
    response = requests.get(url, timeout=25)
    print(f"✅ Status code: {response.status_code}")
    print("-" * 80)
    print("Response headers:")
    for k, v in response.headers.items():
        print(f"{k}: {v}")
    print("-" * 80)

    # Try to parse JSON
    try:
        data = response.json()
        print(f"JSON type: {type(data).__name__}")
        if isinstance(data, (list, dict)):
            print(f"JSON keys (if dict) or length (if list): {len(data) if isinstance(data, list) else list(data.keys())}")
        print("-" * 80)
        print("Sample JSON preview:")
        print(json.dumps(data, indent=2)[:1000])
    except json.JSONDecodeError:
        print("❌ Response is not valid JSON. Raw content:")
        print(response.text[:1000])

except Exception as e:
    print("❌ Error during request:", e)

print("=" * 80)
print("Done.")

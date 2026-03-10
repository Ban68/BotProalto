import os
import requests
from dotenv import load_dotenv
import json

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
PHONE_ID = os.getenv("BUSINESS_PHONE")
API_VERSION = os.getenv("API_VERSION", "v21.0")

if not API_TOKEN or not PHONE_ID:
    print("Error: API_TOKEN or BUSINESS_PHONE not found in .env")
    exit(1)

print(f"Checking status for Phone ID: {PHONE_ID}")

url = f"https://graph.facebook.com/{API_VERSION}/{PHONE_ID}"
headers = {
    "Authorization": f"Bearer {API_TOKEN}"
}
# Requesting key status fields
params = {
    "fields": "verified_name,code_verification_status,display_phone_number,quality_rating,platform_type,status,name_status"
}

try:
    response = requests.get(url, headers=headers, params=params)
    print(f"Status Code: {response.status_code}")
    print("Response JSON:")
    print(json.dumps(response.json(), indent=2))
except Exception as e:
    print(f"Request failed: {e}")

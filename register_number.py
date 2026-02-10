import os
import requests
from dotenv import load_dotenv
import json

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
PHONE_ID = os.getenv("BUSINESS_PHONE")
API_VERSION = os.getenv("API_VERSION", "v21.0")
# Using a simple default PIN for registration. 
# If a PIN was already set, this will fail. 
# If not, this will SET the PIN to 123456.
PIN = "123456" 

if not API_TOKEN or not PHONE_ID:
    print("Error: API_TOKEN or BUSINESS_PHONE not found in .env")
    exit(1)

print(f"Attempting to REGISTER Phone ID: {PHONE_ID}")
print(f"Using PIN: {PIN}")

url = f"https://graph.facebook.com/{API_VERSION}/{PHONE_ID}/register"
headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json"
}

payload = {
    "messaging_product": "whatsapp",
    "pin": PIN
}

try:
    response = requests.post(url, headers=headers, json=payload)
    print(f"Status Code: {response.status_code}")
    print("Response JSON:")
    print(json.dumps(response.json(), indent=2))
except Exception as e:
    print(f"Request failed: {e}")

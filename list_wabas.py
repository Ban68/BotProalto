import os
import requests
from dotenv import load_dotenv
import json

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
API_VERSION = os.getenv("API_VERSION", "v21.0")

if not API_TOKEN:
    print("Error: API_TOKEN not found in .env")
    exit(1)

# Get the User ID from debug_token first (or hardcode if we knew it, but better dynamic)
# Actually, we can just query me/accounts or similar? 
# For System User, we can query "me/assigned_business_assets" or similar?
# Or just "me/whatsapp_business_accounts" - usually works for System Users if granular scope is there.

print(f"Listing WABAs...")

url = f"https://graph.facebook.com/{API_VERSION}/me/whatsapp_business_accounts"
headers = {
    "Authorization": f"Bearer {API_TOKEN}"
}

try:
    response = requests.get(url, headers=headers)
    print(f"Status Code: {response.status_code}")
    print("Response JSON:")
    print(json.dumps(response.json(), indent=2))
except Exception as e:
    print(f"Request failed: {e}")

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

print(f"Debugging Token...")

url = f"https://graph.facebook.com/debug_token"
params = {
    "input_token": API_TOKEN,
    "access_token": API_TOKEN # You can inspect a token using itself if it has sufficient perms, or use an App Token. Let's try self.
}

try:
    response = requests.get(url, params=params)
    print(f"Status Code: {response.status_code}")
    print("Response JSON:")
    print(json.dumps(response.json(), indent=2))
except Exception as e:
    print(f"Request failed: {e}")

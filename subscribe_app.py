import requests
import os
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = os.getenv('API_TOKEN')
# The WABA ID identified by the user
WABA_ID = "1196765072669065" 
API_VERSION = os.getenv('API_VERSION', 'v21.0')

def subscribe_app_to_waba():
    print(f"Attempting to subscribe App to WABA ID: {WABA_ID}...")
    
    url = f"https://graph.facebook.com/{API_VERSION}/{WABA_ID}/subscribed_apps"
    
    headers = {
        'Authorization': f'Bearer {ACCESS_TOKEN}',
        'Content-Type': 'application/json'
    }
    
    # We don't need to send the callback_url here if it's already set in the App Dashboard.
    # This call essentially says "Enable webhooks for THIS WABA pointing to THIS App".
    response = requests.post(url, headers=headers)
    
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
    
    if response.status_code == 200 and '"success":true' in response.text:
        print("\n✅ SUCCESS! The App is now explicitly subscribed to the Proalto WABA.")
        print("Incoming messages should now start arriving.")
    else:
        print("\n❌ Failed to subscribe. Check permissions or IDs.")

def check_subscriptions():
    print(f"\nChecking current subscriptions for WABA {WABA_ID}...")
    url = f"https://graph.facebook.com/{API_VERSION}/{WABA_ID}/subscribed_apps"
    response = requests.get(url, params={'access_token': ACCESS_TOKEN})
    print(f"Current Subscriptions: {response.text}")

if __name__ == "__main__":
    subscribe_app_to_waba()
    check_subscriptions()

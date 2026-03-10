import requests
import os
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = os.getenv('API_TOKEN')
TARGET_PHONE_ID = os.getenv('BUSINESS_PHONE')
API_VERSION = os.getenv('API_VERSION', 'v21.0')

def find_waba():
    print(f"Searching for WABA owning Phone ID: {TARGET_PHONE_ID}...")
    
    # 1. Get the user's businesses
    url = f"https://graph.facebook.com/{API_VERSION}/me/businesses"
    response = requests.get(url, params={'access_token': ACCESS_TOKEN})
    
    if response.status_code != 200:
        print(f"Error fetching businesses: {response.text}")
        return

    businesses = response.json().get('data', [])
    print(f"Found {len(businesses)} businesses linked to this token.")

    for biz in businesses:
        biz_id = biz['id']
        biz_name = biz['name']
        print(f"\nChecking Business: {biz_name} ({biz_id})")
        
        # 2. Get WABAs for this business
        waba_url = f"https://graph.facebook.com/{API_VERSION}/{biz_id}/owned_whatsapp_business_accounts"
        waba_res = requests.get(waba_url, params={'access_token': ACCESS_TOKEN})
        
        if waba_res.status_code != 200:
            # Try 'client_whatsapp_business_accounts' if owned fails (for partners)
            waba_url = f"https://graph.facebook.com/{API_VERSION}/{biz_id}/client_whatsapp_business_accounts"
            waba_res = requests.get(waba_url, params={'access_token': ACCESS_TOKEN})

        if waba_res.status_code != 200:
            print(f"  Could not list WABAs for this business.")
            continue

        wabas = waba_res.json().get('data', [])
        print(f"  Found {len(wabas)} WABAs.")

        for waba in wabas:
            waba_id = waba['id']
            waba_name = waba.get('name', 'Unknown')
            # 3. Check phone numbers in this WABA
            phone_url = f"https://graph.facebook.com/{API_VERSION}/{waba_id}/phone_numbers"
            phone_res = requests.get(phone_url, params={'access_token': ACCESS_TOKEN})
            
            if phone_res.status_code == 200:
                phones = phone_res.json().get('data', [])
                for phone in phones:
                    pid = phone['id']
                    pnum = phone.get('display_phone_number', 'Unknown')
                    print(f"    -> WABA {waba_name} ({waba_id}) has phone: {pnum} (ID: {pid})")
                    
                    if pid == TARGET_PHONE_ID:
                        print(f"\n✅ MATCH FOUND! The correct WABA is:")
                        print(f"Name: {waba_name}")
                        print(f"ID: {waba_id}")
                        print(f"Business: {biz_name}")
                        print("\n--> Please ensure you select THIS account in the Webhook Dropdown.")
                        return

    print("\n❌ Search complete. Phone number ID not found in any accessible WABA.")

if __name__ == "__main__":
    find_waba()

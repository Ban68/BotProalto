import requests
import json
from config import Config

def send_test_template(to_number):
    url = f"https://graph.facebook.com/{Config.API_VERSION}/{Config.BUSINESS_PHONE}/messages"
    headers = {
        "Authorization": f"Bearer {Config.API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    data = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "template",
        "template": {
            "name": "hello_world",
            "language": {
                "code": "en_US"
            }
        }
    }
    
    print(f"Sending to {to_number} using Token starting with {Config.API_TOKEN[:10]}... and ID {Config.BUSINESS_PHONE}")
    
    try:
        response = requests.post(url, headers=headers, json=data)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # User's number from screenshot: +33 7 82 28 93 84 -> 33782289384
    send_test_template("33782289384")
